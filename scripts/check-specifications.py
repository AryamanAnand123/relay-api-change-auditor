"""Read-only live checks using original synthetic specifications; no persistence."""

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "/api/specifications/validate"
OLD = (ROOT / "examples/orders-v1.json").read_bytes()
NEW = (ROOT / "examples/orders-v2-breaking.json").read_bytes()


def files(old=OLD, new=NEW):
    return {"old": ("old.json", old, "application/json"), "new": ("new.json", new, "application/json")}


def main():
    checks = []
    with httpx.Client(base_url="http://127.0.0.1:8010", trust_env=False, timeout=30) as client:
        health = client.get("/health")
        health.raise_for_status()
        assert health.json()["section"] >= 1, "Start the Section 1 or later backend first."
        response = client.post(ENDPOINT, files=files())
        assert response.status_code == 200, response.status_code
        result = response.json()
        assert result["comparison_performed"] is False
        assert result["old"]["coverage"]["operation_count"] == 2
        assert result["new"]["coverage"]["operation_count"] == 1
        checks.append({"case": "original_pair", "http": response.status_code, "old_operations": 2, "new_operations": 1})

        for name, old, expected in (
            ("malformed_json", b"{", "invalid_json"),
            ("duplicate_keys", b'{"openapi":"3.1.0","openapi":"3.0.3"}', "duplicate_key"),
            ("invalid_structure", b'{"openapi":"3.1.0"}', "invalid_openapi"),
            ("unsupported_version", b'{"openapi":"3.2.0"}', "unsupported_version"),
        ):
            response = client.post(ENDPOINT, files=files(old=old))
            assert response.status_code == 422
            assert response.json()["detail"]["code"] == expected
            checks.append({"case": name, "http": response.status_code, "code": expected})

        for target in ("https://127.0.0.1/private.json", "file:///C:/private.json"):
            value = json.loads(OLD)
            value["components"]["schemas"]["Order"] = {"$ref": target}
            response = client.post(ENDPOINT, files=files(old=json.dumps(value).encode()))
            assert response.status_code == 422 and response.json()["detail"]["code"] == "unsupported_reference"
            checks.append({"case": "external_reference_" + target.split(":")[0], "http": 422, "code": "unsupported_reference"})

        for name, schema, expected in (
            ("composition_warning", {"oneOf": [{"type": "string"}, {"type": "integer"}]}, "schema_keywords_not_analyzed"),
            ("recursive_warning", {"type": "object", "properties": {"next": {"$ref": "#/components/schemas/Order"}}}, "recursive_schema"),
        ):
            value = json.loads(OLD)
            value["components"]["schemas"]["Order"] = schema
            response = client.post(ENDPOINT, files=files(old=json.dumps(value).encode()))
            assert response.status_code == 200
            normalized = response.json()["old"]
            assert normalized["coverage"]["status"] == "partial"
            assert any(w["code"] == expected for w in normalized["warnings"])
            assert all(op["coverage_warning_ids"] for op in normalized["operations"])
            checks.append({"case": name, "http": 200, "coverage": "partial", "warning": expected})

        value = json.loads(OLD)
        value["openapi"] = "3.0.3"
        response = client.post(ENDPOINT, files=files(old=json.dumps(value).encode()))
        assert response.status_code == 200 and response.json()["old"]["openapi_version"] == "3.0.3"
        checks.append({"case": "openapi_30", "http": 200})

        value = json.loads(OLD)
        value["components"]["schemas"]["Text"] = {"type": "string"}
        value["components"]["schemas"]["Order"] = {"$ref": "#%2Fcomponents%2Fschemas%2FText"}
        response = client.post(ENDPOINT, files=files(old=json.dumps(value).encode()))
        assert response.status_code == 200
        assert response.json()["old"]["schemas"]["#/components/schemas/Text"]["type"] == "string"
        checks.append({"case": "encoded_reference_fragment", "http": 200})

        response = client.post(ENDPOINT, files=files(old=OLD + b" " * (2 * 1024 * 1024 + 1 - len(OLD))))
        assert response.status_code == 413 and response.json()["detail"]["code"] == "file_too_large"
        checks.append({"case": "oversized_file", "http": 413})

        prepared = httpx.Request("POST", "http://127.0.0.1:8010", files=files())
        body = prepared.read()
        headers = {key: val for key, val in prepared.headers.items() if key not in {"content-length", "host"}}
        response = client.post(ENDPOINT, headers=headers, content=(body[i:i + 127] for i in range(0, len(body), 127)))
        assert response.status_code == 200
        checks.append({"case": "chunked_multipart", "http": 200})

        response = client.post(ENDPOINT, files=files(), headers={"Origin": "https://unrelated.example"})
        assert response.status_code == 403
        checks.append({"case": "cross_origin", "http": 403})
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "status": "passed", "transport": "actual loopback HTTP and disposable validation subprocesses", "checks": checks, "persistence": "none", "comparison_performed": False}
    (ROOT / "docs/section-1-live.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
