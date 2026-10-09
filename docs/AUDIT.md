# Agent 0 MVP Audit

**Audit date:** 2026-10-09  
**Scope:** repository and current working tree, before the Phase 1 implementation changes requested in the product brief. This audit records what the checked-in and uncommitted code demonstrates; it does not imply production readiness or validated user research.

## Executive summary

Agent 0 is a Python/FastAPI investigation API and Celery worker, with a Next.js/React workspace and PostgreSQL-backed case records. It already accepts factual text, public URLs, images, and short videos; plans claims and searches; retrieves selected public pages when enabled; stores evidence and findings; and presents source and media context. OpenAI and Exa search are currently called as separate planned provider traces in the in-progress worktree, without provider failover. Search results are candidate leads: the backend retrieves pages separately before their text can enter the evidence packet.

The MVP does **not** yet implement the brief's strict claim triage taxonomy, exact verdict/confidence contract, two-independent-source rule, per-sentence citation validation, provenance timeline, contradiction-pair panel, persistent human editorial decision, or case exports. Audio and document input are represented in domain/history types but have no end-to-end intake and analysis workflow. Production authentication and retention/deletion remain explicitly gated. The latest routing changes and dependency declaration are unverified because the environment health gate reports critically low disk space; no tests or package installation were run for this audit.

## Repository map

| Area | Stack / responsibility |
|---|---|
| `backend/` | Python 3.12, FastAPI, Pydantic Settings, SQLAlchemy, Alembic, PostgreSQL, Celery/Redis, boto3-compatible private object storage, OpenAI Agents SDK and OpenAI SDK, C2PA Python binding |
| `backend/app/main.py` | API application; request ID middleware; mounts health, investigation, and ClickCast routers |
| `backend/app/worker.py`, `backend/app/tasks.py` | Celery worker and periodic outbox dispatch / stalled-job recovery |
| `backend/app/modules/investigations/` | Intake, persistence, orchestration, model tasks, media safety/analysis, results API and user-facing summaries |
| `backend/app/modules/sources/` | Exa and OpenAI web-search adapters, Jina Reader page retrieval, URL normalization, source classification/prioritization, excerpt selection |
| `frontend/` | Next.js 16, React 19, TypeScript; investigation workspace, results/evidence views, history, public pages and server-side API proxy routes |
| `backend/migrations/` | Alembic schema history. Existing migrations persist investigations, claims, sources, evidence/findings, audit/usage, media, confidence and search route metadata |
| `backend/tests/` | Pytest unit/service/pipeline/provider/media/worker tests with local fixtures and provider mocks |
| `frontend/src/app/investigate/presentation.test.mjs` | Node test for presentation helpers; frontend package scripts also expose ESLint and Next production build |

There is no dedicated eval suite, golden-claim dataset, PDF/JSON export subsystem, or `/demo` script in the current inventory.

## Current claim path

1. **Input:** The web workspace accepts a text question/claim or URL and JPEG/PNG/WebP image or MP4/WebM video. The API stores an `Investigation`, `Submission`, `ProcessingJob`, outbox event and audit event. The current local development owner is a fixed `DEV_USER_ID`; non-development use is refused because the authentication adapter is not implemented.
2. **Queue:** The worker dispatches outbox records to Celery and records stage transitions/audit events. A scheduled recovery task marks stale active jobs failed/retryable. PostgreSQL is the system of record; media and retrieved source text use configured private object storage.
3. **Intake and planning:** The orchestrator runs media checks as applicable, registers a submitted URL as a source candidate, then asks the OpenAI Agents SDK using structured Pydantic output to extract up to three claims and plan up to five queries. The schema currently has generic `claim_type` text and typed query route metadata. Ambiguous/no-claim inputs may return a clarification question, but there is no persisted clarification-pending workflow that lets the user edit/split claims before search.
4. **Search:** Planned queries create separate Exa and OpenAI Responses `web_search` traces in the current worktree. Exa needs its own key; OpenAI web search uses the configured OpenAI key/model. They are parallel providers, not fallback providers. The orchestrator orders primary, reporting/reference, fact-check, then social lanes, and widens based on retrieved domain coverage. Social traces are marked unavailable; no social provider is integrated. Fact-check is a search lane, not a dedicated ClaimReview API adapter.
5. **Source retrieval:** Search results are candidates, not findings. When `SOURCE_READER_PROVIDER=jina_reader`, the backend sends the public URL to Jina Reader and stores bounded extracted text privately; the default is disabled. The retrieval adapter blocks non-public IP destinations, credential-like query strings, redirects, oversized content, and unsupported content types. Retrieved excerpts are selected with deterministic claim-aware matching and stored as `Evidence` with source links.
6. **Reasoning and result:** OpenAI receives a bounded evidence packet and returns structured findings, evidence relationships, qualitative confidence, limitations and next steps. Application checks constrain evidence links/statuses and downgrade unsupported findings. API serialization returns claims, findings, evidence, sources, retrieval/search traces, media summaries and a deterministic verification brief. The UI renders progress, findings, evidence/source candidates, limitations and media observations. Processing completion is explicitly distinguished from factual verification.

## What currently works in code

- Durable asynchronous case creation, idempotency keys, processing stages, retry path, audit events and usage records.
- Text and submitted public URL intake; image normalization/private preview; bounded video frame sampling. Audio is not transcribed. Video audio is explicitly out of scope in the UI.
- Structured model task outputs via Pydantic models for research planning, evidence reasoning and media visual observations.
- Search candidate/source distinction; optional independent page retrieval; bounded excerpt/evidence context; source and URL deduplication and source relationship recording.
- Evidence-linked finding persistence and validation, user-visible uncertainty language, separate qualitative evidence confidence and rationale.
- Image metadata/pHash and local C2PA analysis, plus constrained visual observation; UI describes their limits.
- Case history summary endpoint and source/evidence result views.
- Development-only access guard and explicit refusal of unsupported production authentication configuration.
- Existing tests cover several domain, service, pipeline, source retrieval, media, ClickCast and worker behaviors using mocks/fixtures.

## Stubbed, unavailable, or incomplete

- `auth_mode` accepts `oidc` in configuration but no authentication adapter is implemented; development uses a single fixed owner. Shared demo/history is not private between visitors.
- Source page retrieval defaults to `disabled`. If enabled, Jina Reader is an external processor of submitted source URLs and page retrieval content.
- Social search is not integrated. A planned social lane is recorded as unavailable.
- Search route/claim triage is model-planned and partly code-ordered; there is no deterministic first-class triage record or user edit/split confirmation stage.
- Current verdict enum and evidence-confidence enum do not match the requested exact verdict taxonomy or HIGH/MEDIUM/LOW confidence taxonomy.
- No hard gate for two independent sources on ordinary supported/contradicted findings; source independence groups are not modeled as required ledger fields.
- No exact quote plus location validation for every evidence excerpt and no sentence-level citation validation in explanation text. The UI links finding evidence items, but does not establish that each explanation sentence is supported by its linked item.
- No archived URL/first-seen/provenance chain, contradiction-pair model/panel, or complete gaps panel with “what would change the verdict”.
- No human publish/hold/needs-more-work review action, override/rationale audit workflow, or reviewer identity.
- No PDF/JSON case export. Existing audit records do not constitute the full requested immutable case file of prompts/model/provider inputs and outputs.
- Audio/document input types exist in the domain/history labels but no corresponding upload and processing path is implemented.
- No Google Fact Check Tools API, Wikipedia/Wikidata fast-path integration, archive API, reverse-image search, audio transcription, video audio processing, or embedding-based repost detection.
- The OpenAI web-search adapter uses the OpenAI SDK Responses endpoint to return candidate sources/citations; candidate retrieval and source-text evidence still depend on the separate source reader.

## Known failures and operational constraints

- The repository state file reports a SEOS resource health gate of **4% free disk**, blocking dependency installation and requested verification. This audit did not run tests, builds, package installation, or a live provider check.
- The current worktree has uncommitted changes and generated media artifacts. Search routing, the OpenAI web adapter, migration `0011`, and direct `openai` dependency are in progress in that worktree and have not been verified in this environment. Do not infer behavior from successful earlier checks on a prior revision.
- The OpenAI web adapter catches broad exceptions and exposes a generic provider failure, so actionable provider error distinctions are limited at that boundary.
- Exa's adapter has a 20-second timeout; OpenAI web search has a 30-second client timeout; Jina Reader has a 15-second timeout. No shared cross-provider budget/deadline or cache is evident in these adapters.
- Production settings intentionally fail startup until auth is implemented. Production authentication, retention/deletion, provider data handling, and deployment decisions remain open in `docs/OPEN-QUESTIONS.md`.
- Existing history/data is a shared local-demo owner namespace; case access isolation is therefore not suitable for sensitive/public multi-user use.

## External services and data movement

| Service | Current use | Conditions / limitation |
|---|---|---|
| OpenAI API | Structured claim/query planning, evidence reasoning, optional visual interpretation; current worktree also uses Responses `web_search` | Requires `OPENAI_API_KEY`; prompts, submitted text, selected media (when visual call enabled), and retrieved evidence are sent to OpenAI. Search adapter is newly added in current unverified worktree. |
| Exa | Web search candidates | Requires `EXA_API_KEY`; independent from OpenAI search in current implementation. No failover. |
| Jina Reader | Public-page extraction | Optional; disabled by default. When enabled, target public URLs are sent to Jina and returned extracted text is stored as private source content. This processing choice remains an open product/deployment question. |
| PostgreSQL | Investigations, claims, traces, evidence, findings, audit and usage persistence | Local/dev and deployment connection set by `DATABASE_URL`. |
| Redis | Celery broker/result backend | Connection set by `REDIS_URL`. |
| S3-compatible object storage | Media and retrieved source text | Endpoint, bucket and credentials configured through environment settings. Local development defaults are not production credentials. |
| ClickCast | Optional WhatsApp intake/status integration | Token and identity key required; completion push/reply mechanism is not implemented. |
| C2PA/FFmpeg/local image libraries | Local media analysis and video frame extraction | No reverse-image provider. C2PA remote manifest and OCSP retrieval are disabled per existing design. |

All configured secrets are read through environment-backed settings; production is blocked rather than enabled without the missing auth adapter. A broader user-facing data retention/deletion control is absent.

## Test coverage observed

Test files currently include domain/service, cost controls and orchestrator, evidence localization, image safety, media C2PA/evidence graph/preview, URL source intelligence, ClickCast, worker schedule, OpenAI architecture, and the newly added OpenAI web-search adapter. Frontend coverage is concentrated in investigation presentation helper tests. Most provider paths are unit-tested with mocks; this is not equivalent to live provider verification or a full browser journey.

For this audit, **no tests were run**. The environment state explicitly marks verification blocked by low disk, and the latest provider-routing changes are unverified. The brief-required claim-type end-to-end tests, citation-validity eval runner, 40+ golden claims, and saved eval results do not exist yet.

## Top 10 gaps versus the brief

1. **First-class claim triage:** add strict claim type enum, normalized atomic claims, compound splitting, and persisted deep-investigation routing; distinguish opinion/prediction as not verifiable.
2. **Human-in-the-loop triage:** show triage quickly and allow correction/splitting before research continues; current clarification is generated in planning without an edit/resume journey.
3. **Verdict contract:** align statuses with `SUPPORTED`, `CONTRADICTED`, `PARTLY_TRUE`, `INSUFFICIENT_EVIDENCE`, `NOT_VERIFIABLE`; independently represent HIGH/MEDIUM/LOW evidence confidence.
4. **Enforce evidence sufficiency and independence:** hard-check the two-independent-source rule (with one authoritative source exception for settled facts); model and collapse copied/syndicated source groups.
5. **Citation validation:** validate retrieved URL membership and exact excerpt/location, then ensure every explanatory sentence has evidence links; reject/retry invalid structured outputs.
6. **Complete evidence ledger:** persist/present all requested source metadata, tier, stance, excerpt location, independence group, published date and staleness state; add provenance timeline, explicit contradiction pairs, gaps and uncertainty.
7. **Fast path and provider routing:** implement deterministic settled-fact lane with authoritative references; make OpenAI and Exa coexist safely with bounded calls, source qualification and transparent partial failure. Current routing is recent, worktree-only and unverified.
8. **Editorial decision and case file:** add publish/hold/needs-work, rationale and AI-verdict override with actor/time audit; export JSON and PDF with source/model/prompt trace.
9. **Input parity and demo flow:** complete or explicitly reject audio/document; add illustrative true/false/contested example chips and a reproducible `/demo` flow without implying live outcomes.
10. **Verification, security and operations:** add golden claims/eval runner, per-type end-to-end coverage, citation validation metrics, rate limits/retries/cache, retention/deletion and privacy isolation. Existing production auth gate must be resolved before sensitive or multi-user use.

## Dependency assessment

No dependencies were added as part of this audit. The uncommitted tree already declares `openai` directly for the OpenAI Responses web-search adapter; the lockfile/install state is not verified. The existing OpenAI SDK, Pydantic, SQLAlchemy and standard-library HTTP/media tooling can support the first triage/verdict/evidence-rule slices without adding a schema or document framework. Consider a PDF library only when the JSON export/data contract is implemented and the existing deployment footprint is understood; the archive, fact-check, Wikipedia/Wikidata, social, reverse-image and embedding integrations are not justified until the audit gaps are addressed and provider/data-handling decisions are made.

