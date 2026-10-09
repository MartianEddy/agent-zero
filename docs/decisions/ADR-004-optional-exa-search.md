# ADR-004: Coordinated Exa and OpenAI web search

**Status: Accepted amendment by product owner on 2026-10-09.**

## Context

Agent 0 needs web-search candidates and provider provenance. The existing Lead Investigator uses OpenAI hosted web search. The product also wants Exa available without making it a runtime requirement or breaking the current no-Exa-key workflow.

## Decision

- For each planned search query, run both Exa native `POST /search` and OpenAI Responses `web_search`. They are independent, additive discovery providers; neither is a fallback for the other.
- Persist a separate `SearchTrace` for each provider/query pair, including route metadata, request reference, source list, citations, and provider-specific failure state. If one provider fails or is unconfigured, still attempt the other, record the gap, and do not describe the successful provider as a replacement for the failed one.
- Use Exa's native request with the product's bounded result count, query, and token-efficient highlights. Do not add hard domain filters without an approved source-domain policy.
- OpenAI web search is a required Responses API tool call for these searches (`tool_choice="required"`). Store its source URLs and citation annotations. Ignore its generated prose as a finding; local retrieval and evidence validation remain authoritative for Agent Zero's result.
- Route metadata carries topic, jurisdiction, freshness, source lane, and why a lane is being used. Execute primary lane traces before reference/reporting, fact-check context, and social lanes. Direct social API search remains unconfigured; such traces are marked unavailable instead of silently searching social feeds.
- Keep provider results as candidate leads. A material evidence excerpt still requires matching retrieved page text under the existing evidence policy. Deduplicate URLs for source records while preserving each provider's trace.
- Bound planned queries by `MAX_SEARCH_QUERIES`; each query invokes at most the two configured web providers. Track provider calls individually against the corresponding doubled call budget.
- Do not add a new required Python package for the first adapter; call the documented HTTP API through a narrow server-side provider module.

## Consequences

- The OpenAI SDK is a direct application dependency because the Responses web-search adapter calls it directly; its version is constrained by the existing resolved lock entry. Exa remains a small native HTTP adapter, so a separate Exa SDK is not required for this endpoint.
- If either provider key is missing, its trace reports `unavailable`; the other provider still runs. Readiness reports provider configuration separately.
- Exa and OpenAI remain replaceable provider integrations; source, evidence, and finding domain records are provider-neutral.
- Each query may incur costs at both providers. Search errors are retained independently; no provider failover occurs.
- This integration searches the public web only. It does not add social-platform scraping, browser-cookie access, or universal crawling.

## Rollback

Clear either provider key to stop that provider's calls. The remaining provider continues to operate as an explicitly partial research run; restore the key to resume two-provider searches. Preserve traces. Migration `0011_search_route_metadata` adds route metadata and should be downgraded only before any investigation relies on the column.

## References

- [Exa build-with-exa skill](../../.agents/skills/build-with-exa/SKILL.md)
- [Exa Search API](https://exa.ai/docs/reference/search)
- [OpenAI web search](https://developers.openai.com/api/docs/guides/tools-web-search)
