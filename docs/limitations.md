# Scope and known limitations

Relay reviews **declared contracts under an explicit client policy**. It does not prove complete JSON Schema inclusion or observe a running API. It does not inspect client repositories, find every affected caller, execute patches, or review arbitrary code/security bugs.

| Area | Current behavior |
| --- | --- |
| Inputs | OpenAPI 3.0.x/3.1.x UTF-8 JSON, up to 2 MiB/file. No YAML, Swagger 2, URL import, or external references. |
| Rules | 23 implemented rules for supported operations, parameters, body/media/status declarations, scalar types/enums, and object requirements/properties. |
| Coverage | Composition, recursive semantics, complex dialects/constraints, authentication/server behavior, and ambiguous matching remain explicit review gaps. |
| Evidence | JSON Pointers and before/after values identify source declarations. A logical finding ID is stable across formatting, but is not a content hash of all evidence. |
| AI | Optional advisory migration prose for supported saved findings. Valid JSON/references do not establish factual grounding; schema and runtime assumptions occurred in evaluation. |
| Storage | Single-user unencrypted SQLite, outside source/OneDrive. No account isolation, automatic expiry, encrypted database, or cloud durability guarantee. |
| Runtime | One loopback API process and bounded offline workers. Local request/AI counters are not distributed abuse prevention or billing controls. |
| Hosting | Full application verified locally on Windows x64/Python 3.12. No public backend deployment; Linux locks and public access/storage controls remain separate work. |

The declared-client policy assumes old callers use declared request fields and tolerate additional response properties, while depending on declared required fields/types and exhaustive response enums. A zero-breaking result only means no breaking change was found in the supported subset under those assumptions. It is not universal upgrade approval.

The internal frozen evaluation matched 56 expected findings across 90 cases and all 23 rules. This authored corpus is not an external or blind benchmark. The first baseline and a specification-grounded label correction are retained. Do not generalize its precision/recall to all APIs.

The six-case AI evaluation accepted five structured outputs and rejected one. All generated core summaries identified the change, but agent review rated only one fully grounded and four partially grounded because of additional assumptions. It was not independently expert-graded. Read [the full evidence and rubric](section-6-review.md).

Deletion removes the active saved snapshot and explanation cache entries. It cannot remove exported files, operating-system backups, screenshots, or copies already shared. Git ignore rules do not prevent OneDrive from syncing source, and the local provider key is protected by folder access control rather than encryption.

See [comparison policy](comparison-policy.md), [architecture](architecture.md), and [hosting decision](hosting-decision.md).
