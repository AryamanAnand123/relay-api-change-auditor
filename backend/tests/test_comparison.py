import copy
import json
from pathlib import Path

import pytest

from auditor.comparison import Comparator, accepts, finite_domain, subset
from auditor.spec_input import SpecError, parse_document, resolve_pointer
from auditor.spec_worker import analyze_pair

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def document(direction="response", schema=None):
    schema = {"type": "string"} if schema is None else schema
    operation = {"responses": {"204": {"description": "No content"}}}
    if direction == "request":
        operation["requestBody"] = {"required": True, "content": {"application/json": {"schema": schema}}}
    else:
        operation["responses"] = {"200": {"description": "Result", "content": {"application/json": {"schema": schema}}}}
    return {"openapi": "3.1.0", "info": {"title": "Original comparison fixture", "version": "1"}, "paths": {"/items": {"post": operation}}}


def schema_at(value, direction):
    op = value["paths"]["/items"]["post"]
    return (op["requestBody"] if direction == "request" else op["responses"]["200"])["content"]["application/json"]["schema"]


def compare(old, new):
    payload = {"old": json.dumps(old), "new": json.dumps(new)}
    result = analyze_pair(payload, compare=True)
    assert result["comparison_performed"] is True
    report = result["comparison"]
    # Every concrete evidence pointer resolves to the actual before/after value.
    for finding in report["findings"]:
        for side, key in (("old", "before"), ("new", "after")):
            evidence = finding[key]
            source = old if side == "old" else new
            if evidence["present"]:
                assert resolve_pointer(source, evidence["pointer"])[0] == evidence["value"]
            else:
                assert evidence["pointer"] is None
                resolve_pointer(source, evidence["context_pointer"])
                with pytest.raises(SpecError):
                    resolve_pointer(source, evidence["expected_pointer"])
    return report


def rule(report, name):
    return [finding for finding in report["findings"] if finding["rule_id"] == name]


def test_original_pair_has_exactly_three_breaking_findings():
    old = json.loads((EXAMPLES / "orders-v1.json").read_text(encoding="utf-8"))
    new = json.loads((EXAMPLES / "orders-v2-breaking.json").read_text(encoding="utf-8"))
    report = compare(old, new)
    assert {f["rule_id"] for f in report["findings"]} == {"operation_removed", "request_property_required", "schema_type_changed"}
    assert report["summary"] == {"total_findings": 3, "breaking": 3, "potentially_breaking": 0, "informational": 0, "needs_review": 0}
    assert report["engine_version"] == "1.0.1"
    assert report["policy_version"] == "declared-client-v1"


def test_original_additive_file_has_two_informational_findings():
    old = json.loads((EXAMPLES / "orders-v1.json").read_text(encoding="utf-8"))
    new = json.loads((EXAMPLES / "orders-v2-compatible.json").read_text(encoding="utf-8"))
    report = compare(old, new)
    assert report["summary"]["total_findings"] == 2
    assert report["summary"]["informational"] == 2
    assert report["summary"]["breaking"] == 0


def test_identical_and_documentation_only_changes_have_no_findings():
    old = document()
    new = copy.deepcopy(old)
    new["info"].update(version="2", description="New documentation")
    new["paths"]["/items"]["post"]["operationId"] = "renamedOperation"
    schema_at(new, "response")["description"] = "Description is not a contract change"
    assert compare(old, old)["findings"] == []
    report = compare(old, new)
    assert report["findings"] == []
    assert report["verdict"] == "no_breaking_changes_detected_in_supported_subset"
    assert report["coverage"]["full_compatibility_analysis"] is False


@pytest.mark.parametrize("direction,old_enum,new_enum,severity", [
    ("request", ["a", "b"], ["a"], "breaking"),
    ("request", ["a"], ["a", "b"], "informational"),
    ("response", ["a"], ["a", "b"], "breaking"),
    ("response", ["a", "b"], ["a"], "informational"),
    ("request", None, ["a"], "breaking"),
    ("request", ["a"], None, "informational"),
    ("response", None, ["a"], "informational"),
    ("response", ["a"], None, "breaking"),
])
def test_enum_direction(direction, old_enum, new_enum, severity):
    old, new = document(direction), document(direction)
    if old_enum is not None:
        schema_at(old, direction)["enum"] = old_enum
    if new_enum is not None:
        schema_at(new, direction)["enum"] = new_enum
    findings = rule(compare(old, new), f"{direction}_enum_changed")
    assert len(findings) == 1 and findings[0]["severity"] == severity


@pytest.mark.parametrize("direction,a,b,severity", [
    ("request", "integer", "number", "informational"),
    ("request", "number", "integer", "breaking"),
    ("response", "integer", "number", "breaking"),
    ("response", "number", "integer", "informational"),
    ("request", "string", "object", "breaking"),
    ("response", "number", "object", "breaking"),
])
def test_type_direction(direction, a, b, severity):
    findings = rule(compare(document(direction, {"type": a}), document(direction, {"type": b})), "schema_type_changed")
    assert len(findings) == 1 and findings[0]["severity"] == severity


@pytest.mark.parametrize("direction", ["request", "response"])
def test_finite_enum_prevents_false_numeric_type_break(direction):
    report = compare(document(direction, {"type": "integer", "enum": [1]}), document(direction, {"type": "number", "enum": [1.0]}))
    assert report["summary"]["breaking"] == 0
    assert rule(report, "schema_type_changed")[0]["severity"] == "informational"
    assert rule(report, f"{direction}_enum_changed") == []


def test_numeric_enum_equality_does_not_equate_booleans_and_numbers():
    old = document("request", {"type": "number", "enum": [1, 2]})
    new = document("request", {"type": "number", "enum": [2.0, 1.0]})
    assert compare(old, new)["findings"] == []
    new = document("request", {"type": "boolean", "enum": [True]})
    assert compare(old, new)["summary"]["breaking"] >= 1


def test_boolean_full_domain_does_not_become_a_fake_restriction():
    report = compare(document("request", {"type": "boolean"}), document("request", {"type": "boolean", "enum": [True, False]}))
    assert rule(report, "request_enum_changed")[0]["severity"] == "informational"
    assert report["summary"]["breaking"] == 0


@pytest.mark.parametrize("direction,severity", [("request", "breaking"), ("response", "informational")])
def test_new_required_property_is_directional(direction, severity):
    schema = {"type": "object", "properties": {"currency": {"type": "string"}}}
    old = document(direction, copy.deepcopy(schema))
    new = document(direction, {**schema, "required": ["currency"]})
    finding = rule(compare(old, new), f"{direction}_property_required")[0]
    assert finding["severity"] == severity
    assert finding["before"]["present"] is False
    assert finding["after"]["value"] == ["currency"]


@pytest.mark.parametrize("direction,severity", [("request", "informational"), ("response", "breaking")])
def test_required_property_relaxation_is_directional(direction, severity):
    schema = {"type": "object", "properties": {"id": {"type": "string"}}}
    old = document(direction, {**schema, "required": ["id"]})
    new = document(direction, schema)
    assert rule(compare(old, new), f"{direction}_required_relaxed")[0]["severity"] == severity


@pytest.mark.parametrize("required,severity", [(True, "breaking"), (False, "potentially_breaking")])
def test_removed_response_property(required, severity):
    schema = {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"] if required else []}
    report = compare(document("response", schema), document("response", {"type": "object"}))
    finding = rule(report, "property_removed")[0]
    assert finding["severity"] == severity
    assert finding["after"]["present"] is False
    assert rule(report, "response_required_relaxed") == []


@pytest.mark.parametrize("direction", ["request", "response"])
def test_optional_property_addition_is_informational_under_declared_field_policy(direction):
    old = document(direction, {"type": "object"})
    new = document(direction, {"type": "object", "properties": {"note": {"type": "string"}}})
    report = compare(old, new)
    assert rule(report, "property_added")[0]["severity"] == "informational"
    assert report["summary"]["breaking"] == 0


@pytest.mark.parametrize("required,severity", [(True, "breaking"), (False, "informational")])
def test_parameter_addition(required, severity):
    old, new = document(), document()
    new["paths"]["/items"]["post"]["parameters"] = [{"name": "limit", "in": "query", "required": required, "schema": {"type": "integer"}}]
    assert rule(compare(old, new), "parameter_added")[0]["severity"] == severity


def test_parameter_requirement_and_removal():
    old = document()
    old["paths"]["/items"]["post"]["parameters"] = [{"name": "limit", "in": "query", "schema": {"type": "integer"}}]
    new = copy.deepcopy(old)
    new["paths"]["/items"]["post"]["parameters"][0]["required"] = True
    assert rule(compare(old, new), "parameter_requirement_changed")[0]["severity"] == "breaking"
    new = document()
    assert rule(compare(old, new), "parameter_removed")[0]["severity"] == "potentially_breaking"


def test_header_names_are_case_insensitive_and_parameter_order_is_irrelevant():
    old = document()
    old["paths"]["/items"]["post"]["parameters"] = [{"name": "X-Trace", "in": "header", "schema": {"type": "string"}}, {"name": "limit", "in": "query", "schema": {"type": "integer"}}]
    new = copy.deepcopy(old)
    new["paths"]["/items"]["post"]["parameters"][0]["name"] = "x-trace"
    new["paths"]["/items"]["post"]["parameters"].reverse()
    assert compare(old, new)["findings"] == []


def test_required_body_addition_and_requirement_change():
    old, new = document(), document("request")
    assert rule(compare(old, new), "request_body_added")[0]["severity"] == "breaking"
    old = copy.deepcopy(new)
    old["paths"]["/items"]["post"]["requestBody"]["required"] = False
    assert rule(compare(old, new), "request_body_requirement_changed")[0]["severity"] == "breaking"


def test_renamed_component_is_not_a_type_change():
    old = document("response", {"$ref": "#/components/schemas/OldName"})
    old["components"] = {"schemas": {"OldName": {"type": "string"}}}
    new = document("response", {"$ref": "#/components/schemas/NewName"})
    new["components"] = {"schemas": {"NewName": {"type": "string"}}}
    assert compare(old, new)["findings"] == []


def test_template_parameter_rename_is_review_not_removed_operation():
    old, new = document(), document()
    old["paths"]["/items/{id}"] = old["paths"].pop("/items")
    new["paths"]["/items/{item_id}"] = new["paths"].pop("/items")
    for value, name in ((old, "id"), (new, "item_id")):
        next(iter(value["paths"].values()))["post"]["parameters"] = [{"name": name, "in": "path", "required": True, "schema": {"type": "string"}}]
    report = compare(old, new)
    assert report["summary"]["breaking"] == 0
    assert rule(report, "path_template_changed")[0]["severity"] == "needs_review"


def test_unknown_composition_downgrades_changed_required_list():
    old = document("request", {"type": "object", "allOf": [{"required": ["id"]}], "properties": {"id": {"type": "string"}}})
    new = copy.deepcopy(old)
    schema_at(new, "request")["required"] = ["id"]
    report = compare(old, new)
    finding = rule(report, "request_property_required")[0]
    assert finding["policy_severity"] == "breaking" and finding["severity"] == "needs_review"
    assert finding["coverage_warning_ids"]["old"]
    assert report["verdict"] == "review_required"


def test_unchanged_unsupported_input_has_no_change_but_requires_review():
    value = document("response", {"oneOf": [{"type": "string"}, {"type": "integer"}]})
    report = compare(value, value)
    assert report["findings"] == []
    assert report["coverage"]["status"] == "partial"
    assert report["verdict"] == "review_required"


def test_missing_schema_returns_review_and_resolvable_absence_evidence():
    old = document()
    del old["paths"]["/items"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    report = compare(old, document())
    finding = rule(report, "schema_declaration_changed")[0]
    assert finding["before"]["present"] is False
    assert finding["severity"] == "needs_review"


def test_nested_array_schema_change_is_found():
    old = document("request", {"type": "array", "items": {"type": "object", "properties": {"count": {"type": "number"}}}})
    new = copy.deepcopy(old)
    schema_at(new, "request")["items"]["properties"]["count"]["type"] = "integer"
    finding = rule(compare(old, new), "schema_type_changed")[0]
    assert finding["severity"] == "breaking"
    assert finding["location"][-3:] == ["items", "properties", "count"]


def test_empty_enum_domain_is_not_a_false_supported_result():
    old = document("request", {"type": "string", "enum": [1]})
    new = document("request", {"type": "string", "enum": ["x"]})
    report = compare(old, new)
    assert report["coverage"]["status"] == "partial"
    assert any(g["code"] == "empty_enum_domain" for g in report["coverage"]["analysis_warnings"])


def test_schema_dialect_change_cannot_silently_pass():
    old, new = document(), document()
    old["openapi"] = "3.0.3"
    report = compare(old, new)
    assert report["findings"] == []
    assert report["verdict"] == "review_required"


def test_wildcard_media_and_default_status_coverage_are_explicit():
    old, new = document(), document()
    for value in (old, new):
        content = value["paths"]["/items"]["post"]["responses"]["200"]["content"]
        content["*/*"] = content.pop("application/json")
    report = compare(old, new)
    assert any(g["code"] == "media_matching_not_analyzed" for g in report["coverage"]["analysis_warnings"])
    old, new = document(), document()
    for value in (old, new):
        responses = value["paths"]["/items"]["post"]["responses"]
        responses["default"] = responses.pop("200")
    report = compare(old, new)
    assert any(g["code"] == "response_status_matching_not_analyzed" for g in report["coverage"]["analysis_warnings"])


def test_response_status_changes_are_not_request_restrictions():
    old, new = document(), document()
    responses = new["paths"]["/items"]["post"]["responses"]
    responses["201"] = responses.pop("200")
    report = compare(old, new)
    assert rule(report, "response_status_removed")[0]["severity"] == "informational"
    assert rule(report, "response_status_added")[0]["severity"] == "potentially_breaking"


def test_stable_ids_survive_key_enum_and_required_order_changes():
    old = document("request", {"type": "object", "properties": {"id": {"type": "string"}, "code": {"type": "string", "enum": ["a", "b"]}}})
    new = copy.deepcopy(old)
    schema_at(new, "request")["required"] = ["id", "code"]
    schema_at(new, "request")["properties"]["code"]["enum"] = ["a"]
    first = compare(old, new)
    schema_at(old, "request")["properties"]["code"]["enum"].reverse()
    schema_at(new, "request")["required"].reverse()
    second = compare(json.loads(json.dumps(old, sort_keys=True)), json.loads(json.dumps(new, sort_keys=True)))
    assert [f["id"] for f in first["findings"]] == [f["id"] for f in second["findings"]]


def test_precision_losing_decimals_are_explicitly_rejected():
    for raw in (b'{"openapi":"3.1.0","x":0.123456789012345678901}', b'{"openapi":"3.1.0","x":1e-999}'):
        with pytest.raises(SpecError) as captured:
            parse_document(raw)
        assert captured.value.detail["code"] == "unsupported_numeric_precision"


def test_large_numeric_domains_do_not_depend_on_decimal_context_precision():
    number = 10 ** 100
    assert accepts("integer", number)
    a = {"type": "integer", "enum": [number]}
    b = {"type": "number", "enum": [float("1e100")]}
    assert subset(a, b) and subset(b, a)


def test_comparison_budgets_raise_instead_of_truncating(monkeypatch):
    import auditor.comparison as module
    old = document("request", {"type": "object"})
    new = document("request", {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "string"}}})
    monkeypatch.setattr(module, "MAX_FINDINGS", 1)
    with pytest.raises(SpecError, match="finding"):
        compare(old, new)


def test_unsupported_constraint_cannot_turn_a_partial_widening_into_a_compatible_claim():
    old = document("request", {"type": "string", "enum": ["abc"]})
    new = document("request", {"type": "string", "enum": ["abc", "x"], "maxLength": 1})
    finding = rule(compare(old, new), "request_enum_changed")[0]
    assert finding["policy_severity"] == "informational"
    assert finding["severity"] == "needs_review"


def test_required_but_undeclared_property_gaining_a_type_needs_review():
    old = document("request", {"type": "object", "required": ["id"]})
    new = document("request", {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}})
    assert rule(compare(old, new), "property_added")[0]["severity"] == "needs_review"


def test_changed_media_types_and_case_normalization():
    old, new = document("request"), document("request")
    content = new["paths"]["/items"]["post"]["requestBody"]["content"]
    content["Application/JSON"] = content.pop("application/json")
    assert compare(old, new)["findings"] == []
    content["text/plain"] = content.pop("Application/JSON")
    report = compare(old, new)
    assert rule(report, "media_type_removed")[0]["severity"] == "breaking"
    assert rule(report, "media_type_added")[0]["severity"] == "informational"


def test_changed_response_media_addition_is_potentially_breaking():
    old, new = document(), document()
    content = new["paths"]["/items"]["post"]["responses"]["200"]["content"]
    content["text/plain"] = {"schema": {"type": "string"}}
    assert rule(compare(old, new), "media_type_added")[0]["severity"] == "potentially_breaking"


def test_recursive_schema_change_stays_bounded_and_requires_review():
    old = document("response", {"$ref": "#/components/schemas/Node"})
    old["components"] = {"schemas": {"Node": {"type": "object", "properties": {"next": {"$ref": "#/components/schemas/Node"}, "name": {"type": "string"}}}}}
    new = copy.deepcopy(old)
    new["components"]["schemas"]["Node"]["properties"]["name"]["type"] = "integer"
    report = compare(old, new)
    assert rule(report, "schema_type_changed")[0]["severity"] == "needs_review"
    assert report["verdict"] == "review_required"


def test_comparison_is_pure_and_does_not_mutate_original_documents():
    old, new = document("request"), document("request", {"type": "integer"})
    snapshots = copy.deepcopy((old, new))
    compare(old, new)
    assert (old, new) == snapshots
