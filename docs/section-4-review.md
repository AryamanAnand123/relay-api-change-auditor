# Section 4 review: Relay browser workspace

Section 4 is complete. Open **http://127.0.0.1:8010/** while the backend is running. This section adds the React workspace; AI explanations remain scheduled for Section 5.

## Behavior to review

- Choose or drop old/new OpenAPI JSON files, or load the original breaking, additive, and identical examples. Each file is limited to 2 MiB; the server remains authoritative for validation.
- Compare with saving enabled, or explicitly compare without saving. When history is unavailable, the stateless workflow remains usable.
- Inspect four severity summaries, endpoint groups, search, severity filters, and before/after evidence. Selection follows visible findings. Missing values are distinct from JSON null; large integer evidence retains its exact digits.
- Read policy assumptions and coverage warnings. A zero-finding result does not certify universal compatibility. AI availability does not alter rule severity.
- Reopen and paginate saved history, reload a bookmarked saved UUID, export JSON/Markdown, or confirm deletion. Duplicate comparisons reuse their existing snapshot. A report deleted elsewhere produces a clear error and clears stale selection.
- Use Specifications, Findings, and Evidence tabs on mobile, including arrow/Home/End keyboard navigation. Controls have labels, focus indicators, a skip link, and reduced-motion styling. This is not a full accessibility audit.

Reports contain contract information. Evidence previews stop at 20,000 characters and show an explicit clipping notice; server exports for saved reports preserve the full bounded snapshot. No file data is placed in the URL, localStorage, or sessionStorage. The bookmark contains only the saved UUID. Deletion removes the server snapshot, not previously downloaded copies.

## Implementation

React and React DOM 19.3.1 with Vite 8.3.6 build a static UI under `frontend/dist`. FastAPI serves `/`, the local SVG, and only contained files under `/assets/`. Unknown API routes do not fall back to HTML. Missing builds produce an actionable 503 without disabling API endpoints. Backend JSON diagnostics moved to `/api/system`; health is Section 4/version 0.4.0.

`/api/examples/{name}` serves only the three original allowlisted JSON specifications. Browser requests use the same origin and existing API limits. Uploaded text renders through React escaping; it is never injected as HTML. The HTML response sets a self-only script/style/connect policy, disallows framing and objects, and uses no external assets. Existing Host/origin restrictions remain in effect. This remains a single-user loopback workspace, pending a separate hosting/access review.

No Python dependency was added. Exact npm pins and package integrity hashes are recorded in `frontend/package-lock.json`; [download provenance](section-4-downloads.json) lists registry artifacts. Dependency lifecycle scripts are disabled. Existing Node 22.14.0, npm 10.9.2, and installed Chrome were reused; no browser, model, database server, or installer was downloaded. The installation audit reported zero known vulnerabilities at installation time, not a guarantee of future safety.

## Verification

All **202 backend tests passed**, including the existing 188 tests and 14 frontend-serving tests covering security headers, paths, MIME types, example allowlisting, and missing-build behavior.

The final Chrome run passed **15 simulated browser-state checks**, covering input/error handling, partial coverage, filters and evidence, exact large numbers, unsafe-looking strings, zero-change results, duplicate-click protection, history pagination, deletion, saved reload, stale exports, unavailable history, and mobile keyboard/layout behavior. See [the browser-state report](section-4-browser.json). Its API responses are synthetic current-engine fixtures; it does not establish backend integration by itself.

A separate Chrome run against the actual FastAPI, offline comparison workers, and SQLite passed **9 workflow checks**: uploads and saving, duplicate reuse, evidence/search, both downloaded exports, bookmarked reload, cancel/confirm deletion, an unsaved additive example, desktop/mobile rendering, and no external requests/browser storage/uncaught errors. See [the live report](section-4-live.json). Saved-history count was zero before and after; only the run's uniquely marked fixture was created and removed. No preexisting records were deleted.

Earlier concurrent browser runs crashed during a period of very low available Windows memory. Final checks were rerun sequentially and both passed. The application requires only the backend process after building the UI.

Screenshots from the final real workflow were visually reviewed: [desktop](section-4-workspace.png), [mobile findings](section-4-mobile.png), and [mobile evidence](section-4-evidence.png). The earlier `section-4-empty.png` is an initial-layout reference taken before typography refinements.

## Run and next checkpoint

Follow the [README setup and start commands](../README.md). Build from the `frontend` folder using `npm.cmd ci` and `npm.cmd run build`; serve using the project's loopback FastAPI launcher. Browser checks are `npm.cmd test` followed by `npm.cmd run test:live` from `frontend`, with the backend already running. Existing Chrome/Edge is used; `RELAY_BROWSER` can identify another existing executable.

Pause here for review. Section 5 will verify a free inference option and implement LangChain explanations grounded in existing findings, with bounded retries and clear failure states. No provider credentials, hosted resources, paid fallback, GitHub publication, or changes to Cedar were introduced in this section.
