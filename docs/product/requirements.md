# Agent 0 platform requirements

**Status: Approved for phased implementation by product owner on 2026-10-03.** The product owner subsequently authorized the next implementation slice: a shared investigation pipeline for text, URL, image, and video inputs, including an OpenAI Agents SDK Lead Investigator adapter. This does not authorize production rollout or sensitive submissions; authentication, retention/deletion, and provider safeguards remain gated.

## Product principle

Agent 0 is an evidence-verification platform. Web, WhatsApp and future integrations are channels into one Investigation Engine. “Assume nothing. Follow the evidence.” “AI investigates. Humans decide.”

## Users and goals

- Journalists and fact-checkers need to trace claims to sources, compare independent accounts, identify contradictions and gaps, and explain uncertainty.
- Editors need a reviewable brief with source citations, evidence relationships, limitations and a clear distinction between automated analysis and human judgment.
- A user can submit text, a URL, image, video, audio or document through a supported channel and later inspect its investigation progress and result.

## Product requirements

1. Every submitted request becomes an `Investigation`, independent of its channel.
2. Investigations retain channel-neutral submissions and move through explicit, persisted processing stages with progress and recoverable failure state.
3. Claims, sources, evidence, findings and briefs are structured records with stable identifiers and auditable relationships.
4. A source is distinct from a specific evidence excerpt or observation from that source.
5. Material findings reference evidence; evidence traces to a source or media asset and records extraction method and limitations.
6. Source lineage can represent citation, copying and reposting so repeated reports are not automatically treated as independent corroboration.
7. The system preserves uncertainty. Supported, contradicted, unverified and inconclusive are distinct outcomes; technical job failure is not an investigation verdict.
8. Media provenance or forensic signals are evidence inputs, not proof of the depicted event and not standalone truth scores.
9. AI operations return validated structured data. Models cannot create source records or material findings without evidence references.
10. Investigations are private by default. No automatic publication or model training on submissions. Retention, deletion, user authentication and production identity linking must be designed before accepting production sensitive submissions.
11. The web workspace presents the full evidence trail and brief. Messaging channels send acknowledgements and concise result summaries from the same brief data.
12. Begin with a modular monolith and asynchronous workers. Add service separation only when scale, ownership or fault isolation justifies it.

## Phased scope

### Foundation (implemented)

- Python 3.12+, FastAPI, PostgreSQL, SQLAlchemy, Alembic, Redis, Celery, private S3-compatible storage abstraction, Docker Compose development services.
- Domain foundation: Investigation, Submission, ProcessingJob and AuditEvent; explicit lifecycle, API contracts, migrations, health/readiness, configuration validation, logging and targeted tests.
- No fabricated AI/search results. Analysis providers are not connected in this phase.
- Local development may use a clearly marked development identity. Production startup must reject disabled authentication until an approved auth adapter exists.

### Next implementation slice (authorized 2026-10-03)

- Shared async investigation workflow for text, URL, image, and video submissions.
- Persisted claims, sources, evidence, evidence/claim relationships, findings, and versioned brief.
- One Lead Investigator using OpenAI Agents SDK behind a provider adapter; narrow application tools; validate structured outputs and evidence references.
- Web search results are candidate sources. An optional source-reader adapter retrieves public pages; only verbatim quotations matched against the retrieved page may become source evidence. If retrieval is disabled or unavailable, Luna explains that limitation and the claim remains unverified; source candidates cannot support or contradict it.
- Before dispatch, Luna classifies each search query as `CURRENT`, `HISTORICAL`, or `BALANCED`. Current queries explicitly seek latest official updates and dated independent reporting; historical queries retain the requested period; balanced queries seek both original records and current context. Persist provider publication dates when supplied and use recency to order retrieval only for current-intent searches. Recency does not replace source relevance, authority, independence, or evidence validation.
- Agent Reach may inform channel/backend selection, but its local CLI, browser sessions, cookies and social-platform credentials are not executed or stored by the server-side investigation workflow.
- Image/video intake to private object storage with type/size validation, content hashes, and available metadata/keyframe/transcript observations. Unsupported analysis is recorded as a limitation; no universal deepfake verdict.
- API read surfaces for investigation progress, claims, sources, evidence, findings, and brief.
- Local development/test credentials only. Production auth, retention/deletion and sensitive data handling remain blocked pending separate decisions.

### Later phases

1. Authentication, access control, retention/deletion, audit operations, observability and deployment hardening before real sensitive data.
2. WhatsApp adapter using the shared investigation interfaces.
3. Evaluated advanced source-independence and synthetic-media analysis.

### ClickCast WhatsApp intake MVP (authorized 2026-10-04)

- Use ClickCast to connect and manage the WhatsApp Business account and run the bot/inbox. Its HTTP API builder calls Agent 0 endpoints; Agent 0 does not register a competing Meta webhook or store Meta access tokens.
- An incoming text or direct URL creates a `WHATSAPP` investigation through the shared service and async worker. Repeated message event IDs return the existing investigation.
- ClickCast maps the intake response into an immediate acknowledgement. A later “check result” interaction calls Agent 0's result endpoint and maps its bounded status/brief response into a WhatsApp reply.
- Sender identity is HMAC-pseudonymized; raw sender numbers are not persisted. Each ClickCast integration maps to one configured workspace owner. Configure the bearer token in the HTTP API builder's Authorization header.
- Use ClickCast Test & Verify to confirm the available message, sender and event ID variables, and response mappings before live traffic.
- This authorizes local implementation and sandboxed integration only. Production multi-user use remains blocked until authentication/tenant ownership, retention/deletion, provider handling and deployment decisions are resolved.

### Evidence answer and confidence presentation

- For every claim finding, OpenAI Luna drafts a concise, direct answer grounded in the investigation packet, along with the finding status, traceable evidence links where available, limitations, and a confidence rationale. When no source excerpt is retrieved, Luna still explains what the investigation found and could not assess; candidate sources are explicitly leads, never evidence.
- Luna classifies the request and each research query before bounded dispatch. Time-sensitive questions use a date-filtered recent-coverage lane and, when search budget allows, a separate historical-context lane. Publication dates must be shown for candidates when available; older context cannot establish current status.
- Relative dates are normalized against the investigation receipt timestamp in UTC. Because the submitter's timezone may be unknown, Luna must flag date ambiguity when it could change the answer and request clarification instead of silently guessing.
- For image-origin questions, Luna answers from recorded provenance, visual-review, and source-check outcomes. It must not infer AI generation from appearance or metadata, and must distinguish failed credential checks from credentials that were checked and absent.
- Results must call unretrieved results "sources found" or "candidates," reserve "sources reviewed" for retrieved page content, and avoid repeating the same limitation in overview, open questions, and the brief.
- Use `UNVERIFIED` when claim-linked source evidence is absent or insufficient. Reserve `INCONCLUSIVE` for materially conflicting or irreconcilable retrieved evidence. The application must downgrade any supported or contradicted model assessment that lacks eligible traceable evidence, while retaining Luna's useful explanation of the gap.
- Show evidence confidence as LOW, MODERATE, or HIGH with its rationale. This is a qualitative assessment of evidence sufficiency, not a calibrated probability that the claim is true. Do not expose a numeric confidence percentage until calibration is supported by a labelled evaluation set.
- HIGH requires multiple relevant, independent, authoritative sources and no material contradiction. UNVERIFIED and INCONCLUSIVE findings cannot receive HIGH confidence. If application validation downgrades a finding, the persisted confidence must also be downgraded.
- The web result and WhatsApp result message use the same persisted answer and confidence rationale; channel formatting must not add new factual conclusions.

## Status semantics

Lifecycle: `RECEIVED → PROCESSING → ANALYZING → RESEARCHING → CORROBORATING → GENERATING_BRIEF → COMPLETE`, with explicit `NEEDS_REVIEW`, `FAILED` and `CANCELLED` paths. A completed investigation may have an inconclusive finding. `COMPLETE` means processing finished, not that claims were established as true.

Claim assessment: `SUPPORTED`, `CONTRADICTED`, `UNVERIFIED`, `INCONCLUSIVE`; contextual media/claim labels such as `MISLEADING_CONTEXT` or `ALTERED_MEDIA` remain separate classifications rather than being overloaded into lifecycle state.

## Acceptance criteria for Foundation

- Backend installs reproducibly in an isolated Python environment and validates required settings at startup.
- Migrations create the initial relational schema; Postgres is the system of record and Redis only coordinates jobs/transient state.
- A caller can create and retrieve a private investigation, observe its state/progress, and inspect audit/job metadata through versioned API contracts.
- Lifecycle transitions are validated; retries/idempotency do not duplicate an investigation or erase audit history.
- API and worker use the same application-level investigation interface; transport code contains no verification logic.
- Health/readiness distinguish API process health from dependency readiness. Logs contain trace IDs but not submitted content, secrets or direct identifiers.
- Development Compose describes PostgreSQL, Redis and S3-compatible local object storage. Backend API/worker container build definitions are present.
- Unit and integration tests cover lifecycle invariants and API behavior; production mode cannot run with disabled auth or unsafe storage defaults.

## Non-goals for Foundation

- Real claim verification, LLM prompts, web search, WhatsApp, user-facing media upload, universal deepfake detection, vector search, public fact-check pages, newsroom tenancy or production deployment.
- Claiming that configured package versions are installed or that services are running unless the environment check proves it.
