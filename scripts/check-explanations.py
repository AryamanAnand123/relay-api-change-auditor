"""Opt-in real provider pilot using only original public synthetic examples."""

import asyncio
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from auditor.config import Settings
from auditor.explanations import AIError, ExplanationService
from auditor.history import encode_result
from auditor.spec_worker import analyze_pair


async def main():
    service = ExplanationService(Settings())
    if not service.status()["configured"]:
        raise SystemExit("Run scripts/configure-ai.py first. No provider call was made.")
    result = analyze_pair({"old": (ROOT / "examples/orders-v1.json").read_text(encoding="utf-8"),
                           "new": (ROOT / "examples/orders-v2-breaking.json").read_text(encoding="utf-8")}, compare=True)
    original = copy.deepcopy(result)
    record = {"id": "original-example-pilot", "result": result, "result_sha256": encode_result(result)[2]}
    responses = []
    for finding in result["comparison"]["findings"]:
        try:
            response = await service.generate(record, finding["id"])
        except AIError as error:
            print(json.dumps({"status": "failed", "code": error.code, "message": error.message}))
            raise SystemExit(1)
        service.remember(record, finding["id"], response)
        cached = await service.generate(record, finding["id"])
        assert cached["cached"] and cached["content"] == response["content"]
        assert result == original
        responses.append({"rule_id": finding["rule_id"], "response": response})
        print(json.dumps({"rule": finding["rule_id"], "status": "generated", "latency_ms": response["provenance"]["latency_ms"], "cache_reuse": True}))
    report = {"status": "passed_structural_and_cache_checks", "real_provider": True, "synthetic_examples_only": True,
              "calls": len(responses), "automatic_retries": 0, "authoritative_findings_unchanged": result == original,
              "quality_review": "Review generated prose separately; schema and evidence binding do not establish factual correctness.",
              "responses": responses}
    (ROOT / "docs/section-5-pilot.json").write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
