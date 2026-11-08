"""Two-phase live check: prepare, restart the API, verify and delete own fixture."""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from auditor.config import Settings


def files(old, new):
    return {"old": ("old.json", old, "application/json"), "new": ("new.json", new, "application/json")}


def prepare(client, state_file):
    if state_file.exists():
        raise RuntimeError("A prepared check already exists. Restart the API and run --verify; it will clean up its own fixture.")
    baseline = client.get("/api/system/database")
    baseline.raise_for_status()
    label = "section-3-live-" + str(uuid4())
    old = json.loads((ROOT / "examples/orders-v1.json").read_text(encoding="utf-8"))
    old["info"]["title"] = label
    old["info"]["description"] = "Original synthetic live-check input; never retained as raw file bytes."
    new = json.loads((ROOT / "examples/orders-v2-breaking.json").read_text(encoding="utf-8"))
    new["info"]["title"] = label
    old_bytes, new_bytes = json.dumps(old).encode(), json.dumps(new).encode()
    response = client.post("/api/comparisons", files=files(old_bytes, new_bytes))
    response.raise_for_status()
    saved = response.json()
    if response.status_code != 201 or saved["reused"]:
        raise RuntimeError("Unique synthetic fixture was unexpectedly reused; no automatic deletion performed.")
    state = {"id": saved["id"], "label": label, "result_sha256": saved["result_sha256"],
             "baseline_count": baseline.json()["saved_comparisons"], "checks": ["create 201 with complete snapshot"]}
    state_file.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    detail = client.get("/api/comparisons/" + saved["id"])
    detail.raise_for_status()
    assert detail.json()["result"] == saved["result"]
    state["checks"].append("detail matches completed comparison")
    duplicate = client.post("/api/comparisons", files=files(old_bytes, new_bytes))
    assert duplicate.status_code == 200 and duplicate.json()["reused"] and duplicate.json()["id"] == saved["id"]
    state["checks"].append("duplicate reuses same record")
    json_export = client.get("/api/comparisons/" + saved["id"] + "/export?format=json")
    assert json_export.status_code == 200
    assert json_export.json() == {"export_schema_version": "1", **detail.json()}
    state["checks"].append("JSON export equals stored detail")
    markdown = client.get("/api/comparisons/" + saved["id"] + "/export?format=markdown")
    blocks = [json.loads(block) for block in re.findall(r"```json\n(.*?)\n```", markdown.text, flags=re.S)]
    assert blocks[2]["counts"] == saved["summary"] and blocks[4:] == saved["result"]["comparison"]["findings"]
    state["checks"].append("Markdown summary and evidence match")
    state["json_export_sha256"] = hashlib.sha256(json_export.content).hexdigest()
    state["markdown_export_sha256"] = hashlib.sha256(markdown.content).hexdigest()
    cursor = None
    while True:
        page = client.get("/api/comparisons", params={"limit": 1, **({"cursor": cursor} if cursor else {})}).json()
        if any(item["id"] == saved["id"] for item in page["items"]):
            break
        cursor = page["next_cursor"]
        assert cursor is not None, "Synthetic saved record missing from history"
    state["checks"].append("paginated metadata includes fixture")
    invalid = client.post("/api/comparisons", files=files(old_bytes, b"{"))
    assert invalid.status_code == 422
    assert client.get("/api/system/database").json()["saved_comparisons"] == state["baseline_count"] + 1
    state["checks"].append("failed validation leaves no additional record")
    stateless = client.post("/api/specifications/compare", files=files(old_bytes, new_bytes))
    assert stateless.status_code == 200 and client.get("/api/system/database").json()["saved_comparisons"] == state["baseline_count"] + 1
    state["checks"].append("stateless comparison does not save")
    assert client.get("/api/comparisons", headers={"Origin": "https://unrelated.example"}).status_code == 403
    assert client.delete("/api/comparisons/" + saved["id"], headers={"Origin": "https://unrelated.example"}).status_code == 403
    state["checks"].append("cross-origin read and delete rejected")
    state_file.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print("Prepared one synthetic comparison. Restart only Apiproj's API, then run this script with --verify.")


def verify(client, state_file):
    state = json.loads(state_file.read_text(encoding="utf-8"))
    run_id = str(UUID(state["id"]))
    if not re.fullmatch(r"section-3-live-[a-f0-9-]{36}", state["label"]):
        raise RuntimeError("Unexpected fixture identity; refusing deletion.")
    response = client.get("/api/comparisons/" + run_id)
    response.raise_for_status()
    saved = response.json()
    if saved["old"]["title"] != state["label"] or saved["new"]["title"] != state["label"] or saved["result_sha256"] != state["result_sha256"]:
        raise RuntimeError("Saved fixture does not match captured identity; refusing deletion.")
    state["checks"].append("snapshot survived API restart")
    for format, key in (("json", "json_export_sha256"), ("markdown", "markdown_export_sha256")):
        export = client.get("/api/comparisons/" + run_id + "/export?format=" + format)
        assert export.status_code == 200 and hashlib.sha256(export.content).hexdigest() == state[key]
    state["checks"].append("both exports byte-identical after restart")
    deleted = client.delete("/api/comparisons/" + run_id)
    assert deleted.status_code == 204
    assert client.get("/api/comparisons/" + run_id).status_code == 404
    assert client.get("/api/comparisons/" + run_id + "/export?format=json").status_code == 404
    assert client.get("/api/comparisons/" + run_id + "/export?format=markdown").status_code == 404
    state["checks"].append("deletion removes detail and both exports")
    readiness = client.get("/api/system/database").json()
    assert readiness["saved_comparisons"] == state["baseline_count"], "History changed during the check; inspect it without deleting other records."
    state["checks"].append("saved-record count restored to baseline")
    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "status": "passed", "transport": "actual HTTP across an API process restart",
              "runtime": client.get("/health").json(), "schema_revision": readiness["schema_revision"], "checks": state["checks"],
              "temporary_fixture_deleted": True, "preexisting_records_deleted": False, "ai_used": False}
    (ROOT / "docs/section-3-live.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    state_file.unlink()
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    phase = parser.add_mutually_exclusive_group(required=True)
    phase.add_argument("--prepare", action="store_true")
    phase.add_argument("--verify", action="store_true")
    arguments = parser.parse_args()
    state_file = Settings().runtime_root / "section-3-live-state.json"
    with httpx.Client(base_url="http://127.0.0.1:8010", trust_env=False, timeout=30) as client:
        response = client.get("/health")
        response.raise_for_status()
        assert response.json()["section"] >= 3, "Start the Section 3 or later backend first."
        (prepare if arguments.prepare else verify)(client, state_file)


if __name__ == "__main__":
    main()
