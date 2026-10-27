# WhatsApp conversational agent implementation plan

**Status:** Approved for the first direct Meta implementation by product owner on 2026-10-27. Owner-run tests exposed conversational fallback and preview UX defects. The current fixes reject unresolved placeholder claims, remove unsupported company-specific copy, and add preview-bound Meta quick-reply actions. Focused verification passes (47 WhatsApp tests); deploy and fresh owner-run journey are required before Phase 1 acceptance. This approval does not authorize n8n adoption or ClickCast parity.
**Authoritative execution plan:** This file. The product direction and architecture rationale live in [Conversational investigative intelligence proposal](../architecture/conversational-investigative-intelligence-proposal.md); the user journey lives in [WhatsApp conversational investigation journey](../ux/whatsapp-journey-v1.md).
**Priority boundary:** Implement core conversational and investigative domain logic first. Cross-investigation knowledge, claim graphing, and evidence reuse are explicitly deferred until the core lifecycle and data ownership are implemented and validated.

## 1. Outcome

Turn WhatsApp from “any text starts an investigation” into a natural conversational entry point over Agent Zero's existing investigative system.

A user can greet Agent Zero, ask what it does, discuss a story, ask about an authorized case, or request an investigation in ordinary language. GPT Luna interprets investigation requests using bounded structured tasks. Agent Zero shows a clear claim/scope preview and requires explicit approval before it creates a persistent investigation and queues research. The approved case then runs through the existing durable worker and evidence pipeline. Commands, buttons, and references remain convenient shortcuts.

The initial implementation covers one authorized user's private cases through one selected WhatsApp transport. It does not build a cross-case knowledge network, newsroom sharing, automatic model retraining, proactive completion messages, media intake, or public multi-tenant deployment.

## 2. Repository evidence and current seams

- `backend/app/modules/channels/whatsapp.py` recognizes `RESULT` and otherwise creates an investigation from almost any text message.
- `backend/app/modules/channels/clickcast.py` similarly creates cases from incoming text/direct URLs.
- `backend/app/modules/investigations/routes.py` already exposes `/investigations/triage` and `/{investigation_id}/continue`. Triage calls `ModelGateway.extract_claims_and_queries`; continue queues the durable workflow after claim review.
- Those triage endpoints currently use the development-only `current_owner_id()` path and are not yet a WhatsApp service-to-service contract. Triage creates a temporary Investigation record and uses a random idempotency key; it is not a durable channel conversation draft abstraction.
- `backend/app/modules/investigations/investigator.py` contains GPT Luna / `ModelGateway` tasks. `backend/app/modules/investigations/orchestrator.py` and the durable worker handle research, persisted evidence and findings. Keep that pipeline as the investigative brain and source of truth.
- PostgreSQL is the existing source of truth; Celery/outbox handles durable processing. Do not place case state or evidence in n8n.
- Open blockers include authenticated identity/tenant scope, retention/deletion, triage latency, ClickCast stable event ID, cancellation semantics, and outcome/confidence contract alignment.

## 3. Target interaction contract

### Ordinary conversation

- Greeting, capability question, context sharing, and discussion do not create a case or queue research.
- A bounded GPT Luna conversation task may respond naturally or ask what the user wants to do. It must not claim that fresh research happened unless the research pipeline actually ran.
- General factual answers require a defined evidence/freshness policy. If that policy is not yet approved, keep responses to capability/context and offer to investigate rather than inventing a researched answer.
- Recognize factual question wording with or without punctuation. A short topic answer to a preceding assistant question must be acknowledged contextually rather than sent through the same generic fallback. Do not classify a subject as a company or organization without evidence, and reject model-produced placeholder claims before preview.
- Preview actions use Meta reply buttons bound to the displayed preview; text fallback remains available. Edit invalidates the previous token and proposal; Cancel discards only the draft.
- Source-backed open research questions (for example, asking for an entity's founding date) require a separate question-shaped case and evidence-grounded answer contract. They remain a follow-on rather than being coerced into an unknown-value claim.

### Investigation request

1. Parse explicit commands/interactive replies deterministically where possible; route free-form requests and relevant context to GPT Luna's structured triage task.
2. Triage either returns one targeted clarification question, a supported-scope explanation, or a proposed set of at most three claims.
3. Show the user a concise preview with exact claims and key date/place qualifiers. User may submit, edit, or cancel.
4. Any edit/clarification reruns triage as needed, increments draft version, and invalidates old approval.
5. On explicit natural-language or button confirmation, Agent Zero verifies identity, authorization, draft version/expiry, and idempotency; atomically persists one investigation and outbox job.
6. The worker uses the approved claim set. It must not silently replace or widen the user's approved scope. Any necessary scope change is shown for approval.
7. Return a stable case reference. A transport send failure does not roll back a persisted case or cause a duplicate on retry.

### Case navigation

- Natural language (“show my recent checks”, “what is happening with my investigation?”) and optional shortcuts (`STATUS <reference>`, `RESULT <reference>`) call owner-scoped read APIs.
- Exact-reference lookups never silently fall through to another case. A bare latest-case shortcut identifies the selected reference.
- A reference is not authorization. Check authenticated principal and case ownership on every read/write.
- Cancellation applies to unconfirmed drafts only until cooperative investigation cancellation is implemented.

## 4. Proposed implementation phases

### Phase 0 — Product, identity, and architecture decisions

**Purpose:** Remove design blockers before schema or channel changes.

**Tasks**

1. Approve natural conversation by default and explicit approval before persistent case/job creation.
2. Select the first channel path. Recommendation: direct Meta first because its stable provider message ID and signature verification are available in the repository path; ClickCast follows after its event-ID and conversation ownership behavior are confirmed. A product decision may choose ClickCast first instead.
3. Select one owner for inbound event verification, conversation routing/state, and outbound replies per WhatsApp account. Do not run two handlers for the same messages.
4. Define the sandbox identity principal and sender-to-owner mapping. HMAC sender pseudonymization alone is not authentication. Define how the service integration authenticates without embedding a user JWT/OpenAI key in n8n.
5. Decide draft content retention, TTL, deletion behavior, message minimization, and whether conversation context is persisted as messages or a bounded summary.
6. Resolve triage sync latency and timeout using existing open question; decide synchronous triage versus accepted asynchronous draft.
7. Decide whether a supported no-case factual answer is in the first slice. Recommended: capability/context conversation only until a safe evidence/freshness contract is defined.
8. Approve an API contract and record ADR(s) for channel identity/draft lifecycle and n8n placement. Keep n8n optional until Phase 5 value test.
9. Check SEOS BUILD gate: approved requirements/architecture, stage-blocking open questions, sandbox policy, rollback, and risk tier (MAJOR for identity/persistent user state; ARCHITECTURAL if adopting n8n).

**Exit criteria**

- Approved journey and typed API contract.
- Named first transport and single channel owner.
- Authenticated sandbox principal and authorization boundary.
- Draft TTL/retention/deletion and provider-data path recorded.
- Rollback and sandbox verification plan recorded.

### Phase 1 — Channel-neutral conversation and draft domain

**Purpose:** Represent a pending conversation action separately from a real investigation.

**Likely modules/files**

- Add a conversation/draft domain module under `backend/app/modules/` rather than placing draft logic in WhatsApp transport code.
- Add typed schemas/routes to `backend/app/modules/investigations/routes.py` or a dedicated conversations router mounted in `backend/app/main.py`.
- Add ORM models and an additive migration under `backend/app/modules/investigations/models.py` and `backend/migrations/versions/` (final ownership to settle after inspecting existing model boundaries).
- Use typed audit/idempotency records and existing PostgreSQL/transaction patterns.

**Tasks**

1. Define principal ID, channel sender pseudonym, conversation ID, draft ID, draft status, expiry, preview version, last inbound provider event ID, and minimum retained content.
2. Define draft states: `OPEN`, `NEEDS_CLARIFICATION`, `AWAITING_CONFIRMATION`, `CONFIRMED`, `CANCELLED`, `EXPIRED`, `FAILED`.
3. Persist only sender HMAC reference, not raw phone/BSUID. Do not log message/claim content or credentials.
4. Add unique constraints/idempotency for provider event receipt and each state transition/confirmation.
5. Add atomic expiry/version checks and invalidate prior previews after edits.
6. Define retention/deletion job or explicit cleanup strategy; drafts must not live forever by accident.
7. Keep conversation draft separate from Investigation so casual chat and unconfirmed previews do not look like cases.

**Acceptance evidence**

- Duplicate inbound event returns same conversation/draft result.
- Cross-principal access is denied without revealing whether another user's draft exists.
- Expired draft cannot be confirmed.
- Edit increments version; stale version cannot be confirmed.
- Cancellation removes/marks only an unconfirmed draft and creates no investigation/job.
- Database write/transaction failure creates neither partial case nor false “started” response.
- Persistence inspection confirms raw sender and secret values are absent.

### Phase 2 — GPT Luna conversation and triage APIs

**Purpose:** Reuse Luna's existing brain while controlling its actions.

**Tasks**

1. Add an authenticated channel-service API principal and route-level owner scope. Do not expose the development-only owner resolver to WhatsApp.
2. Adapt existing `/investigations/triage` behavior into the draft API, preserving the `ModelGateway.extract_claims_and_queries` schema/prompt and deterministic text normalization.
3. Add a narrowly scoped conversational task for greetings, capability explanations, and context exchange. It may return text plus typed action proposals; it has no direct DB/provider tools.
4. Treat command/button inputs (`HELP`, submit/edit/cancel, status/result) as typed intents; natural language remains supported.
5. Triage returns either one clarification question, unsupported-scope guidance, or a preview with proposed claim(s), qualifiers, and relevant limitations. It does not create an Investigation or dispatch work.
6. Clarification/edit updates the same draft and reruns triage; changed preview version invalidates previous approval.
7. For Luna timeout/unavailable/invalid structured output, return a safe retry message, preserve draft where appropriate, and create no investigation.
8. Add bounded token/input/output limits, rate/cost controls for the authenticated channel principal, request IDs and privacy-safe task telemetry.

**Acceptance evidence**

- Synthetic cases: greeting, capability question, story discussion, ambiguous claim, clear claim, compound claim, opinion/prediction, unsupported request, URL, relative date, prompt injection, malformed model output, model timeout.
- Greeting/discussion does not call costly research stages or create a case.
- Ambiguous input asks one useful question and creates no investigation.
- Clear explicit investigation request produces a preview but no job.
- Luna-produced factual claims remain proposals until user approval.
- Every model task is bounded and records safe provider/model/task metadata without prompt or user-content logging.

### Phase 3 — Idempotent confirmation and existing worker integration

**Purpose:** Convert an approved preview into exactly one case through the existing pipeline.

**Tasks**

1. Implement `confirm_draft(draft_id, preview_version, confirmation_event_id)` in the application/domain boundary.
2. In one transaction, validate principal/ownership, state/version/expiry, record approval, create Investigation from approved claims, create durable ProcessingJob and OutboxEvent, and mark the draft confirmed.
3. Ensure repeated confirmation or webhook retries return the same case/reference.
4. Adapt worker input so approved claims are authoritative. Preserve original request and preview/approval history. If worker requires internal query planning, use Luna only within current budgets and do not silently change the user-approved proposition.
5. Return `202`/equivalent only after case and outbox are durable. Outbound WhatsApp send is a separate side effect.
6. Reuse existing `InvestigationService`, outbox dispatcher, Celery worker, orchestrator, evidence validation, result projection, and source lanes. Do not create a second n8n investigation pipeline.
7. Keep “cancel investigation” disabled until a cooperative cancellation endpoint/worker behavior is designed; `CANCEL` on a draft remains supported.

**Acceptance evidence**

- Concurrent confirmation requests produce one Investigation and one queued job.
- API timeout after database commit followed by retry returns the existing reference.
- Outbox dispatch retries do not duplicate processing jobs or overwrite lifecycle history.
- A confirmed claim is visible on the case and remains the analysis scope.
- Failure before transaction commit leaves no case; failure after commit is recoverable from outbox.
- Acknowledgement send failure never results in a second case.

### Phase 4 — First WhatsApp journey and case retrieval

**Purpose:** Complete one real sandbox journey on the selected transport.

**Tasks**

1. Update the selected transport adapter to normalize inbound event, authenticate/verify it, dedupe it, and call the conversation API; remove direct create-on-any-text behavior behind a controlled rollout flag.
2. Render natural, short messages for greeting, clarification, preview, confirmation, processing, needs-review, complete, failure, unsupported input, and uncertain delivery.
3. Add WhatsApp interactive submit/edit/cancel controls if supported by the selected account/provider; keep text and natural-language fallback. Do not assume the interactive capability without a sandbox probe.
4. Add owner-scoped “my recent investigations” and exact status/result reads; use persisted API data, not n8n cached fields.
5. Keep result summary bounded with evidence caveats, reference, and next step. Do not expose findings across owners.
6. Reconcile Meta delivery callbacks with an allowlisted delivery state; never describe Graph API acceptance as proof the recipient received the message.
7. Do not add proactive completion push in this phase; delivery window/template and recipient routing remain separate unresolved work.

**Acceptance evidence**

- Full real sandbox path: greeting → natural investigation request → Luna preview/clarification → approve → worker queued/completed → natural status/result retrieval.
- Complete journey includes user-visible screenshots/transcript and persisted case reference.
- Duplicate Meta callback, invalid signature, unsupported event, send failure, stale draft, unknown reference, unauthorized reference, and unavailable Luna are exercised with safe expected outcomes.
- Follow SEOS health checks before and after resource-heavy verification; if blocked, stop resource-heavy verification and record the block.

### Phase 5 — Optional n8n proof of value

**Purpose:** Decide whether n8n improves operations after the Agent Zero conversation contract works.

**Tasks**

1. Create a non-production workflow using synthetic data and private authenticated Agent Zero conversation APIs.
2. Have n8n route structured intents/results and channel replies only; keep durable draft/case/evidence state in Agent Zero.
3. Use scoped credentials, environment separation, secret rotation, execution-history minimization/redaction, retention limits, alerting and a kill switch.
4. Prove raw webhook signature validation stays at one clearly owned boundary. If n8n is to receive Meta webhooks directly, it becomes the transport owner and must replace—not duplicate—the existing path after a separate security review.
5. Compare operational editability, maintenance, recovery and failure rate with the direct adapter. Reject n8n if benefits do not justify its service/data/security burden.
6. Record architecture/security review and ADR before adopting it beyond the proof.

**Acceptance evidence**

- n8n restart, duplicate trigger, timeout after Agent Zero commit, Agent Zero outage, revoked credential, malformed response, expired draft and kill switch do not create duplicate cases or lose authoritative state.
- No direct database access, research calls, or independent GPT claim assessment from n8n.
- Workflow history contains no unnecessary raw message/sender data.
- Documented recovery and removal path returns channel to the direct integration without dual-active handlers.

### Phase 6 — ClickCast parity (after first channel is stable)

**Purpose:** Apply the same conversation contract to the second transport.

**Tasks**

1. Verify current ClickCast payload fields, stable event ID availability, authentication/retry behavior, and response mapping in its test environment.
2. Reuse Agent Zero conversation APIs; do not duplicate triage or investigation domain logic in ClickCast or n8n.
3. If no stable inbound event ID is available, design and review a safe dedupe strategy before claiming exactly-once behavior. A content hash must not collapse two intentional identical user requests without a product rule.
4. Contract-test both channel adapters against identical domain outcomes and authorization behavior.

**Acceptance evidence**

- Same natural conversation/confirmation/result contract across both transports.
- Documented behavior under ClickCast retry without event ID and reply mapping failure.
- Only one active bot/workflow owner for each connected account.

## 5. Future enhancement — cross-investigation knowledge (deferred)

Cross-case intelligence is explicitly **not part of Phases 0–6**. Do not add a global claim registry, evidence reuse, cross-owner search, graph database, vector index, recurring-claim ranking, or automatic finding updates while the core domain is still being implemented.

After the conversational and investigation lifecycle is stable, propose a separate discovery/architecture phase for:

- Normalized claim variants while retaining original wording and provenance.
- Reusable evidence/source registry with access and source-dependency policy.
- Candidate relationships among investigations, claims, sources, entities and events.
- Versioned assessment history and impact review when new evidence appears.
- Same-owner/workspace boundaries first; cross-organization reuse only after explicit governance.
- Evaluation for false matches, duplicate-origin detection, stale evidence, contradiction preservation, access filtering, and popularity-vs-evidence separation.

A repeated allegation is a prioritization signal, not corroboration. Prior findings are historical assessments, not ground truth. Any later cross-case system must preserve provenance and access boundaries and must not silently alter prior results.

## 6. Rollout, measurement, and recovery

### Rollout

- Start with feature flag for the selected sandbox channel.
- Keep a documented fallback that pauses new conversational intake while preserving authorized read access to existing investigations.
- Expand to the second transport only after Phase 4 acceptance evidence and independent review.
- Do not enable sensitive or public multi-user traffic until authentication/tenancy, retention/deletion, provider handling, deployment, abuse/cost limits and incident procedures are resolved.

### Measures

- Accidental case creation (target: zero in acceptance suite).
- Preview-to-confirm and clarification resolution rates.
- Triage latency, timeout/error rate and cost per conversation/confirmed case.
- Duplicate case rate under webhook and confirmation retries (target: zero).
- Authorization denial and cross-owner access attempts (no data disclosure).
- Case status/result retrieval success and provider delivery failure rate.
- User ability to complete the flow without memorizing commands (usability evidence required).

Do not equate message delivery, processing completion, user interest, count of related cases, or raw model confidence with truth.

### Recovery

- Disable new draft/confirm intake through feature flag or channel config; preserve case reads and audit state.
- Revert application code without deleting confirmed investigations. Database rollback must preserve data or use additive migration rollback policy; do not drop tables containing drafts/audit without an approved retention/export plan.
- If n8n is used, disable its trigger/credential and ensure exactly one fallback route is active.
- Existing investigations continue under current worker lifecycle. Do not attempt destructive migration or data cleanup as part of rollback.

## 7. Decisions required before BUILD

1. Select first transport (recommended direct Meta; ClickCast may be selected if its conversational capabilities are confirmed).
2. Approve private authorized-user scope and sandbox principal; production identity/tenancy remains separate gate.
3. Approve what natural conversational answers are allowed before a case exists.
4. Approve draft/message retention, TTL and deletion behavior.
5. Decide synchronous vs asynchronous Luna triage after latency measurement.
6. Confirm how approved claims bind to worker analysis scope.
7. Decide whether n8n is deferred until Phase 5 proof (recommended) and who operates it if adopted.
8. Resolve result status/confidence contract before changing WhatsApp outcome copy.
9. Read and follow `docs/engineering/testing/sandbox.md` before any paid or irreversible provider verification.

## 8. Verification boundary

Phase 1 code is implemented, including durable inbound receipts before Luna, preview-specific approval codes, typed natural confirmation, the channel-neutral conversation service, capability/context-only no-case replies, and the default-off rollout flag. Static compilation, scoped Ruff, and `git diff --check` pass. Automated tests and the full sandbox journey remain incomplete because `sinaps health` reports 6% free disk and classifies verification as blocked; the owner will perform the live WhatsApp journey. The existing persistent database must not be changed during this work; migrations `0015`, `0016`, and `0017` must be applied to an isolated sandbox before integration verification. Verification must include focused unit/integration cases, idempotency/concurrency behavior, a complete sandboxed user journey, security/access checks, privacy review, resource-health checks, and an independent review appropriate to the final risk tier. Do not advance to the next implementation phase until the recorded blockers and high-priority findings are resolved or explicitly accepted.
