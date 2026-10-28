# WhatsApp conversation stopped responding after reaching the model-call cap

**Date:** 2026-10-28 (UTC)  
**Service:** Render API, direct Meta WhatsApp adapter, ConversationService  
**Severity:** Conversation availability and recovery-copy defect

## User impact

The user sent “What's sinaps Technology” and later “Hello”. WhatsApp repeatedly returned “I'm having trouble understanding that message right now … Please try again shortly.” No investigation was created.

## Evidence

- The screenshot's 11:33 EAT greeting corresponds to 08:33 UTC.
- At 08:33:36.594 UTC, the webhook parsed one inbound text message. At 08:33:36.841 UTC, request `a7ca47edc6914105a707b16655c1578f` logged `WhatsApp conversational model unavailable category=ModelCallBudgetExceeded`.
- The usage guard runs before the structured model call. The failing turn was rejected by the conversation budget; this log does not indicate a Luna response or a WhatsApp parsing/delivery failure.
- `ModelCallBudget.begin` compared the conversation's lifetime `model_calls` count with the limit of 12. Conversation `expires_at` is refreshed on each message, but the model-call count was reset only after that same inactivity expiry. Consequently, an active conversation could consume all 12 calls and remain over budget indefinitely while the user kept messaging.
- The catch block rendered every budget exhaustion as a transient model-understanding failure and said “try again shortly,” although no reset time was given.

## Root cause

Application-side budget accounting made a lifetime cap behave as a permanent lockout for active conversations. The response text incorrectly described the exhausted budget as a temporary provider/model issue.

## Remediation

- Count WhatsApp model attempts from persisted `ModelUsageRecord` rows in a rolling 24-hour window. Preserve the existing bounded cap and investigation-specific budget behavior.
- When capped, calculate the first time a usage slot will reopen and tell the user that time in East Africa Time. Do not imply a fresh investigation started.
- Use separate outage wording for actual model invocation failures.
- Add regressions for expired calls no longer consuming quota, active-window calls enforcing the cap, and user-facing reset-time copy.

## Verification and next action

- WhatsApp suite: 49 passed. Cost-control helper suite: 10 passed. Scoped Ruff, compileall, and `git diff --check` passed.
- No schema migration is required; the existing model-usage records and their timestamps are the source of truth.
- Deployment is pending. Phase 1 remains in VERIFY. After deployment, repeat a WhatsApp greeting and claim-preview journey; confirm the model-call window and exact reset copy if the cap is reached again.

## Rollback

Revert the application commit. The prior implementation is more restrictive for long-running conversations and uses inaccurate recovery wording; no database migration or persisted-data rollback is involved.
