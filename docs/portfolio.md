# Portfolio and interview material

**Project title:** Relay — API Change Impact Auditor

**Repository:** [relay-api-change-auditor](https://github.com/AryamanAnand123/relay-api-change-auditor)

**GitHub description:** Compare OpenAPI contracts with deterministic compatibility rules, source evidence, saved history, and optional LangChain migration guidance.

**Suggested topics:** `python`, `fastapi`, `react`, `langchain`, `openapi`, `sqlite`, `api-testing`, `llm`, `developer-tools`.

## Resume entry

- Built a React/FastAPI OpenAPI auditor with 23 compatibility rules, severity filters, and JSON Pointer evidence.
- Integrated optional LangChain/Groq guidance with structured validation, explicit consent, timeouts, and caching.
- Added transactional SQLite history and JSON/Markdown exports; verified 90 frozen evaluation cases and 375 backend tests.

Stack: Python, FastAPI, React, Vite, LangChain, Groq, Pydantic, SQLAlchemy, Alembic, SQLite, pytest, Playwright. A paste-ready [LaTeX entry](resume-project.tex) includes the repository link. The count includes the final Section 7 release/exclusion tests.

## A 30-second explanation

“Relay helps review an API upgrade by comparing two OpenAPI JSON documents. Python rules identify declared compatibility changes and point to the exact old/new source values. A React interface lets you filter findings, inspect evidence, and reopen or export saved reports. LangChain adds optional migration suggestions, but the model cannot change the rule severity or coverage. I evaluated the rule engine separately from AI prose, so the project shows both reproducible results and honest limitations.”

## Interview discussion points

| Question | Concrete answer |
| --- | --- |
| Why use rules and an LLM? | Rules own reproducible compatibility judgments; the LLM helps explain selected evidence. They fail independently. |
| What does LangChain do? | Composes system/data messages and connects ChatGroq structured output to local Pydantic/reference validation. |
| How do you bound untrusted inputs? | Byte/depth/node/reference budgets, an offline subprocess deadline, admission limits, and explicit unsupported coverage. |
| Why SQLite? | A single-user application needs reliable transactions and simple setup; a distributed database would add unnecessary operations. |
| How did you evaluate it? | A frozen 90-case authored corpus across 23 rules, pointer checks, compatible controls, repeated results, and separately graded first-attempt AI outputs. |
| What did evaluation find? | A validator inconsistency and an SDK timeout classification issue were fixed. A fixture-label correction and all baseline failures were retained. |
| Is the AI accurate? | Five of six evaluation attempts generated valid guidance. Core summaries were correct, but four outputs made additional assumptions; one was rejected. No broad accuracy claim is justified. |
| Is it deployed? | The source is available on GitHub and the full app is verified locally. No public backend is deployed; hosting has separate access/storage requirements. |

Avoid claims of “100% API compatibility,” “production-ready multi-user security,” “automatic code review,” or “deployed cloud application.” None is demonstrated by the current scope. The 90-case result applies to an internal authored corpus, not arbitrary APIs or an external benchmark.
