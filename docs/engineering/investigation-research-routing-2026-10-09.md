# Agent Zero investigation research and routing recommendation

**Status:** MVP design recommendation, based on the current local implementation and official provider documentation reviewed on 2026-10-09.

## Product decision

Agent Zero should be a claim-first investigation assistant. It converts a request into one or more checkable propositions, gathers traceable passages in a deliberate source order, evaluates each passage against each proposition, and gives a direct answer with clickable evidence and clear limits. Search rank, a familiar fact from model memory, and the mere existence of a source must never count as proof.

The current pipeline already has bounded OpenAI model calls, Exa discovery, Jina retrieval, source candidates distinguished from retrieved evidence, claim-evidence relationships, and persistence checks. The main orchestration gap is that every planned search trace currently goes through the same Exa path. Source order and social exclusion are therefore prompt guidance, not enforced routing. The source registry also lacks topic-specific reference coverage for basic Kenyan history, despite having several modern Kenyan institutions.

## Recommended user flow

1. **Understand the request.** Classify it as a factual question, a factual assertion to check, a request to find information, an opinion, or ambiguous. Restate it as a narrow proposition and preserve the place, actor, timeframe, and important qualifiers. Ask one concise clarification only when a missing detail could change the answer.
2. **Select a research route.** Assign topic, jurisdiction, and freshness. Choose domain/source packs that have relevant authority for that topic. A source being official for one subject does not make it authoritative for every claim.
3. **Search authoritative material first.** Search applicable government records, original documents, court/statistical records, academic publishers, and vetted specialist references. Retrieve the actual page or document and preserve publication metadata and the exact supporting passage.
4. **Widen only to fill a named gap.** If the first pass lacks a relevant passage, corroboration, or current context, search reputable independent reporting and specialist references. Record which gap triggered the wider search. Do not use a low result count alone as a reason to weaken source standards.
5. **Use fact-check and social sources as separate lanes.** Search fact-check archives for prior reviews. Search social platforms only when the claim concerns a circulating post, firsthand account, public reaction, or a social claim’s origin. Treat posts as leads or as evidence of what an account published, not as proof of the event described.
6. **Build a claim-evidence map.** For every finding, show which retrieved passage supports, challenges, contextualizes, or does not address it. Preserve material disagreement and distinguish duplicate/derivative coverage from independent corroboration.
7. **Answer plainly, then show the audit trail.** Start with the verdict and the reason; link each factual sentence to a specific source passage. State what could not be established and give the most useful next step. Keep editorial review separate from the model’s assessment.

## Verdict and answer language

Keep the internal statuses (`SUPPORTED`, `CONTRADICTED`, `UNVERIFIED`, `INCONCLUSIVE`) for logic and API compatibility. Present them in user language:

| Internal status | User label | First sentence pattern |
|---|---|---|
| SUPPORTED | Evidence supports this | “Yes. [Direct answer]. [Clickable source] records …” |
| CONTRADICTED | Evidence challenges this | “The available evidence points the other way. [Direct correction]. [Clickable source] says …” |
| UNVERIFIED | Not enough evidence yet | “I couldn’t confirm this from the sources available in this check. I found [specific search/retrieval result]. The next useful step is …” |
| INCONCLUSIVE | Sources disagree | “The sources I found do not settle this. [Source A] says … while [Source B] says …; the unresolved point is …” |

Do not make “not verified” the answer by itself. For stable, widely documented facts, avoid an unnecessarily skeptical tone: find the reference or record, cite it, and answer directly. If retrieval failed or the relevant source was unavailable, say that it was unavailable; do not imply that the underlying claim is doubtful.

## Expected handling: Kenya independence

For “Kenya gained independence in 1963,” Agent Zero should produce a `SUPPORTED` finding, not default to `UNVERIFIED`. Search a Kenya-history source pack first. The Kenya Presidential Library documents the 1963 Independence Order and identifies the independence celebrations on December 12, 1963; the UN decolonization list independently records Kenya’s independence in 1963. These are directly relevant government/archive and intergovernmental sources. A suitable short answer is: **“Yes. Kenya became independent in 1963; the independence date was 12 December 1963.”** Link the statement to the archival instrument and the UN entry. The distinction between internal self-government on June 1 and full independence on December 12 can be added when relevant, rather than muddying a straightforward answer.

This example exposes a registry/routing coverage gap, not a need to let the model answer from memory. Add topic-scoped historical records to the Kenya source pack (starting with the Kenya Presidential Library/Archives, UN Decolonization, and relevant primary legal records), then retrieve and cite them just like any other check.

## Integration and package assessment

| Candidate | Value in this product | Recommendation |
|---|---|---|
| Existing Exa adapter with domain filters | Makes source tiers enforceable while retaining current discovery and query budget controls | **Integrate first.** Add `includeDomains` / `excludeDomains` support to the existing adapter and a route planner that emits authoritative, independent-reporting, and optional social lanes. Keep broader discovery as an explicit fallback. No SDK needed for this thin HTTP call. |
| Versioned source packs and source-role taxonomy | Adds relevant authority for Kenya/history, law, health, elections, statistics, etc.; prevents one generic registry from overclaiming authority | **Integrate first.** Start with a small Kenya pack and international official/reference records. Store jurisdiction, topic, source role, and scope of authority. Registry membership affects routing and explanation, never truth status by itself. |
| Google Fact Check Tools API | Finds prior ClaimReview articles, including text and image search | **Add as a bounded secondary lookup.** A fact-check is a published assessment with its own date, scope, and evidence; do not inherit its verdict as Agent Zero’s verdict. Follow the review back to primary records and retain the fact-check as a cited source. |
| OpenAI Responses API `web_search` | Provides a managed search path with domain filters, source lists, and citation annotations; useful as a fallback or research mode | **Defer as a provider adapter behind the same evidence contract.** Do not let its generated answer bypass local retrieval, evidence eligibility, or citation validation. For the focused MVP, current Exa + explicit routing is the lower-disruption change. |
| X, Reddit, YouTube and other social APIs | Useful for investigating origin, circulation, firsthand reports, and what a named account/video published | **Defer and make opt-in by claim type.** Use official supported APIs only, with a separate social lane, platform metadata, permalink, retrieval time, and removal/privacy policy. Never scrape around access controls. Posts establish that an account made a post, not that its claims are true. |
| Academic metadata (Crossref/OpenAlex) | Discovery of papers and bibliographic details | **Later, for scientific claims.** Metadata helps locate work but is not the paper’s result; retrieve the paper or abstract and evaluate study scope and limitations. |
| Vector database / general agent framework / extra browser stack | Could add broad retrieval or orchestration features | **Do not add for this MVP.** Current evidence is mostly public-web, bounded and per-investigation; a vector store does not solve source authority or claim-evidence entailment. Existing Agents SDK/model gateway and bounded page retrieval are enough for now. |

### Specific API/package guidance

- Keep provider calls behind small adapters implementing a shared search result contract: provider, route/lane, query, URL, title, publisher, date, snippet, request reference, and limitations.
- Prefer thin HTTP adapters for APIs already called with a small fixed schema; add a vendor SDK only if OAuth, pagination, typed response parsing, or signing makes its maintenance worthwhile.
- Do not add scraping packages as a substitute for platform APIs. Existing Jina Reader is already an external URL recipient; provider handling and retention decisions remain a production gate.
- Social content needs its own evidence origin/type and eligibility policy. Do not fold it into the existing `EXA` web-search lane and lose provenance.

## Minimum logic changes, in priority order

### P0 — Enforce route order and relevance

- Extend `PlannedQuery` or the deterministic plan with `topic`, `jurisdiction`, `freshness`, and a route lane. Do not ask the model to invent a trusted-domain allowlist.
- Resolve topic/jurisdiction to curated domain sets in application code. Execute authoritative searches first; use independent reporting if authoritative retrieval leaves a gap; call social search only for a matching claim type and only after public-web coverage is recorded.
- Record each route, domain set, trigger, result count, and retrieval outcome in search traces. Keep current call and result budgets.
- Treat domain filters as search constraints, not source validation. Still apply URL safety, retrieved-passage relevance, source eligibility, deduplication, and claim-level reasoning.

### P1 — Make the evidence answer auditable

- Require each factual answer sentence to map to eligible evidence IDs. Validate those IDs and links deterministically before rendering; reject unsupported sentences or replace them with a bounded explanation.
- Add passage-level citation anchors and compact visible citations in the UI. Show source title, publisher, date when known, and why it was selected. Preserve source disagreement.
- Add a small fact-check archive adapter after source routing is stable, with a clear `FACT_CHECK_CONTEXT` role.

### P2 — Complete the investigation loop

- Add persisted editorial dispositions with reviewer, timestamp, correction, and reason, separate from model findings. Respect the existing shared-demo restriction and production identity/retention gate.
- Add optional official social-source adapters only after access terms, cost, data handling, and deletion obligations are resolved.
- Add an evaluation set of stable facts, ambiguous requests, current claims, conflicting sources, misleading source candidates, and unavailable pages. Track correct answer, citation coverage, source-lane order, false certainty, and cost per completed investigation.

## Open risks and constraints

- Source authority is claim-specific and country-specific; a source list will have gaps and needs versioning and review.
- Search providers may return incomplete or stale indexes. A constrained first lane must not be reported as proof that no information exists.
- Citation presence alone does not prove entailment. An answer can cite a real page that does not support its sentence.
- Social API availability, pricing, scopes, and retention rules change; verify current platform requirements at implementation time.
- OpenAI’s official docs describe web-search citations/source annotations and a separate Deep Research workflow, but Agent Zero should retain its own staged routing, evidence model, and validation. Deep Research is a broad report workflow and is not required to fix this MVP’s basic factual-verification path.

## Sources reviewed

- OpenAI official documentation: [Web search](https://developers.openai.com/api/docs/guides/tools-web-search), [Deep research](https://developers.openai.com/api/docs/guides/deep-research), and [Citation formatting](https://developers.openai.com/api/docs/guides/citation-formatting).
- Google official documentation: [Fact Check Tools API](https://developers.google.com/fact-check/tools/api/reference/rest/).
- Kenya primary/official sources: [Kenya Presidential Library — Independence Order in Council](https://www.presidentiallibrary.go.ke/index.php/documents/statutory-instruments-1963-number-1968-kenya-independence-order-council-196312121963), [Kenya Presidential Library — independence celebrations](https://www.presidentiallibrary.go.ke/index.php/events/independence-celebrations-december-12-1963), and [UN Decolonization — former territories](https://www.un.org/dppa/decolonization/history/former-trust-and-nsgts).
- Social platform API references to recheck before implementation: [Reddit Data API documentation](https://www.reddit.com/dev/api/) and [Reddit Data API policy/help](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki).
