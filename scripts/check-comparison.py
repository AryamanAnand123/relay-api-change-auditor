"""Live deterministic comparison checks on original synthetic fixtures only."""

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "/api/specifications/compare"


def document(direction, kind="string", enum=None):
    schema = {"type": kind}
    if enum is not None:
        schema["enum"] = enum
    operation = {"responses": {"204": {"description": "No content"}}}
    if direction == "request":
        operation["requestBody"] = {"required": True, "content": {"application/json": {"schema": schema}}}
    else:
        operation["responses"] = {"200": {"description": "Result", "content": {"application/json": {"schema": schema}}}}
    return {"openapi": "3.1.0", "info": {"title": "Original live comparison fixture", "version": "1"}, "paths": {"/items": {"post": operation}}}


def main():
    checks = []
    original = {name: (ROOT / "examples" / file).read_bytes() for name, file in (
        ("old", "orders-v1.json"), ("breaking", "orders-v2-breaking.json"), ("compatible", "orders-v2-compatible.json"))}

    def files(old, new):
        return {"old": ("old.json", old, "application/json"), "new": ("new.json", new, "application/json")}

    with httpx.Client(base_url="http://127.0.0.1:8010", trust_env=False, timeout=30) as client:
        health = client.get("/health").json()
        assert health["section"] >= 2, "Start the Section 2 or later backend first."

        def compare(name, old, new, expected):
            response = client.post(ENDPOINT, files=files(old, new))
            assert response.status_code == 200, (name, response.status_code)
            wrapper = response.json()
            assert wrapper["status"] == "compared" and wrapper["comparison_performed"] is True
            report = wrapper["comparison"]
            for severity, count in expected.items():
                assert report["summary"][severity] == count, (name, report["summary"])
            assert report["coverage"]["full_compatibility_analysis"] is False
            checks.append({"case": name, "http": 200, "summary": report["summary"], "verdict": report["verdict"]})
            return report

        sample = compare("original_breaking", original["old"], original["breaking"], {"breaking": 3, "total_findings": 3})
        compare("identical", original["old"], original["old"], {"total_findings": 0})
        compare("additive", original["old"], original["compatible"], {"breaking": 0, "informational": 2, "total_findings": 2})
        for direction, a, b, severity in (
            ("request", ["a", "b"], ["a"], "breaking"),
            ("request", ["a"], ["a", "b"], "informational"),
            ("response", ["a"], ["a", "b"], "breaking"),
            ("response", ["a", "b"], ["a"], "informational"),
        ):
            compare(direction + "_enum_" + severity, json.dumps(document(direction, enum=a)).encode(), json.dumps(document(direction, enum=b)).encode(), {severity: 1, "total_findings": 1})
        for direction, severity in (("request", "informational"), ("response", "breaking")):
            compare(direction + "_integer_to_number", json.dumps(document(direction, "integer")).encode(), json.dumps(document(direction, "number")).encode(), {severity: 1, "total_findings": 1})

        old = document("request", "object")
        old_schema = old["paths"]["/items"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        old_schema.update(properties={"id": {"type": "string"}}, allOf=[{"required": ["id"]}])
        new = copy.deepcopy(old)
        new["paths"]["/items"]["post"]["requestBody"]["content"]["application/json"]["schema"]["required"] = ["id"]
        partial = compare("unsupported_constraints_need_review", json.dumps(old).encode(), json.dumps(new).encode(), {"breaking": 0, "needs_review": 1})
        assert partial["coverage"]["status"] == "partial"

        for name, content, status, code in (
            ("invalid_new", b"{", 422, "invalid_json"),
            ("oversized_new", b" " * (2 * 1024 * 1024 + 1), 413, "file_too_large"),
        ):
            response = client.post(ENDPOINT, files=files(original["old"], content))
            assert response.status_code == status and response.json()["detail"]["code"] == code
            assert "comparison" not in response.json()
            checks.append({"case": name, "http": status, "code": code})

        response = client.post(ENDPOINT, files=files(original["old"], original["breaking"]), headers={"Origin": "https://unrelated.example"})
        assert response.status_code == 403
        checks.append({"case": "cross_origin", "http": 403})

        prepared = httpx.Request("POST", "http://127.0.0.1:8010", files=files(original["old"], original["breaking"]))
        body = prepared.read()
        headers = {k: v for k, v in prepared.headers.items() if k not in {"content-length", "host"}}
        response = client.post(ENDPOINT, headers=headers, content=(body[i:i + 127] for i in range(0, len(body), 127)))
        assert response.status_code == 200
        assert [f["id"] for f in response.json()["comparison"]["findings"]] == [f["id"] for f in sample["findings"]]
        checks.append({"case": "chunked_comparison_stable_ids", "http": 200})

        response = client.post("/api/specifications/validate", files=files(original["old"], original["breaking"]))
        assert response.status_code == 200 and response.json()["comparison_performed"] is False
        checks.append({"case": "validation_route_preserved", "http": 200})

    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "status": "passed", "runtime": health,
              "engine_version": sample["engine_version"], "policy_version": sample["policy_version"],
              "transport": "actual loopback HTTP and disposable offline workers", "checks": checks,
              "original_sample_findings": sample["findings"], "persistence": "none", "ai_used": False}
    (ROOT / "docs/section-2-live.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "live_checks": len(checks), "original_sample_summary": sample["summary"], "report": "docs/section-2-live.json"}, indent=2))


if __name__ == "__main__":
    main()
