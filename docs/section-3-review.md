# Section 3: saved comparison history, deletion, and export

Runtime `0.3.0`, health section 3; SQLite schema `0001_history`. This section adds explicit saving and report retrieval/export. It introduces no browser interface, accounts, AI provider, or public hosting. The Section 2 comparison engine/policy remains unchanged.

## Endpoints

| Method/path | Behavior |
| --- | --- |
| POST /api/comparisons | Validate/compare multipart old/new JSON files, then atomically save a completed snapshot. 201 new, 200 reused. |
| GET /api/comparisons | Newest-first metadata page; limit 1-50, optional UUID cursor. No full payloads in the list. |
| GET /api/comparisons/{id} | Saved metadata plus the immutable result. |
| DELETE /api/comparisons/{id} | Delete the record and its payload; 204 success, 404 missing. |
| GET /api/comparisons/{id}/export?format=json | Attachment with export schema version 1, metadata, and full saved result. |
| GET /api/comparisons/{id}/export?format=markdown | Attachment containing summary, policy, coverage, and all finding/evidence records. |
| GET /api/system/database | Readiness, schema revision, record/result-byte usage, and limits; no filesystem paths or payloads. |

The existing specification validate/compare routes remain stateless. Uploads, comparison, and save requests share one admission lock per API process. All prior byte/field/origin/worker limits remain active. Saved-history routes reject cross-origin reads and mutations, including cross-site fetch requests without Origin. Unknown hosts are rejected. No permissive CORS is configured.

## Storage and retention decision

The single-user history database is `%LOCALAPPDATA%\ApiChangeAuditor\history.sqlite3`, outside the source checkout and OneDrive. `scripts/setup-history.py` creates the separate runtime, applies Alembic migrations, and configures user-owned access. On the current machine, ACL inspection showed only the current Windows account's full-control entry on the runtime directory. Initialization refuses an unrelated nonempty directory and never resets an existing database. Importing the app or creating an uninitialized store does not create a directory/database.

Store an immutable canonical report snapshot instead of raw upload files. It contains normalized schemas, source pointers, exact input hashes, policy/engine versions, finding/evidence values, coverage, and completed status. Some findings cite an entire removed operation, so evidence can include descriptions/examples from that operation. Saved reports may contain private contract information even though complete original file bytes are not retained. Raw inputs are processed in memory and not saved as separate files. Reviewing saved evidence works without the original files; reconstructing or analyzing the original specifications with newer rules requires uploading them again.

Metadata contains a UUID, UTC timestamp, bounded display titles/versions, hashes, summary, verdict, coverage, and result size. Full original title/version strings remain in the saved result; list display strings are bounded. Detailed result hashes detect inconsistent stored payloads; they are not an encryption or adversarial tamper-proofing mechanism. The local database is unencrypted, and the API is a single-user loopback workspace without login. Authentication/isolation is still required before private multi-user public deployment.

There is no automatic expiration. Defaults permit 100 records and 64 MiB of logical stored result JSON, with at most 8 MiB per snapshot. An identical canonical result, including exact input hashes and engine/policy data, reuses the same record without resetting its timestamp. Different source formatting can change the input hash and create a new record. Limits produce 409 rather than silently evicting existing history. Duplicate reuse works even at capacity. Physical database pages/journals/metadata can exceed logical payload usage.

## Transactions, migrations, and deletion

SQLAlchemy Core uses explicit SQLite transactions. Saves/deletes use BEGIN IMMEDIATE, serializing duplicate/quota checks and writes. Only completed snapshots exist in the schema; invalid uploads, worker failures, quota failures, and failed commits do not create successful-looking pending/partial records. Database errors are redacted to generic 503 responses. A retry after an uncertain network result can reuse the already committed snapshot.

Keyset pagination orders by `(created_at DESC, id DESC)` and handles timestamp ties. Deleted/missing cursor anchors return a clear 400 so a client can reload the first page. A short SQLite busy timeout bounds lock waits; storage work runs off the API event loop. The comparison/worker path and process liveness remain available independently of an uninitialized history database.

Deletion removes the single database row containing metadata and the whole result. There is no separate upload file, AI record, or orphaned child payload to remove. Detail and both export endpoints return 404 afterward, and logical quota is released. `secure_delete=ON` overwrites freed record content in the active database file; a synthetic canary test confirms that behavior. This is not a promise of forensic erasure from filesystem history, deleted journals, backups, or reports already downloaded elsewhere. SQLite may retain allocated empty pages for reuse, so deletion does not promise file shrinkage.

Alembic revision `0001_history` creates the snapshot table and constraints/index. The setup script is idempotent. Tests perform down/up migrations only against disposable scratch databases. Never downgrade the real populated history database as a verification shortcut. A mismatched/unavailable schema produces 503 instead of accidental reads/writes against unknown tables.

## Export fidelity and rendering

JSON contains exactly the saved detail plus `export_schema_version: 1`. It preserves normalized inputs, findings, source evidence, hashes, and coverage. Markdown includes every finding and coverage record without truncating or hiding unsupported analysis. User-controlled strings remain JSON-encoded data inside fenced blocks; backticks, angle brackets, and ampersands are escaped losslessly so a description cannot inject HTML or terminate a fence. Parsing those blocks restores the saved values.

Exports are deterministic for a given record and bounded to 16 MiB. Oversized exports return 413 without changing the snapshot. Filenames derive only from the validated UUID, never uploaded names/titles. Attachments use appropriate JSON/Markdown types, no-store/nosniff headers, restrictive CSP, and no-referrer. The API does not log uploaded or exported bodies.

## Verification and reproduction

The full suite passed **188 tests**, including 39 new storage/API/export checks. Coverage includes restart/reopen persistence, duplicate/concurrent saves, count/byte quotas, transactional rollback, migration metadata/round-trips, pagination/ties/stale cursors, invalid results/uploads, deleted payload/detail/export access, tampered snapshots, uninitialized storage, cross-origin/host rejection, export injection/size/fidelity, and unchanged stateless behavior.

The [live report](section-3-live.json) records **13 workflow checks** through actual HTTP across an actual API process restart. One UUID-marked original synthetic record was created, duplicate reuse and both exports checked, the verified Apiproj process restarted, and both exports found byte-identical afterward. The verifier matched the captured ID/title/hash before deleting only that fixture. History returned to its original zero-record baseline; no preexisting record was deleted. These are workflow checks, not 13 independent quality benchmark cases.

Reproduce from the project root with the backend running:

```powershell
.\.venv\Scripts\python.exe scripts\setup-history.py
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe scripts\check-history.py --prepare
# Stop/restart only Apiproj's API in its own terminal.
.\.venv\Scripts\python.exe scripts\check-history.py --verify
```

The checker requires that explicit operator restart between its two phases; it does not restart arbitrary processes itself. Its pending state is a small identity/hash file inside the private runtime and is removed after successful verification. If interrupted, rerun verify after restart rather than preparing another fixture. Never delete other history to make room for a check. Routine restarts retain the database.

## Dependencies and scope boundary

Five new official PyPI wheels were installed: SQLAlchemy 2.0.57, Alembic 1.20.1, greenlet 3.5.6, Mako 1.4.3, and MarkupSafe 3.0.4. All 39 previous dependency versions are unchanged. The [Section 3 download report](section-3-downloads.json) records HTTPS artifact URLs/hashes; the cumulative [lockfile](../backend/requirements.lock.txt) pins 44 packages for Windows x64 / CPython 3.12. The previous [39-package lock](section-1-requirements.lock.txt) is preserved alongside the original Section 0 lock/report. No new system tools, database server, model downloads, subscriptions, or API keys were needed.

Final checks: hash-required lockfile dry-run passed; `pip check` found no broken requirements; `alembic check` found no new upgrade operations. Compilation passed, all 23 relative documentation links resolve, whitespace is clean across 55 publishable text files, and common token/private-key patterns were absent from that inventory. Environment, runtime/database/key paths, and the example downloaded-report filenames are ignored by Git. The live database is ready at `0001_history` with zero saved comparisons and zero stored result bytes after fixture cleanup. These checks do not constitute a vulnerability/security certification.

Cedar remains unchanged. No GitHub publication, repository remote, commit, or cloud deployment was added. Work pauses here for review; Section 4 will build the React workspace using these endpoints.
