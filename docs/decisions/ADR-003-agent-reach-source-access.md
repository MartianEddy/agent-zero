# ADR-003: Agent Reach-aligned source access

**Status: Accepted for the local v1 implementation by product owner on 2026-10-03.**

## Context

Agent 0 needs a replaceable way to read candidate source pages and eventually add platform-specific source discovery. Agent Reach is a capability installer/router for local AI-agent environments. Its documented workflow has the agent invoke upstream tools (for example, Jina Reader for web pages) directly; the `agent-reach` command itself is not a stable backend search/read API. Some channels depend on a user's browser session or manually supplied cookies.

The current Agent 0 worker runs server-side. It cannot safely assume access to a submitter's browser, and giving an LLM arbitrary shell access would bypass the application's audit, privacy, and evidence rules.

## Decision

- Keep Agent 0's `SourceReader` as an application-owned provider seam.
- Provide an opt-in Jina Reader adapter aligned with Agent Reach's documented public web-reading route. `SOURCE_READER_PROVIDER=disabled` remains the default; `jina_reader` explicitly enables external page retrieval.
- Keep hosted web search as candidate discovery. Store source retrieval status, provider and retrieved-content SHA-256 separately from the source URL.
- Admit model-proposed excerpts as evidence only when the source was retrieved and the normalized quotation appears verbatim in that retrieved text. Findings without such linked evidence become `INCONCLUSIVE`.
- Never execute Agent Reach or upstream commands from the model/tool loop. Do not install cookie/browser-session channels in the server. A later social integration requires an explicit per-platform API/consent/security decision and a narrow adapter.
- Do not install the Agent Reach CLI into the project runtime. A developer may install it locally for independent research workflows, but that is separate from the product backend.

## Consequences

- The worker can retrieve public pages without coupling domain logic to Agent Reach's CLI or its rotating backend choices.
- Enabling the adapter sends the source URL to Jina Reader. It is disabled by default, and credential-bearing URLs must not be submitted for retrieval.
- Retrieval is bounded to five candidate source URLs per investigation (plus a submitted URL already fetched for context); excess candidates remain unattempted.
- A matching quotation establishes that the passage appears in the retrieved page; it does not establish that the claim itself is true or the source is reliable.
- Social search/read, source lineage and independence analysis remain out of scope for this integration.

## Rollback

Set `SOURCE_READER_PROVIDER=disabled` to stop external page retrieval; search results remain candidates and findings without retrieved quotations become inconclusive. The additive migration `0003_source_retrieval` can be downgraded if it has not accumulated data; after use, prefer a forward migration and preserve audit history.
