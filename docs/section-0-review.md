# Section 0 review: isolated foundation

Completed on 8 November 2026 (Asia/Calcutta). Work stops here for review before Section 1.

## Delivered

- Separate Python 3.12.4 virtual environment in `Apiproj/.venv`.
- Separate local Git repository on `main`; no commits, remote, or public publication yet. The parent repository and Cedar repository were not modified.
- FastAPI application named `auditor`, version `0.0.0`, with root status, `/health`, and `/openapi.json`.
- Loopback launcher on port 8010, with an occupied-port check and proxy headers disabled. No running process was terminated to acquire the port.
- Environment-prefixed settings and an optional `.env.example`; no actual `.env` or model key is needed.
- Git ignore rules for environments, keys, databases, and runtime data; Git attributes preserve text line endings and binary assets.
- Two original synthetic order specifications with three deliberate development changes: removed GET endpoint, newly required request currency, and changed response price type.
- Setup/start commands, tests, exact dependency lock, download provenance, and this review.

## Installed packages and provenance

Five direct requirements resolved to 25 packages. Main versions:

| Package | Installed version |
| --- | --- |
| FastAPI | 0.162.2 |
| Uvicorn | 0.54.0 |
| Pydantic | 2.14.3 |
| pydantic-settings | 2.16.2 |
| httpx | 0.28.1 |
| pytest | 9.2.0 |

Packages were resolved using pip's isolated mode and the official `https://pypi.org/simple` index with binary wheels only. All artifact URLs in the [pip installation report](section-0-downloads.json) are HTTPS `files.pythonhosted.org` URLs, with a recorded SHA-256 for every artifact. The [preserved Section 0 lockfile](section-0-requirements.lock.txt) pins the original resolved set and those hashes; the current backend lock evolves with subsequent sections. It targets Windows x64 / CPython 3.12; another platform requires a reviewed artifact lock rather than assuming the platform-specific wheel hash applies everywhere.

The dependency consistency check passed. A dry-run install with `--require-hashes` confirms the installed versions satisfy the lock; it is not an independent reinstall or a vulnerability audit. Recorded artifact hashes improve reproducibility and integrity checks, not a guarantee that packages have no vulnerabilities. No package source builds or remote shell scripts were executed. Python environment bootstrapping and pip's temporary-directory checks required execution outside the filesystem sandbox; they completed successfully without changing persistent PowerShell policy. No global Python packages were installed or upgraded.

LangChain, a provider integration, frontend packages, a semantic OpenAPI validator, SQLAlchemy/Alembic, and AI models are intentionally deferred to sections that need them. No Docker, database server, cloud account, paid service, or additional system tool installation was needed. Existing Node/npm/Git tools were reused without reinstalling them.

## Verification results

- Four foundation tests passed with no warnings: liveness/headers, unexpected-host rejection, absent feature routes, and current schema scope.
- Python compilation check passed.
- `pip check`: no broken requirements.
- All 25 installed package versions match the download report.
- Actual HTTP checks on port 8010: root, health, and schema return 200; an unrelated Host returns 400; unimplemented comparison returns 404.
- Health reports exactly `{"status":"ok","section":0,"version":"0.0.0"}`.
- Environment, `.env`, runtime, key, and database example paths are ignored by this project's Git rules. Common token/private-key pattern scan found no matches in the publishable source inventory checked.
- Both original example files parse as JSON, and their three intended changes were checked. Full OpenAPI semantic validation is not claimed until Section 1.

Read-only live-check results are saved in [section-0-checks.json](section-0-checks.json). No external model request, uploaded-spec URL fetch, ingestion job, or database operation was part of verification. The backend deliberately does not enable external Swagger CDN assets in this section.

## Review locally

While the server is running, open **http://127.0.0.1:8010/** or **http://127.0.0.1:8010/health**. This is backend status JSON, not the planned React interface. Server restart and verification commands are in [README](../README.md). Stop it with Ctrl+C in its terminal; do not start a duplicate instance on the same port.

Runtime storage under `%LOCALAPPDATA%\ApiChangeAuditor` is reserved in configuration but no database or upload store is initialized. Source and `.venv` remain in the OneDrive-backed project folder; Git ignore rules do not control OneDrive synchronization. No files or settings in Cedar were changed.

## Next section, after review

Section 1 adds bounded JSON uploads, semantic OpenAPI validation, a normalized specification model, and explicit outcomes for unsupported constructs and references. It does not yet implement compatibility rules or AI explanations. The complete sequence remains in [PLAN](../PLAN.md).

Reference guidance used during setup: [FastAPI virtual environments](https://fastapi.tiangolo.com/virtual-environments/) and [pip installation](https://pip.pypa.io/en/stable/cli/pip_install/).
