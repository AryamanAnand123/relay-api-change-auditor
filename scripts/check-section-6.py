"""Read-only real HTTP regression checks; no saved records or model calls."""

import json
import sys
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.evaluate import load_corpus, payload_for, signature


def main():
    corpus, manifest = load_corpus()
    cases = {case["id"]: case for case in corpus["cases"]}
    checks = []
    with httpx.Client(base_url="http://127.0.0.1:8010", timeout=15, trust_env=False, follow_redirects=False) as client:
        health = client.get("/health").json()
        assert health["section"] >= 6
        before = client.get("/api/system/database").json()
        ai_before = client.get("/api/ai/status").json()["calls_this_process_today"]
        response = client.get("/")
        assert response.status_code == 200 and "Relay" in response.text
        checks.append("workspace and Section 6 liveness are served on loopback")
        for name in ["request-enum-narrow", "documentation-only", "review-recursive-reference", "escaped-component-reference", "escaped-component-reference-oas30", "escaped-property-reference", "escaped-property-reference-oas30", "reject-duplicate-key"]:
            case = cases[name]; payload = payload_for(case)
            files = {side: (side + ".json", payload[side].encode(), "application/json") for side in ("old", "new")}
            response = client.post("/api/specifications/compare", files=files)
            if "error_code" in case["expected"]:
                assert response.status_code == 422
                assert response.json()["detail"]["code"] == case["expected"]["error_code"]
                assert response.json()["detail"]["side"] == case["expected"]["side"]
            else:
                assert response.status_code == 200
                report = response.json()["comparison"]
                assert report["engine_version"] == "1.0.1"
                assert Counter(signature(item) for item in report["findings"]) == Counter(signature(item) for item in case["expected"]["findings"])
                assert report["coverage"]["status"] == case["expected"]["coverage"]
                assert report["coverage"]["full_compatibility_analysis"] is False
            checks.append({"case": name, "http_status": response.status_code})
        after = client.get("/api/system/database").json()
        assert after["saved_comparisons"] == before["saved_comparisons"]
        assert after["stored_result_bytes"] == before["stored_result_bytes"]
        assert client.get("/api/ai/status").json()["calls_this_process_today"] == ai_before
        checks.append("stateless regression checks leave saved history, stored bytes, and provider-call count unchanged")
    result = {"status": "passed", "runtime": health, "corpus_sha256": manifest["sha256"], "checks": checks,
              "transport": "actual loopback HTTP and disposable offline workers", "history_writes": 0, "model_requests": 0,
              "saved_comparisons_before": before["saved_comparisons"], "saved_comparisons_after": after["saved_comparisons"]}
    (ROOT / "docs/section-6-live.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "checks": len(checks), "history_writes": 0, "model_requests": 0}))


if __name__ == "__main__":
    main()
