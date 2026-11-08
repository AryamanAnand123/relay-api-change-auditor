"""Validate evidence lineage and summarize every evaluated AI attempt, including failures."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def summarize(raw_bytes, review, manifest, rubric_bytes):
    raw = json.loads(raw_bytes)
    if hashlib.sha256(raw_bytes).hexdigest() != review["source_report_sha256"]:
        raise ValueError("Manual review does not match the retained AI output report")
    if raw["corpus_sha256"] != manifest["sha256"] or raw["rubric_sha256"] != hashlib.sha256(rubric_bytes).hexdigest():
        raise ValueError("Evaluation lineage mismatch")
    attempts = {row["case_id"]: row for row in raw["cases"]}
    reviews = {row["case_id"]: row for row in review["cases"]}
    expected = set(manifest["ai_case_ids"])
    if set(attempts) != expected or set(reviews) != expected or len(attempts) != len(raw["cases"]) or len(reviews) != len(review["cases"]):
        raise ValueError("An evaluation case was omitted or duplicated")
    grades = Counter()
    for case_id in manifest["ai_case_ids"]:
        item, assessment = attempts[case_id], reviews[case_id]
        grade = assessment["grade"]
        if grade not in {"grounded", "partially_grounded", "ungrounded", "not_generated"}:
            raise ValueError("Unknown manual grade")
        if (grade == "not_generated") != (item["status"] != "generated"):
            raise ValueError("Failed generations must remain in the denominator")
        if grade == "grounded" and assessment["unsupported_assumptions"]:
            raise ValueError("Unsupported assumptions cannot receive a grounded grade")
        grades[grade] += 1
    return {"attempted": len(expected), "accepted_structural_outputs": sum(row["status"] == "generated" for row in attempts.values()),
            "not_generated": grades["not_generated"], "manual_grades": dict(grades),
            "grounded_denominator_all_attempts": {"numerator": grades["grounded"], "denominator": len(expected)},
            "authoritative_reports_unchanged": sum(row["authoritative_result_unchanged"] for row in attempts.values()),
            "failed_attempts_without_latency_sample": sum(row["status"] != "generated" and "wall_latency_ms" not in row for row in attempts.values()),
            "automatic_retries": raw["summary"]["automatic_retries"], "review_method": review["reviewer"],
            "scope": "Original six-case first-attempt sample; not independent or general model accuracy."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "docs/section-6-summary.json")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Summary exists; choose a new --output to retain prior evidence.")
    load = lambda name: json.loads((ROOT / name).read_text(encoding="utf-8"))
    manifest = load("evaluation/manifest.json")
    deterministic = load("docs/section-6-deterministic.json")
    reliability = load("docs/section-6-reliability.json")
    ai = summarize((ROOT / "docs/section-6-ai.json").read_bytes(), load("docs/section-6-ai-review.json"), manifest, (ROOT / "evaluation/ai-rubric.json").read_bytes())
    if deterministic["corpus"]["sha256"] != manifest["sha256"] or reliability["corpus_sha256"] != manifest["sha256"]:
        raise ValueError("Deterministic/reliability reports use a different corpus")
    report = {"status": "evaluated_with_documented_AI_limitations", "corpus_sha256": manifest["sha256"],
              "engine_version": deterministic["engine_version"], "policy_version": deterministic["policy_version"],
              "deterministic": deterministic["summary"], "production_worker": reliability["worker_latency_ms"], "ai": ai,
              "note": "Deterministic corpus passes; AI prose remains advisory. Reports preserve baseline failures, label erratum, and first-attempt AI rejection."}
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "deterministic_cases": report["deterministic"]["passed"], "ai": ai}))


if __name__ == "__main__":
    main()
