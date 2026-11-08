import asyncio
import copy
import json
import re
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from auditor import exports, uploads
from auditor.config import Settings
from auditor.exports import ExportTooLarge, json_export, markdown_export
from auditor.history import HistoryStore
from auditor.history_setup import initialize_history
from auditor.main import create_app
from auditor.spec_worker import analyze_pair

ROOT = Path(__file__).resolve().parents[2]
OLD = (ROOT / "examples/orders-v1.json").read_bytes()
NEW = (ROOT / "examples/orders-v2-breaking.json").read_bytes()


@pytest.fixture(scope="module")
def result():
    return analyze_pair({"old": OLD.decode(), "new": NEW.decode()}, compare=True)


@pytest.fixture
def app(tmp_path):
    settings = Settings(_env_file=None, runtime_root=tmp_path / "history")
    initialize_history(settings)
    app = create_app(settings)
    yield app
    app.state.history.close()


def request(app, method, path, **kwargs):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8010") as client:
            return await client.request(method, path, **kwargs)
    return asyncio.run(run())


def files(old=OLD, new=NEW):
    return {"old": ("old.json", old, "application/json"), "new": ("new.json", new, "application/json")}


def test_real_save_detail_duplicate_and_delete(app):
    response = request(app, "POST", "/api/comparisons", files=files())
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["status"] == "completed" and created["reused"] is False
    assert created["summary"]["breaking"] == 3
    run_id = created["id"]
    assert response.headers["location"] == "/api/comparisons/" + run_id
    detail = request(app, "GET", "/api/comparisons/" + run_id)
    assert detail.status_code == 200 and detail.json()["result"] == created["result"]
    response = request(app, "POST", "/api/comparisons", files=files())
    assert response.status_code == 200 and response.json()["reused"] is True
    assert response.json()["id"] == run_id
    page = request(app, "GET", "/api/comparisons").json()
    assert len(page["items"]) == 1 and "result" not in page["items"][0]
    response = request(app, "DELETE", "/api/comparisons/" + run_id)
    assert response.status_code == 204 and response.content == b""
    for suffix in ("", "/export?format=json", "/export?format=markdown"):
        assert request(app, "GET", "/api/comparisons/" + run_id + suffix).status_code == 404


def test_json_and_markdown_exports_match_saved_facts_and_coverage(app, result):
    record, _ = app.state.history.save(result)
    url = "/api/comparisons/" + record["id"]
    detail = request(app, "GET", url).json()
    response = request(app, "GET", url + "/export?format=json")
    assert response.status_code == 200
    exported = response.json()
    assert exported == {"export_schema_version": "1", **detail}
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["cache-control"] == "no-store"
    assert "attachment" in response.headers["content-disposition"]
    assert record["id"] in response.headers["content-disposition"]
    assert "sandbox" in response.headers["content-security-policy"]
    markdown = request(app, "GET", url + "/export?format=markdown")
    blocks = [json.loads(block) for block in re.findall(r"```json\n(.*?)\n```", markdown.text, flags=re.S)]
    assert blocks[0]["id"] == record["id"]
    assert blocks[1] == result["comparison"]["policy_assumptions"]
    assert blocks[2]["counts"] == result["comparison"]["summary"]
    assert blocks[3] == result["comparison"]["coverage"]
    assert blocks[4:] == result["comparison"]["findings"]
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert request(app, "GET", url + "/export?format=json").content == response.content


def test_markdown_escapes_html_links_and_code_fences_without_losing_data(app, result):
    malicious = copy.deepcopy(result)
    payload = '```\n<img src="https://untrusted.invalid/x" onerror="alert(1)"> [click](javascript:alert(1))'
    malicious["old"]["title"] = payload
    malicious["comparison"]["findings"][0]["title"] = payload
    record, _ = app.state.history.save(malicious)
    detail = app.state.history.get(record["id"])
    rendered = markdown_export(detail).decode()
    assert "<img" not in rendered and "onerror=\"alert(1)\"" not in rendered
    blocks = [json.loads(block) for block in re.findall(r"```json\n(.*?)\n```", rendered, flags=re.S)]
    assert blocks[4:][0]["title"] == payload
    assert json.loads(json_export(detail))["result"] == malicious


def test_invalid_new_file_does_not_save_any_record(app):
    response = request(app, "POST", "/api/comparisons", files=files(new=b"{"))
    assert response.status_code == 422
    assert app.state.history.readiness()["saved_comparisons"] == 0


def test_stateless_routes_do_not_create_history(app):
    response = request(app, "POST", "/api/specifications/compare", files=files())
    assert response.status_code == 200
    assert app.state.history.readiness()["saved_comparisons"] == 0


def test_export_limit_fails_without_deleting_or_modifying_record(app, result, monkeypatch):
    record, _ = app.state.history.save(result)
    monkeypatch.setattr(exports, "MAX_EXPORT_BYTES", 100)
    for format in ("json", "markdown"):
        response = request(app, "GET", "/api/comparisons/" + record["id"] + "/export?format=" + format)
        assert response.status_code == 413
    assert app.state.history.get(record["id"])["result"] == result


def test_history_limit_gives_conflict_and_no_partial_record(app, result):
    app.state.history.settings.history_max_records = 1
    app.state.history.save(result)
    value = json.loads(OLD)
    value["info"]["version"] = "another-synthetic-version"
    response = request(app, "POST", "/api/comparisons", files=files(old=json.dumps(value).encode()))
    assert response.status_code == 409 and response.json()["detail"]["code"] == "history_full"
    assert app.state.history.readiness()["saved_comparisons"] == 1


@pytest.mark.parametrize("method,suffix", [("GET", ""), ("POST", ""), ("GET", "/00000000-0000-0000-0000-000000000000"), ("DELETE", "/00000000-0000-0000-0000-000000000000"), ("GET", "/00000000-0000-0000-0000-000000000000/export")])
def test_cross_site_history_requests_are_rejected(app, method, suffix):
    response = request(app, method, "/api/comparisons" + suffix, headers={"Origin": "https://unrelated.example"})
    assert response.status_code == 403


def test_cross_site_without_origin_and_untrusted_host_rejected(app):
    assert request(app, "GET", "/api/comparisons", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert request(app, "GET", "/api/comparisons", headers={"Host": "unrelated.example"}).status_code == 400


@pytest.mark.parametrize("path", ["/api/comparisons?limit=0", "/api/comparisons?limit=51", "/api/comparisons?cursor=bad", "/api/comparisons/not-a-uuid", "/api/comparisons/00000000-0000-0000-0000-000000000000/export?format=html"])
def test_history_query_and_path_bounds(app, path):
    assert request(app, "GET", path).status_code == 422


def test_missing_or_stale_cursor_has_a_clear_error(app):
    response = request(app, "GET", "/api/comparisons?cursor=" + str(uuid4()))
    assert response.status_code == 400


def test_uninitialized_history_is_unavailable_without_creating_files(tmp_path):
    settings = Settings(_env_file=None, runtime_root=tmp_path / "not-created")
    app = create_app(settings)
    try:
        response = request(app, "GET", "/api/system/database")
        assert response.status_code == 503
        assert request(app, "POST", "/api/comparisons", files=files()).status_code == 503
        assert request(app, "GET", "/health").status_code == 200
        assert not settings.runtime_root.exists()
    finally:
        app.state.history.close()


def test_reopened_app_reads_saved_snapshot_after_disposal(app, result):
    record, _ = app.state.history.save(result)
    settings = app.state.history.settings
    app.state.history.close()
    restarted = create_app(settings)
    try:
        response = request(restarted, "GET", "/api/comparisons/" + record["id"])
        assert response.status_code == 200 and response.json()["result"] == result
    finally:
        restarted.state.history.close()


def test_saving_shares_admission_with_stateless_comparison(app, monkeypatch):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def fake(payload, compare=False):
            entered.set()
            await release.wait()
            raise RuntimeError("test-only stop before save")
        monkeypatch.setattr(uploads, "run_validation", fake)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8010") as client:
            first = asyncio.create_task(client.post("/api/comparisons", files=files()))
            await entered.wait()
            assert (await client.post(uploads.COMPARE_PATH, files=files())).status_code == 429
            assert (await client.get("/health")).status_code == 200
            release.set()
            with pytest.raises(RuntimeError):
                await first
        assert app.state.history.readiness()["saved_comparisons"] == 0
    asyncio.run(scenario())
