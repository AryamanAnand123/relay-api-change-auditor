# Section 2: deterministic compatibility comparison

Section 2 adds the comparison engine and a stateless `POST /api/specifications/compare` endpoint so the result is directly reviewable before saved-history work. Runtime is `0.2.0`, health section 2. Engine is `1.0.0`, policy is `declared-client-v1`. Validation-only behavior remains available at `/api/specifications/validate`.

## Delivered behavior

Upload old/new `.json` files exactly as in Section 1. The same bounded body parser, one-request admission lock, offline validation, reference rules, in-memory file handling, worker timeout/cleanup, origin checks, and error redaction protect both endpoints. Comparison runs inside the existing disposable worker. It does not call model APIs, specification servers, or GitHub.

The result contains normalized inputs and a comparison report with direction-aware severities, logical finding IDs, source evidence, input hashes, rule/policy versions, counts, verdict, and explicit coverage gaps. Read the [full rule catalog and consumer assumptions](comparison-policy.md) before interpreting findings. Uncertainty changes affected findings to review; it is not hidden behind a zero-breaking count.

Original sample results:

| Old/new pair | Expected result |
| --- | --- |
| orders-v1 / orders-v2-breaking | Three breaking findings: removed GET, newly required request currency, response price number-to-object. |
| orders-v1 / orders-v1 | Zero findings within the supported subset. |
| orders-v1 / orders-v2-compatible | Two informational findings: optional request note and new GET /status. |

No UI is implemented yet. To inspect the current result:

```powershell
curl.exe -sS -F "old=@examples/orders-v1.json;type=application/json" -F "new=@examples/orders-v2-breaking.json;type=application/json" http://127.0.0.1:8010/api/specifications/compare
.\.venv\Scripts\python.exe scripts\check-comparison.py
```

The check script uses original synthetic inputs only and writes [section-2-live.json](section-2-live.json). There is no database, saved report store, account, export feature, or upload persistence in this section. Source examples/check artifacts are ordinary project files, not retained user uploads.

## Verification

Regression coverage includes original positive/additive cases; request/response enum and numeric-type direction; required-field guarantees; optional additions; parameter/body changes; removed/added statuses and media; nested arrays; component renames; path-template renames; inherited parameters; case-insensitive headers/media; missing-schema evidence; empty enum domains; unknown composition constraints; recursive graphs; stable IDs; source pointer resolution; numeric precision; pure comparison; and explicit finding-budget failure. API checks include actual worker processes, invalid second-file behavior, upload boundaries, and shared validate/compare admission while liveness remains responsive.

The recorded live run passed **15 actual loopback HTTP checks**: original/identical/additive examples; four enum-direction cases; two integer-to-number directions; unsupported constraints requiring review; invalid/oversized new inputs; cross-origin rejection; chunked comparison with stable IDs; and preserved validation-only behavior. These curated development checks are not held-out accuracy measurements. Broader frozen evaluation remains Section 6.

No new packages, models, system tools, keys, or paid services were needed. The cumulative 39-package lock is unchanged from Section 1. Cedar's files, environment, database, and services were not modified. Apiproj remains a local uncommitted repository with no remote/publication configured.

Final verification: **149 tests passed** with no warnings, including real disposable subprocesses. `pip check` reports no broken requirements; all 39 installed package versions still match the original download reports. Python compilation passed. All 18 relative documentation links resolve, whitespace is clean across the 38 publishable text files checked, and the common token/private-key pattern scan found no matches. These scans do not constitute a security audit. The running backend remains on port 8010 at section 2 / version 0.2.0.

## Remaining limits and review boundary

This is a declared-client policy, not universal schema compatibility. It excludes callers relying on undocumented extra request values and clients rejecting all additional response fields. Unsupported schemas/status/media semantics require review; a no-breaking result never certifies a safe upgrade. Some conservative warning propagation can mark multiple operations sharing a path item. Runtime/business behavior, client source-code impact, and AI explanations are not established by this engine.

Section 2 stops here for review. Section 3 will add comparison persistence/history, deletion, and JSON/Markdown export; no database or frontend work is included now.
