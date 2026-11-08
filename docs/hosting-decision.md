# Free hosting review — November 8, 2026

The current application is a single-user loopback workspace. This review recommends publishing its source, screenshots, and recorded original-example reports first. The complete app remains runnable locally at no hosting cost. No service was created or account upgraded during this review.

| Option | Verified free capability | Fit for Relay |
| --- | --- | --- |
| GitHub public repository + optional GitHub Pages | Pages is available for public repositories on GitHub Free and serves static HTML/CSS/JavaScript. | Good for project documentation or a clearly labelled recorded-example viewer. It cannot run FastAPI, SQLite history, or server-side Groq calls. |
| Render Free web service | Python web services are supported; free services sleep after 15 minutes, receive 750 shared workspace hours/month, and lose local files on restarts/redeploys/sleep. Free persistent disks are unavailable; free Postgres expires after 30 days. Usage overages without a payment method suspend services/builds rather than silently supplying unlimited capacity. | A later sample-only/stateless demo may fit. The current SQLite history cannot be represented as durable storage there. Account eligibility/card prompts must be checked during signup; do not add billing for this project. |
| Hugging Face Spaces | Static Spaces are free. Current documentation requires a paid plan to create compute-backed Docker/Gradio Spaces, despite the CPU Basic table showing no hourly compute price. | A new Docker-hosted FastAPI deployment does not meet the strict free-only requirement under the current creation rules. A static showcase remains possible. |

Sources: [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages), [Pages usage limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits), [Render Free](https://render.com/docs/free), [Spaces overview](https://huggingface.co/docs/hub/spaces-overview), [Spaces hardware eligibility](https://huggingface.co/docs/hub/spaces-gpus). These provider terms can change; review again immediately before deployment.

GitHub Pages currently limits published sites to 1 GB, applies a soft 100 GB/month bandwidth limit, and limits ordinary builds. A documentation showcase is far smaller than those limits. Publishing the current Vite build alone would not provide a working live backend; no such deployment has been prepared or claimed.

## Concrete recommendation

Publish `relay-api-change-auditor` as a public source repository after review. Include the README, architecture, local setup, synthetic examples/reports, screenshots, tests, evaluation evidence, and limitations. Do not publish the server key, runtime folder, databases, uploaded contracts, environments, dependency directories, or build output.

An optional later Pages site could present these screenshots and recorded examples with a prominent “recorded demo; no live analysis or AI” label. That would be a separate static viewer implementation, not the full application. No domain purchase, hosting subscription, or model key is needed to show the repository materials.

## Before any live hosted backend

The current Host/origin checks and launcher target loopback, and the runtime/lock target Windows x64/Python 3.12. Do not simply bind this version publicly. A reviewed hosting subsection must:

1. Define a sample-only mode that accepts no private uploads and exposes no private saved history, or implement authentication and per-user data isolation.
2. Make storage behavior explicit. For an ephemeral free service, disable persistence or label it temporary; do not advertise durable SQLite history.
3. Adapt host/origin/HTTPS settings and process lifecycle for the chosen host, then verify provider-specific build/runtime behavior.
4. Create a platform-appropriate hashed dependency lock. Several current wheel hashes are Windows-specific; the present lock is not a tested Linux deployment lock.
5. Enforce durable/shared abuse and AI usage controls before exposing a server key. Current per-process counters reset on restart and are not a public quota system. Keeping hosted AI disabled is acceptable.
6. Verify free-plan eligibility, card requirements, account limits, and suspension behavior on the actual account. Stop if billing or a paid upgrade is required.

These are concrete gaps in adapting this local design, not claims that a public multi-user deployment already exists. A hosted backend can be added after its scope and provider are reviewed.
