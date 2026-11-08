# API Change Impact Auditor report

Deterministic declared-contract findings. This is not a full compatibility certification.

## Saved comparison

```json
{"example_only":true,"export_schema_version":"1","id":"public-example-additive","status":"completed","storage":"Generated offline; not a saved user comparison"}
```

## Policy assumptions

```json
["Old callers use declared request fields; undocumented extra request values are outside this policy.","Clients accept additional response properties but rely on declared types and required fields.","Response enums are treated as exhaustive client expectations.","Findings describe declared contracts, not observed server behavior or a proof of full schema subsumption."]
```

## Summary

```json
{"counts":{"breaking":0,"informational":2,"needs_review":0,"potentially_breaking":0,"total_findings":2},"verdict":"no_breaking_changes_detected_in_supported_subset"}
```

## Coverage

```json
{"analysis_warnings":[],"full_compatibility_analysis":false,"input_warnings":{"new":[],"old":[]},"status":"supported_subset"}
```

## Findings

### Finding 1

```json
{"after":{"pointer":"#/paths/~1orders/post/requestBody/content/application~1json/schema/properties/note","present":true,"value":{"type":"string"}},"before":{"context_pointer":"#/paths/~1orders/post/requestBody/content/application~1json/schema/properties","expected_pointer":"#/paths/~1orders/post/requestBody/content/application~1json/schema/properties/note","pointer":null,"present":false,"value":null},"coverage_warning_ids":{"new":[],"old":[]},"direction":"request","id":"change-49323634943ba982d053","location":["requestBody","content","application/json","properties","note"],"method":"POST","path":"/orders","policy_severity":"informational","rule_id":"property_added","severity":"informational","title":"Declared property added"}
```

### Finding 2

```json
{"after":{"pointer":"#/paths/~1status/get","present":true,"value":{"responses":{"204":{"description":"No content"}}}},"before":{"context_pointer":"#/paths","expected_pointer":"#/paths/~1status/get","pointer":null,"present":false,"value":null},"coverage_warning_ids":{"new":[],"old":[]},"direction":"operation","id":"change-c54f85668a1ddc4c9fb2","location":[],"method":"GET","path":"/status","policy_severity":"informational","rule_id":"operation_added","severity":"informational","title":"HTTP operation added"}
```

