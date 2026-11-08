"""Opt-in first-attempt AI evaluation; retain failures and never tune to this run."""

import argparse
import asyncio
import copy
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evaluation"))
from evaluate import canonical, load_corpus, payload_for
from auditor.config import Settings
from auditor.explanations import AIError, ExplanationService, MODEL, PROMPT_VERSION, SYSTEM, context_for
from auditor.history import encode_result
from auditor.spec_worker import analyze_pair


async def evaluate(output):
    corpus, manifest = load_corpus()
    rubric_bytes = (ROOT / "evaluation/ai-rubric.json").read_bytes()
    rubric = json.loads(rubric_bytes)
    if set(manifest["ai_case_ids"]) != set(rubric["cases"]):
        raise ValueError("Frozen AI case/rubric mismatch")
    service = ExplanationService(Settings())
    if not service.status()["configured"]:
        raise SystemExit("Configure your project Free-plan key first. No provider call made.")
    by_id = {case["id"]: case for case in corpus["cases"]}
    report = {"status": "running", "mode": "real Groq via LangChain; original synthetic evaluation inputs only",
              "corpus_sha256": manifest["sha256"], "rubric_sha256": hashlib.sha256(rubric_bytes).hexdigest(),
              "model": MODEL, "prompt_version": PROMPT_VERSION, "prompt_sha256": hashlib.sha256(SYSTEM.encode()).hexdigest(),
              "generated_at": datetime.now(timezone.utc).isoformat(), "attempts_per_case": 1,
              "spacing_seconds": manifest["ai_spacing_seconds"], "cases": []}
    for index, case_id in enumerate(manifest["ai_case_ids"]):
        if index:
            print(json.dumps({"status": "waiting_for_free_quota_spacing", "seconds": manifest["ai_spacing_seconds"]}), flush=True)
            await asyncio.sleep(manifest["ai_spacing_seconds"])
        case = by_id[case_id]
        result = analyze_pair(payload_for(case), compare=True)
        before = copy.deepcopy(result)
        findings = result["comparison"]["findings"]
        if len(findings) != 1:
            raise ValueError("Frozen AI case must produce exactly one finding")
        finding = findings[0]
        record = {"id": "eval-" + case_id, "result": result, "result_sha256": encode_result(result)[2]}
        context, _ = context_for(record, finding["id"])
        row = {"case_id": case_id, "finding": finding, "context": json.loads(context), "attempts": 1}
        started = time.perf_counter()
        try:
            response = await service.generate(record, finding["id"])
            row.update(status="generated", response=response, output_schema_and_binding_valid=True)
        except AIError as error:
            row.update(status="not_generated", error={"code": error.code, "message": error.message}, output_schema_and_binding_valid=False)
        row["wall_latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        row["authoritative_result_unchanged"] = canonical(result) == canonical(before)
        if not row["authoritative_result_unchanged"]:
            raise ValueError("AI changed authoritative result")
        report["cases"].append(row)
        output.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"case": case_id, "status": row["status"], "latency_ms": row.get("response", {}).get("provenance", {}).get("latency_ms")}), flush=True)
    report["status"] = "complete_awaiting_manual_review"
    report["summary"] = {"attempted": len(report["cases"]), "generated": sum(row["status"] == "generated" for row in report["cases"]),
                         "not_generated": sum(row["status"] != "generated" for row in report["cases"]),
                         "automatic_retries": 0, "database_writes": 0, "retained_failures": True,
                         "quality_note": "Structural validity is scored automatically; prose fidelity requires the frozen manual rubric."}
    output.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"]), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-ai", action="store_true", help="Explicitly allow six real Free-plan provider attempts")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/section-6-ai.json")
    args = parser.parse_args()
    if not args.live_ai:
        raise SystemExit("Use --live-ai to opt in to the six provider attempts. Default execution makes no calls.")
    if args.output.exists():
        raise SystemExit("An evaluation report already exists. Use a new --output; do not overwrite first-attempt results.")
    asyncio.run(evaluate(args.output))


if __name__ == "__main__":
    main()
