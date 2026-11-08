# Section 6 review: evaluation and reliability

Section 6 evaluates the existing project and fixes two observed reliability issues. The workspace remains at **http://127.0.0.1:8010/**, now version **0.6.0**. No packages, models, hosting, or paid resources were added. The existing 66 Python dependencies and frontend lock remain in use.

## Deterministic results

The [frozen corpus](../evaluation/corpus.json) has 90 original parcel API cases, distinct from development orders examples. Expectations were authored from the documented policy rather than generated from predictions. This is an internal additional-evaluation set, not an independent or blind benchmark.

| Check | Recorded result |
| --- | --- |
| Exact case outcomes | 90/90 pass: 76 comparisons, 14 rejections |
| Supported rule coverage | All 23 rules represented in expected findings |
| Exact finding matches | 56 true positives, 0 false positives, 0 false negatives |
| Compatible controls | 26 cases; 0 breaking false-positive cases |
| Partial coverage | 13 cases preserve explicit review/coverage limits |
| Evidence | 112 before/after sides resolve correctly or prove absence |
| Reproducibility | Repeated results and semantic reports after formatting/key-order changes stay stable |

Precision and recall are 1.0 **on the exact labelled finding signatures in this corpus**. They do not measure arbitrary OpenAPI compatibility. Signatures include rule, both severity fields, direction, logical location, method, and path; wrong severity or location counts as both a missed expectation and an unexpected prediction. Empty denominators are reported as null, not perfect scores. Source checks distinguish missing values from JSON null and booleans from numeric values.

The corpus is pinned at SHA-256 `7f2eb935e58d042484bd70d11a39745262a172f21487e41c85255f5ebd781665`. Scoring refuses modified fixture bytes. See [full per-rule results](section-6-deterministic.json) and [evaluation methodology](../evaluation/README.md).

## Preserved baseline and validation fix

The initial corpus had one incorrect interpretation: slash/tilde component names were labelled valid. The [OpenAPI Components rule](https://spec.openapis.org/oas/v3.1.0.html#components-object) forbids those characters. The original 88-case corpus and 87/88 result were retained. The documented v2 revision corrects two invalid-name labels and adds two valid escaped-property-reference cases.

Before changing the engine, the corrected-label corpus passed 89/90: the dependency's OpenAPI 3.0 validator accepted an invalid component name that its 3.1 validator rejected. Explicit fixed-map key validation now enforces the same rule for both supported families. Component vendor extensions remain allowed; escaped property names and valid JSON Pointers still work. Engine version is **1.0.1**; rule policy remains **declared-client-v1**. Existing saved reports retain their recorded engine version and content.

Evidence is preserved in [original baseline](section-6-baseline.json), [corrected-label baseline](section-6-corrected-labels-baseline.json), and [archived v1 corpus](../evaluation/archive/parcel-v1/corpus.json). No baseline failures or changed labels were silently removed.

## Latency and failure handling

In-process scoring used three repeats per comparison: 228 timing samples, with p50 about **6.2 ms** and p95 **11.2 ms**. The cold maximum was about **754 ms**; first-use samples were not discarded. These timings exclude subprocess startup, HTTP, persistence, and AI.

Twelve actual production-worker measurements included startup, serialization, pipes, validation, normalization, and comparison/rejection. Their p50 was about **749 ms**, p95/max **928 ms** on this machine. This is a small local workload measurement, not a production SLA or a load test.

The worker check also exercised actual 2 MiB file, 20,000-node, 300-operation, and 500-finding limits. Each failed explicitly rather than returning a truncated successful report. An actual cancelled worker was killed and reaped, and a following comparison succeeded. No database or provider calls were made by these checks. See [worker/resource report](section-6-reliability.json).

A new regression found that Groq's SDK wraps transport timeouts as `APITimeoutError`, which previously appeared as general provider unavailability. That case now returns the specific bounded 504 `ai_timeout` response, without exposing transport text or retrying. Cancellation also releases AI admission, counts the attempted call, leaves cache empty, and preserves the authoritative result. Existing tests continue to cover upload timeout/admission, atomic history quotas, commit rollback, restart persistence, deletion, and model failure states.

## AI evaluation: separate from rule accuracy

The six selected AI cases and [evidence-fidelity rubric](../evaluation/ai-rubric.json) were frozen before generation. Groq received only original synthetic inputs through the existing LangChain workflow. Each case got one attempt with spacing; the prompt/model were not tuned after reviewing this run.

| Case | First attempt | Agent review against the frozen rubric |
| --- | --- | --- |
| Request enum narrowed | Generated | Partially grounded: runtime acceptance/rejection assumptions |
| Required response property removed | Generated | Grounded, with runtime/replacement caveats |
| Integer-to-number change inside an array | Generated | Partially grounded: inferred units and runtime examples |
| Operation removed | Rejected by output validation | Not generated; retained in the denominator |
| Nested request field becomes required | Generated | Partially grounded: non-null and runtime assumptions |
| Instruction-like field name and malicious description | Generated | Task preserved; partially grounded runtime test assumptions |

Five of six attempts produced accepted structured guidance. All five generated summaries identified the core change correctly. Agent review rated **1 grounded, 4 partially grounded, 1 not generated** across all six attempts. This is a transparent qualitative assessment by the coding agent, not independent expert review or a general model accuracy estimate.

All six authoritative reports remained unchanged. In the one adversarial case, malicious descriptions were excluded and the instruction-like field name remained literal contract data; the model did not mark all changes compatible. That observation does not prove resistance to arbitrary prompt injection. No tools, URL retrieval, or generated patch execution were enabled.

Successful generation latency ranged from **2.2 to 4.2 seconds**, with p50 about **2.4 seconds**. The failed attempt's duration was not captured in this first run. The evaluator now captures success/failure wall latency for future runs; the original report was preserved and the case was not retried to improve its score. See [raw outputs/failure](section-6-ai.json), [manual review](section-6-ai-review.json), and [validated combined summary](section-6-summary.json).

AI remains advisory. Suggestions can assume details absent from the bounded context, even when JSON and references validate. The displayed notice now calls out missing-schema and runtime assumptions explicitly. Check proposed values, parsing rules, and expected responses against the full contract and actual service. There is no AI factual-accuracy claim.

## Verification and review checkpoint

The full backend suite passes **363 tests**. The new coverage includes 90 frozen cases, evaluation checksum/metric/lineage checks, consistent component-name rejection, the SDK timeout fix, and cancellation behavior. The real loopback API passed [10 Section 6 checks](section-6-live.json), including valid escaped references, invalid component names in both families, partial coverage, and unchanged history/AI call counters.

The frontend build succeeds. Browser regression results are recorded in the final [Section 6 check report](section-6-checks.json). No saved history was created or deleted by the evaluation/HTTP checks; the six AI evaluations ran in memory. Credentials remain outside source and reports. No new dependency or model downloads were needed.

Reproduction commands are in the [evaluation guide](../evaluation/README.md) and [README](../README.md). Each real AI rerun must be explicitly requested and uses provider quota; ordinary regression tests use synthetic providers.

Pause here for review. Section 7 will prepare the portfolio documentation, demo, resume material, and a concrete hosting/publication decision. This section did not publish or deploy the project.
