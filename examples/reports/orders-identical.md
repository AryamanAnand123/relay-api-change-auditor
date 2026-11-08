# API Change Impact Auditor report

Deterministic declared-contract findings. This is not a full compatibility certification.

## Saved comparison

```json
{"example_only":true,"export_schema_version":"1","id":"public-example-identical","status":"completed","storage":"Generated offline; not a saved user comparison"}
```

## Policy assumptions

```json
["Old callers use declared request fields; undocumented extra request values are outside this policy.","Clients accept additional response properties but rely on declared types and required fields.","Response enums are treated as exhaustive client expectations.","Findings describe declared contracts, not observed server behavior or a proof of full schema subsumption."]
```

## Summary

```json
{"counts":{"breaking":0,"informational":0,"needs_review":0,"potentially_breaking":0,"total_findings":0},"verdict":"no_breaking_changes_detected_in_supported_subset"}
```

## Coverage

```json
{"analysis_warnings":[],"full_compatibility_analysis":false,"input_warnings":{"new":[],"old":[]},"status":"supported_subset"}
```

## Findings

No findings in the implemented subset; review the coverage limitations above.

