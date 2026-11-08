# Section 7 review: portfolio and publication preparation

Section 7 preparation is complete in **Relay 0.7.0**. Open **http://127.0.0.1:8010/** for the local app. At this preparation checkpoint, no repository, commit, push, hosting service, or deployment had been created. The user subsequently approved public source publication to [relay-api-change-auditor](https://github.com/AryamanAnand123/relay-api-change-auditor); see the [publication record](publication-plan.md). The full app remains runnable locally, with no public backend deployment.

## Material prepared

- A concise portfolio [README](../README.md), with the complete tested commands preserved in [local development](local-development.md).
- An [architecture diagram and design rationale](architecture.md), [rule catalog](comparison-policy.md), and consolidated [limitations](limitations.md).
- A [two-minute demo walkthrough](demo.md), fresh desktop/mobile screenshots, and six reproducible public JSON/Markdown reports for the original breaking, additive, and identical examples.
- [Resume/interview material](portfolio.md) and a paste-ready [LaTeX project entry](resume-project.tex). These describe the implemented scope and use the final 375-test count without inventing a hosted URL or broad accuracy claim.
- A [current free-hosting comparison](hosting-decision.md), a concrete [publication proposal](publication-plan.md), and a source-review archive workflow.

The demo reports use the production validator, comparator, and exporters, with no history access or model calls. They are explicitly marked offline public examples rather than saved user reports. A manifest records their exact hashes; re-generation is byte-for-byte reproducible.

Fresh screenshots show the real application analysing unsaved original examples. Existing saved-history metadata is masked rather than published or deleted. Earlier real AI screenshots remain separately labelled historical evidence; no new provider call was made for this section's portfolio walkthrough.

## Release verification

The full backend suite passes **375 tests**, including 12 new checks for archive exclusions, known/generic token detection without echo, manifest/hash integrity, reproducible archive bytes, changed-source rejection, and public-report reproduction. The Section 6 frozen 90-case evaluation and engine/policy remain unchanged.

An isolated source-review checkout also passed all **375 backend tests**, using the already validated 66-package Python environment rather than claiming a new Python installation. A clean `npm.cmd ci` installed 19 locked packages, audited 20 packages, reported zero known vulnerabilities at that check, and built the React frontend successfully. Dependency lifecycle scripts stayed disabled. No dependency versions or model downloads were added.

The final actual-browser demo passed **5 workflow checks**, covering all three original examples, search/source evidence, desktop/mobile screenshots, no overflow, no external page requests/browser storage, and unchanged history/provider-call counts. The real loopback API also passed **10 regression checks**. See [demo verification](section-7-demo.json) and [release checks](section-7-checks.json).

Chrome initially crashed during a period with roughly 400 MiB of available Windows memory commit. After the user freed memory, the screenshot run passed. This was a browser startup limit; the final checks use the actual application and backend.

## Source review archive

Run `.\.venv\Scripts\python.exe scripts\prepare-release.py` from the project root to regenerate `release/relay-api-change-auditor-source.zip` and `release/source-manifest.json`. The `release` directory is ignored and is not part of the proposed repository. The ZIP includes an internal `SOURCE-MANIFEST.json` listing exact source paths, sizes, and SHA-256 hashes.

The builder inspects Git-visible candidates without staging or changing Git. It rejects unreviewed roots/file types, escaping paths/symlinks, runtime/dependency/build directories, databases, environment files other than the sample, private-key files, and credential patterns. It also checks the actual configured project key in memory without printing it. Archive contents are reread and verified against source hashes. This is a concrete source review, not a guarantee against every possible secret format.

The archive contains application source, fixtures/reports, docs/screenshots, locked manifests, and tests. It excludes `.git`, `.venv`, `node_modules`, `dist`, runtime storage, the provider key, databases, logs, and extracted review checkouts. Preserve the manifest with the archive; rerun the audit if source changes before publication.

## Hosting and approval checkpoint

The current recommendation is the public repository and documented demo first. GitHub Pages can host static documentation but cannot run the FastAPI backend. Render Free uses ephemeral storage and does not provide durable free SQLite history. Current Hugging Face rules require a paid plan to create Docker/Gradio compute Spaces. The [hosting review](hosting-decision.md) links the official sources checked on November 8, 2026.

A live public backend needs a separately reviewed deployment adaptation: sample-only or authenticated isolated data, appropriate storage, platform-specific hashed dependencies, HTTPS/Host/origin settings, and abuse/provider-quota controls. This section did not expose the loopback app to the public internet or add billing. No open-source license has been selected.

The reviewed source-publication scope is recorded in [source publication](publication-plan.md). User approval covers this new public repository and its source push, not a hosted backend deployment. The completed Cedar repository and its runtime remain separate and unchanged.
