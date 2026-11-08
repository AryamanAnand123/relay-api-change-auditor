# Section 1: offline input validation and normalized specification model

This section adds `POST /api/specifications/validate` to runtime version `0.1.0`. Upload multipart fields `old` and `new`, each containing a `.json` file. It validates both specifications and returns their normalized graphs. No compatibility comparison, persistence, AI, or browser interface is implemented in this section. Development remains on loopback port 8010, separate from Cedar.

## Input and reference policy

- Accept UTF-8 JSON OpenAPI 3.0.x and 3.1.x documents. Swagger 2, OpenAPI 3.2, YAML, malformed JSON, duplicate keys, non-finite numbers, invalid Unicode scalars, and non-object roots are rejected explicitly.
- Use `openapi-spec-validator` 0.9.0 for structure/schema validation, selecting its 3.0 or 3.1 validator explicitly. A JSON object is not accepted solely because its syntax parses.
- Support same-document JSON Pointer references, with correct tilde, slash, percent, array-index, and Unicode handling. Preserve canonical URI-fragment pointers as graph/evidence identifiers. Shared schemas are normalized once; references remain graph edges instead of expanding copies.
- Resolve pointers before semantic validation and reject missing targets and inappropriate scalar targets. External URLs, relative-file references, file URLs, and named anchors receive explicit unsupported-reference errors. Custom schema IDs/anchors/dynamic references and custom dialects receive policy errors rather than an assertion that every such document is invalid OpenAPI.
- Supply an empty reference-handler mapping to the validator's SchemaPath; defaults would permit URL/file retrieval. The validator receives a bounded copy with canonical equivalent pointers so encoded leading slashes are resolved correctly; original inputs and their hashes are not mutated. The disposable worker also disables Python socket connection methods. Known packaged validator schemas remain local library resources. No uploaded-reference URL is fetched or executed.
- Literal examples/defaults/enum values and vendor-extension payloads are not treated as executable reference instructions. A property called `example` remains a real schema property; an Example Object's `$ref` is still checked. Descriptions are inert input and are omitted from the normalized schema facts.

The reference/dialect restrictions are deliberately narrower than the full OpenAPI standard. A policy rejection is not evidence that a document is universally invalid.

## Resource boundaries

| Resource | Initial limit |
| --- | --- |
| File bytes | 2 MiB each |
| Total multipart request | 4 MiB + 64 KiB overhead |
| Upload fields | Exactly two files, named old and new; no text fields |
| JSON container nesting | 64 |
| Input tree nodes | 20000 per file, counting object keys and values |
| Structural references | 1000 per file |
| Normalized schema nodes | 2000 per file |
| Schema/reference traversal depth | 64 |
| Operations | 300 per file |
| Coverage warnings | 200 per file; over-limit is an error, not silent truncation |
| Body receive time | 10 seconds |
| Pair worker time | 10 seconds, including process startup |
| Serialized worker output | 8 MiB |
| Active upload/validation requests | One per API process; extra requests receive 429 |

The outer upload boundary counts actual bytes even without Content-Length or with a false smaller header, before multipart parsing. Compressed request bodies are unsupported. The bounded multipart files remain in memory rather than spilling private specifications to the shared temporary directory. Tests check a full-size 2 MiB file without rollover. Files and forms are closed after use; this section does not save originals or normalized reports on the server. Python bytecode caches are ordinary ignored source artifacts, not retained uploads.

Validation/normalization run in a disposable subprocess; a timeout kills and reaps it. The API remains responsive during that work. This is a time/failure boundary, not an OS sandbox or a claim of a hard RSS memory limit. There is no uploaded-code execution. Local development uses one API process, and public multi-user deployment remains deferred.

Cross-origin browser uploads are rejected; same-origin local requests and non-browser local clients are supported. No model, account session, or AI-provider key is involved. Untrusted Hosts are rejected before upload work. Application logs contain no uploaded bodies or returned normalized reports. Errors use stable codes/messages and bounded source pointers instead of copying validator exception messages that can embed input values.

## Normalized model and coverage

Each side returns:

- Normalizer version, exact input-byte SHA-256, OpenAPI version, title, and API version.
- Operations keyed by path/method, with source pointers, effective parameters, request-body requirements/content, and response statuses/media.
- Reusable schema graph nodes containing source pointers, reference edges, explicit types, required fields, simple scalar enums, properties, and array items.
- Stable coverage-warning IDs, locations, and explicit unsupported-keyword lists. Warnings follow referenced schema/parameter/body/response origins into affected operation coverage. Warning attachment is conservative and may cover multiple operations sharing a path item.
- Coverage status `supported_subset` or `partial`, warning/operation counts, and `full_compatibility_analysis: false` in all cases.

Path parameters are inherited, with operation parameters overriding by `(in, name)`. HTTP operations are identified by path/method rather than operationId. Schemas are not silently merged across `$ref` siblings: 3.0 and 3.1 have different sibling semantics, so unresolved compatibility semantics are flagged for review.

Composition (`allOf`, `anyOf`, `oneOf`), recursive schemas, union/boolean/untyped schemas, object/array enum values, constraints such as patterns/bounds/formats, read/write annotations, serialization settings, authentication, server URLs, callbacks/webhooks, and response metadata receive coverage warnings where encountered in analyzed structures. Complex unsupported subschemas are not recursively interpreted as if their semantics were supported. Unused reusable non-schema components are still structurally validated, but do not constitute analyzed operations. Documents with no normalized operations receive a warning. Full schema subsumption, actual server behavior, and caller-code compatibility are not established.

## Responses and reproduction

From the project root, with the server running:

```powershell
curl.exe -sS -F "old=@examples/orders-v1.json;type=application/json" -F "new=@examples/orders-v2-breaking.json;type=application/json" http://127.0.0.1:8010/api/specifications/validate
.\.venv\Scripts\python.exe scripts\check-specifications.py
```

Successful result: `status: validated`, `comparison_performed: false`, old operations = 2, new operations = 1. The existing examples contain intended breaking changes, but those findings belong to Section 2. No result here says an upgrade is safe.

Failure statuses: 400 for an invalid length header, 403 for rejected origin, 408 for a slow upload, 413 for size limits, 415 for unsupported request encoding/media type, 422 for malformed/unsupported input or exceeded analysis workload, 429 while another pair is active, and 503 for worker/service failures. If either file fails, no partial-success pair is returned. No persistence or half-saved comparison exists to clean up.

## Dependencies and verification

Section 1 adds 14 wheel packages, including `openapi-spec-validator` 0.9.0, `python-multipart` 0.0.33, jsonschema, referencing, and jsonschema-path. PyYAML is a transitive validator dependency, but the endpoint still parses JSON only. All 25 original package versions are unchanged. [Section 1 download report](section-1-downloads.json) retains official HTTPS artifact URLs and SHA-256 hashes; the cumulative [backend lock](../backend/requirements.lock.txt) pins 39 packages for Windows x64 / CPython 3.12. The original Section 0 lock/report/checks remain available.

The test suite covers JSON/Unicode/numeric failures, schema validation, reference escapes and scope, cyclic/shared references, bounded graphs, partial coverage, inherited parameters, before/after evidence pointers, exact upload fields, max-size in-memory files, actual-byte/chunked limits, cross-origin rejection, busy admission, slow bodies, malformed workers, and timeout kill/reap behavior. Real subprocess tests require Windows named-pipe permissions in the managed Codex environment.

The [live checker report](section-1-live.json) records 14 actual loopback HTTP checks using synthetic inputs: both version families, original pair, malformed/duplicate/invalid documents, unsupported version, HTTPS/file references, an encoded reference fragment, composition/recursion warnings, oversized file, chunked multipart, and cross-origin rejection. These are implementation checks, not model evaluation or a security certification. No AI or paid service was used.

Final verification: **88 tests passed** with no warnings, including actual disposable worker processes. The cumulative lockfile dry-run with `--require-hashes` passed; `pip check` reports no broken requirements. Python compilation, publishable-file whitespace, relative documentation links, and common secret-pattern checks passed. All 25 Section 0 package versions remain unchanged. No new GitHub remote, commit, or deployment was created. The running backend reports section 1 / version 0.1.0 and work pauses here for review.

## Next section

After review, Section 2 consumes this normalized model to produce deterministic compatibility findings and before/after evidence under a documented direction-aware rule catalog. No Section 2 work is included here.

References: [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0.html), [validator Python API](https://python-openapi.org/openapi-spec-validator/docs/latest/python.html), and [JSON Schema reference registries](https://github.com/python-jsonschema/jsonschema/blob/main/docs/referencing.rst).
