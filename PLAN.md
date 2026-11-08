# API Change Impact Auditor: section-by-section plan

Status: Section 7 portfolio preparation is complete in application version 0.7.0: concise README, full local setup, architecture, limitations, reproducible original-example reports, demo walkthrough, resume material, hosting comparison, and a source-review archive workflow. The full backend suite passes 375 tests, including release/exclusion/report-reproduction checks. Engine 1.0.1 and declared-client-v1 remain unchanged. The user approved public source publication to [relay-api-change-auditor](https://github.com/AryamanAnand123/relay-api-change-auditor). See [Section 7 review](docs/section-7-review.md) and [publication record](docs/publication-plan.md). Public backend hosting remains a separate decision; no deployment has been created.

## Objective and working agreement

Build a browser application that compares an old and new OpenAPI document, identifies supported client-facing compatibility changes, shows exact evidence, and optionally uses LangChain to explain migration work. Deliver one section at a time, verify it, present a review summary, and pause before the next section. Routine downloads/installations within an authorized section are performed by the coding agent from reviewed official sources. Never require a paid API, a credit card, or automatic paid fallback.

Location: `C:\Users\aryam\OneDrive\Desktop\Python\Apiproj`. This directory was empty when inspected. Cedar is a separate completed project; do not change its repository, database, environment, or services. Reusing its existing local Ollama service is optional and read-only with respect to installed models/settings.

## Product workflow

1. Select a built-in original example or upload old/new OpenAPI JSON files.
2. Validate inputs and identify supported and unsupported constructs.
3. Produce deterministic findings with stable IDs, affected endpoint/method, request/response direction, rule identifier, old/new JSON Pointers, and relevant before/after values.
4. Show breaking, potentially breaking, informational, and unsupported/needs-review results separately from AI availability.
5. Optionally request AI explanations and migration suggestions grounded in selected findings and bounded source snippets.
6. Inspect the structured evidence and export JSON/Markdown reports. Reopen saved comparisons or delete their stored data.

Example: an old POST request accepts an optional `currency`; the new request requires it. The rule engine reports a breaking request requirement, points to both schemas, and AI may explain how callers can supply that field. A changed response type such as number to object is flagged under a separate rule. Do not infer the business intent of a change or claim to find every affected caller without examining client code.

## Initial scope and compatibility policy

Accept OpenAPI 3.0.x and 3.1.x JSON documents only, with a documented supported subset. No Swagger 2, YAML, URL import, automatic fetching of references, repository execution, automatic PR comments, or generated patch execution in the first release. Unsupported versions fail clearly. Unsupported complex schema semantics produce explicit coverage warnings; a comparison with missing coverage cannot report universal compatibility.

Begin with paths, operations, parameters, request bodies, response status/media declarations, simple object properties, primitive types, required fields, and simple enums. Resolve bounded internal `$ref` references, including correct JSON Pointer escaping. Detect recursive references and report unsupported paths without unbounded expansion. External references are never fetched. Advanced composition (`allOf`/`anyOf`/`oneOf`), conditional schemas, full JSON Schema subsumption, discriminator semantics, and difficult version-specific dialect behavior are outside initial analysis coverage unless deliberately implemented and tested later. Propagate coverage warnings to affected findings rather than silently skipping them.

Document a client-facing, declared-contract policy rather than promising runtime compatibility. Request constraints and response guarantees have different directions:

- Removing an operation can break callers.
- Adding required request inputs or making an optional request body mandatory can break old requests.
- Restricting accepted request enum values can break old requests.
- Adding possible response enum values can break exhaustive consumers; narrowing a response enum is not automatically the same compatibility case.
- Removing a required response property weakens a guarantee; optional-property removal is potentially breaking under the documented consumer assumptions.
- Changed types require direction-aware checks; unsupported equivalence or widening/narrowing cases go to review.
- Security/authentication changes and advanced constraints remain explicit manual-review coverage initially.

Changing schema descriptions, key ordering, or operation IDs must not be treated as a removed HTTP endpoint. Match operations by path/method. Path-template renames and schema component renames require explicit handling or review rather than confident semantic equivalence. A stable, documented policy is more defensible than an opaque severity score.

## Proposed architecture

React/Vite UI -> FastAPI -> validation/normalization -> deterministic comparison -> SQLite history and evidence -> optional LangChain explanation -> export.

Use Python 3.12, FastAPI/Pydantic, SQLAlchemy/Alembic with SQLite, React/Vite, pytest, and browser checks. SQLite keeps the first release simple; database files stay outside the source tree under a distinct project runtime directory. Do not add PostgreSQL, Redis, Docker, vector storage, or a worker service unless an actual requirement justifies them. Start with one API process, bounded workloads, and explicit timeouts. Choose synchronous comparison versus a small persisted job workflow after measuring the supported fixture sizes; avoid an unnecessary distributed queue.

LangChain must have an identifiable role: provider integration, prompt composition, structured Pydantic outputs, and bounded retry/failure handling. AI output references existing finding IDs; it cannot create authoritative rule findings, remove warnings, change deterministic severity, or invent impacted source files. A fixed explanation workflow is sufficient; LangGraph and autonomous agents are optional future additions.

The model provider is an adapter. At the AI section, verify a hosted provider's actual free eligibility, quotas, model capabilities, and data handling before selecting it. No guarantee of unlimited free inference. Existing local Ollama is an optional no-API-bill fallback and must be benchmarked with this task before adoption. A public hosted backend cannot assume it can reach the laptop's loopback Ollama endpoint. Deterministic comparison/export remains useful when AI is unavailable, explicitly labelled as such. Never present canned text as a live AI response.

Development API uses port 8010 if free, separate from Cedar's 8000. Prefer serving the built frontend from FastAPI on one origin. Bind local development to loopback. Public deployment is a separate section with persistent-storage, abuse, privacy, and usage-limit checks; local development settings are not automatically production settings.

## Prerequisites, installations, and download handling

Already observed: Python 3.12 and 3.13, Node 22.14.0, npm 10.9.2, Git 2.51.0. Use a new Python 3.12 `.venv`, not Cedar's environment. Check project/ancestor AGENTS instructions before implementation.

Expected downloads:

- Python packages from official PyPI: backend, schema validation, SQLAlchemy/Alembic, pytest, and LangChain/provider packages when needed.
- npm packages from the official registry: React, Vite, and minimal UI/browser verification dependencies.
- Model download only if the existing local model is insufficient and a local route is selected; no download is assumed necessary now.
- No new Python/Node/Git installation is expected based on the inspection. No Docker/PostgreSQL installation is required for the MVP.

Select and pin mutually compatible versions during setup, record provenance, and retain lockfiles. Verify model/installer hashes/signatures when relevant; check npm integrity/audit and Python dependency consistency. Do not run arbitrary downloaded shell scripts or change persistent PowerShell execution policy. Keep keys in server-side environment variables outside Git; never put them in frontend code, reports, screenshots, or logs.

## Sections and acceptance checks

### Section 0: prerequisites and foundation

Create isolated environment/repository structure, ignore rules, line-ending/binary attributes, runtime configuration, pinned initial dependencies, basic FastAPI liveness endpoint, and original example specifications. Check port conflicts before binding. Do not initialize a new public GitHub repository or publish anything as part of setup.

Acceptance: imports and dependency checks pass; health responds on the selected local port; no credentials/runtime files are trackable; Cedar is unaffected. Review installed items and commands before advancing.

### Section 1: input validation and normalized specification model

Accept two JSON files under a documented initial 2 MiB/file limit with bounded nesting, schema visits, references, and findings. Reject malformed JSON, duplicate keys, unsupported root/version shapes, invalid structural documents, and unresolved internal references clearly. Select a maintained OpenAPI validator compatible with both targeted versions and configure/guard it so validation never retrieves external references. Validation must distinguish an invalid document from a valid document whose comparison semantics are unsupported.

Acceptance: valid examples load; malformed/oversized inputs fail clearly; escaping, duplicate keys, cyclic/shared refs, external refs, and advanced schemas have tested outcomes; input descriptions are treated as untrusted data. No HTTP fetches or code execution from uploaded specs.

### Section 2: deterministic comparison engine

Implement a small, explicit rule catalog covering supported operation removal, required request additions, request enum restriction, type changes, response-property removal, and response-enum expansion. Additive/documentation-only changes serve as negative controls. Keep rules direction-aware and emit coverage warnings for unsupported areas. Store engine/policy version in output.

Acceptance: curated old/new fixture pairs have expected findings, evidence pointers resolve, unchanged/reordered documents do not create changes, and request/response cases are not conflated. Define stable finding IDs and a coverage summary. This is the first useful product milestone without AI.

### Section 3: comparison API, saved history, and export

Expose upload/compare, list/detail, delete, and JSON/Markdown export endpoints. Persist comparison status, input hashes, bounded original inputs/evidence, findings, coverage, engine version, and timestamps. Decide whether raw inputs need retaining or can be replaced by minimal evidence; document that choice and retention/deletion behavior. Use consistent size/error handling and transactions.

Acceptance: comparison survives restart, exports match stored findings, deleting a run removes its associated stored content, failures do not leave a successful-looking partial run, and oversized/duplicate requests are bounded. This is a single-user local workspace initially; authentication/access isolation must precede private saved history on a shared public deployment.

### Section 4: browser workspace

Build a clean old/new upload interface, example selector, summary, filters, endpoint grouping, evidence inspector, coverage warnings, saved comparisons, and export controls. Show the direction and assumptions behind severity. Make AI state visible without blocking deterministic results. Include empty, loading, validation-error, partial-coverage, and mobile states.

Acceptance: complete example upload-to-export browser flow, responsive layout, accessible labels/keyboard navigation, safe rendering of uploaded strings, and clear errors. No external model key in browser assets. Review the actual UI before advancing.

### Section 5: LangChain migration explanations

Verify and choose a free model route; use a provider adapter, bounded prompt/input/output, strict structured output, finding-ID checks, explicit AI provenance, and at most a small fixed retry budget. Request explanations only for selected/batched supported findings so free quotas are not consumed unnecessarily. Cache results by input hashes, engine/prompt version, provider, and model identity where available. Preserve deterministic reports if AI times out, is rate-limited, or fails validation.

Acceptance: real generated explanations are useful on a small pilot; structured results reference existing findings; prompt injection in descriptions cannot alter authoritative findings; missing credentials and quota/network/model failures leave comparison usable. Do not call arbitrary tools based on uploaded descriptions. Record calls/latency without keys or private input dumps.

### Section 6: evaluation and reliability

Freeze a broader fixture corpus before final scoring, separate development/tuning examples from additional evaluation cases, and record expected rule findings plus known coverage gaps. Measure deterministic precision/recall by rule, false positives on compatible changes, pointer correctness, comparison latency, and report reproducibility. Evaluate AI explanations separately for evidence fidelity, unsupported claims, validity, failures, and latency. Do not equate JSON validity with factual correctness.

Acceptance: recorded reproducible results, meaningful regression tests, user-visible known limitations, and no hidden model retries or cherry-picked accuracy claims. Check deletion/retention and malformed/deep-input handling. Further performance tuning only follows measured problems.

### Section 7: portfolio, hosting decision, and publication

Finish README, setup/startup, architecture diagram, original before/after demos, rule catalog, limitations, resume bullets, and screenshots. Prepare a reviewable repository with source/fixtures/results and no keys, private specs, runtime databases, or environment packages.

Verify current free hosting terms before choosing a provider: persistent filesystem, sleeping, storage, outbound calls, build limits, and whether billing/card details are required. A stateless sample-only public demo is an acceptable first hosted release if private uploads/history or free persistent storage are not viable; label any AI-disabled mode. Add authentication, isolation, request/AI quotas, restrictive CORS, HTTPS settings, deletion, and key controls before hosting private multi-user data. New security/deployment work may need its own reviewed subsection rather than being rushed into publication.

Acceptance: setup guide follows actual commands, final demo works, secrets exclusion verified, hosting capabilities stated honestly, and user approves the concrete publication/deployment scope. GitHub upload follows explicit user authorization, as with Cedar.

## Deferred enhancements

Client-code tracing for a defined Python HTTP-client subset, GitHub PR integration, automatic CI checks, YAML, additional schema semantics, authentication changes, patch drafting, and broader language support are later sections. None is required for the first complete version. Client tracing particularly changes complexity; do not include it in the initial 3-5-focused-day MVP estimate.

## Timing and review expectations

The earlier 3-5 focused working day estimate applies to a compact upload/compare/explain/export MVP, not full arbitrary OpenAPI compatibility or cloud multi-user hosting. A polished evaluated portfolio release may take around 1-2 focused weeks, depending on model/provider integration and hosting. These are estimates, not delivery guarantees. Each completed section stops for review even if other sections could be started immediately.

## Reference documentation

- OpenAPI 3.1 semantics: https://spec.openapis.org/oas/v3.1.0.html
- LangChain structured output: https://docs.langchain.com/oss/python/langchain/structured-output
- LangChain Ollama adapter, if selected: https://docs.langchain.com/oss/python/integrations/chat/ollama

Versions and hosted provider terms must be checked when installing/selecting them rather than inferred from these links.
