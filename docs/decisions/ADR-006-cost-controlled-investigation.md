# ADR-006: Cost-controlled, evidence-first investigation workflow

**Status:** Accepted for local development
**Date:** 2026-10-03

## Context

The previous provider fallback restarted a model-directed research/tool workflow for each provider. This multiplied requests and delayed persistence of claims, sources and evidence until a complete proposal existed.

## Decision

- The application owns the workflow: structured claim/query planning, bounded Exa search, source deduplication/retrieval, deterministic excerpt selection, evidence persistence, bounded evidence reasoning and deterministic brief formatting.
- OpenAI is the only configured model provider, accessed through the thin `ModelGateway`; provider adapters and routing branches for Gemini, Groq and OpenRouter are removed.
- Use configurable model ID `OPENAI_MODEL`, defaulting to `gpt-6-luna`; use the Agents SDK Responses API adapter because Luna documents its reasoning and structured-output support on that endpoint.
- `OPENAI_REASONING_EFFORT` centralizes reasoning effort and defaults to `low` for both bounded operations.
- Structured claim/query planning and evidence reasoning are separate calls. There is no model-controlled search loop. Evidence reasoning only runs after retrieved-source excerpts are persisted.
- Budgets are configurable: 4 model calls/investigation, 3 claims, 5 queries, 5 results/query, 8 sources, 5 retrieved sources, 6,000 chars/source, 24,000 evidence chars total, 4 model images, 700 planning tokens, 900 reasoning tokens, 1 retry, bounded retry-after, and a 45-second model request timeout.
- Usage tables record attempted model calls and exact provider token usage when available; unavailable usage stays null. Investigation counters record search and source activity.
- Each successful stage commits its artifacts before moving forward. `POST /api/v1/investigations/{id}/retry` reuses persisted plans, sources, retrieved content and evidence.
- Provider failure messages returned to users are generic; safe categories and request diagnostics are kept in server logs/audit records.
- Supported or contradicted findings require a matching persisted evidence relationship. Brief rendering uses application code and adds no model call.
- URL submissions are retrieved before claim extraction when the configured reader is enabled. The page is persisted as `SUBMITTED` context and cannot supply verification evidence for its own claims; only separately discovered and retrieved sources enter the evidence packet.
- A small domain registry provides source type, jurisdiction and claim-topic authority scope without a credibility score. Relationships are limited to explicit retrieved-page citations and exact duplicates by canonical URL or content hash. `CITES` alone does not imply derivation; uncertain lineage remains unknown.
- Retrieved source metadata and honest retrieval status/failure codes are returned through the results API. The frontend labels the submitted article and surfaces source type, role, publisher, author/date and detected relationships.

## Consequences

- Migrations `0005_cost_controlled_pipeline` and `0006_source_intelligence` add usage tracking, reusable retrieved content, source metadata and relational source relationships.
- Retrying remains within the investigation's lifetime model-call budget; completed searches and retrieval are not repeated.
- Source retrieval remains disabled unless explicitly configured. In that case, search results are candidates and do not become evidence.
- This work does not establish production authentication, retention/deletion, provider data terms or operational pricing. Paid API tests remain prohibited unless separately authorized.

## Rollback

Stop API and worker use of the new source fields before reverting the application. Downgrade `0006_source_intelligence` only after confirming source relationship and metadata data can be removed; retain `0005_cost_controlled_pipeline` unless its usage/retrieved-content data is separately approved for removal.
