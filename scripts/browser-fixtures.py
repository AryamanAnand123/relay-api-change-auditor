"""Generate current-engine synthetic responses for simulated browser-state tests."""

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from auditor.spec_worker import analyze_pair


def compare(old, new):
    return json.dumps(analyze_pair({"old": json.dumps(old), "new": json.dumps(new)}, compare=True), ensure_ascii=True)


old = json.loads((ROOT / "examples/orders-v1.json").read_text(encoding="utf-8"))
new = json.loads((ROOT / "examples/orders-v2-breaking.json").read_text(encoding="utf-8"))
additive = json.loads((ROOT / "examples/orders-v2-compatible.json").read_text(encoding="utf-8"))
partial = copy.deepcopy(old)
partial["paths"]["/orders"]["post"]["requestBody"]["content"]["application/json"]["schema"]["allOf"] = [{"required": ["currency"]}]
numeric = copy.deepcopy(old)
numeric["paths"]["/orders"]["post"]["parameters"] = [{"name": "code", "in": "query", "schema": {"type": "integer", "enum": [2, 900719925474099312345678901]}}]
numeric_new = copy.deepcopy(numeric)
numeric_new["paths"]["/orders"]["post"]["parameters"][0]["schema"]["enum"] = [2]
malicious = copy.deepcopy(old)
malicious["info"]["title"] = '<img src=x onerror="window.__relayInjected=1">'
field = '<img src=x onerror="window.__relayInjected=1">'
malicious["paths"]["/orders"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"][field] = {"type": "string"}
malicious_new = copy.deepcopy(malicious)
malicious_new["paths"]["/orders"]["post"]["requestBody"]["content"]["application/json"]["schema"]["required"].append(field)
print(json.dumps({"breaking": compare(old, new), "additive": compare(old, additive), "identical": compare(old, old), "partial": compare(partial, new), "numeric": compare(numeric, numeric_new), "malicious": compare(malicious, malicious_new)}, ensure_ascii=True))
