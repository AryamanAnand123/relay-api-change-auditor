"""Deterministic, bounded comparison under the declared-field client policy."""

import hashlib
import json
import re
from decimal import Decimal

from auditor.spec_input import MAX_DEPTH, SpecError, pointer, resolve_pointer

ENGINE_VERSION = "1.0.1"
POLICY_VERSION = "declared-client-v1"
MAX_FINDINGS = 500
MAX_PAIRS = 10_000
MAX_GAPS = 500
TYPES = {"string", "integer", "number", "boolean", "null", "object", "array"}


def at(path, *parts):
    for part in parts:
        path = pointer(path, part)
    return path


def value_key(value):
    # JSON booleans are not numbers; JSON 1 and 1.0 are the same enum value.
    if isinstance(value, bool):
        return "boolean", value
    if value is None:
        return "null", None
    if isinstance(value, (int, float)):
        return "number", Decimal(str(value))
    return "string", value


def accepts(kind, value):
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "integer":
        number = Decimal(str(value)) if accepts("number", value) else None
        return number is not None and number == number.to_integral_value()
    return {"string": isinstance(value, str), "boolean": isinstance(value, bool), "null": value is None}.get(kind, False)


def finite_domain(schema):
    values = schema["enum"]
    if values is None:
        values = {"boolean": [False, True], "null": [None]}.get(schema["type"])
    if values is None:
        return None
    return {value_key(value) for value in values if accepts(schema["type"], value)}


def subset(left, right):
    """Scalar/type domain inclusion; object properties are checked separately."""
    left_values, right_values = finite_domain(left), finite_domain(right)
    if left_values is not None:
        if right_values is not None:
            return left_values <= right_values
        return all((kind == "number" and right["type"] in {"number", "integer"} and (right["type"] == "number" or value == value.to_integral_value())) or kind == right["type"] for kind, value in left_values)
    if right_values is not None:
        return False
    return left["type"] == right["type"] or (left["type"], right["type"]) == ("integer", "number")


class Comparator:
    def __init__(self, old, new, documents):
        self.specs = {"old": old, "new": new}
        self.documents = documents
        self.findings = {}
        self.gaps = {}
        self.pairs = 0
        self.dialect_changed = old["openapi_version"].split(".")[:2] != new["openapi_version"].split(".")[:2]
        if self.dialect_changed:
            self.gap("dialect_changed", None, "Schema interpretation changed between OpenAPI 3.0 and 3.1; schema findings need review.")

    def evidence(self, side, path):
        try:
            value, canonical = resolve_pointer(self.documents[side], path)
            return {"present": True, "pointer": canonical, "value": value}
        except SpecError:
            context = path
            while "/" in context:
                context = context.rsplit("/", 1)[0]
                try:
                    resolve_pointer(self.documents[side], context)
                    break
                except SpecError:
                    continue
            return {"present": False, "pointer": None, "expected_pointer": path, "context_pointer": context, "value": None}

    def gap(self, code, operation, message):
        identity = json.dumps([code, operation], sort_keys=True)
        self.gaps[identity] = {"code": code, "operation": operation, "message": message}
        if len(self.gaps) > MAX_GAPS:
            raise SpecError("resource_limit", "Comparison coverage gaps exceed the supported limit.")

    def emit(self, rule, severity, op, direction, location, title, before, after, uncertain=False, warning_ids=None):
        logical = {"method": op[0], "path": op[1], "direction": direction, "location": location}
        identity = json.dumps([POLICY_VERSION, rule, logical], sort_keys=True, ensure_ascii=True)
        finding_id = "change-" + hashlib.sha256(identity.encode()).hexdigest()[:20]
        self.findings[finding_id] = {
            "id": finding_id, "rule_id": rule,
            "severity": "needs_review" if uncertain else severity,
            "policy_severity": severity, "title": title, **logical,
            "before": self.evidence("old", before), "after": self.evidence("new", after),
            "coverage_warning_ids": warning_ids or {"old": [], "new": []},
        }
        if len(self.findings) > MAX_FINDINGS:
            raise SpecError("resource_limit", "Comparison exceeds the 500-finding limit; split the specifications.")

    def dereference(self, side, source):
        seen = set()
        while source is not None:
            if source in seen:
                return None
            seen.add(source)
            node = self.specs[side]["schemas"][source]
            if node["ref"] is None:
                return node
            source = node["ref"]
        return None

    def empty_enum(self, side, operation):
        roots = [p["schema"] for p in operation["parameters"]]
        if operation["request_body"]:
            roots.extend(operation["request_body"]["content"].values())
        for response in operation["responses"].values():
            roots.extend(response["content"].values())
        stack, seen = [p for p in roots if p], set()
        while stack:
            source = stack.pop()
            if source in seen:
                continue
            seen.add(source)
            node = self.specs[side]["schemas"][source]
            if isinstance(node["type"], str) and node["type"] in TYPES and node["enum"] is not None and not finite_domain(node):
                return True
            stack.extend(p for p in [node["ref"], node["items"], *node["properties"].values()] if p)
        return False

    def schemas(self, old_path, new_path, op, direction, location, uncertain, warnings, active=(), old_expected=None, new_expected=None):
        self.pairs += 1
        if self.pairs > MAX_PAIRS or len(active) >= MAX_DEPTH:
            raise SpecError("resource_limit", "Schema comparison exceeds its pair/depth budget.")
        old = self.dereference("old", old_path)
        new = self.dereference("new", new_path)
        if old is None or new is None:
            self.gap("schema_not_comparable", op, "Missing or cyclic schema declarations require review.")
            if (old_path is None) != (new_path is None):
                self.emit("schema_declaration_changed", "needs_review", op, direction, location, "Schema declaration added or removed", old_path or old_expected or "#", new_path or new_expected or "#", warning_ids=warnings)
            return
        pair = (old["pointer"], new["pointer"])
        if pair in active:
            self.gap("recursive_schema_pair", op, "Recursive schema compatibility is not analyzed.")
            return
        if not isinstance(old["type"], str) or not isinstance(new["type"], str) or old["type"] not in TYPES or new["type"] not in TYPES:
            self.gap("unsupported_schema_type", op, "Boolean, union, and untyped schema compatibility requires review.")
            return
        ctx = (*active, pair)
        local_uncertain = uncertain or finite_domain(old) == set() or finite_domain(new) == set()
        if old["type"] != new["type"]:
            compatible = subset(old, new) if direction == "request" else subset(new, old)
            self.emit("schema_type_changed", "informational" if compatible else "breaking", op, direction, location,
                      "Declared schema type changed", at(old["pointer"], "type"), at(new["pointer"], "type"), local_uncertain, warnings)
        old_enum = None if old["enum"] is None else {value_key(v) for v in old["enum"]}
        new_enum = None if new["enum"] is None else {value_key(v) for v in new["enum"]}
        if old_enum != new_enum:
            compatible = subset(old, new) if direction == "request" else subset(new, old)
            rule = ("request_enum_changed" if direction == "request" else "response_enum_changed")
            self.emit(rule, "informational" if compatible else "breaking", op, direction, location,
                      "Declared enum values changed", at(old["pointer"], "enum"), at(new["pointer"], "enum"), local_uncertain, warnings)
        if old["type"] == new["type"] == "object":
            old_properties, new_properties = old["properties"], new["properties"]
            old_required, new_required = set(old["required"]), set(new["required"])
            for name in sorted(new_required - old_required):
                self.emit("request_property_required" if direction == "request" else "response_property_required", "breaking" if direction == "request" else "informational", op, direction, [*location, "properties", name],
                          "Property added to the required list", at(old["pointer"], "required"), at(new["pointer"], "required"), local_uncertain, warnings)
            for name in sorted(old_required - new_required):
                if direction == "response" and name in old_properties and name not in new_properties:
                    continue  # The removed-property finding already captures this lost guarantee.
                self.emit("request_required_relaxed" if direction == "request" else "response_required_relaxed", "informational" if direction == "request" else "breaking", op, direction, [*location, "properties", name],
                          "Property removed from the required list", at(old["pointer"], "required"), at(new["pointer"], "required"), local_uncertain, warnings)
            for name in sorted(old_properties.keys() - new_properties.keys()):
                severity = "breaking" if direction == "response" and name in old_required else "potentially_breaking"
                self.emit("property_removed", severity, op, direction, [*location, "properties", name], "Declared property removed", old_properties[name], at(new["pointer"], "properties", name), local_uncertain, warnings)
            for name in sorted(new_properties.keys() - old_properties.keys()):
                if direction == "request" and name in new_required - old_required:
                    continue
                severity = "needs_review" if direction == "request" and name in old_required else "informational"
                self.emit("property_added", severity, op, direction, [*location, "properties", name], "Declared property added", at(old["pointer"], "properties", name), new_properties[name], local_uncertain, warnings)
            for name in sorted(old_properties.keys() & new_properties.keys()):
                self.schemas(old_properties[name], new_properties[name], op, direction, [*location, "properties", name], local_uncertain, warnings, ctx)
        elif old["type"] == new["type"] == "array":
            if old["items"] is not None or new["items"] is not None:
                self.schemas(old["items"], new["items"], op, direction, [*location, "items"], local_uncertain, warnings, ctx, at(old["pointer"], "items"), at(new["pointer"], "items"))

    def media(self, old, new, old_pointer, new_pointer, op, direction, location, uncertain, warnings):
        def keys(content):
            result = {}
            for name in content:
                canonical = name.lower()
                if not re.fullmatch(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+", canonical) or canonical in result:
                    return None
                result[canonical] = name
            return result
        old_keys, new_keys = keys(old), keys(new)
        if old_keys is None or new_keys is None:
            self.gap("media_matching_not_analyzed", op, "Wildcard, parameterized, or ambiguous media matching requires review.")
            return
        for canonical in sorted(old_keys.keys() - new_keys.keys()):
            name = old_keys[canonical]
            self.emit("media_type_removed", "breaking", op, direction, [*location, canonical], "Declared media type removed", at(old_pointer, name), at(new_pointer, name), uncertain, warnings)
        for canonical in sorted(new_keys.keys() - old_keys.keys()):
            name = new_keys[canonical]
            self.emit("media_type_added", "informational" if direction == "request" else "potentially_breaking", op, direction, [*location, canonical], "Declared media type added", at(old_pointer, name), at(new_pointer, name), uncertain, warnings)
        for canonical in sorted(old_keys.keys() & new_keys.keys()):
            self.schemas(old[old_keys[canonical]], new[new_keys[canonical]], op, direction, [*location, canonical], uncertain, warnings, old_expected=at(old_pointer, old_keys[canonical], "schema"), new_expected=at(new_pointer, new_keys[canonical], "schema"))

    def operations(self, key, old, new):
        warnings = {"old": old["coverage_warning_ids"], "new": new["coverage_warning_ids"]}
        uncertain = self.dialect_changed or any(warnings.values())
        if self.empty_enum("old", old) or self.empty_enum("new", new):
            self.gap("empty_enum_domain", key, "A reachable typed enum has no valid values; compatibility implications require review.")
            uncertain = True
        def parameter_key(parameter):
            return parameter["in"], parameter["name"].lower() if parameter["in"] == "header" else parameter["name"]
        old_parameters = {parameter_key(p): p for p in old["parameters"]}
        new_parameters = {parameter_key(p): p for p in new["parameters"]}
        if len(old_parameters) != len(old["parameters"]) or len(new_parameters) != len(new["parameters"]):
            self.gap("ambiguous_header_parameters", key, "Case-insensitive header collisions require manual operation review.")
            return
        for name in sorted(old_parameters.keys() - new_parameters.keys()):
            p = old_parameters[name]
            self.emit("parameter_removed", "potentially_breaking", key, "request", ["parameters", *name], "Declared parameter removed", p["pointer"], at(new["pointer"], "parameters"), uncertain, warnings)
        for name in sorted(new_parameters.keys() - old_parameters.keys()):
            p = new_parameters[name]
            self.emit("parameter_added", "breaking" if p["required"] else "informational", key, "request", ["parameters", *name], "Required parameter added" if p["required"] else "Optional parameter added", at(old["pointer"], "parameters"), p["pointer"], uncertain, warnings)
        for name in sorted(old_parameters.keys() & new_parameters.keys()):
            a, b = old_parameters[name], new_parameters[name]
            if a["required"] != b["required"]:
                self.emit("parameter_requirement_changed", "breaking" if b["required"] else "informational", key, "request", ["parameters", *name], "Parameter requirement changed", at(a["pointer"], "required"), at(b["pointer"], "required"), uncertain, warnings)
            self.schemas(a["schema"], b["schema"], key, "request", ["parameters", *name], uncertain, warnings, old_expected=at(a["pointer"], "schema"), new_expected=at(b["pointer"], "schema"))
        a, b = old["request_body"], new["request_body"]
        if a is None and b is not None:
            self.emit("request_body_added", "breaking" if b["required"] else "informational", key, "request", ["requestBody"], "Request body declaration added", at(old["pointer"], "requestBody"), b["pointer"], uncertain, warnings)
        elif a is not None and b is None:
            self.emit("request_body_removed", "potentially_breaking", key, "request", ["requestBody"], "Request body declaration removed", a["pointer"], at(new["pointer"], "requestBody"), uncertain, warnings)
        elif a is not None and b is not None:
            if a["required"] != b["required"]:
                self.emit("request_body_requirement_changed", "breaking" if b["required"] else "informational", key, "request", ["requestBody"], "Request body requirement changed", at(a["pointer"], "required"), at(b["pointer"], "required"), uncertain, warnings)
            self.media(a["content"], b["content"], at(a["pointer"], "content"), at(b["pointer"], "content"), key, "request", ["requestBody", "content"], uncertain, warnings)
        a, b = old["responses"], new["responses"]
        if any(not re.fullmatch(r"[1-5][0-9]{2}", status) for status in a.keys() | b.keys()):
            self.gap("response_status_matching_not_analyzed", key, "Default/range response precedence requires manual review.")
            return
        for status in sorted(a.keys() - b.keys()):
            self.emit("response_status_removed", "informational", key, "response", ["responses", status], "Previously possible response status removed", a[status]["pointer"], at(new["pointer"], "responses", status), warning_ids=warnings)
        for status in sorted(b.keys() - a.keys()):
            self.emit("response_status_added", "potentially_breaking", key, "response", ["responses", status], "New possible response status added", at(old["pointer"], "responses", status), b[status]["pointer"], uncertain, warnings)
        for status in sorted(a.keys() & b.keys()):
            self.media(a[status]["content"], b[status]["content"], at(a[status]["pointer"], "content"), at(b[status]["pointer"], "content"), key, "response", ["responses", status, "content"], uncertain, warnings)

    def run(self):
        old = {(op["method"], op["path"]): op for op in self.specs["old"]["operations"]}
        new = {(op["method"], op["path"]): op for op in self.specs["new"]["operations"]}
        removed, added = set(old) - set(new), set(new) - set(old)
        handled = set()
        for key in sorted(removed):
            template = re.sub(r"\{[^{}]+\}", "{}", key[1])
            matches = [candidate for candidate in sorted(added) if candidate[0] == key[0] and re.sub(r"\{[^{}]+\}", "{}", candidate[1]) == template]
            if matches:
                target = matches[0]
                handled.add(target)
                self.emit("path_template_changed", "needs_review", key, "operation", ["path", target[1]], "Path-template parameter names changed; route equivalence needs review", old[key]["pointer"], new[target]["pointer"])
            else:
                self.emit("operation_removed", "breaking", key, "operation", [], "HTTP operation removed", old[key]["pointer"], at("#/paths", key[1], key[0].lower()))
        for key in sorted(added - handled):
            self.emit("operation_added", "informational", key, "operation", [], "HTTP operation added", at("#/paths", key[1], key[0].lower()), new[key]["pointer"])
        for key in sorted(set(old) & set(new)):
            self.operations(key, old[key], new[key])
        findings = sorted(self.findings.values(), key=lambda f: (f["path"], f["method"], f["direction"], json.dumps(f["location"]), f["rule_id"]))
        counts = {name: sum(f["severity"] == name for f in findings) for name in ("breaking", "potentially_breaking", "informational", "needs_review")}
        partial = bool(self.gaps or self.specs["old"]["warnings"] or self.specs["new"]["warnings"])
        verdict = "breaking_changes_detected" if counts["breaking"] else "review_required" if partial or counts["potentially_breaking"] or counts["needs_review"] else "no_breaking_changes_detected_in_supported_subset"
        return {"engine_version": ENGINE_VERSION, "policy_version": POLICY_VERSION,
                "policy_assumptions": ["Old callers use declared request fields; undocumented extra request values are outside this policy.",
                                       "Clients accept additional response properties but rely on declared types and required fields.",
                                       "Response enums are treated as exhaustive client expectations.",
                                       "Findings describe declared contracts, not observed server behavior or a proof of full schema subsumption."],
                "verdict": verdict,
                "input_sha256": {side: spec["input_sha256"] for side, spec in self.specs.items()},
                "summary": {"total_findings": len(findings), **counts}, "findings": findings,
                "coverage": {"status": "partial" if partial else "supported_subset", "full_compatibility_analysis": False,
                             "input_warnings": {side: spec["warnings"] for side, spec in self.specs.items()},
                             "analysis_warnings": sorted(self.gaps.values(), key=lambda g: json.dumps(g, sort_keys=True))}}
