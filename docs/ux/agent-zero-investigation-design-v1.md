# Agent Zero investigation experience and system design

**Status:** Draft for product/engineering alignment. This document defines the intended MVP behavior before provider and SDK integrations are implemented.

**Scope:** Claim-focused public information investigations for journalists, fact-checkers, and editors, using the existing web workspace and shared investigation backend. The agent assists investigation and drafts an evidence-based assessment. It does not publish findings or make editorial decisions.

**Related records:** [Product requirements](../product/requirements.md), [Architecture](../architecture/architecture.md), [Research and routing recommendation](../engineering/investigation-research-routing-2026-10-09.md), [Open questions](../OPEN-QUESTIONS.md).

## 1. Intended outcome

Given a clear factual question, assertion, source URL, image, or supported video, Agent Zero should:

1. Identify the precise claim or explain what detail is needed.
2. Search a relevant, ordered set of sources instead of issuing undirected web queries.
3. Retrieve source passages and retain their provenance.
4. Assess each claim against eligible passages, preserve conflicts, and reject unsupported model conclusions.
5. Give the user a direct, readable answer with citations they can inspect.
6. Show what remains unknown and the most useful next action.

Completion means the investigation workflow finished. It does not mean a claim is true, the sources are exhaustive, or an editor approved the result.

## 2. Roles and authority boundary

| Role | Responsibility | Authority |
|---|---|---|
| Submitter | Supplies a claim, source, or media and inspects the result | Can clarify or refine the request; cannot make a model result true by agreeing with it |
| Agent Zero | Extracts claims, routes research, collects evidence, drafts a finding and brief | Can search, retrieve, organize, assess, and recommend follow-up; cannot publish externally or mark a human review complete |
| Editor/reviewer | Reviews source relevance, claim-evidence links, and the draft finding | Makes the editorial decision and can correct the claim or evidence relationship once a private, auditable review action is designed |
| Providers | Return search results, page content, metadata, or model output | Are untrusted data processors; provider ranking/output is never itself a verdict |

The draft result is decision support. Human editorial responsibility remains explicit. The shared demo stays demo-only; do not enable persistent reviewer changes until identity, access, audit, and retention are resolved.

## 3. End-to-end flow

```text
Submit
  → Normalize request and record channel/input boundaries
  → Classify task and extract checkable claim(s)
      ├─ unclear or unsupported → ask one useful question / explain supported scope
      └─ clear
          → Assign topic, jurisdiction, timeframe, and search route
          → Tier 1: primary records and topic-authoritative sources
          → Tier 2: trusted reference and independent reporting
          → Tier 3: prior fact-checks as context
          → Tier 4: social search only when the claim requires it
          → Retrieve and inspect candidate source pages
          → Extract traceable passages and map passages to claims
          → Resolve support, contradiction, gaps, and independence
          → Validate every finding and rendered citation
          → Draft answer, limitations, and next step
          → Show brief and source trail; editor decides what to do next
```

The model proposes claim wording and query candidates. Application code owns route eligibility, provider budgets, source metadata, URL safety, passage/evidence persistence, citation validation, status transitions, and fallback behavior.

### Step 1 — Intake and scope

- Preserve the user's original text and any submitted source/media reference.
- Identify whether the user wants a claim checked, information researched, a URL assessed, media context examined, or an opinion answered. Do not turn a request for analysis/opinion into a factual verdict.
- Convert clear yes/no and direct factual questions into declarative propositions. Keep actor, action, location, date, and qualifier intact. Split a compound request only when each claim can be evaluated separately.
- Ask one concise clarification question when the missing detail could change the proposition or its timeframe. Pause claim research until clarification; do not quietly guess or emit an unsupported negative assessment.
- For unsupported media types, explain exactly what can be checked from the current file and do not imply unimplemented audio/document analysis.

### Step 2 — Research plan

For each claim, produce a bounded internal route record:

```json
{
  "claim_id": "...",
  "topic": "history",
  "jurisdiction": ["Kenya"],
  "freshness": "HISTORICAL",
  "route": ["PRIMARY_RECORDS", "TRUSTED_REFERENCE", "INDEPENDENT_REPORTING", "FACT_CHECK_CONTEXT"],
  "social_required": false,
  "reason": "Settled historical date; official archival and intergovernmental records are relevant."
}
```

The structured record is an application contract, not a hardcoded fact. The model can suggest topic, jurisdiction, dates, and queries. A curated, versioned source catalog resolves which domains are appropriate. The model cannot add trusted domains, mark a source authoritative, set the final verdict, or bypass query/cost limits.

### Step 3 — Ordered discovery and stop/widen rules

| Lane | When to use | Examples | Widen/stop rule |
|---|---|---|---|
| 1. Primary and topic-authoritative | Always first when an authority is applicable | Statutes, court records, official data, original statements, archives, intergovernmental records | Widen if no relevant passage is retrieved, the source is incomplete, or independent confirmation matters |
| 2. Trusted reference and independent reporting | To corroborate, explain context, or fill a primary-source gap | Established reference works, specialist organizations, independent newsroom reports with identifiable sourcing | Stop when the claim has adequate relevant traceable evidence and no material conflict; widen only to resolve a named gap |
| 3. Fact-check archive | When an existing reviewed claim may be discoverable or a claim has circulated before | Google Fact Check Tools / ClaimReview entries, established fact-check publishers | Treat as a prior assessment and route back to its evidence; never import the external rating as Agent Zero's own status |
| 4. Social platforms | Only when the subject is a specific post/video/account, origin, circulation, firsthand account, or an explicitly requested social claim | Official X/Reddit/YouTube APIs where access and terms permit | Search only relevant platforms; preserve post ID/permalink, account/channel, created time, retrieval time, and context. A post proves publication by an account, not the asserted event |

Do not run all lanes automatically. Each new lane must answer a documented evidence gap. Do not interpret an empty constrained search as evidence of absence. If a lane is unavailable, surface that limitation and continue only if the remaining route can responsibly answer.

**MVP defaults:** use current Exa adapter for bounded public web discovery; use existing optional Jina Reader for public-page retrieval only where configured; add no general-purpose crawler or scraping/browser-cookie path. Implement curated source routes and Google Claim Search as the first optional discovery additions. Keep social providers behind feature flags until the platform, privacy, retention, and cost decisions are approved.

### Step 4 — Retrieval and evidence admission

- Search results, titles, snippets, highlights, social search hits, and fact-check metadata are candidate leads, never claim evidence by themselves.
- Retrieve the actual public page using the approved reader. Apply existing SSRF controls, redirect policy, content type and byte limits, credential/query stripping, and provenance capture.
- Evidence is an exact source passage or a clearly typed observation. Store source URL, title/publisher, publication date if available, retrieval timestamp, content hash, extraction method, and limitations.
- Admit a quoted passage only when it matches retrieved content under deterministic normalization. Keep the surrounding context/heading so a quote is not detached from its scope.
- Track original/duplicate/cites relationships. Reprints and articles repeating the same unnamed report do not count as independent corroboration.
- Social statements may be evidence for the narrow proposition “this account published this post at this time” if captured through a permitted API. They are not evidence that the post's factual content is true.

### Step 5 — Claim-evidence reasoning

For each claim, create relationships `SUPPORTS`, `CONTRADICTS`, `CONTEXTUALIZES`, `MENTIONS`, or `UNKNOWN`. Use only eligible persisted evidence. Preserve relevant disagreement rather than averaging sources into a confident-sounding synthesis.

Verdict rules:

- `SUPPORTED`: retrieved relevant evidence supports the proposition and no material unresolved contradiction changes its meaning.
- `CONTRADICTED`: retrieved relevant evidence challenges the proposition; clearly state the corrected fact and keep scope/date aligned.
- `INCONCLUSIVE`: eligible retrieved evidence materially conflicts or the distinction needed to decide is unresolved.
- `UNVERIFIED`: there is not enough claim-linked eligible evidence, retrieval failed, sources were only candidates, or coverage is too weak. This is not a false verdict.

Confidence remains qualitative evidence sufficiency, not truth probability. `HIGH` requires multiple relevant independent authoritative sources with no material conflict. A stable fact may still be `SUPPORTED` with moderate evidence strength; do not withhold a direct answer merely because a numeric/high-confidence threshold was not met. Never use citation count alone as confidence.

### Step 6 — Citation and answer validation

The answer composer may only use the validated finding, claim, source metadata, evidence passages, and limitations in the investigation packet. Before rendering:

1. Validate that every cited evidence/source ID belongs to this investigation and is eligible for that relationship.
2. Validate each displayed factual sentence against at least one cited passage. Citation existence alone is insufficient; the passage must support the sentence.
3. Remove or rewrite unsupported specific details. If the central claim has no evidence, use the `UNVERIFIED` answer shape below.
4. Render citations as visible, clickable links attached to the supported sentence; show source title, publisher, date when known, and a readable evidence excerpt on inspection.
5. Keep editorial review status separate from agent assessment status.

If sentence-level entailment cannot be validated reliably, do not pretend it can. In the MVP, use structured finding/evidence links and deterministic quote validation plus bounded model reasoning, then mark the validation limitation. Build a reviewed evaluation set before claiming automated entailment checks.

## 4. User-facing answer design

### Result order

1. **Direct answer:** one or two sentences that answer the user's question and show the user-language result label.
2. **Why:** the strongest evidence passages, with visible citations beside the statements they support.
3. **What remains unclear:** only material gaps, contradictions, dates, or limitations.
4. **Next step:** one useful action, such as supplying a source, clarifying a date, or reviewing a disagreement.
5. **Review marker:** “AI assessment — not yet reviewed” or a clearly recorded human review state when available.

### Status copy and response shapes

**Evidence supports this claim**

> Yes. Kenya became independent on 12 December 1963. The Kenya Presidential Library’s archival record and the UN decolonization list support the date. [Open the records]
>
> **Evidence strength:** High — two relevant records from distinct institutions. **Review:** AI assessment, not yet reviewed.

**Evidence challenges this claim**

> The evidence points the other way. [Corrected statement], according to [specific primary record]. The original claim may be mixing up [relevant distinction, if supported].

**Not enough evidence yet**

> I couldn’t confirm this from the material retrieved in this check. I found [specific candidate/source retrieval result], but it did not contain a passage that establishes [claim detail]. That does not show the claim is false. The next useful step is [specific source, document, date, or clarification].

**Evidence leaves this unresolved**

> The sources I retrieved disagree about [specific point]. [Source A] reports [supported detail], while [Source B] records [supported detail]. I can’t resolve the difference from the available records; [specific follow-up] may settle it.

Do not display empty phrases such as “not verified,” “no evidence,” or “the AI is unsure” without explaining what was searched/retrieved and what the user can do next. Avoid saying sources were reviewed if only search candidates were discovered.

## 5. State and recovery contract

| State | User sees | Action / recovery |
|---|---|---|
| Received | Request saved; investigation reference | Leave, reopen history, or cancel if not yet processing |
| Clarification needed | One exact question; no finding has been made | Edit/answer and resume the same investigation; cancel |
| Analyzing | Claim extraction/media scope in progress | Keep original input; refresh/reopen; cancel if supported |
| Researching | Current lane and high-level stage; no success language yet | Reopen; user may cancel; route failures are recorded |
| Corroborating | Sources are being retrieved and compared | Reopen; do not present candidates as reviewed evidence |
| Complete | Brief exists; each claim has a separate result | Inspect passages, sources, limits; submit a follow-up/refinement |
| Needs review | Why automation stopped; partial work retained | Retry a named failed stage or hand off to a human when supported |
| Failed | Safe reason and whether retry is available | Retry idempotently or preserve/export reference for support |
| Cancelled | Processing stopped; completed work may remain visible | Resume/restart as an explicit new run if allowed |

Clarification may require an explicit `NEEDS_INPUT`/equivalent lifecycle state. Do not represent “waiting for user” as completed claim assessment. Provider errors, empty results, retrieval failures, and evidence insufficiency must be distinguishable in the internal trace and in concise user copy.

## 6. Integration architecture and package choices

Use the existing modular monolith and add capability adapters, not an agent framework rewrite:

```text
InvestigationService
  ├─ IntakeNormalizer / TaskClassifier
  ├─ ClaimPlanner (OpenAI Agents SDK / current ModelGateway)
  ├─ RoutePlanner (application policy + versioned source catalog)
  ├─ SearchProvider[] (existing Exa; optional OpenAI web search; Google Claim Search)
  ├─ SourceReader[] (existing optional Jina Reader)
  ├─ EvidenceExtractor / deterministic quote matcher
  ├─ EvidenceReasoner (existing structured model call)
  ├─ FindingValidator / CitationValidator
  ├─ BriefComposer
  └─ Channel renderers (web, ClickCast/WhatsApp)
```

Provider adapters return a shared candidate contract: provider, lane, query ID, candidate URL or platform ID, title, publisher/account, publication/creation time, discovery time, snippet/highlights, provider reference, and limitations. Evidence has a separate contract and cannot be created from a candidate-only payload.

| Integration | Intended position | Dependency stance |
|---|---|---|
| OpenAI Agents SDK / existing model gateway | Claim extraction and structured evidence reasoning | Keep; pin compatible SDK version; retain structured schemas, budgets, provider metadata, and deterministic validation |
| Exa Search API | First search adapter for web lanes; domain include/exclude routed by application policy | Keep thin native HTTP adapter; no extra SDK required while schema remains small |
| Jina Reader | Optional bounded fetch of selected public web candidates | Keep current adapter only with explicit provider and source-URL disclosure; provider-data decision remains a rollout gate |
| Google Fact Check Tools API (`claims.search`) | Secondary archive lookup, after initial relevant-source plan | Small adapter; Google's Python client is optional, not required for one simple REST call. Keep API key server-side; the returned ClaimReview is a lead/context and must be fetched/evaluated separately |
| OpenAI Responses `web_search` | Optional search adapter/fallback when configured; preserve returned citations/source metadata | Do not swap current flow to free-form generated answers. Reconcile the current ADR/architecture mismatch before enabling this route |
| X API | Later, only for claims about X posts/accounts or circulation/origin | Official API adapter only after current access tiers/cost, auth scopes, storage/deletion rules, and product need are confirmed. No cookie/browser session or unofficial scraper |
| Reddit Data API | Later, opt-in for Reddit post/context investigations | OAuth-supported API only; confirm terms, deletion obligations, and access before implementation. Do not treat posts as independent factual corroboration by default |
| YouTube Data API | Later, locate public video/channel metadata for video-origin claims | Search API can find videos/channels; video search metadata alone cannot validate footage or establish captions/content. Media/audio analysis needs a separately scoped workflow |
| Vector database / pgvector | Not needed for current public-web per-case search | Reconsider only for a permissioned internal archive or durable cross-case corpus, with retention and deletion design |
| Browser automation, Agent Reach CLI, scraping packages | Not part of server investigation | Do not integrate. These can create cookie/session, provider, audit, and arbitrary-execution paths that bypass the application contract |

Provider and package versions, live API scopes, availability, price, and data terms must be checked against current official docs immediately before implementation. SDK necessity should be justified per adapter; avoid dependency accumulation where a bounded REST adapter is simpler.

## 7. MVP rollout order

### Slice A — Align existing logic and plan schema

- Reconcile requirements, architecture and ADR-004: they currently describe OpenAI hosted search as a fallback/normal path while the current orchestrator executes persisted Exa traces directly.
- Replace freshness-only text markers with typed route records: topic, jurisdiction, lane, freshness, trigger/reason, and provider.
- Add relevant source packs and route tests/fixtures for Kenya history, current public-health claims, a claim with no authoritative domain, an ambiguous question, and a deliberately irrelevant official page.
- Keep budget and source cap enforcement in application code.

### Slice B — Enforce discovery order and improve answers

- Implement authoritative and reference/reporting lanes with configured domain filters and a bounded broad-web fallback.
- Preserve candidates as candidates and retrieve only selected sources.
- Add deterministic evidence/citation eligibility checks, sentence-oriented answer projection where evidence allows, and the answer/status display contract above.
- Add a fact-check archive adapter behind configuration. It enriches the packet but cannot override Agent Zero's assessment.

### Slice C — Social integrations by claim need

- Add separate provider adapters and evidence origin/type, not a generic “social search” boolean mixed into web candidates.
- Choose one platform only after product need, access/cost, API terms, privacy, and removal handling are documented.
- Start in lead/context mode. Let the user inspect the post, account, timestamp and original media/link; require corroboration from independent or primary evidence before supporting the post's factual assertion.

### Slice D — Editorial review and production gates

- Define reviewer identity, correction/decision values, audit trail, conflict resolution, ownership, and retention before persisted review controls.
- Resolve authentication, tenant isolation, user-owned deletion, retention, provider handling, deployment, and demo data isolation before sensitive or public launch.
- Add model/retrieval evaluation and observability owned by the engineering/evaluation plan, with no user-content logging by default.

## 8. Acceptance criteria for the designed experience

1. A clear factual question is rendered as a specific checked claim; the original wording remains inspectable.
2. An ambiguous request asks one targeted question and does not produce a claim verdict before clarification.
3. The Kenya independence fixture resolves as supported using retrieved archival and UN passages, with visible clickable citations. Model memory alone cannot satisfy it.
4. Search lanes execute in the declared order; broader/social lanes only run for explicit gap/claim triggers. The trace makes the route and trigger auditable.
5. An empty authoritative lane is described as a search limitation, not as evidence that the claim is false or nonexistent.
6. Search snippets, social posts, fact-check ratings, duplicates and inaccessible pages cannot independently produce `SUPPORTED` or `CONTRADICTED`.
7. Each displayed factual statement maps to eligible evidence from the same investigation; invalid or unsupported citations are suppressed or cause safe fallback copy.
8. Conflicting evidence yields `INCONCLUSIVE` with both sides shown. Missing eligible evidence yields `UNVERIFIED` with what was searched, what could not be established, and a specific next step.
9. Social-origin claims can distinguish “this account posted this” from “the event in the post happened.”
10. Processing completion, claim assessment, and human editorial review are shown as separate concepts.

## 9. Decisions still needed before integration

| Decision | Recommendation for MVP | Gate |
|---|---|---|
| Search provider path | Make Exa the first explicit web-discovery adapter; use OpenAI web search only as a declared optional fallback/route | Resolve ADR-004 and current worker behavior; verify cost and provider-data handling |
| Fact-check archive | Add Google Claim Search as optional context lane, not a verdict source | Configure API key/quota and confirm terms/data handling |
| Social platforms | Start with one platform only after selecting a validated use case; no universal multi-network search | Confirm platform priority, API access, cost, retention/deletion and consent |
| Clarification lifecycle | Add `NEEDS_INPUT` or equivalent, distinct from `COMPLETE` | Confirm frontend/API behavior and resume semantics |
| Human review | Store a separate editorial disposition with reviewer identity and audit | Auth/ownership and retention decision |
| Search adequacy thresholds | Use qualitative evidence rules and fixture-based evaluation; do not claim completeness | Establish representative labelled evaluation fixtures before release |

## 10. Current gaps this design addresses

- The current planner has claims and freshness-tagged free-text queries but no typed topic/jurisdiction/route lane or deterministic widening trigger.
- The same Exa execution function runs planned traces; source order is currently phrased in the prompt rather than enforced as an orchestration policy.
- The source registry is a small identity list; it does not yet function as a versioned source catalog with enough historical/domain topic coverage.
- Search title/highlight candidates must not become evidence; downstream validators already enforce important evidence-reference rules, but sentence-to-passage citation entailment needs its own acceptance criterion and evaluation.
- The API/frontend currently turns unclear no-claim outcomes into a completed investigation response; a durable clarification-pending state/resume path has not been designed.
- Requirements and ADR-004 describe OpenAI hosted search as a fallback/available path, but the current direct orchestrator path reviewed for this design creates and executes Exa traces. The final implementation must choose and document one provider orchestration contract.
- Audio and documents are not end-to-end supported; social search is not currently part of the product. Do not imply either capability in product copy until its intake, analysis, provenance, policy, and recovery flows exist.
