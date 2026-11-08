"""SQLite snapshots with serialized quota checks and all-or-nothing writes."""

import hashlib
import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from auditor.history_schema import runs
from auditor.spec_input import OUTPUT_LIMIT

SCHEMA_REVISION = "0001_history"
SUMMARY_KEYS = ("total_findings", "breaking", "potentially_breaking", "informational", "needs_review")
META_COLUMNS = [column for column in runs.c if column.name != "result_json"]


class HistoryUnavailable(Exception):
    pass


class HistoryFull(Exception):
    pass


class RunNotFound(Exception):
    pass


class InvalidCursor(Exception):
    pass


def make_engine(path):
    engine = sa.create_engine(
        sa.URL.create("sqlite", database=str(path)), poolclass=NullPool,
        connect_args={"check_same_thread": False, "timeout": 5},
        hide_parameters=True,
    )

    @event.listens_for(engine, "connect")
    def configure(connection, _):
        # Explicit BEGIN events avoid sqlite3's legacy DDL/SELECT autocommit quirks.
        connection.isolation_level = None
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA secure_delete=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    @event.listens_for(engine, "begin")
    def begin(connection):
        mode = connection.get_execution_options().get("sqlite_begin_mode", "DEFERRED")
        if mode not in {"DEFERRED", "IMMEDIATE"}:
            raise ValueError("Unsupported internal transaction mode")
        connection.exec_driver_sql("BEGIN " + mode)

    return engine


def encode_result(result):
    try:
        if result["status"] != "compared" or result["comparison_performed"] is not True:
            raise ValueError("Expected completed comparison")
        report = result["comparison"]
        summary = report["summary"]
        if set(summary) != set(SUMMARY_KEYS) or not all(type(summary[k]) is int and summary[k] >= 0 for k in SUMMARY_KEYS):
            raise ValueError("Invalid summary")
        if summary["total_findings"] != sum(summary[k] for k in SUMMARY_KEYS[1:]) or summary["total_findings"] != len(report["findings"]):
            raise ValueError("Inconsistent summary")
        if report["coverage"]["status"] not in {"supported_subset", "partial"} or report["verdict"] not in {"breaking_changes_detected", "review_required", "no_breaking_changes_detected_in_supported_subset"}:
            raise ValueError("Invalid report metadata")
        for key in ("engine_version", "policy_version"):
            if not isinstance(report[key], str) or not 0 < len(report[key]) <= 80:
                raise ValueError("Invalid version metadata")
        for side in ("old", "new"):
            if not isinstance(result[side]["input_sha256"], str) or not re.fullmatch("[a-f0-9]{64}", result[side]["input_sha256"]):
                raise ValueError("Invalid input hash")
            if report["input_sha256"][side] != result[side]["input_sha256"] or not isinstance(result[side]["title"], str) or not isinstance(result[side]["api_version"], str):
                raise ValueError("Invalid input metadata")
        encoded = json.dumps(result, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))
        size = len(encoded.encode("utf-8"))
        if not 0 < size <= OUTPUT_LIMIT:
            raise ValueError("Snapshot too large")
        return encoded, size, hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    except (AssertionError, KeyError, TypeError, ValueError, OverflowError):
        raise HistoryUnavailable("The generated comparison could not be saved as a valid snapshot.") from None


def metadata_record(row):
    try:
        return {
            "id": row["id"], "created_at": row["created_at"], "status": row["status"],
            "old": {"title": row["old_title"], "version": row["old_version"], "input_sha256": row["old_sha256"]},
            "new": {"title": row["new_title"], "version": row["new_version"], "input_sha256": row["new_sha256"]},
            "engine_version": row["engine_version"], "policy_version": row["policy_version"],
            "verdict": row["verdict"], "coverage_status": row["coverage_status"],
            "summary": json.loads(row["summary_json"]), "result_bytes": row["result_bytes"],
            "result_sha256": row["fingerprint"],
        }
    except (ValueError, TypeError):
        raise HistoryUnavailable("Saved history metadata could not be read.") from None


class HistoryStore:
    def __init__(self, settings):
        self.settings = settings
        self.path = settings.runtime_root / "history.sqlite3"
        self.engine = make_engine(self.path)  # No connection or directory creation here.

    def close(self):
        self.engine.dispose()

    @contextmanager
    def connection(self, write=False):
        if not self.path.is_file():
            raise HistoryUnavailable("Initialize history with scripts/setup-history.py before using saved comparisons.")
        try:
            mode = "IMMEDIATE" if write else "DEFERRED"
            with self.engine.connect().execution_options(sqlite_begin_mode=mode) as connection:
                with connection.begin():
                    revision = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one_or_none()
                    if revision != SCHEMA_REVISION:
                        raise HistoryUnavailable("History schema is not current; run the history setup script.")
                    yield connection
        except SQLAlchemyError:
            raise HistoryUnavailable("History is temporarily unavailable; no successful save is claimed.") from None

    def readiness(self):
        with self.connection() as connection:
            count, used = connection.execute(sa.select(sa.func.count(), sa.func.coalesce(sa.func.sum(runs.c.result_bytes), 0))).one()
        return {"status": "ready", "database": "sqlite", "schema_revision": SCHEMA_REVISION,
                "mode": "single_user_local", "saved_comparisons": count, "stored_result_bytes": used,
                "limits": {"records": self.settings.history_max_records, "result_bytes": self.settings.history_max_bytes}}

    def save(self, result):
        encoded, size, fingerprint = encode_result(result)
        report = result["comparison"]
        with self.connection(write=True) as connection:
            existing = connection.execute(sa.select(*META_COLUMNS).where(runs.c.fingerprint == fingerprint)).mappings().first()
            if existing is not None:
                return metadata_record(existing), False
            count, used = connection.execute(sa.select(sa.func.count(), sa.func.coalesce(sa.func.sum(runs.c.result_bytes), 0))).one()
            if count >= self.settings.history_max_records or used + size > self.settings.history_max_bytes:
                raise HistoryFull("History limit reached; delete saved comparisons before saving another.")
            record = {
                "id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
                "fingerprint": fingerprint, "status": "completed",
                "old_title": result["old"]["title"][:160], "new_title": result["new"]["title"][:160],
                "old_version": result["old"]["api_version"][:80], "new_version": result["new"]["api_version"][:80],
                "old_sha256": result["old"]["input_sha256"], "new_sha256": result["new"]["input_sha256"],
                "engine_version": report["engine_version"], "policy_version": report["policy_version"],
                "verdict": report["verdict"], "coverage_status": report["coverage"]["status"],
                "summary_json": json.dumps(report["summary"], sort_keys=True),
                "result_json": encoded, "result_bytes": size,
            }
            connection.execute(runs.insert().values(**record))
        return metadata_record(record), True

    def list(self, limit=20, cursor=None):
        with self.connection() as connection:
            query = sa.select(*META_COLUMNS)
            if cursor is not None:
                anchor = connection.execute(sa.select(runs.c.created_at).where(runs.c.id == cursor)).scalar_one_or_none()
                if anchor is None:
                    raise InvalidCursor("History cursor no longer exists; reload the first page.")
                query = query.where(sa.or_(runs.c.created_at < anchor, sa.and_(runs.c.created_at == anchor, runs.c.id < cursor)))
            rows = connection.execute(query.order_by(runs.c.created_at.desc(), runs.c.id.desc()).limit(limit + 1)).mappings().all()
        has_more = len(rows) > limit
        page = [metadata_record(row) for row in rows[:limit]]
        return {"items": page, "next_cursor": page[-1]["id"] if has_more else None, "has_more": has_more}

    def get(self, run_id):
        with self.connection() as connection:
            row = connection.execute(sa.select(runs).where(runs.c.id == run_id)).mappings().first()
        if row is None:
            raise RunNotFound("Saved comparison not found.")
        try:
            encoded = row["result_json"].encode("utf-8")
            if len(encoded) != row["result_bytes"] or hashlib.sha256(encoded).hexdigest() != row["fingerprint"]:
                raise ValueError("Snapshot integrity mismatch")
            result = json.loads(encoded)
        except (ValueError, TypeError, UnicodeError):
            raise HistoryUnavailable("Saved comparison snapshot could not be read consistently.") from None
        return {**metadata_record(row), "result": result}

    def delete(self, run_id):
        with self.connection(write=True) as connection:
            result = connection.execute(runs.delete().where(runs.c.id == run_id))
            if result.rowcount != 1:
                raise RunNotFound("Saved comparison not found.")
