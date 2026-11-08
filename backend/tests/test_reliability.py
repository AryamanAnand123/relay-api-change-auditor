import asyncio
import copy
from pathlib import Path

import httpx
import pytest
from groq import APITimeoutError

from auditor.config import Settings
from auditor.explanations import AIError, ExplanationService
from auditor.history import encode_result
from auditor.spec_worker import analyze_pair


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "runtime"; root.mkdir()
    (root / "groq.key").write_text("gsk_" + "synthetic_test_key_" * 2, encoding="ascii")
    settings = Settings(_env_file=None, runtime_root=root)
    examples = Path(__file__).resolve().parents[2] / "examples"
    result = analyze_pair({"old": (examples / "orders-v1.json").read_text(encoding="utf-8"), "new": (examples / "orders-v2-breaking.json").read_text(encoding="utf-8")}, compare=True)
    record = {"id": "synthetic", "result": result, "result_sha256": encode_result(result)[2]}
    return settings, record, result["comparison"]["findings"][0]["id"]


def test_real_sdk_timeout_is_classified_without_exposing_transport_text(setup):
    settings, record, finding = setup
    class Provider:
        calls = 0
        async def generate(self, *args):
            self.calls += 1
            raise APITimeoutError(request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"))
    provider = Provider()
    service = ExplanationService(settings, provider)
    with pytest.raises(AIError) as error:
        asyncio.run(service.generate(record, finding))
    assert error.value.code == "ai_timeout" and error.value.status == 504
    assert provider.calls == 1 and not service.cache


def test_cancelled_ai_attempt_releases_admission_without_caching_or_editing_report(setup):
    settings, record, finding = setup
    original = copy.deepcopy(record)
    class Provider:
        async def generate(self, *args):
            await asyncio.sleep(60)
    async def scenario():
        service = ExplanationService(settings, Provider())
        task = asyncio.create_task(service.generate(record, finding))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not service.lock.locked() and not service.cache
        assert service.daily_calls == 1
        assert record == original
    asyncio.run(scenario())
