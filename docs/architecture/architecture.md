# Draft architecture: Agent 0 evidence-verification platform

**Status: Approved v0.1 and expanded next-slice scope by product owner on 2026-10-03.** This follows the root `Agent 0 AI Verification Architecture.png` diagram. The current slice includes shared text/URL/image/video investigations with bounded application orchestration and a single OpenAI `ModelGateway`. Production-sensitive use remains gated.

## Context, goals and constraints

Agent 0 organizes verification work as traceable claims, sources, evidence, provenance, relationships and findings. Web, WhatsApp and future integrations are input/output channels. They must call the same Investigation interface and must not contain verification logic.

Design goals:

- Every material finding traces to one or more stored evidence records and source references. A finding without evidence references is a question, limitation or hypothesis, never an established conclusion.
- Preserve uncertainty. Absence of a located source is not proof of falsity. Media provenance is distinct from the truth of what media depicts.
- Keep the system operable by a small team: begin as a modular monolith with one deployable API and one worker process, not a fleet of services.
- Treat submissions as private by default. Do not publish them or use them for model training by default.
- Allow search providers, models, media analyzers and channels to be replaced behind narrow internal interfaces.

Assumptions pending product/security decisions: single-tenant MVP; web workspace is the primary review surface; WhatsApp is a later adapter; initial users authenticate; submitted material may contain personal or sensitive information; no production-grade universal deepfake determination is promised.

## System shape

```text
Next.js web ─────┐
WhatsApp adapter ├──> FastAPI v1 ──> Investigation application module
Future adapters ┘                         │
                               ┌───────────┼───────────┐
                               ▼           ▼           ▼
                         PostgreSQL   Object store   Job queue/worker
                               │           │           │
                               └───────────┴───────────┘
                                           │
                                  Analysis adapters
                           claim / search / media / provenance
```

PostgreSQL is the system of record for domain data, audit history and durable job records. Model evidence relationships with relational foreign keys and typed relationship rows; do not introduce a graph database for the first version. Store original media in private S3-compatible object storage and persist derived artifacts separately with explicit retention metadata. Celery workers use Redis as broker and transient progress/cache/rate-limit state; durable state and audit remain in PostgreSQL. Use `pgvector` only after a concrete semantic-retrieval requirement is validated. Local development uses Docker Compose with PostgreSQL, Redis and SeaweedFS's S3 API; production provider choices remain deployment decisions.

## Domain language and data model

- **Investigation**: private case created from normalized input; owns lifecycle, channel metadata, claims, assets, sources, evidence, findings and brief.
- **Submission**: immutable record of what arrived, when and through which channel; references original input/media without treating user assertions as facts.
- **MediaAsset**: stored original or derived media, with content hash, detected type, size, storage reference, retention status and processing lineage.
- **Claim**: proposition extracted from input or source, retaining original wording and normalized form, language, entities and time/place qualifiers.
- **Source**: retrievable origin (URL, document, account/post, official record), with publisher/author, published/retrieved timestamps, source class and provenance metadata.
- **Evidence**: a specific excerpt, observation, media signal or document passage from a Source or MediaAsset, including locator, extraction method and confidence/limitations.
- **EvidenceRelation**: typed link between Claim and Evidence (`SUPPORTS`, `CONTRADICTS`, `CONTEXTUALIZES`, `MENTIONS`, `UNKNOWN`) or between Sources (`DUPLICATES`, `DERIVES_FROM`, `CITES`). Record who/what asserted the relation, method, time and review state.
- **Finding**: claim-level assessment with status, concise rationale, evidence references when available, limitations and review state. Status is `SUPPORTED`, `CONTRADICTED`, `UNVERIFIED`, `INCONCLUSIVE` or `MISLEADING_CONTEXT`; status is not a numeric truth score. Luna reasons over retrieved evidence plus explicitly labeled source-candidate and retrieval-state context. Missing claim-linked excerpts produce `UNVERIFIED`; `INCONCLUSIVE` is reserved for materially conflicting or irreconcilable retrieved evidence. Persistence validation prevents candidates alone from supporting or contradicting a claim.
- **Evidence confidence**: a qualitative LOW/MODERATE/HIGH assessment of evidence sufficiency for a finding, with an explanation grounded in relevance, source authority, independence and disagreement. It is not a probability or calibrated truth score. HIGH is reserved for multiple relevant, independent, authoritative sources without material conflict; unresolved findings cannot be HIGH.
- **Search intent**: Luna classifies each planned query as current, historical, or balanced before dispatch. The orchestrator makes currentness explicit in the persisted provider query, retains provider publication dates on source candidates, and applies a bounded recency boost only to current-intent retrieval. Recency is separate from credibility and cannot establish evidence polarity.
- **Brief**: versioned, channel-neutral presentation assembled from findings, citations, uncertainty and next steps. Channel adapters render a short or full view from the same brief data.
- **ProcessingJob / AuditEvent**: durable stage execution, retries, errors and consequential changes. Avoid logging submitted content, phone numbers or credentials.

Keep source independence explicit: multiple sources that cite or reproduce the same underlying origin do not count as independent corroboration. Store these links and explain the count and basis; do not claim independence when lineage is unknown.

**Current URL slice:** the worker retrieves the submitted URL before claim extraction when source reading is enabled. That page is a `SUBMITTED` source and claim-extraction context, never evidence for its own claims. Search candidates are URL-normalized and deduplicated before retrieval; deterministic excerpts from separately retrieved candidates are persisted before reasoning. A small domain registry classifies source type and records claim-relevant authority scope without a trust score. Current source links are limited to explicit `CITES` hyperlinks and exact `DUPLICATES` matches by canonical URL or content hash; all other lineage remains unknown.

**Evidence localization v0.3:** bounded candidate retrieval is ordered deterministically using claim anchors, search title/query context, source role/type, matching registry scope and available reporting periods. Retrieved documents are segmented into heading-aware passages and tables; numeric, entity, unit and temporal matches rank candidate excerpts while generic boilerplate is penalized. At most two excerpts per claim/source are persisted by default, remain `UNKNOWN` until model reasoning, and must still match retrieved content. This ordering is a retrieval aid, not a credibility or truth score. `MAX_EVIDENCE_WINDOWS_PER_SOURCE_PER_CLAIM` configures the window cap; the existing source retrieval, total evidence-context and model-call budgets remain unchanged.

**Long-document acquisition v0.4:** raw retrieved source text is retained up to `MAX_RETRIEVED_DOCUMENT_CHARS` (default 60,000) independently of the 6,000-character evidence-window cap. Deterministic coarse localization selects at most `MAX_MATCHING_REGIONS_PER_CLAIM` (default 4) bounded regions per claim; the existing passage ranker then selects persisted evidence, still subject to `MAX_TOTAL_EVIDENCE_CHARS` (default 24,000). Explicit page markers present in reader text are retained as transient region location metadata. This does not increase model calls or the five-source retrieval limit.

OpenAI Luna drafts each finding's user-facing answer and evidence-confidence explanation from the supplied evidence packet. Application code validates evidence references and finding status before persistence; channel adapters render the persisted answer and confidence fields. Older findings remain `UNASSESSED`. Confidence remains qualitative until a labelled evaluation set supports calibration; never display it as a percentage.

## Domain modules and interfaces

Modules live under `backend/app/modules/<module>/` and own their domain rules. HTTP handlers validate/translate transport input and call application interfaces; they do not implement verification logic. Persistence adapters own queries. Pydantic models define external I/O; domain objects and IDs remain transport-independent.

| Module | Owns | Small interface (conceptual) |
|---|---|---|
| `ingestion` | Channel-neutral submission validation, normalization and intake | `accept(input, channel_context) -> InvestigationId` |
| `investigations` | Aggregate lifecycle, access policy, status, progress and orchestration | `create`, `get`, `request_processing`, `record_stage_result` |
| `claims` | Claim decomposition, normalization, entity/time qualifiers | `extract(submission) -> Claim[]` |
| `sources` | Query planning, candidate discovery, safe retrieval, source classification and source lineage | `discover(claims) -> Source[]`; `retrieve(source) -> RetrievedPage` |
| `evidence` | Evidence extraction and claim/source relationship recording | `extract(source, claims) -> Evidence[]`; `relate(...)` |
| `media` | Asset storage, metadata, OCR/transcript/keyframe/forensic adapters | `analyze(asset) -> MediaObservations` |
| `corroboration` | Support/contradiction evaluation, independence and gaps | `assess(claims, evidence_graph) -> Assessment[]` |
| `briefs` | Evidence-backed finding validation and brief versioning/render model | `build(investigation_id) -> Brief` |
| `channels` | Web and messaging transport adapters, webhook verification, rendering | adapter translates inbound/outbound channel events only |
| `jobs` | Idempotent stage scheduling, retry policy and durable progress | `enqueue(investigation_id, stage)` |

Internal analysis adapters are injected at module seams. A missing or failed provider yields a recorded limitation or retryable job failure; it must not silently produce invented evidence. Avoid separate deployables until independent ownership, scaling or fault isolation demonstrates a need.

## Investigation lifecycle and invariants

```text
RECEIVED → ANALYZING → RESEARCHING → CORROBORATING → COMPLETE
    │           │             │               │
    └───────────┴─────────────┴───────────────┴──> NEEDS_REVIEW
    └────────────────────────────────────────────> FAILED
```

- `RECEIVED`: normalized submission and Investigation exist; acknowledgment may be sent.
- `ANALYZING`: claims, entities and media observations are being generated.
- `RESEARCHING`: source discovery and evidence extraction are running.
- `CORROBORATING`: evidence relations, source lineage and gaps are assessed.
- `COMPLETE`: a brief is available; it may contain `UNVERIFIED` or `INCONCLUSIVE` findings.
- `NEEDS_REVIEW`: automation cannot safely proceed or human review is required; preserve partial results and explain why.
- `FAILED`: unrecoverable processing error; retain the case and safe error detail, allow retry where appropriate.

Transitions are explicit and persisted with timestamps and stage/job IDs. Repeated webhook delivery and job retries must be idempotent. A later retry does not erase prior events. Terminal cases can be explicitly reprocessed into a new run/version. Every transition and finding change is auditable. `COMPLETE` means the workflow finished, not that the claim is true.

## API and channel contract

Expose versioned `/api/v1/` endpoints. Initial web contract: create investigation from text/URL; fetch investigation and progress; list claims, sources, evidence, findings and brief; request retry when allowed. Use opaque IDs, cursor pagination for collections, request IDs, stable error codes and authorization checks in every handler. Return `202 Accepted` for processing intake with investigation ID/status; use polling initially, with server-sent events as a later progress enhancement.

WhatsApp webhook adapter verifies provider signatures, validates size/type, retrieves media server-side and delegates intake. It acknowledges promptly and sends a short result only after the shared Investigation workflow produces a brief. Web and messaging use the same access-controlled investigation records. A channel is never trusted as identity proof beyond the provider's verified identity context.

### ClickCast WhatsApp intake MVP

For the MVP, ClickCast owns Meta Embedded Signup, WhatsApp webhook registration, and inbox/bot delivery. Its HTTP API builder calls two Agent 0 endpoints; do not subscribe Agent 0 directly to Meta for the same account. Configure the builder's Authorization header with a bearer integration token. The intake endpoint accepts a stable event ID, sender identifier and message text, maps the integration to its configured workspace owner, derives a stable HMAC sender reference, and calls the shared `InvestigationService` with `Channel.WHATSAPP`. Event IDs form the idempotency key. Persist only the event ID and HMAC sender reference in submission metadata; do not persist raw sender/receiver numbers. Return `202` with the normal investigation reference/status for response mapping.

The result endpoint accepts a sender identifier and an optional investigation reference. When a reference is supplied, it checks that exact investigation; when omitted, it selects the sender's latest WhatsApp investigation in the configured workspace. It verifies the sender against the HMAC reference stored on the original submission, then returns a bounded status, journalist-facing summary, limitations and up to five findings. The summary is generated from persisted finding statuses at read time as well as at brief creation, so existing WhatsApp investigations receive current plain-language copy without a data migration. `ready` means an assessment is available; it does not mean the claim is proven. Terminal statuses (`COMPLETE`, `NEEDS_REVIEW`, `FAILED`, `CANCELLED`) are reported as ready so the bot does not label a finished investigation as pending. ClickCast must send the same sender identifier form on intake and result requests (for example, WhatsApp chat ID in both). Confirm the builder's event/message variables and response mappings using Test & Verify before live traffic.

## Security, privacy and failure model

- Private-by-default investigations; authorization enforced at each API operation. For the first release, explicitly decide single-user vs newsroom tenancy before designing authorization keys or data partitioning.
- Validate URL schemes and destinations; block private/link-local IPs and revalidate redirects to reduce SSRF risk. Enforce content-type, file-size, duration and decompression limits before processing.
- Page reading is disabled by default. When enabled, only public HTTP(S) source URLs are sent to the configured reader; keep credentials/query secrets out of submitted URLs and enforce deployment egress restrictions.
- Keep originals in private object storage with short-lived signed access. Separate originals from derived artifacts; define deletion and retention behavior before accepting sensitive production submissions.
- Minimize sender identifiers passed to downstream analysis. Encrypt transport and stored data using platform controls. Keep secrets in managed configuration, never logs or source.
- Treat retrieved pages, documents, prompts and media text as untrusted data, not instructions. Constrain model outputs to schemas and validate all evidence references before brief publication.
- Record provider/model/version and extraction method with derived evidence. Provider outages, malformed output and rate limits become explicit retryable failures or `NEEDS_REVIEW`, never fabricated confidence.
- No automatic public publication. Any future publication requires explicit user action and a separate review/permission flow.

## Deployment and repository boundaries

Keep the existing `frontend/` Next.js application. Add a separately managed `backend/` FastAPI application as the first backend deployable, with one API process and one worker process from the same codebase. Do not move current frontend routes into backend templates or duplicate domain logic in Next.js.

```text
backend/
  app/
    api/v1/                 # HTTP routes, schemas, auth dependencies
    core/                   # config, request context, logging, errors
    modules/<domain>/       # domain interface, application logic, adapters
    worker.py               # job entrypoint
  migrations/               # Alembic
  tests/unit/               # domain/application tests without DB
  tests/integration/        # API + PostgreSQL + worker contract
```

Request context includes `user_id`/tenant context when approved and `trace_id`; initialize it for HTTP and worker entrypoints. Keep module imports directed inward: handlers may call application interfaces; domain/application code cannot import API handlers; database adapters cannot import transport schemas. Enforce this with import-boundary linting or a focused dependency check once BUILD is authorized. Each module's public interface is its test seam.

## Phased delivery

1. **Foundation:** FastAPI, PostgreSQL/SQLAlchemy/Alembic, Redis/Celery, S3-compatible storage, configuration, logging, health checks, initial domain entities, lifecycle, audit and API contracts.
2. **Shared text/URL/image/video slice:** one Lead Investigator through the OpenAI Agents SDK, structured claims/source/evidence/finding/brief records, hosted web search, optional Agent Reach-aligned Jina Reader retrieval, private media upload and bounded video keyframes. Search excerpts remain candidates; only exact quotations matched against a retrieved source can support a finding.
3. **Trust and operations:** production authentication/access policy, retention/deletion, rate limits, observability, source lineage and human review controls.
4. **Media depth:** C2PA, audio transcription, OCR, visual similarity and evaluated forensic tools; each signal stays distinct from the truth assessment.
5. **Messaging channel:** WhatsApp webhook adapter and brief renderer over shared investigation interfaces.
6. **Advanced corroboration:** source-independence clustering, additional search providers, optional embeddings/pgvector and evaluated forensic models.

Each phase is a usable vertical slice with a rollback path. Do not describe phase 1 as comprehensive verification or phases 3/5 as universal deepfake detection.

## Quality, checks and rollback

- Domain tests cover valid/invalid transitions, evidence-reference invariants, status semantics, idempotency and source-lineage rules without a database.
- Integration tests cover API authorization, migrations, storage access and worker retries against test doubles/local services. No paid provider or production credentials in automated verification.
- Contract tests validate each analysis adapter and channel adapter against its internal interface; provider outage and malformed output are tested.
- Acceptance journey follows a known claim from web submission to a brief, verifies every displayed factual finding has an evidence/source chain, and verifies an insufficient-evidence case stays inconclusive.
- Each deployable has health/readiness checks and structured logs/metrics with trace IDs and no submitted content or PII. Track stage latency/failure, retry counts and evidence-reference validation failures.
- Roll back API/worker by reverting the deployment; database changes use forward-compatible Alembic migrations and documented downgrade/recovery. Keep new integrations behind configuration flags until verified.

## Open decisions before approval and BUILD

1. Replace the current website-only requirements with platform requirements: first supported input types, target users, status semantics, acceptance journey, non-goals and what claims the product may make.
2. Choose initial identity/access model: single-user private workspace or newsroom tenancy. This affects authorization and data model.
3. Confirm deployment environment, object storage, search provider, model provider, budget/quotas and whether external network retrieval is allowed.
4. Define retention/deletion, consent, residency and handling for WhatsApp phone numbers and user-submitted media.
5. Decide whether a human reviewer is required before any finding is shown as `SUPPORTED` or `CONTRADICTED`.

Production authentication, retention, deployment and provider decisions remain unresolved; they are not silently decided by the local foundation. No external provider credentials or production infrastructure are assumed here.
