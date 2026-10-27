# WhatsApp conversational investigation journey

**Status:** Draft UX direction; implementation requires product and architecture approval.
**Detailed proposal:** [Conversational investigative intelligence proposal](../architecture/conversational-investigative-intelligence-proposal.md).

## Experience principle

Natural conversation by default. Explicit approval before creating a persistent investigation. The user should not need to learn commands to talk with Agent Zero; buttons and references are shortcuts. Conversation about a claim does not itself start research.

## Primary journey

1. The user greets Agent Zero, asks what it can do, or discusses a story. Agent Zero responds naturally within its supported evidence and freshness limits. No investigation is created.
2. The user asks Agent Zero to investigate a claim. GPT Luna uses the existing structured triage capability to identify the proposed claim and ask for a missing detail when needed.
3. Agent Zero presents the claim and scope for review, with **Submit investigation**, **Edit**, and **Cancel** actions. No research job starts yet.
4. On explicit user approval, Agent Zero validates owner and draft version, creates one investigation idempotently, queues the existing durable worker, and returns a persistent reference.
5. The user can ask naturally for progress or their investigations, or use `STATUS <reference>` / `RESULT <reference>`. Every read is authorized; a reference alone grants no access.
6. Agent Zero answers from persisted case state. Results distinguish assessment, evidence quality, coverage, uncertainty and limitations. Processing completion is not proof or editorial approval.

## UX constraints

- Do not create cases from greetings, general discussion, or ambiguous intent.
- Do not imply that fresh research occurred if it did not.
- Treat submitted links and user statements as context until evidence is retrieved and validated.
- Distinguish cancelling a draft from cancelling a persisted investigation; the latter requires backend support.
- Keep natural language as the main path and commands as optional shortcuts.
- Do not expose prior cases or cross-case material without authorization.

The detailed proposal documents current implementation gaps, GPT Luna and n8n boundaries, memory layers, authorization, the future evidence knowledge network, phased implementation, evaluation, risks, and open decisions. It is a proposal, not BUILD authorization.
