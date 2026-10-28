# ADR-009: Keep WhatsApp conversation state separate from investigations

**Status:** Accepted for the first direct Meta implementation by product owner on 2026-10-27. This authorizes local/sandbox code changes only; it does not authorize production multi-user rollout, a live provider smoke test, n8n adoption, or ClickCast parity.

## Context

The direct Meta and ClickCast handlers currently turn most inbound text into an investigation immediately. The repository already has GPT Luna structured claim triage, clarification behavior, a durable Agent Zero worker, and persisted evidence assessment. WhatsApp should support natural conversation while requiring approval before a persistent case and research job are created.

The first slice must distinguish conversational state from investigative state. A greeting, draft, clarification, or claim preview is not an Investigation. The existing Investigation aggregate remains the durable source of truth only after user confirmation.

## Decision

- Start with the direct Meta path. Keep raw-body signature verification at the existing webhook boundary. Do not run ClickCast automation as a competing conversation handler for the same WhatsApp account.
- Keep conversation state and draft transitions in the channel-neutral `ConversationService` (`app.modules.conversations`), behind a thin Meta adapter that authenticates and normalizes inbound events. Persist short-lived state separately from investigations, keyed by configured owner plus HMAC sender reference; store bounded context, a preview, model usage, and durable inbound receipts, never the raw sender number.
- Use GPT Luna through `ModelGateway` for typed natural-turn interpretation (`CONFIRM_DRAFT` included) and structured claim/query proposals. Luna proposes intent and content; the application handles authorization, preview version/expiry, confirmation-code comparison, commands, state transitions, idempotency, persistence, and final case creation. Each inbound provider event is uniquely claimed and committed before model work; duplicate deliveries replay the saved reply or receive a retryable in-progress response.
- Do not create an Investigation or enqueue research before explicit user approval. Store the approved claim set and Luna query metadata on confirmation, then atomically create the Investigation, claims, planned provider traces, ProcessingJob, and OutboxEvent. Continue with the existing worker and evidence pipeline.
- Conversation context and inbound receipts expire after 24 hours and are deleted with the conversation by a scheduled cleanup task. A pending preview expires after 30 minutes. Each displayed preview has a random confirmation code; approval must include the code displayed with that preview, so an older approval cannot approve a replacement preview. Local/sandbox scope uses the configured single workspace owner; HMAC sender matching is not production authentication or tenant isolation.
- Natural case-list/status/result requests are supported with owner/sender-scoped reads. Text commands and reference lookups remain shortcuts. References do not grant access.
- Keep n8n optional and out of this implementation. It may be evaluated later as routing glue but must not own case state, call the database, or duplicate Luna/research logic.

## Consequences

- WhatsApp conversation state and Investigation records are separate persistence/domain concepts. Confirmation is the only transition that creates an Investigation.
- GPT Luna usage can be associated with an expiring conversation before a case exists; usage rows cascade when the conversation expires.
- At confirmation, planned search traces prevent the worker from re-extracting a different claim set. The worker retains its existing bounded route and evidence validation rules.
- Webhook handling currently waits for the bounded Luna response. Measure triage latency and callback timeout behavior before production or increasing traffic; if it does not fit the provider response window, move the turn to an async conversation job with a reviewed recipient/delivery design.
- The confirmation interface uses Meta reply buttons for Submit claim, Edit claim, and Cancel, with text fallbacks. Submit button IDs include the exact preview token; text approval must include the same code. Edit clears the old proposal and approval code before accepting a correction. No-case factual answers do not use model memory. General source-backed profiles and open research questions remain out of scope until their evidence and entity-resolution contract is designed. Proactive completion pushes, media intake, ClickCast parity, and cross-investigation knowledge are deferred.
- For ordinary `CONVERSATION` turns, the service sends GPT Luna's bounded natural-language reply directly. The prompt restricts factual answers without retrieved evidence and repeats no canned fallback; deterministic application logic still owns action routing, authorization, state changes, and explicit case approval. A typed `START`/`SUBMIT` with no pending preview receives a direct no-preview explanation without a model request.
- Enforce WhatsApp conversation model-call limits over a rolling 24-hour window from persisted usage records. If the cap is reached, report the next reset time instead of presenting a long budget wait as a transient error.
- Migrations `0016_whatsapp_conversation` and `0017_whatsapp_inbound_receipts` are required. The existing persistent local database remains at `0009`; do not run the new application against that database until the migration chain is applied at a deliberate maintenance point.
- The owner reports that the OpenAI `401` was resolved by updating the provider key on 2026-10-27. This review did not make a live provider call, so the repair is not independently verified here. On provider failure, the application safely replies that no investigation was started; no alternate investigation pipeline is used.

## Rollback

Set `WHATSAPP_CONVERSATION_ENABLED=false` to pause new direct Meta conversation intake, or disable the webhook subscription, then revert the application code. Existing confirmed Investigation records remain intact and readable. Keep migrations `0016` and `0017` unless no conversation or model-usage rows exist and a deliberate down-migration is approved; the cleanup task removes only expired conversation state and its associated conversation usage records.
