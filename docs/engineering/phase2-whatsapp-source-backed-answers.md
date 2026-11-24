# Phase 2: source-backed conversational answers

**Status:** Implemented locally and focused checks passed; live deployment and acceptance pending.

## Outcome

Let a WhatsApp user ask a clear factual question and receive a short answer based on a fresh web search, with clickable source links, without accidentally creating an investigation. Keep the existing explicit investigation path for users who ask Agent Zero to investigate or verify a claim.

Acceptance criteria:

- A clear factual question gets a short, current answer with at least one source link and a clear “quick answer” scope label.
- Ambiguous entities trigger one useful clarification question and no search or case.
- Greetings, opinions, unsupported questions, story discussion, and investigation requests do not use the quick-answer route.
- No quick answer creates an Investigation, ProcessingJob, or evidence assessment.
- OpenAI web search is unavailable during intent classification and runs only after the application selects the quick-answer route; the answer task is bounded to one search action, low search context, and the conversation's existing model-call budget.
- If web search fails or returns no usable source citations, Agent Zero says it could not source the answer and offers `INVESTIGATE` as the next step; it does not answer from model memory.
- The answer shows direct source links and says a quick answer is not a full investigation.
- The formatted WhatsApp reply stays within the provider's 4,096-character text limit, even when search returns long URLs.

## Approach

Extend the existing typed WhatsApp `ModelGateway` task with a `FACTUAL_ANSWER_REQUEST` intent, then use a separate answer task with OpenAI's hosted `WebSearchTool`. Application routing ensures the search tool is not even available during intent classification or on any other intent. The answer task permits at most one search action. Extract citations from raw Responses output, discard unsafe/non-HTTP URLs, and render only if at least one citation survives. Application code still owns every side effect.

This reuses the existing OpenAI model credential, conversation usage records, 24-hour budget, webhook signature boundary, sender-scoped conversation context, and Meta text reply. It adds no database schema, second provider, persistent case, or research worker. The search result and answer remain within the existing expiring conversation context.

## Decisions and boundaries

- Ordinary factual questions are answered only with a fresh web-search-backed response. No factual answer comes from model memory alone.
- A quick answer is a convenience response, not an assessment. It does not claim source independence, exhaustive coverage, or an investigation verdict.
- Broad identity questions with an ambiguous entity require location or a public URL first. The current context can resolve short follow-ups such as “Kenya” without creating a case.
- An explicit “investigate,” “verify,” or “check whether this claim is true” continues to show the existing approval preview and starts no work until approval.
- The existing single-owner WhatsApp sandbox boundary remains. This change does not enable public multi-user traffic or ClickCast.
- Web-search failure, no citations, invalid structured output, model budget exhaustion, and webhook timeout must fail closed without making an unsourced assertion or creating a case. Classification and answer requests each have a seven-second bound; the forwarding Worker allows up to 18 seconds for their combined processing.

## Verification

- Added regression coverage for cited answers, URL filtering, no-citation fallback, and no-case side effects.
- WhatsApp conversation suite: 61 passed. Cloudflare webhook worker suite: 9 passed.
- Ruff import checks, scoped Ruff outside existing line-length violations in the investigator module, and `git diff --check` passed.
- Live acceptance after deployment: ask one stable factual question, confirm a short answer and clickable source links arrive, then confirm `HISTORY` remains unchanged.

## Recovery

The existing `WHATSAPP_CONVERSATION_ENABLED` switch disables the conversational WhatsApp route as a whole; a code revert is the narrower rollback for this capability. No persisted investigations or schema changes are created by the quick-answer route; existing cases and reads remain available.
