"""Reproduce public example reports without accessing history, credentials, or a provider."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from auditor.exports import json_export, markdown_export
from auditor.spec_worker import analyze_pair


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    cases = [("breaking", "orders-v2-breaking.json", 3, 0),
             ("additive", "orders-v2-compatible.json", 0, 2),
             ("identical", "orders-v1.json", 0, 0)]
    manifests = []
    for label, filename, breaking, informational in cases:
        payload = {"old": (ROOT / "examples/orders-v1.json").read_text(encoding="utf-8"),
                   "new": (ROOT / "examples" / filename).read_text(encoding="utf-8")}
        result = analyze_pair(payload, compare=True)
        summary = result["comparison"]["summary"]
        if summary["breaking"] != breaking or summary["informational"] != informational or summary["total_findings"] != breaking + informational:
            raise ValueError("Original example outcomes changed; review before updating public reports")
        record = {"id": "public-example-" + label, "status": "completed", "example_only": True,
                  "storage": "Generated offline; not a saved user comparison", "result": result}
        for suffix, content in (("json", json_export(record)), ("md", markdown_export(record))):
            path = output / ("orders-" + label + "." + suffix)
            path.write_bytes(content)
            manifests.append({"file": path.name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
    (output / "manifest.json").write_text(json.dumps({"source": "original synthetic development examples", "engine_version": result["comparison"]["engine_version"],
                                                  "policy_version": result["comparison"]["policy_version"], "model_calls": 0, "history_access": False, "files": manifests}, indent=2) + "\n", encoding="utf-8")
    return manifests


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "examples/reports")
    files = build(parser.parse_args().output)
    print(json.dumps({"status": "passed", "example_reports": len(files), "model_calls": 0, "history_access": False}))
