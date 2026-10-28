# WhatsApp factual-question fallback loop

**Date:** 2026-10-27 (UTC)  
**Service:** Render API, direct Meta WhatsApp adapter, ConversationService  
**Severity:** Conversation quality defect; no investigation was created

## User impact

In the owner-run journey, “What is Sinaps Technology” received a generic prompt asking what to investigate. The follow-up “Sinaps Technology” received the same generic prompt, so the conversation did not advance. A prior case’s “needs human review” result was also visible above the conversation and was unrelated to these turns.

## Evidence

- The API deployment for commit `d6f6e2d61eb9c4061d75e23d60b9ab39029383bc` became live at 14:59:24 UTC, before the test.
- At 15:02:55 UTC, the API parsed one inbound text message, called `POST https://api.openai.com/v1/responses` and received HTTP 200, then returned HTTP 200 from the WhatsApp webhook.
- At 15:03:20 UTC, the API parsed the second inbound text message, called OpenAI, and handled the message. Meta status callbacks reported sent/delivered for the replies. No provider authentication or delivery failure was logged in this window.
- The screenshot’s response exactly matches `_conversation_reply`’s application fallback. That helper only recognized a factual question if the text contained `?`; WhatsApp input was “What is Sinaps Technology” without punctuation. The short follow-up also had no punctuation and fell through to the same generic string.
- `WhatsAppTurnOutput.reply` is not used for `CONVERSATION` responses. Luna produces structured intent plus a draft reply, but the application deliberately selects its own reply to maintain the no-case factual-answer policy. Render logs did not record Luna’s structured intent or reply text, so the exact model intent cannot be established from logs. The final user-visible wording is nevertheless attributable to the deterministic application fallback.

## Root cause

This was an application behavior defect, not a replaced model, stale deployment, OpenAI 401, webhook parsing failure, or WhatsApp delivery failure. The deployment was current and both model requests succeeded. The breakpoint was after structured model interpretation, where the service discarded the conversational reply and rendered a punctuation-dependent fallback.

## Remediation

- Pass Luna's `CONVERSATION` reply through to WhatsApp rather than replacing it with a canned application response. The prompt asks Luna to respond naturally to the latest turn and context, avoid repeating a limitation already explained, and ask one useful follow-up at most.
- Route broad identity/background questions to conversation unless the user asks for a specific factual check. Luna must not guess from model memory, infer an entity type from its name, or claim fresh research; source-backed general overviews remain a separate product capability to design.
- Handle `Start`/`Submit` with no pending preview as a clear missing-preview state, without calling Luna or creating an investigation.
- Keep authorization, intent handling, preview confirmation, case creation, and all side effects under application control.
- Log the model’s typed intent and whether a draft is pending without logging message text, model reply text, sender identifiers, or credentials.
- Add regression tests that verify Luna's response is sent directly, ordinary conversation creates no case, and `Start` without a preview explains the next step.

## Verification and next action

- Focused WhatsApp suite passes: 48 tests. Investigator prompt tests pass: 5 tests. Scoped Ruff, compilation, and `git diff --check` pass.
- Direct Luna reply and no-preview `Start` regression tests are included. Commit `83b37a3abed1a0edd2540ae5f2b2a7582abc50ab` is live on Render as `dep-dbgr3sec6qcc73ce6fmg`; `/api/v1/ready` reports ready with database, Redis, object storage, investigation engine, OpenAI provider, and web search configured.
- Have the owner repeat a natural conversation test after deployment. Phase 1 remains in VERIFY until the live journey and remaining migration/preview/approval/status evidence are recorded.
- Decide separately whether WhatsApp should support source-backed general entity/company overviews. This remediation does not add memory-based factual answers or start investigations automatically.

## Rollback

The fix changes only conversational response selection and adds no schema or provider change. Roll back by reverting the application commit; the existing `WHATSAPP_CONVERSATION_ENABLED` flag remains the operational intake stop if needed.
