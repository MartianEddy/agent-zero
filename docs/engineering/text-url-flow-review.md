# Text and URL flow review

> Historical implementation review. Its flow and provider descriptions below predate the cost-controlled single-OpenAI pipeline in [ADR-006](../decisions/ADR-006-cost-controlled-investigation.md); retain this document as a record of the earlier implementation only.

**Review type:** static code and architecture review plus owner-provided local run logs.
**Scope:** text/URL intake, queueing, investigation, search/retrieval, evidence persistence, result API, Agent Reach integration, and local model-provider configuration.

## Flow at review time (superseded)

```text
POST /api/v1/investigations
    ↓ validate TEXT or URL
InvestigationService.create()
    ├── Investigation + Submission
    ├── ProcessingJob
    ├── OutboxEvent + AuditEvent
    └── 202 response
    ↓ Celery Beat dispatches outbox every 2 seconds
Celery worker → process_investigation()
    ├── direct URL: optional Jina Reader retrieval for page context
    ├── Lead Investigator research step (Gemini → Groq → optional OpenRouter fallback) + Exa search tool
    ├── structured synthesis step using the provider that completed the run
    ├── model proposes claims, source URLs, quotations, relationships, findings
    ├── optional Jina retrieval of up to five candidate sources
    ├── quotation match + status/relationship checks
    ├── persist provider queries, result URLs, highlights/citations and provider request references
    └── persist claims/sources/evidence/findings/brief
    ↓
GET /api/v1/investigations/{id}/results
```

The Next.js `/investigate` page submits through same-origin API routes and polls the FastAPI status and results endpoints. FastAPI/OpenAPI and direct API calls are also available for diagnosis.

## Architecture fit

The main boundary is right: channel intake enters one investigation service and the worker owns analysis. Web requests do not perform verification. PostgreSQL persists the job and evidence domain; Redis/Celery coordinate asynchronous work. Agent Reach is not installed or executed inside the worker; the worker uses a narrow Jina Reader adapter. Exa is an optional search tool exposed to the Investigator; it does not replace the investigation engine or create a second verification pipeline. Model selection is configurable and remains behind the Investigator adapter.

The implementation is a modular monolith in deployment, but several target domains are still concentrated in `investigations/orchestrator.py` and `investigations/models.py`. In particular, source discovery, corroboration, finding validation, and brief assembly do not yet have distinct domain services. This is acceptable for the current vertical slice, but the orchestrator is now the main change hotspot.

## Findings before interpreting test results

### Fixed in this turn

- Compose loads `backend/.env` for both the API and worker; explicit container database/Redis/storage settings continue to override the local-host values in that file. The worker needs provider credentials to run analysis. `/api/v1/ready` exposes configured model providers and search readiness without exposing keys.
- The ignored `backend/.env` keeps credentials local. Provider credentials are supplied by the owner, and `SOURCE_READER_PROVIDER=jina_reader` is enabled for local runs.

### Fixed in this implementation

- With `EXA_API_KEY` set, the Research step gets an Exa search function tool backed by Exa's native `/search` endpoint (`type: auto`, `contents.highlights: true`). If the key is absent, only the explicitly configured OpenAI provider can use OpenAI hosted web search. For Gemini/Groq, Exa is required. If Exa returns an error, the model must report insufficient search coverage rather than claim it searched successfully.
- Exa search actions, request references, queries, URLs, titles, dates, authors and highlights are persisted as provider traces. OpenAI search actions, queries, source lists, citation annotations and call references remain persisted too. Traces stay separate from model-proposed sources.
- `Source.discovery_method` distinguishes `EXA`, `OPENAI_WEB_SEARCH`, `SUBMITTED_URL`, and `MODEL_PROPOSED`; provider-discovered sources link to their search trace. An exact URL match is required before a model-proposed source is marked as provider-discovered.
- Jina quote matching still means only that the excerpt occurs in the retrieved page. It does not establish source authority or entailment.
- `GET /results` exposes search traces, source discovery provenance, and `ClaimEvidence` relationship rows. The frontend now submits TEXT and URL investigations through same-origin Next.js API routes and renders progress, findings, source/evidence links, search activity, and relationship labels.
- Gemini 3.8 Flash, Groq Qwen 3.8 27B, and optional OpenRouter Qwen 3.8 27B free are configured in order through the Agents SDK Chat Completions adapter. Research/tool use is separated from structured synthesis for provider compatibility. Successful provider/model and failed provider attempts are recorded in audit metadata and exposed as `model_run` in the results API. Research is limited to four turns; Groq/OpenRouter calls set `max_tokens=900` and concise output instructions. Custom provider clients disable automatic retries so hard quota errors advance directly to fallback.
- The results contract reports evidence coverage counts (claim/evidence links, findings with evidence, and retrieved sources). It still has no numeric confidence/probability.

These are implemented changes; owner logs confirm Gemini calls returned HTTP 200 before reaching the free-tier daily request quota, and Groq rejected fallback because its estimated 1,878 output tokens exceeded the account's 1,000 OTPM cap. The Groq output cap and OpenRouter fallback were added afterward. A later owner run found the two-turn research cap insufficient for Groq and random OpenRouter free routing returned malformed structured output, so research was raised to four turns and OpenRouter default changed to Qwen 3.8 27B free, which documents tool and JSON Schema support. These paths still need another owner-run journey. Search coverage comes from Exa for Gemini/Groq/OpenRouter, or OpenAI hosted search on the explicitly selected OpenAI path; Agent 0 does not directly search or scrape social platforms.

### Screenshot diagnosis — stale foundation fallback

The workspace screenshot displayed `The investigation engine is not enabled in this foundation release. No verification analysis was performed.` That exact text belonged to an obsolete `mark_pipeline_unavailable()` fallback, and there are no callers for it in the current source. The active Celery task invokes `process_investigation()` in the orchestrator. I removed the obsolete fallback so current code cannot emit that misleading foundation-release result. The screenshot therefore points to a stale API/worker process or an investigation created by an older revision; rebuild/recreate the Compose services before submitting a fresh investigation. Existing investigations retain their stored failure message.

### Source and relationship visibility gap — fixed in code, pending verification

`/results` now returns `claim_evidence` rows with `SUPPORTS`/`CONTRADICTS` and other relationship values, and preserves the query/provider details in `search_traces`.

### Accuracy and confidence

There is no confidence/probability field in the schema, prompt output, database, or results API. Current outputs are categorical statuses. Do not manufacture a percentage from the model's self-reported confidence. A useful future confidence model needs a labelled evaluation set and calibration, with factors such as primary-source strength, independence, quote relevance, date fit, and contradictory evidence. Until then, show evidence coverage and limitations rather than a number.

### Agent Reach capability boundary

The upstream Agent Reach documentation describes Jina Reader for reading a supplied web URL and Exa via `mcporter` for web search. That is useful access tooling, but it is not a universal crawler and it does not establish truth. Social/platform access is a separate capability, often requiring an explicitly user-controlled browser session or manually provided cookies. Agent 0 currently searches the public web through Exa, reads selected pages through Jina when enabled, and does not search or scrape social platforms directly.

## Recommended text/URL acceptance journey

Run after provider quotas are available and the local service environment is healthy:

1. Submit a known current claim as `TEXT`; inspect `202`, stage progression, claims, source candidates, fetched source status, exact evidence quote, claim/evidence relationship, finding, and brief.
2. Submit the direct URL of a known public article as `URL`; verify the submitted page is separately represented and quoted content matches its fetched text.
3. Submit an obscure/unsubstantiated claim; verify it ends `UNVERIFIED` or `INCONCLUSIVE`, never contradicted only because search found nothing.
4. For each finding, follow `FindingEvidence → Evidence → Source`, verify source URL and retrieval metadata, and confirm the excerpt is present in the source page.
5. Record actual provider/model, search query/source trace, latency, and any provider errors. Treat one demonstration as a workflow check, not an accuracy benchmark.

The API now exposes claim/evidence relationships and search provenance. Run the journey after provider quotas and local services are available; do not treat the code change as a verified end-to-end result.

## Package and feature choices

| Need | Recommendation | Reason |
|---|---|---|
| Search provenance | Persist provider-returned sources and citations from search traces, separately from model-proposed sources | Adds auditability while keeping search execution behind a provider-neutral domain contract |
| Web search | Exa native `/search` tool for Gemini/Groq/OpenRouter; OpenAI hosted search is limited to the explicit OpenAI provider when Exa is not configured | Exa returns source URLs and highlights; those remain search leads until a quote matches retrieved page text |
| Page extraction | Keep Jina for this first local run; evaluate Trafilatura only if we choose controlled direct retrieval instead of a remote reader | Trafilatura extracts main text and metadata from downloaded pages, but introduces downloader/SSRF/egress responsibilities and is redundant with Jina today |
| Numeric confidence | Do not add a package or model-generated score yet | First collect labelled outcomes and measure calibration; expose evidence coverage and uncertainty meanwhile |
| Image/video later | Evaluate the official C2PA Python SDK when media work starts | Reads and validates C2PA manifests; it reports provenance signals, not whether depicted claims are true |

References: [Agent Reach web-reading workflow](https://github.com/Panniantong/Agent-Reach/blob/main/agent_reach/skill/references/web.md), [Agent Reach English README](https://github.com/Panniantong/Agent-Reach/blob/main/docs/README_en.md), [OpenAI web search](https://developers.openai.com/api/docs/guides/tools-web-search), [OpenAI Agents SDK tools](https://openai.github.io/openai-agents-python/tools/), [Exa Search API](https://exa.ai/docs/reference/search), [Trafilatura](https://github.com/adbar/trafilatura), [C2PA Python SDK](https://github.com/contentauth/c2pa-python).

## Verification status

Owner-provided logs show Compose built the API/worker images, the migration container exited successfully, and a submitted investigation reached Gemini. Gemini returned multiple HTTP 200 responses before its 20-request free-tier daily quota was exhausted. Groq fallback returned HTTP 429 because its estimated 1,878 output tokens exceeded the account's 1,000 OTPM cap. The Groq output cap and OpenRouter fallback were implemented afterward; those paths and complete evidence journeys remain unverified.

Model-provider follow-up: defaults are Gemini primary, Groq fallback, then optional OpenRouter free-model routing. OpenRouter currently advertises 50 free requests/day and 20/minute; its free router can select different upstream models, whose availability and data handling vary. Provider fallback sends the submission to another company. Continue using public information only and validate structured output/function calling before treating the chain as operational.
