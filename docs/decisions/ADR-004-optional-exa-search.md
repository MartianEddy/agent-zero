# ADR-004: Optional Exa web-search tool

**Status: Accepted for the local v1 implementation by product owner on 2026-10-03.**

## Context

Agent 0 needs web-search candidates and provider provenance. The existing Lead Investigator uses OpenAI hosted web search. The product also wants Exa available without making it a runtime requirement or breaking the current no-Exa-key workflow.

## Decision

- Exa is an optional search tool exposed to the existing OpenAI Agents SDK Lead Investigator when `EXA_API_KEY` is non-empty.
- Use Exa's native `POST /search` endpoint with its recommended minimal request: `query`, `type: "auto"`, and `contents: {"highlights": true}`. Do not add category, domain, result-count, or freshness filters without a product requirement.
- Keep OpenAI hosted web search available. If `EXA_API_KEY` is blank, it remains the only web-search tool. When Exa is configured, instruct the investigator to prefer Exa and use OpenAI search if the Exa tool reports an error.
- Persist Exa query, request reference, and provider-returned result metadata/highlights separately from the investigator's structured source proposal. Mark a source as discovered by a provider only when its URL exactly matches that provider's returned URL.
- Treat Exa highlights and all search results as candidate leads. A material evidence excerpt still requires matching independently retrieved page text under the existing evidence policy.
- Do not add a new required Python package for the first adapter; call the documented HTTP API through a narrow server-side provider module.

## Consequences

- Local investigations continue when the Exa key is absent; no `EXA_API_KEY` value is committed.
- Exa and OpenAI remain replaceable provider integrations; source, evidence, and finding domain records are provider-neutral.
- Exa usage may add provider cost. Search errors are retained in provider traces, and the Investigator can fall back to OpenAI web search.
- This integration searches the public web only. It does not add social-platform scraping, browser-cookie access, or universal crawling.

## Rollback

Clear `EXA_API_KEY` in the worker environment to disable Exa; OpenAI hosted web search becomes the normal path again. Preserve existing search traces. No migration rollback is needed because the current search-trace schema already supports multiple providers.

## References

- [Exa build-with-exa skill](../../.agents/skills/build-with-exa/SKILL.md)
- [Exa Search API](https://exa.ai/docs/reference/search)
- [OpenAI web search](https://developers.openai.com/api/docs/guides/tools-web-search)
