import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from auditor.config import PROJECT_ROOT, Settings
from auditor.history import HistoryFull, HistoryStore, HistoryUnavailable, InvalidCursor, RunNotFound, encode_result
from auditor.history_schema import metadata, runs
from auditor.history_setup import initialize_history, migration_config
from auditor.spec_worker import analyze_pair

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def original_result():
    return analyze_pair({side: (ROOT / "examples" / filename).read_text(encoding="utf-8") for side, filename in (("old", "orders-v1.json"), ("new", "orders-v2-breaking.json"))}, compare=True)


@pytest.fixture
def store(tmp_path):
    settings = Settings(_env_file=None, runtime_root=tmp_path / "history")
    initialize_history(settings)
    result = HistoryStore(settings)
    yield result
    result.close()


def distinct(original, version):
    result = copy.deepcopy(original)
    # A changed version is metadata within the snapshot; the comparison result
    # stays internally consistent, and the canonical snapshot fingerprint differs.
    result["new"]["api_version"] = version
    return result


def test_no_import_or_store_constructor_creates_runtime(tmp_path):
    settings = Settings(_env_file=None, runtime_root=tmp_path / "not-created")
    store = HistoryStore(settings)
    try:
        assert not settings.runtime_root.exists()
        with pytest.raises(HistoryUnavailable):
            store.readiness()
        assert not settings.runtime_root.exists()
    finally:
        store.close()


def test_save_duplicate_and_reopen_after_restart(store, original_result):
    record, created = store.save(original_result)
    assert created
    again, created = store.save(copy.deepcopy(original_result))
    assert not created and again["id"] == record["id"]
    assert store.readiness()["saved_comparisons"] == 1
    settings = store.settings
    store.close()
    reopened = HistoryStore(settings)
    try:
        assert reopened.get(record["id"])["result"] == original_result
        assert reopened.list()["items"][0]["summary"] == original_result["comparison"]["summary"]
    finally:
        reopened.close()


def test_delete_removes_metadata_payload_and_releases_capacity(store, original_result):
    record, _ = store.save(original_result)
    store.delete(record["id"])
    assert store.readiness()["saved_comparisons"] == 0
    assert store.readiness()["stored_result_bytes"] == 0
    assert store.list()["items"] == []
    with pytest.raises(RunNotFound):
        store.get(record["id"])
    with pytest.raises(RunNotFound):
        store.delete(record["id"])
    replacement, _ = store.save(original_result)
    assert replacement["id"] != record["id"]


def test_cursor_pagination_has_no_duplicate_or_skipped_rows(store, original_result):
    for i in range(5):
        store.save(distinct(original_result, str(i)))
    ids, cursor = [], None
    while True:
        page = store.list(2, cursor)
        assert all("result" not in item and "result_json" not in item for item in page["items"])
        ids.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(ids) == len(set(ids)) == 5
    store.delete(ids[1])
    with pytest.raises(InvalidCursor):
        store.list(2, ids[1])


def test_count_and_byte_quota_are_atomic_and_duplicates_work_at_limit(store, original_result):
    store.settings.history_max_records = 1
    record, _ = store.save(original_result)
    assert store.save(original_result)[1] is False
    with pytest.raises(HistoryFull):
        store.save(distinct(original_result, "another"))
    store.delete(record["id"])
    store.settings.history_max_bytes = 1
    with pytest.raises(HistoryFull):
        store.save(original_result)
    assert store.readiness()["saved_comparisons"] == 0


def test_concurrent_duplicates_have_one_row(store, original_result):
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: store.save(original_result), range(2)))
    assert len({record["id"] for record, _ in outcomes}) == 1
    assert sum(created for _, created in outcomes) == 1
    assert store.readiness()["saved_comparisons"] == 1


def test_concurrent_distinct_saves_cannot_exceed_quota(store, original_result):
    store.settings.history_max_records = 1
    def save(i):
        try:
            store.save(distinct(original_result, str(i)))
            return "saved"
        except HistoryFull:
            return "full"
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(save, range(2))) == ["full", "saved"]
    assert store.readiness()["saved_comparisons"] == 1


def test_corrupt_payload_and_wrong_revision_fail_closed(store, original_result):
    record, _ = store.save(original_result)
    with store.connection(write=True) as connection:
        changed = " " + encode_result(original_result)[0][1:]
        connection.execute(runs.update().where(runs.c.id == record["id"]).values(result_json=changed))
    with pytest.raises(HistoryUnavailable):
        store.get(record["id"])
    with store.connection(write=True) as connection:
        connection.exec_driver_sql("UPDATE alembic_version SET version_num='unknown_revision'")
    with pytest.raises(HistoryUnavailable):
        store.readiness()


def test_migration_idempotence_metadata_and_roundtrip_on_scratch_only(store):
    assert initialize_history(store.settings)["schema_revision"] == "0001_history"
    with store.engine.begin() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, metadata) == []
    with store.engine.begin() as connection:
        config = migration_config()
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
        assert "comparison_runs" not in sa.inspect(connection).get_table_names()
        command.upgrade(config, "head")
    assert store.readiness()["saved_comparisons"] == 0


def test_failed_commit_rolls_back_without_a_successful_record(store, original_result, monkeypatch):
    original = store.engine.dialect.do_commit
    def fail(connection):
        raise sa.exc.OperationalError("COMMIT", {}, RuntimeError("private diagnostic"))
    monkeypatch.setattr(store.engine.dialect, "do_commit", fail)
    with pytest.raises(HistoryUnavailable) as captured:
        store.save(original_result)
    assert "private diagnostic" not in str(captured.value)
    monkeypatch.setattr(store.engine.dialect, "do_commit", original)
    assert store.readiness()["saved_comparisons"] == 0


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(status="failed"),
    lambda r: r["comparison"]["summary"].update(breaking=999),
    lambda r: r["old"].update(input_sha256="not-a-hash"),
])
def test_incomplete_or_inconsistent_results_never_persist(store, original_result, mutate):
    result = copy.deepcopy(original_result)
    mutate(result)
    with pytest.raises(HistoryUnavailable):
        store.save(result)
    assert store.readiness()["saved_comparisons"] == 0


def test_history_setup_refuses_unrelated_nonempty_directory(tmp_path):
    (tmp_path / "important.txt").write_text("retain", encoding="utf-8")
    with pytest.raises(RuntimeError, match="does not belong"):
        initialize_history(Settings(_env_file=None, runtime_root=tmp_path))
    assert (tmp_path / "important.txt").read_text() == "retain"
    assert not (tmp_path / "history.sqlite3").exists()


def test_runtime_cannot_be_in_checkout_or_cedar():
    for path in (PROJECT_ROOT / "runtime", Path("relative/runtime")):
        with pytest.raises(ValueError):
            Settings(_env_file=None, runtime_root=path)


def test_deleted_payload_is_overwritten_in_active_database_file(store, original_result):
    value = copy.deepcopy(original_result)
    canary = "synthetic-delete-canary-" + str(uuid4())
    value["old"]["title"] = canary
    record, _ = store.save(value)
    assert canary.encode() in store.path.read_bytes()
    store.delete(record["id"])
    assert canary.encode() not in store.path.read_bytes()


def test_timestamp_ties_have_stable_uuid_cursor_order(store, original_result):
    for i in range(4):
        store.save(distinct(original_result, str(i)))
    with store.connection(write=True) as connection:
        connection.execute(runs.update().values(created_at="2026-11-08T00:00:00.000000Z"))
    first = store.list(2)
    second = store.list(2, first["next_cursor"])
    ids = [item["id"] for item in [*first["items"], *second["items"]]]
    assert len(set(ids)) == 4 and ids == sorted(ids, reverse=True)
