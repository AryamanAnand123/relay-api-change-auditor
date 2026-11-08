"""Score frozen labels; never derive expectations from engine output."""

import argparse
import copy
import hashlib
import json
import math
import platform
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from auditor.comparison import ENGINE_VERSION, POLICY_VERSION
from auditor.spec_input import SpecError, resolve_pointer
from auditor.spec_worker import analyze_pair

SIGNATURE_FIELDS = ("rule_id", "severity", "policy_severity", "direction", "location", "path", "method")


def canonical(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))


def load_corpus(directory=None):
    directory = directory or ROOT / "evaluation"
    encoded = (directory / "corpus.json").read_bytes()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if hashlib.sha256(encoded).hexdigest() != manifest["sha256"]:
        raise ValueError("Frozen corpus checksum mismatch; refusing to score modified labels.")
    corpus = json.loads(encoded)
    if len(corpus["cases"]) != manifest["case_count"] or len({case["id"] for case in corpus["cases"]}) != len(corpus["cases"]):
        raise ValueError("Corpus count/identity mismatch")
    return corpus, manifest


def payload_for(case, reformatted=False):
    return {side: case.get(side + "_text", json.dumps(case[side], ensure_ascii=True, sort_keys=reformatted, indent=1 if reformatted else None)) for side in ("old", "new")}


def signature(finding):
    return canonical({field: finding[field] for field in SIGNATURE_FIELDS})


def evidence_checks(result, sources):
    checked, errors = 0, []
    for finding in result["comparison"]["findings"]:
        for side, key in (("old", "before"), ("new", "after")):
            value = finding[key]
            checked += 1
            try:
                if value["present"]:
                    actual = resolve_pointer(sources[side], value["pointer"])[0]
                    if canonical(actual) != canonical(value["value"]):
                        raise ValueError("Evidence value differs from source")
                else:
                    if value["pointer"] is not None or value["value"] is not None:
                        raise ValueError("Absent evidence must have null value and pointer")
                    resolve_pointer(sources[side], value["context_pointer"])
                    try:
                        resolve_pointer(sources[side], value["expected_pointer"])
                    except SpecError as error:
                        if error.detail["code"] != "unresolved_reference":
                            raise ValueError("Invalid expected pointer") from None
                    else:
                        raise ValueError("Absent evidence points to an existing value")
            except (SpecError, ValueError, KeyError, TypeError):
                errors.append({"finding_id": finding["id"], "side": side, "issue": "pointer/value consistency failed"})
    return checked, errors


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def score_case(case, repeats=3):
    payload = payload_for(case)
    timings, results, failures = [], [], []
    for _ in range(repeats):
        started = time.perf_counter()
        try:
            result = analyze_pair(payload, compare=True)
            results.append(result)
            failures.append(None)
        except SpecError as error:
            results.append(None)
            failures.append({"code": error.detail["code"], "side": error.detail.get("side")})
        except Exception as error:
            results.append(None)
            failures.append({"code": "unexpected_engine_exception", "type": type(error).__name__, "side": None})
        timings.append((time.perf_counter() - started) * 1000)
    expected, errors = case["expected"], []
    if "error_code" in expected:
        target = {"code": expected["error_code"], "side": expected["side"]}
        if any(item != target for item in failures):
            errors.append("rejection differs from frozen code/side")
        return {"id": case["id"], "status": "passed" if not errors else "failed", "kind": "rejection", "expected_error": target,
                "observed_errors": failures, "latency_ms": [round(value, 3) for value in timings], "issues": errors}
    expected_counts = Counter(signature(item) for item in expected["findings"])
    first = results[0]
    actual_counts = Counter(signature(item) for item in first["comparison"]["findings"]) if first else Counter()
    if any(failures):
        errors.append("valid comparison rejected")
    if expected_counts != actual_counts:
        errors.append("exact finding signatures differ from frozen labels")
    reproducible = all(canonical(item) == canonical(first) for item in results)
    if not reproducible:
        errors.append("repeated result changed")
    checked, pointer_errors, formatting_stable = 0, [], False
    if first:
        report = first["comparison"]
        if report["coverage"]["status"] != expected["coverage"]:
            errors.append("coverage differs from frozen expectation")
        if report["coverage"]["full_compatibility_analysis"] is not False:
            errors.append("full compatibility was claimed")
        checked, pointer_errors = evidence_checks(first, {side: json.loads(payload[side]) for side in ("old", "new")})
        if pointer_errors:
            errors.append("source evidence failed validation")
        try:
            changed = analyze_pair(payload_for(case, reformatted=True), compare=True)["comparison"]
            left, right = copy.deepcopy(report), copy.deepcopy(changed)
            left.pop("input_sha256"); right.pop("input_sha256")
            formatting_stable = canonical(left) == canonical(right)
        except Exception:
            formatting_stable = False
        if not formatting_stable:
            errors.append("formatting/key ordering changed semantic report or finding IDs")
    return {"id": case["id"], "status": "passed" if not errors else "failed", "kind": "comparison",
            "expected": [json.loads(item) for item in sorted(expected_counts.elements())],
            "predicted": [json.loads(item) for item in sorted(actual_counts.elements())],
            "compatible_control": case["compatible_control"], "expected_coverage": expected["coverage"],
            "observed_coverage": first["comparison"]["coverage"]["status"] if first else None,
            "reproducible": reproducible, "formatting_and_ids_stable": formatting_stable,
            "evidence_checks": checked, "evidence_errors": pointer_errors,
            "latency_ms": [round(value, 3) for value in timings],
            "result_sha256": hashlib.sha256(canonical(first).encode()).hexdigest() if first else None, "issues": errors}


def aggregate(rows):
    counts = {}
    for row in rows:
        if row["kind"] != "comparison":
            continue
        expected, actual = Counter(signature(item) for item in row["expected"]), Counter(signature(item) for item in row["predicted"])
        tp, fp, fn = expected & actual, actual - expected, expected - actual
        for field, values in (("tp", tp), ("fp", fp), ("fn", fn)):
            for key, count in values.items():
                rule = json.loads(key)["rule_id"]
                counts.setdefault(rule, {"tp": 0, "fp": 0, "fn": 0})[field] += count
    for values in counts.values():
        values["precision"] = values["tp"] / (values["tp"] + values["fp"]) if values["tp"] + values["fp"] else None
        values["recall"] = values["tp"] / (values["tp"] + values["fn"]) if values["tp"] + values["fn"] else None
    tp, fp, fn = (sum(values[field] for values in counts.values()) for field in ("tp", "fp", "fn"))
    controls = [row for row in rows if row.get("compatible_control")]
    false_positives = sum(any(f["severity"] == "breaking" for f in row["predicted"]) for row in controls)
    latencies = [value for row in rows if row["kind"] == "comparison" for value in row["latency_ms"]]
    pointers = sum(row.get("evidence_checks", 0) for row in rows)
    bad_pointers = sum(len(row.get("evidence_errors", [])) for row in rows)
    return {"cases": len(rows), "passed": sum(row["status"] == "passed" for row in rows),
            "comparison_cases": sum(row["kind"] == "comparison" for row in rows),
            "rejection_cases": sum(row["kind"] == "rejection" for row in rows),
            "exact_signature_micro": {"tp": tp, "fp": fp, "fn": fn,
                                      "precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None},
            "per_rule": dict(sorted(counts.items())), "rules_with_expected_findings": sum(values["tp"] + values["fn"] > 0 for values in counts.values()),
            "compatible_control_cases": len(controls), "compatible_controls_with_breaking_false_positives": false_positives,
            "breaking_false_positive_case_rate": false_positives / len(controls) if controls else None,
            "evidence_sides_checked": pointers, "evidence_errors": bad_pointers,
            "evidence_correct_fraction": (pointers - bad_pointers) / pointers if pointers else None,
            "latency_in_process_ms": {"samples": len(latencies), "p50": statistics.median(latencies) if latencies else None,
                                      "p95_nearest_rank": percentile(latencies, .95), "max": max(latencies) if latencies else None},
            "scope": "Exact policy labels in this original frozen corpus only; not general OpenAPI accuracy or an external benchmark."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "docs/section-6-deterministic.json")
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=3)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    if args.output.exists() and not args.replace:
        raise SystemExit("Report exists; choose another --output or explicitly --replace.")
    corpus, manifest = load_corpus()
    rows = [score_case(case, args.repeats) for case in corpus["cases"]]
    summary = aggregate(rows)
    report = {"status": "passed" if summary["passed"] == summary["cases"] else "failed", "corpus": manifest,
              "engine_version": ENGINE_VERSION, "policy_version": POLICY_VERSION, "repeats": args.repeats,
              "python": platform.python_version(), "platform": platform.platform(), "generated_at": datetime.now(timezone.utc).isoformat(),
              "timing_note": "Local in-process parse, offline validation, normalization and comparison. Includes first-use cost; excludes worker startup, HTTP, database and AI. No warm-up samples discarded.",
              "summary": summary, "cases": rows}
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "summary": summary, "failed_cases": [{"id": row["id"], "issues": row["issues"]} for row in rows if row["status"] != "passed"]}))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
