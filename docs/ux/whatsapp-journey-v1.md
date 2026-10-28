# WhatsApp conversation and investigation journey

**Status:** Phase 1 interaction contract; source-backed open research questions are a proposed follow-on capability.
**Detailed proposal:** [Conversational investigative intelligence proposal](../architecture/conversational-investigative-intelligence-proposal.md).

## Experience principle

Let people speak naturally. Keep discussion, research questions, and claim investigations distinct. Never imply that a source was checked before retrieval, and never turn an unknown answer into an invented claim. Creating an investigation requires approval of the exact preview.

## Phase 1 journey: claim investigation

1. **Start a conversation.** GPT Luna writes a short response that fits the user's actual message and recent context. The application sends that reply directly; it does not replace ordinary conversation with a fixed greeting/topic script. No case or research job is created.
2. **Clarify the task.** If the user names a subject without a checkable claim, Luna asks which specific fact or claim they want checked. Do not classify the subject as a company, person, event, or other entity type without evidence.
3. **Triage the claim.** GPT Luna proposes a specific claim or asks one targeted clarification. The application rejects generic placeholders such as “a particular date”; it does not display them as claims.
4. **Review the preview.** Show the exact proposed claim(s), make clear that no research has started, then offer **Submit claim**, **Edit claim**, and **Cancel** reply buttons. The submit button ID contains the current preview token, so tapping it approves only that preview. Keep `SUBMIT <code>`, `EDIT <correction>`, and `CANCEL` as text fallbacks.
5. **Edit or cancel.** Edit invalidates the old preview and asks for a correction; the agent then creates a new preview that needs fresh approval. Cancel discards only the unconfirmed draft.
6. **Start the case.** On a valid submit action, validate the token, owner, draft expiry, and idempotency; persist one case and queue the existing durable worker. Return the case reference.
7. **Return to the case.** The user can ask naturally for status/results or use `STATUS <reference>` and `RESULT <reference>`. Every read is owner-scoped; a reference alone grants no access.

## Current behavior for open-ended factual questions

Phase 1 supports claim checking with public evidence. It does not yet provide source-backed general profiles or answer unknown questions such as “When was this entity founded?” as a research question. Luna should explain this briefly in language that fits the conversation, say it has not checked the answer, and ask what specific fact or claim the user wants verified. It must not invent a proposition or entity type, repeat the same canned disclaimer after each rephrase, or start an investigation while the scope is unresolved.

## Proposed follow-on: source-backed research questions

Add a distinct research-question mode for requests such as “When was Sinaps Technology founded?” It should:

- Preserve the question as a question rather than invent a declarative claim with an unknown date.
- Resolve the named subject from public sources after approval. If sources point to multiple plausible entities, ask the user for a location or URL before continuing.
- Describe entity type only when a retrieved, cited source supports that description.
- Preview the research question and proposed scope before creating a case.
- Return the answer with citations, source dates, unresolved ambiguity, and a clear “not established” state when evidence is insufficient.

This needs a product/architecture decision about question-shaped cases and evidence-grounded answer rendering. It is not implemented by the claim-only Phase 1 pipeline.

## Conversation states and recovery

| State | User-facing behavior | Available action |
|---|---|---|
| Conversation | Natural greeting, capability or scope response; no research implied | Ask a question or provide a specific claim |
| Needs clarification | One precise question; no claim preview and no case | Reply with missing detail or Cancel |
| Awaiting confirmation | Exact claim preview; research has not started | Submit claim, Edit claim, or Cancel |
| Processing | Case reference and processing status | Ask for status later |
| Assessment ready | Evidence-linked assessment and limitations | Read result or open the authorized case |
| Needs human review | State that no final assessment is available and explain the next supported step | Open the referenced case |
| AI reply limit reached | Explain that no investigation started and show when a conversational model-call slot will reopen, in EAT | Try again after the displayed reset time |

Button replies must be idempotent and preview-bound. If interactive messages are unavailable, the text in the preview must include the matching confirmation code and text alternatives. Replaying a webhook may resend a text version; it must never approve a different preview.

## UX constraints

- Do not create cases from greetings, general discussion, or ambiguous intent.
- Recognize question wording without requiring punctuation.
- Do not answer from model memory or describe a subject as a company/organization unless retrieved evidence supports it.
- Do not present a model placeholder as a claim or as a user-visible fact.
- Treat user statements and submitted links as context until evidence is retrieved and assessed.
- Distinguish draft cancellation from cancellation of a persisted investigation; the latter requires backend support.
- Use Luna's conversational `reply` directly for `CONVERSATION` turns. The application controls side effects and enforces explicit preview approval, but it must not rewrite ordinary Luna replies into a canned template.
- Keep natural language as the main path and buttons/references as shortcuts.
- Do not expose prior cases or cross-case material without authorization.
