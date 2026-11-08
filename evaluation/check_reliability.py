"""Read-only production-worker latency/resource/cancellation checks; no DB or model calls."""

import argparse
import asyncio
import copy
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evaluation"))
from evaluate import load_corpus, payload_for, percentile
from auditor import uploads
from auditor.spec_input import FILE_LIMIT
from fastapi import HTTPException


async def main(output):
    if output.exists():
        raise SystemExit("Report exists; use a new --output to retain prior measurements.")
    corpus, manifest = load_corpus()
    cases = {case["id"]: case for case in corpus["cases"]}
    samples, checks = [], []
    chosen = ["identical", "nested-request-required", "array-escaped-numeric-widening", "review-recursive-reference", "reject-external-reference", "escaped-component-reference-oas30"]
    for case_id in chosen:
        case = cases[case_id]
        for repeat in range(2):
            started = time.perf_counter()
            try:
                result = await uploads.run_validation(payload_for(case), compare=True)
                status, error = "compared", None
            except HTTPException as failure:
                status, error = "rejected", failure.detail["code"]
            expected_error = case["expected"].get("error_code")
            assert error == expected_error, (case_id, error, expected_error)
            samples.append({"case": case_id, "repeat": repeat + 1, "status": status, "error_code": error,
                            "latency_ms": round((time.perf_counter() - started) * 1000, 3)})
    checks.append("12 isolated production-worker requests return expected comparisons/rejections within the 10-second budget")

    base = copy.deepcopy(cases["identical"]["old"])
    workloads = []
    workloads.append(("actual-file-limit", {"old": " " * (FILE_LIMIT + 1), "new": json.dumps(base)}, "file_too_large"))
    node_heavy = copy.deepcopy(base); node_heavy["x-load"] = [0] * 20001
    workloads.append(("actual-input-node-limit", {"old": json.dumps(node_heavy), "new": json.dumps(base)}, "resource_limit"))
    operations = copy.deepcopy(base)
    for index in range(299):
        operations["paths"]["/batch/" + str(index)] = {"get": {"responses": {"204": {"description": "Synthetic"}}}}
    workloads.append(("actual-operation-limit", {"old": json.dumps(operations), "new": json.dumps(base)}, "resource_limit"))
    old = copy.deepcopy(base); new = copy.deepcopy(base)
    old["paths"]["/parcels"]["post"]["responses"]["200"]["content"]["application/json"]["schema"] = {"type": "object", "properties": {"field" + str(i): {"type": "integer"} for i in range(501)}}
    new["paths"]["/parcels"]["post"]["responses"]["200"]["content"]["application/json"]["schema"] = {"type": "object", "properties": {"field" + str(i): {"type": "number"} for i in range(501)}}
    workloads.append(("actual-finding-limit", {"old": json.dumps(old), "new": json.dumps(new)}, "resource_limit"))
    resource_rows = []
    for name, payload, expected in workloads:
        started = time.perf_counter()
        try:
            await uploads.run_validation(payload, compare=True)
        except HTTPException as error:
            assert error.detail["code"] == expected, (name, error.detail)
            resource_rows.append({"check": name, "status": "passed", "error_code": expected, "latency_ms": round((time.perf_counter() - started) * 1000, 3)})
        else:
            raise AssertionError(name + " unexpectedly succeeded")
    checks.append("real file/node/operation/finding limits fail explicitly rather than emitting partial successful reports")

    original_spawn = asyncio.create_subprocess_exec
    started = asyncio.Event()
    owned = []
    async def capture(*args, **kwargs):
        process = await original_spawn(*args, **kwargs)
        owned.append(process)
        started.set()
        return process
    asyncio.create_subprocess_exec = capture
    try:
        task = asyncio.create_task(uploads.run_validation(payload_for(cases["identical"]), compare=True))
        await started.wait()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Cancellation was swallowed")
        assert len(owned) == 1 and owned[0].returncode is not None
    finally:
        asyncio.create_subprocess_exec = original_spawn
    # A cancelled worker must not prevent the next independent comparison.
    assert (await uploads.run_validation(payload_for(cases["identical"]), compare=True))["comparison_performed"]
    checks.append("cancelling an actual request kills and reaps its own worker; the next comparison still succeeds")
    values = [row["latency_ms"] for row in samples]
    report = {"status": "passed", "corpus_sha256": manifest["sha256"], "checks": checks,
              "timing_scope": "Actual production offline subprocess, JSON serialization, pipes and engine; excludes HTTP/history/AI. All samples retained, including first startup and rejection cases.",
              "worker_latency_ms": {"samples": len(values), "p50": statistics.median(values), "p95_nearest_rank": percentile(values, .95), "max": max(values)},
              "samples": samples, "resource_checks": resource_rows, "cancelled_worker_reaped": True,
              "database_writes": 0, "model_requests": 0}
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "worker_latency_ms": report["worker_latency_ms"], "resource_checks": len(resource_rows), "cancelled_worker_reaped": True}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "docs/section-6-reliability.json")
    asyncio.run(main(parser.parse_args().output))
