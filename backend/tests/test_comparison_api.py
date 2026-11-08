import asyncio
from pathlib import Path

import httpx
import pytest

from auditor import uploads
from auditor.main import create_app
from auditor.spec_input import BODY_LIMIT

ROOT = Path(__file__).resolve().parents[2]
OLD = (ROOT / "examples/orders-v1.json").read_bytes()
NEW = (ROOT / "examples/orders-v2-breaking.json").read_bytes()


def files(old=OLD, new=NEW):
    return {"old": ("old.json", old, "application/json"), "new": ("new.json", new, "application/json")}


def post(**kwargs):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://127.0.0.1:8010") as client:
            return await client.post(uploads.COMPARE_PATH, **kwargs)
    return asyncio.run(run())


def test_real_compare_subprocess_returns_three_original_findings():
    response = post(files=files())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "compared" and result["comparison_performed"] is True
    assert result["comparison"]["summary"]["breaking"] == 3
    assert result["comparison"]["summary"]["total_findings"] == 3
    assert response.headers["cache-control"] == "no-store"


def test_real_compare_identical_files_has_no_findings():
    response = post(files=files(new=OLD))
    assert response.status_code == 200
    assert response.json()["comparison"]["findings"] == []


def test_compare_invalid_new_file_does_not_return_partial_findings():
    response = post(files=files(new=b"{"))
    assert response.status_code == 422
    assert response.json()["detail"]["side"] == "new"
    assert "comparison" not in response.json()


@pytest.mark.parametrize("kwargs,status", [
    ({"content": b"", "headers": {"Content-Length": str(BODY_LIMIT + 1)}}, 413),
    ({"files": files(), "headers": {"Origin": "https://unrelated.example"}}, 403),
    ({"json": {"old": {}, "new": {}}}, 415),
])
def test_comparison_shares_upload_boundary(kwargs, status):
    assert post(**kwargs).status_code == status


def test_validate_and_compare_share_one_admission_lock(monkeypatch):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def fake_validation(payload, compare=False):
            entered.set()
            await release.wait()
            return {"status": "test-only"}
        monkeypatch.setattr(uploads, "run_validation", fake_validation)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://127.0.0.1:8010") as client:
            first = asyncio.create_task(client.post(uploads.COMPARE_PATH, files=files()))
            await entered.wait()
            second = await client.post(uploads.VALIDATE_PATH, files=files())
            assert second.status_code == 429
            assert (await client.get("/health")).status_code == 200
            release.set()
            assert (await first).status_code == 200
    asyncio.run(scenario())
