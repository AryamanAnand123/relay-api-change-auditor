# Comparison policy: declared-client-v1

Engine: `1.0.1`. This is a deterministic declared-contract auditor, not a proof that arbitrary old/new JSON Schemas have a subset relationship and not an observation of a running server. Neither specification's `servers` URLs are called. The patch release consistently rejects invalid component names in both OpenAPI families; rule policy remains `declared-client-v1`.

## Consumer assumptions and severity

Assume old callers use declared request fields, including required names, and do not rely on undocumented extra input fields. Assume clients tolerate additional response properties but rely on declared property types, required fields, and exhaustive response enums. Header parameter names and literal media type names are compared case-insensitively. Operation identity is exact path plus HTTP method; component names and operationId are not operation identity.

The extra-input assumption matters: JSON Schema normally allows undeclared object properties unless constrained otherwise. Adding an optional request property can restrict a previously permitted extra value. This policy treats ordinary optional additions as informational for callers using the old declared fields; it does not assert general request-schema inclusion. A previously required but untyped name gaining a schema receives review instead of an unconditional compatibility claim. Likewise, strict clients rejecting all additional response properties are outside the policy assumptions.

- `breaking`: a supported declared-contract incompatibility under these assumptions.
- `potentially_breaking`: impact depends on client/runtime behavior not established by the declarations.
- `informational`: an additive/relaxing or descriptive change under the stated policy; not a blanket upgrade approval.
- `needs_review`: interpretation is unsupported, ambiguous, or affected by coverage uncertainty.

Every finding retains `policy_severity`. When an affected operation has unsupported semantics, changed schema/input-requirement findings become `needs_review`, including apparent informational widenings. A new unsupported constraint could negate an apparent widening. Operation removal remains a declared route-removal finding regardless of unrelated schema warnings. Missing analysis is never converted into a successful full-compatibility claim.

## Rule catalog

| Rule ID | Supported interpretation |
| --- | --- |
| `operation_removed` | Removed exact path/method is breaking. |
| `operation_added` | Added exact path/method is informational. |
| `path_template_changed` | Matching template structure with changed parameter names needs review; no automatic route-equivalence or removed-operation claim. Inner changes on that unmatched route require manual review. |
| `parameter_added` | New required request parameter is breaking; optional is informational. |
| `parameter_removed` | Removal is potentially breaking; actual rejection or ignored-input behavior is unknown. |
| `parameter_requirement_changed` | Becoming required is breaking; becoming optional is informational. |
| `request_body_added` | New required body is breaking; optional is informational. |
| `request_body_removed` | Potentially breaking because runtime handling of old bodies is unknown. |
| `request_body_requirement_changed` | Becoming mandatory is breaking; becoming optional is informational. |
| `media_type_removed` | Loss of a supported literal request/response representation is breaking for clients using it. |
| `media_type_added` | Request expansion is informational; a new possible response representation is potentially breaking. |
| `response_status_removed` | Removing a possible exact response outcome is informational for clients able to consume the old outcomes. |
| `response_status_added` | New exact response outcome is potentially breaking; status handling is client-dependent. |
| `schema_declaration_changed` | Added/removed schema declaration needs review rather than guessing what an undeclared schema guaranteed. |
| `schema_type_changed` | Request integer-to-number is a widening; response integer-to-number weakens a guarantee. Reverse directions invert that judgment. Other supported type differences use the scalar/type domain rule, with enum constraints considered together. |
| `request_enum_changed` | Excluding old allowed scalar values is breaking; widening is informational. |
| `response_enum_changed` | Permitting new scalar values outside old expectations is breaking; narrowing is informational. |
| `request_property_required` | New required name is breaking, including a name not listed in properties. |
| `response_property_required` | Adding a required response name strengthens a guarantee and is informational. |
| `request_required_relaxed` | Relaxing a request requirement is informational. |
| `response_required_relaxed` | Removing a required response guarantee is breaking. |
| `property_removed` | Required response property removal is breaking; optional response and request property removals are potentially breaking. |
| `property_added` | Ordinary additions are informational, except a previously required but undeclared request name gaining a constraint, which needs review. |

For a removed required response property, one removed-property finding captures the lost guarantee; a duplicate required-list-relaxation finding is suppressed. Nested object properties and homogeneous array items are traversed. Missing/recursive/unsupported schemas remain explicit coverage gaps.

Enums compare JSON values, not Python's boolean/number equality: `true` differs from `1`, while JSON numeric `1` and `1.0` compare equally. Scalar finite enums are filtered through their declared type and considered when classifying type changes. For example, integer enum `[1]` becoming number enum `[1]` does not imply the server can suddenly emit arbitrary fractions. Boolean/null intrinsic domains are finite. Empty effective enum domains trigger manual-review coverage, including when reached through another schema.

The parser now rejects decimals whose significant digits would be lost during float conversion, using `unsupported_numeric_precision`. This avoids quietly comparing rounded enum evidence. It is an analyzer input-policy restriction, not a claim that such numbers are invalid JSON. Non-finite numbers and unpaired Unicode remain rejected as before.

## Coverage, identifiers, and evidence

Each report includes engine/policy versions, explicit policy assumptions, exact input hashes, counts, findings, and old/new input warnings plus additional analysis warnings. Findings use deterministic IDs derived from policy, rule, operation identity, direction, and logical location. IDs remain stable across formatting/key/required-list/enum-order changes. They identify the logical change, not a content-addressed immutable finding; changed evidence can reuse the same logical ID across runs. Input hashes and stored evidence identify the specific run.

Concrete `before`/`after` evidence has `present: true`, a resolvable source pointer, and the actual JSON value. Missing evidence has `present: false`, a null pointer/value, the expected missing pointer, and a resolvable context pointer. A literal JSON null remains `present: true`. Some parameter findings cite a source parameter collection on one side and a parameter object on the other because effective parameters may be inherited. References point to their original resolved definitions rather than invented expanded documents.

Wildcards/parameters/ambiguous case aliases in media maps, default/range response precedence, ambiguous case-insensitive header definitions, schema-family changes between OpenAPI 3.0/3.1, recursive pairs, missing/union/boolean/untyped schemas, and empty typed enum domains require review. Section 1's composition, serialization, read/write, authentication/server, and other unsupported-constraint warnings remain attached. Header-name collisions cause that operation's comparison to be skipped with an explicit gap; no effective parameter is silently chosen.

Verdicts are `breaking_changes_detected`, `review_required`, or `no_breaking_changes_detected_in_supported_subset`. The latter is deliberately limited to this policy and implemented rules. `full_compatibility_analysis` is always false. A report can contain both known breaking changes and incomplete coverage.

Limits: 500 findings, 10000 compared schema pairs, 64 traversal depth, and 500 additional analysis gaps, within the existing 10-second pair-worker and 8 MiB output budgets. Crossing a limit fails the request explicitly; reports are not silently truncated. No caller-code tracing, business-logic inference, advanced JSON Schema subsumption, or general security review is performed.

Reference semantics: [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0.html), [JSON Schema object properties and required fields](https://json-schema.org/understanding-json-schema/reference/object), and [schema composition](https://json-schema.org/understanding-json-schema/reference/combining). The specific severities above are this project's documented client policy, not a severity taxonomy prescribed by those standards.
