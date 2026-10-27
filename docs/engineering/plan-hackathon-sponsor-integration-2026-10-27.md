# Hackathon Sponsor Integration Plan

**Status:** Superseded — product lead withdrew Agent Zero from the hackathon on 2026-10-26
**SEOS stage:** OPERATE
**Tier:** Major
**Target deadline:** 2026-10-27 23:45 UTC
**Planning basis:** Rulebook requirements supplied by the product lead; repository and host inspection on 2026-10-26

> Historical planning record only. Zetaris and Nightshift are not needed and will not be used. Keep the Zetaris AWS deployment suspended. Do not use this plan to start sponsor integrations.

## Outcome (withdrawn)

Demonstrate Agent Zero investigating one claim using all required sponsor technologies:

1. Meterless Nightshift is the explicitly selected primary model provider for the run.
2. Zetaris supplies real, inspectable data records used as evidence candidates.
3. One Meterless Engine contributes to a working investigation feature and has a passing test or conformance result.

The investigation must retain Agent Zero's existing claim triage, evidence ledger, citation validation, and deterministic verdict policy. A run is complete only when the saved result identifies the actual provider, the Zetaris source records, and the Engine contribution. A configured service or a UI badge alone is not evidence of integration.

## Product design

### Intended user outcome

A researcher submits one factual claim, sees which public-web and approved Zetaris records were actually retrieved, inspects exact supporting and contradicting excerpts, and receives a cautious, source-linked AI assessment. The AI does not make an editorial decision.

### Proposed investigation journey

1. **Submit:** Researcher enters one claim. The demo identifies its data scope; do not expose private datasets or accept sensitive submissions until access policy is confirmed.
2. **Triage:** Existing claim triage proposes a normalized, checkable claim. The user can correct it before research starts.
3. **Retrieve:** Existing public-web retrieval runs as it does today. A read-only Zetaris adapter retrieves relevant records from one preselected, approved dataset. Each result carries a dataset/record reference and retrieval time.
4. **Admit evidence:** Zetaris rows remain candidates until their source identity, retrieved text, and exact excerpt are traceable. Admitted records use the existing Source/Evidence/citation path where that contract supports them. If no stable record reference or excerpt is available, the result stays unverified and cannot support a finding.
5. **Reuse case context:** The proposed H-MEM feature retrieves source-linked pointers to evidence already admitted for this investigation, including related claims and unresolved conflicts. It may organize or reinject context; it cannot create Evidence rows, change evidence eligibility, or set a verdict.
6. **Assess:** Meterless Nightshift supplies the structured model response. Existing citation checks and deterministic verdict sufficiency rules remain authoritative.
7. **Inspect:** The existing results page presents web and Zetaris sources with their origin, record reference, retrieval state, excerpt-validation status, and relationship to the claim. Conflicts and limitations remain visible.

### Failure and trust behavior

- **Nightshift unavailable or unauthorized:** stop the AI-dependent step, preserve the investigation and any collected sources, and show the provider failure. Never send the same submission to OpenAI silently.
- **Zetaris unavailable:** show the Zetaris lane as unavailable. A web-only result may be offered as a separately labelled partial investigation, but it does not count as the sponsor-integrated demo run.
- **Zetaris record lacks provenance or exact text:** retain it as a candidate/unverified record; do not cite it as validated evidence or use it to support a finding.
- **H-MEM returns no related context:** continue with the ordinary evidence packet and record that the Engine found no eligible memory. The Engine does not become a hard dependency for the evidence ledger.
- **Conflicting evidence:** preserve both sides and leave the current verdict policy to produce its existing cautious outcome.
- **Human decision:** out of scope for the mandatory integration demo until the reviewer identity boundary is defined. Keep the AI assessment distinct from editorial judgment.

### Demo audience and boundary

Use a local, single-operator demo with public or explicitly approved data. Do not expose the shared `DEV_USER_ID` demo as a multi-user review workflow. Do not activate the suspended Zetaris deployment until the dataset, read-only access, expected AWS cost window, and stop procedure are agreed.

## Verified repository and environment facts

- The working branch is `feat/agent0-public-frontend`; the working tree was clean during inspection.
- No Zetaris, Meterless, or Nightshift integration references or sponsor-related configuration variable names were found in the repository, process environment, or inspected `.env` variable names.
- Agent Zero's Compose file contains PostgreSQL, Redis, object storage, migration, API, and worker services; it contains no Zetaris or Meterless service.
- Read-only Docker inspection found the Agent Zero API, worker, Redis, PostgreSQL, and object-storage containers stopped. No Zetaris or Nightshift container was listed. MentorMama services were running and MentorMama Redis was restarting. No containers were started.
- The user reports that Zetaris is deployed in AWS but suspended to reduce cost. AWS was not queried; endpoint, catalog, schema, access policy, and cost are unverified.
- A follow-up local check found no `ns` CLI, no Nightshift/Meterless process, and no listener accepting connections on the documented default `127.0.0.1:8088` endpoint.
- `ModelGateway._structured_call` in `backend/app/modules/investigations/investigator.py` currently uses OpenAI Responses. Meterless documents Chat Completions with a bearer token, `meterless-app`, and `meterless-scope: user`; its model IDs must come from `GET /v1/models`. Agent Zero has no Meterless configuration today.
- Host inspection: Intel i5-4300U, 4 CPUs, 7.6 GiB RAM, no NVIDIA GPU. Project volume has 6% free. `sinaps health` reports **BLOCKED** due to disk. Meterless's published Nightshift computer editions list Windows with a dedicated GPU, Mac M5+ with at least 16 GB, and DGX Spark; its web edition has no local provider endpoint. Do not attempt a local Nightshift install on this laptop. A compatible remote/other host and endpoint are prerequisites.
- Existing `Evidence` requires a `source_id` or `media_asset_id`; exact excerpt offsets and citation validation exist. `Source.url` is text, but no Zetaris record identity contract has been established. Confirm whether a stable Zetaris record URI can pass through the current source/citation representation before deciding whether a migration is needed.
- Product lead states the deadline is 2026-10-27 23:45 UTC. At planning time, approximately 40 hours remain.

## MoSCoW scope

### Must

- A real Nightshift model request succeeds through Agent Zero's structured output path, and provider/mode are persisted.
- One real Zetaris query contributes a retrieved, provenance-bearing record to a saved investigation.
- One Meterless Engine-backed feature runs in that investigation and has a passing Engine conformance/evaluation result plus Agent Zero integration coverage.
- Existing OpenAI behavior remains available when explicitly selected; no automatic provider failover.
- Existing evidence admission, citation validation, uncertainty, contradictions, and deterministic verdict policy remain intact.
- A 1–4 minute demo and submission evidence show the saved investigation and the sponsor technologies' actual contributions.

### Should

- One bounded public-web + Zetaris case with at least one validated excerpt and a visible source trail.
- A concise README update and architecture/data-flow diagram showing Nightshift, Zetaris, H-MEM, and the unchanged evidence/verdict boundary.
- Secret and credential scan of the final diff/submission artifacts.

### Could

- Persistent editorial review and JSON export, only after the sponsor gates pass and reviewer identity is resolved.
- Additional Zetaris datasets, multi-claim UX, or image workflows.

### Won't this time

- Full authentication platform, public multi-user reviews, PDF export, broad provider refactor, or full Scout Intent implementation.
- Starting the full Agent Zero Compose stack or reactivating AWS Zetaris just to explore. Use only the services and a bounded AWS test window required by the approved demo path.
- Local Nightshift installation on the current ThinkPad.

## Sequenced implementation plan

### Gate 0 — Access and resource readiness

**Do first. No implementation until this gate passes.**

- Obtain a Meterless Nightshift endpoint on supported hardware, with a real token and a selected mode returned by `GET /v1/models`. Keep the token out of chat, logs, screenshots, and committed files.
- Obtain Zetaris endpoint/access instructions, one approved dataset/catalog, one record reference format, read-only access, and an agreed AWS activation/stop window. Keep the deployment suspended until the integration is ready to test.
- Repair project-volume capacity using an explicitly approved, named cleanup/repair action. Current health is BLOCKED; do not install packages or run heavy verification first.
- Confirm API/worker network reachability to both endpoints without printing credentials.

**Acceptance:** both endpoint owners and data boundaries are known, runtime/model compatibility is testable, and resource health no longer blocks the required verification. If Nightshift cannot be reached on compatible hardware or Zetaris access cannot be activated safely, report the sponsor integration path blocked rather than simulate it.

### Stage 1 — Nightshift as selectable primary provider

**Likely files:**

- `backend/app/core/config.py`
- `backend/app/modules/investigations/investigator.py`
- `backend/app/modules/health/routes.py`
- `backend/.env.example` and backend setup documentation
- New focused provider tests, alongside `backend/tests/test_cost_controlled_pipeline.py` and `backend/tests/test_openai_only_architecture.py`

**Changes:** add explicit provider selection, secret token, reachable base URL, stable app ID, and selected runtime mode. Preserve the current OpenAI Responses branch. Use a Meterless Chat Completions branch with the documented headers and validate the selected mode against Runtime discovery. Keep OpenAI optional and explicit; do not silently retry through it. Maintain request budgets/timeouts and record actual provider/mode in usage.

**Acceptance tests:** exact request URL/model/headers; missing token; 401/403 classification; mode discovery/unknown-mode handling; structured Pydantic output; current OpenAI path regression. Then run one real triage and one real investigation through Nightshift and confirm persisted usage rows name Meterless. Verify whether the chosen mode supports vision; if not, use a text-only demo case.

### Stage 2 — Zetaris source lane

**Likely files:**

- New `backend/app/modules/sources/zetaris.py` adapter
- `backend/app/core/config.py` and `backend/.env.example`
- The narrow source-acquisition seam in `backend/app/modules/investigations/orchestrator.py`
- `backend/app/modules/investigations/models.py`/a migration only if the confirmed record identity cannot fit existing `Source` and `Evidence` fields
- `frontend/src/app/investigate/types.ts` and `page.tsx` for source-origin display
- New tests under `backend/tests/`

**Contract to confirm before coding:** read-only query; bounded result count and text size; dataset/record ID; stable reference or URI; retrieved timestamp; publisher/owner and access constraints; exact text from which excerpt offsets can be validated. Never put a Zetaris credential in the frontend.

**Acceptance tests:** adapter query mapping; empty result; timeout/auth failure; record-to-Source/Evidence mapping; quote and offset validation; duplicate/conflict preservation; missing provenance never becomes validated evidence. Run one bounded live read against the approved dataset during the agreed activation window, verify the saved result, then stop the AWS service using the owner-approved procedure.

### Stage 3 — H-MEM-backed within-case evidence context

**Candidate Engine:** H-MEM, conditional on the Gate 0 timebox. It is more relevant than Markovian for this evidence-provenance feature; Scout remains a specification/eval harness rather than a published runnable implementation. H-MEM is language-agnostic and has a reference/conformance suite, but implementing the full engine may be too large for the remaining window.

**Narrow feature:** build case-scoped working memory from already-admitted evidence. Every memory item carries the investigation ID and exact claim/evidence/source references. Retrieve related items when reasoning about another claim in the same investigation, so shared context or conflicts can be noticed without duplicating facts or changing the evidence ledger. No cross-investigation recall, no invented evidence, no independent verdicts.

**Likely files:** new `backend/app/modules/investigations/research_memory.py` (or isolated `backend/app/modules/memory/hmem/` package), integration at the evidence-packet construction seam in `orchestrator.py`, and focused Engine + pipeline tests. Add persistence only if required by the chosen H-MEM contract and after verifying the migration impact.

**Hard stop:** timebox implementation feasibility immediately after Gate 0. If a provenance-preserving implementation cannot pass the official H-MEM conformance suite and one Agent Zero multi-claim integration test in the allocated window, do not claim H-MEM integration. Reassess Markovian only if its bounded chunk/carryover contract can fit the existing investigation deadline without replacing citation/verdict validation; otherwise the mandatory Engine gate remains unfulfilled.

**Acceptance:** official H-MEM conformance result; a deterministic test proving retrieved memory contains only valid Evidence IDs from the same investigation; an integration fixture where linked evidence is surfaced across two related claims; and a regression proving no new Evidence or verdict is created by memory retrieval.

### Stage 4 — End-to-end demo, freeze, submission

- Use one claim selected from the approved Zetaris dataset and a corresponding known source reference.
- Show claim triage, Zetaris retrieval, source/citation validation, H-MEM context retrieval, and the saved AI assessment with provider/mode and evidence provenance.
- Include one contradiction or insufficient-evidence case if the approved records support a genuine example; do not fabricate one.
- Verify the expected source IDs and Engine trace in persisted output; capture test/conformance output and the exact branch revision.
- Update README and architecture diagram; exclude credentials, personal data, and unrelated assets from the submission.
- Feature freeze with at least four hours reserved for demo capture and submission checks.

## Verification matrix

| Requirement | Evidence required |
|---|---|
| Nightshift is primary provider | Live Agent Zero request succeeds via Meterless Chat Completions; persisted provider/mode; OpenAI fallback not called |
| Zetaris does real work | Live read-only query; saved Source/Evidence reference maps to an actual approved dataset record |
| Meterless Engine is integrated | H-MEM conformance/eval passes and Agent Zero test proves same-case evidence context retrieval |
| Existing investigation preserved | Existing focused tests plus one end-to-end case retain exact excerpt validation, conflicts, limitations, and deterministic verdict behavior |
| Demo truthful and safe | 1–4 minute recording, source-visible UI, no secrets, no unsupported claims about accuracy or sponsor use |

## Risks, assumptions, unresolved owners

- **Nightshift hardware/endpoint — blocking:** local ThinkPad is unsupported by the published computer editions. Owner must provide a compatible Nightshift host/endpoint or obtain a sponsor-hosted endpoint. No CLI, process, configured endpoint, or listener was found locally.
- **Structured outputs — blocking:** the published Runtime contract confirms Chat Completions but does not explicitly confirm that the deployed runtime/model accepts the `response_format.type=json_schema` payload emitted by Agent Zero. Require documentation or a real schema-constrained request before selecting the mode.
- **Disk health — blocking:** 6% free; `sinaps health` is BLOCKED. Cleanup/repair requires explicit authorization and a named target. Do not install or run suites until repaired.
- **Zetaris access — blocking to live verification:** deployed-but-suspended is product-lead-provided context. This environment has no Zetaris config/tool/active container; endpoint, data catalog, schema, ACL, and activation cost are unknown. Keep AWS suspended until the bounded test plan is accepted.
- **H-MEM effort — high:** full conformance scope is larger than a retrieval helper. The proposed working feature is intentionally bounded, but it only qualifies if the rulebook accepts the integrated Engine and the required suite passes.
- **Structured output and vision — unverified:** validate actual Nightshift mode behavior before selecting demo content.
- **Existing project state — stale:** `.sinaps/state.md` still records the earlier human review/export slice as next. Update it after this sponsor-first plan is approved, not by silently changing the source-of-truth state during drafting.
- **Hackathon rulebook — user-provided:** requirements in this plan follow the supplied rulebook excerpt; the rulebook file itself was not found in the repository.

## Product decision

Sponsor integrations outrank review/export for this submission. H-MEM is the only current Engine candidate in this plan, but remains conditional on the conformance/timebox gate. Do not begin implementation until Gate 0 has a reachable Nightshift mode, an approved Zetaris read path and dataset, and repaired resource health.

## References

- [Meterless Nightshift and Engine overview](https://github.com/Meterless/Meterless/blob/main/README.md)
- [Meterless Runtime endpoint and model-mode contract](https://meterless.ai/engines.html)
- [OpenAI Agents SDK model integrations](https://openai.github.io/openai-agents-python/models/)
- [H-MEM reference architecture](https://github.com/Meterless/H-MEM)
- [H-MEM conformance specification](https://github.com/Meterless/Meterless/blob/main/engines/hmem/AGENTS.md)
- [Agent Zero investigation design](../ux/agent-zero-investigation-design-v1.md)
- [Agent Zero architecture](../architecture/architecture.md)
