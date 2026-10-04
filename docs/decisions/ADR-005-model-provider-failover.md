# ADR-005: Configurable model provider with bounded failover

**Status:** Superseded by ADR-006
**Date:** 2026-10-03

> Historical record of a local-development provider-failover decision. This design is not active; ADR-006 documents the current single-OpenAI architecture.

## Context

The current OpenAI request returned HTTP 429. Agent 0 needs a second model provider for development continuity without moving claim, evidence, search, or persistence logic into a provider-specific integration.

## Decision

- Use Gemini 3.8 Flash as the configured primary model, Groq Qwen 3.8 27B as the first fallback, and OpenRouter's free Qwen 3.8 27B endpoint as the last-resort fallback.
- Keep provider selection in settings and secrets in `backend/.env`; do not hardcode credentials.
- Keep Exa as the shared application-owned search tool. Provider-hosted web search is only used for the explicitly configured OpenAI path when Exa is not configured.
- Split each provider run into a research step with search tools and a structured synthesis step without tools. This preserves the same evidence contract while accommodating provider differences in tool and JSON-schema support.
- Try the fallback after an API or Agents SDK provider error. Do not silently switch providers for application errors outside those provider boundaries.
- Cap the research agent at four turns so it can run a search and return a final research response without exhausting the loop on a follow-up tool call. Disable SDK-level automatic retries for the custom provider clients; the application advances to the next provider rather than resending hard quota failures. Limit Groq/OpenRouter output to 900 tokens per request and keep synthesis proposals concise.
- Record the successful model provider/name and attempted provider failures in the existing audit event and results response. A model response remains a proposal and must pass existing evidence/source validation before it becomes persisted evidence.
- Both providers may receive the same submission when the primary fails. Local development remains limited to public information; this choice does not authorize sensitive or production submissions.
- Gemini's no-cost API tier may use submitted content to improve Google products. Treat its free tier as public-data development only; revisit data terms before handling private newsroom material.

## Consequences

- The model layer can change without changing the investigation domain or evidence graph.
- The fallback can make another provider call and may repeat Exa searches after a mid-run provider failure.
- Free tier access can be rate limited, changed, or withdrawn; this is development resilience, not a production availability guarantee.
- OpenRouter's Qwen free endpoint supports tool calls and JSON Schema output. Free endpoint availability and provider policies still vary, and the OpenRouter free plan currently allows 50 requests/day and 20 requests/minute. Avoid sensitive submissions because the upstream inference provider processes the content.
- OpenAI remains an available provider through the same configuration, but is not in the selected Gemini → Groq → OpenRouter chain.

## Rollback

Set `AI_FALLBACK_PROVIDER=none` or select a single `AI_PRIMARY_PROVIDER`. No database migration is required; model execution details use the existing JSON audit metadata.

## References

- [OpenAI Agents SDK model providers](https://openai.github.io/openai-agents-python/models/)
- [Gemini OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai)
- [Groq OpenAI compatibility](https://console.groq.com/docs/openai)
- [OpenRouter Qwen 3.8 27B free model](https://openrouter.ai/qwen/qwen3.8-27b:free)
- [OpenRouter data handling](https://openrouter.ai/privacy)
