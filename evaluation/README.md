# Frozen evaluation

These are original policy-authored parcel API fixtures, separate from the development orders examples and earlier unit-test fixtures. They are additional evaluation cases, not a blind or externally curated benchmark. All labels and supported severities refer to this project's `declared-client-v1` policy.

`corpus.json` contains **90 cases**: 76 comparisons and 14 expected input rejections. Comparison cases include 26 compatible controls, 13 partial-coverage cases, and expected findings across all 23 rules. Labels match rule, severity, policy severity, request/response direction, logical location, method, and path. The evaluator uses multisets, so duplicate or missing findings affect scores.

The [manifest](manifest.json) pins the corpus SHA-256. It also selects six AI cases, fixes one attempt per case, and specifies spacing. The [AI rubric](ai-rubric.json) was frozen before generation. Original inputs are synthetic; no private user specifications are included.

## Label correction and baseline preservation

The first 88-case corpus incorrectly labelled slash/tilde component names as valid. The OpenAPI Components key rule allows only letters, digits, dot, underscore, and hyphen. The 3.1 validator rejected the fixture; the 3.0 validator accepted it. The [specification](https://spec.openapis.org/oas/v3.1.0.html#components-object) resolved the label error independently of model predictions.

The [original corpus and manifest](archive/parcel-v1/corpus.json) and [87/88 baseline](../docs/section-6-baseline.json) remain preserved. Version 2 corrects both invalid-name labels and adds two valid escaped-property reference cases. Its checksum was frozen before rescoring or changing validation. The [corrected-label baseline](../docs/section-6-corrected-labels-baseline.json) passed 89/90 cases before the 3.0 validation fix. Engine 1.0.1 then passed all 90 with the same v2 checksum. No expected labels were changed to conceal a rule-engine error.

The first AI run remains intact, including its rejected output. The script now records wall latency on future failures too; this first run did not capture the failed attempt's duration. No retry was made to fill that missing sample or improve the first-attempt score.

## Reproduce

From the project root:

```powershell
.\.venv\Scripts\python.exe evaluation\evaluate.py --output docs\my-deterministic-run.json
.\.venv\Scripts\python.exe evaluation\check_reliability.py --output docs\my-worker-run.json
```

Neither command makes model calls or writes saved history. Deterministic timing covers in-process parse/validation/normalization/comparison. Worker timing includes subprocess startup and pipes. Both retain cold/first samples; timing is machine-specific. Resource checks launch only their own offline workers and explicitly verify cancellation reaping.

Real AI evaluation is opt-in and consumes free-provider quota:

```powershell
.\.venv\Scripts\python.exe evaluation\evaluate_ai.py --live-ai --output docs\my-ai-run.json
```

Configure the project Free-plan key first. Each selected case gets one attempt, with 22 seconds between cases. Failures remain in the report; there are no automatic retries. Outputs are not automatically graded for factual correctness. Review new outputs against the frozen rubric, retain their source hash, and distinguish a new run from the preserved first-attempt results.

`summarize.py` validates the retained first run's corpus/rubric/output lineage against its manual review, checks that no failed case was dropped, and writes a summary. Existing reports are protected from accidental overwrite; choose a new `--output`. `evaluate.py` also accepts explicit `--replace` for intentional local reruns. The authoring script refuses to overwrite the corpus; a future revision must preserve prior artifacts and document its reason.

See [Section 6 review](../docs/section-6-review.md) for results, observed AI limitations, and the next review checkpoint.
