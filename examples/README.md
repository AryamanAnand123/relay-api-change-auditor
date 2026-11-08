# Original specification fixtures

These are synthetic author-created JSON specifications, with no customer data or external references. No declared API endpoint in these files is called by the auditor.

Compare `orders-v1.json` with `orders-v2-breaking.json`. Expected findings under engine 1.0.1:

1. `GET /orders/{order_id}` is removed.
2. `POST /orders` now requires the request property `currency`.
3. The successful order response changes `price` from a number to an object.

All three are breaking under `declared-client-v1`. The old/new files have two and one operations respectively. Evidence pointers resolve into the original before/after documents.

Compare `orders-v1.json` with `orders-v2-compatible.json` for two informational findings under the same policy:

1. Optional request property `note` added to `POST /orders`.
2. New `GET /status` operation added.

This policy assumes old callers use declared request fields and tolerate additional response properties; it is not a general schema-subsumption proof or a promise about undocumented extra inputs.

Use `POST /api/specifications/compare` for findings or `/api/specifications/validate` for normalization only. These are development/regression examples, separate from the [frozen parcel evaluation corpus](../evaluation/README.md).

Reproducible public JSON/Markdown reports for breaking, additive, and identical comparisons are in [reports](reports/manifest.json). They are labelled offline examples and contain no saved user history. Regenerate them from the project root with `.\.venv\Scripts\python.exe scripts\build-demo-reports.py`.
