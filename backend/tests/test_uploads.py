import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

from auditor import uploads
from auditor.main import create_app
from auditor.spec_input import BODY_LIMIT, FILE_LIMIT

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
OLD = (EXAMPLES / "orders-v1.json").read_bytes()
NEW = (EXAMPLES / "orders-v2-breaking.json").read_bytes()


def post(files=None, **kwargs):
    async def perform():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://127.0.0.1:8010") as client:
            return await client.post(uploads.VALIDATE_PATH, files=files, **kwargs)
    return asyncio.run(perform())


def pair(old=OLD, new=NEW):
    return {"old": ("old.json", old, "application/json"), "new": ("new.json", new, "application/json")}


def test_real_subprocess_pair_validation():
    response = post(pair())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["comparison_performed"] is False
    assert result["old"]["coverage"]["operation_count"] == 2
    assert result["new"]["coverage"]["operation_count"] == 1
    assert response.headers["cache-control"] == "no-store"


def test_real_subprocess_invalid_new_does_not_return_a_partial_success():
    response = post(pair(new=b'{"openapi":"3.1.0"}'))
    assert response.status_code == 422
    assert response.json()["detail"]["side"] == "new"
    assert response.json()["detail"]["code"] == "invalid_openapi"
    assert "old" not in response.json()


def test_real_subprocess_external_reference_rejection():
    value = json.loads(OLD)
    value["components"]["schemas"]["Order"] = {"$ref": "file:///C:/private.json"}
    response = post(pair(old=json.dumps(value).encode()))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unsupported_reference"


@pytest.mark.parametrize("files", [
    {"old": ("old.json", OLD)},
    [("old", ("old.json", OLD)), ("old", ("duplicate.json", NEW))],
    [("old", ("old.json", OLD)), ("new", ("new.json", NEW)), ("extra", ("extra.json", NEW))],
    {"old": ("old.yaml", OLD), "new": ("new.json", NEW)},
])
def test_exactly_two_named_json_files_are_required(files):
    assert post(files).status_code == 422


def test_non_multipart_request_rejected():
    assert post(json={"old": {}, "new": {}}).status_code == 415


def test_file_over_limit_rejected_before_validation():
    response = post(pair(old=b" " * (FILE_LIMIT + 1)))
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "file_too_large"


def test_maximum_file_is_accepted_without_spilling_to_disk(monkeypatch):
    from tempfile import SpooledTemporaryFile
    def forbidden(*args, **kwargs):
        pytest.fail("Private upload spilled to filesystem")
    monkeypatch.setattr(SpooledTemporaryFile, "rollover", forbidden)
    padded = OLD + b" " * (FILE_LIMIT - len(OLD))
    response = post(pair(old=padded))
    assert response.status_code == 200, response.text


def test_actual_body_bytes_enforced_with_a_false_content_length():
    response = post(content=b"x" * (BODY_LIMIT + 1), headers={"Content-Length": "1", "Content-Type": "multipart/form-data; boundary=test"})
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "request_too_large"


def test_declared_oversized_body_rejected():
    assert post(content=b"", headers={"Content-Length": str(BODY_LIMIT + 1)}).status_code == 413


def test_invalid_length_rejected():
    assert post(content=b"", headers={"Content-Length": "-1"}).status_code == 400


def test_cross_origin_and_compressed_uploads_rejected():
    assert post(pair(), headers={"Origin": "https://unrelated.example"}).status_code == 403
    assert post(pair(), headers={"Origin": "null"}).status_code == 403
    assert post(pair(), headers={"Content-Encoding": "gzip"}).status_code == 415


def test_bad_multipart_and_non_utf8_fail_clearly():
    assert post(content=b"bad", headers={"Content-Type": "multipart/form-data; boundary=test"}).status_code == 422
    assert post(pair(old=b"\xff")).json()["detail"]["code"] == "invalid_encoding"


def test_concurrent_second_pair_is_rejected_and_first_can_finish(monkeypatch):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def fake_validation(payload):
            entered.set()
            await release.wait()
            return {"status": "test-only"}
        monkeypatch.setattr(uploads, "run_validation", fake_validation)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://127.0.0.1:8010") as client:
            first = asyncio.create_task(client.post(uploads.VALIDATE_PATH, files=pair()))
            await entered.wait()
            assert (await client.get("/health")).status_code == 200
            second = await client.post(uploads.VALIDATE_PATH, files=pair())
            assert second.status_code == 429
            release.set()
            assert (await first).status_code == 200
            assert (await client.post(uploads.VALIDATE_PATH, files=pair())).status_code == 200
    asyncio.run(scenario())


def test_timeout_kills_and_reaps_worker(monkeypatch):
    class Process:
        returncode = None
        killed = False
        reaped = False
        def kill(self):
            self.killed = True
            self.returncode = -9
        async def communicate(self, data=None):
            if not self.killed:
                await asyncio.sleep(10)
            self.reaped = True
            return b"", b""
    process = Process()
    async def spawn(*args, **kwargs):
        return process
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(uploads, "WORKER_TIMEOUT", 0.01)
    with pytest.raises(HTTPException) as captured:
        asyncio.run(uploads.run_validation({"old": "{}", "new": "{}"}))
    assert captured.value.detail["code"] == "validation_timeout"
    assert process.killed and process.reaped


@pytest.mark.parametrize("output", [b"not json", b"[]", b'{"ok":true}', b'{"ok":false}'])
def test_malformed_worker_result_is_a_service_error(monkeypatch, output):
    class Process:
        returncode = 0
        async def communicate(self, data=None):
            return output, b"private diagnostic that must not be returned"
    async def spawn(*args, **kwargs):
        return Process()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(HTTPException) as captured:
        asyncio.run(uploads.run_validation({}))
    assert captured.value.status_code == 503
    assert "private diagnostic" not in str(captured.value.detail)


def test_chunked_multipart_without_content_length(monkeypatch):
    async def fake_validation(payload):
        assert set(payload) == {"old", "new"}
        return {"status": "test-only"}
    monkeypatch.setattr(uploads, "run_validation", fake_validation)
    prepared = httpx.Request("POST", "http://127.0.0.1:8010", files=pair())
    raw = prepared.read()
    headers = {k: v for k, v in prepared.headers.items() if k != "content-length"}
    async def scenario():
        async def chunks():
            for start in range(0, len(raw), 127):
                yield raw[start:start + 127]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://127.0.0.1:8010") as client:
            response = await client.post(uploads.VALIDATE_PATH, content=chunks(), headers=headers)
            assert response.status_code == 200
    asyncio.run(scenario())


def test_slow_body_times_out_before_parser_or_worker(monkeypatch):
    original_timeout = asyncio.timeout
    monkeypatch.setattr(asyncio, "timeout", lambda delay: original_timeout(0.01))
    async def scenario():
        async def app(*args):
            pytest.fail("Overslow body reached the app")
        async def receive():
            await asyncio.sleep(10)
        messages = []
        async def send(message):
            messages.append(message)
        scope = {"type": "http", "path": uploads.VALIDATE_PATH, "method": "POST", "headers": []}
        await uploads.UploadBoundary(app)(scope, receive, send)
        assert messages[0]["status"] == 408
    asyncio.run(scenario())


def test_worker_launch_failure_is_redacted_service_error(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise PermissionError("private filesystem location")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden)
    with pytest.raises(HTTPException) as captured:
        asyncio.run(uploads.run_validation({}))
    assert captured.value.status_code == 503
    assert "private filesystem" not in str(captured.value.detail)
