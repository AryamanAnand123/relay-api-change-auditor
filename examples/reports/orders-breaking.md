# API Change Impact Auditor report

Deterministic declared-contract findings. This is not a full compatibility certification.

## Saved comparison

```json
{"example_only":true,"export_schema_version":"1","id":"public-example-breaking","status":"completed","storage":"Generated offline; not a saved user comparison"}
```

## Policy assumptions

```json
["Old callers use declared request fields; undocumented extra request values are outside this policy.","Clients accept additional response properties but rely on declared types and required fields.","Response enums are treated as exhaustive client expectations.","Findings describe declared contracts, not observed server behavior or a proof of full schema subsumption."]
```

## Summary

```json
{"counts":{"breaking":3,"informational":0,"needs_review":0,"potentially_breaking":0,"total_findings":3},"verdict":"breaking_changes_detected"}
```

## Coverage

```json
{"analysis_warnings":[],"full_compatibility_analysis":false,"input_warnings":{"new":[],"old":[]},"status":"supported_subset"}
```

## Findings

### Finding 1

```json
{"after":{"pointer":"#/paths/~1orders/post/requestBody/content/application~1json/schema/required","present":true,"value":["item","currency"]},"before":{"pointer":"#/paths/~1orders/post/requestBody/content/application~1json/schema/required","present":true,"value":["item"]},"coverage_warning_ids":{"new":[],"old":[]},"direction":"request","id":"change-e2e02b141b81927f23da","location":["requestBody","content","application/json","properties","currency"],"method":"POST","path":"/orders","policy_severity":"breaking","rule_id":"request_property_required","severity":"breaking","title":"Property added to the required list"}
```

### Finding 2

```json
{"after":{"pointer":"#/components/schemas/Order/properties/price/type","present":true,"value":"object"},"before":{"pointer":"#/components/schemas/Order/properties/price/type","present":true,"value":"number"},"coverage_warning_ids":{"new":[],"old":[]},"direction":"response","id":"change-6b657224667a8f1c4d09","location":["responses","201","content","application/json","properties","price"],"method":"POST","path":"/orders","policy_severity":"breaking","rule_id":"schema_type_changed","severity":"breaking","title":"Declared schema type changed"}
```

### Finding 3

```json
{"after":{"context_pointer":"#/paths","expected_pointer":"#/paths/~1orders~1%7Border_id%7D/get","pointer":null,"present":false,"value":null},"before":{"pointer":"#/paths/~1orders~1%7Border_id%7D/get","present":true,"value":{"parameters":[{"in":"path","name":"order_id","required":true,"schema":{"type":"string"}}],"responses":{"200":{"content":{"application/json":{"schema":{"$ref":"#/components/schemas/Order"}}},"description":"An order"}}}},"coverage_warning_ids":{"new":[],"old":[]},"direction":"operation","id":"change-1bd47c92219e4e195c3e","location":[],"method":"GET","path":"/orders/{order_id}","policy_severity":"breaking","rule_id":"operation_removed","severity":"breaking","title":"HTTP operation removed"}
```

