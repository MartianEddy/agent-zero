# Evidence quality and assessment policy

**Status:** Implemented foundation; verification pending.

## Product contract

Agent 0 must distinguish the outcome of a claim assessment from the strength of
the evidence trail. A status is not a probability. Confidence is qualitative
coverage/sufficiency guidance, never a numeric estimate that the claim is true.
The model proposes relationships and a verdict; application policy decides the
persisted status and confidence.

## Research flow

1. Turn the request into one or more atomic, time-bounded factual claims. Ask a
   focused clarification when subject, place, event, or time changes the answer.
2. Plan discovery by claim topic, jurisdiction, freshness, and source lane. Search
   the relevant public record or subject-matter authority first. Widen to
   independent reporting/reference sources to fill a named gap. Fact-check
   articles are leads/context and should be followed to their cited records.
3. Treat provider results, titles, snippets, and citations as candidates only.
   Retrieve public page content and validate the excerpt before admitting it as
   claim evidence. Failed retrieval is a coverage limitation, not evidence.
4. Assess each exact excerpt against the exact claim. Preserve support,
   contradiction, context, and uncertainty; reject invented or unsupported
   relationships. Keep all cited material inspectable.
5. Collapse excerpts from the same publisher, syndication/copy chain, or known
   citation chain into one independence group. Multiple passages from one group
   improve context, not corroboration.
6. Apply deterministic status and confidence thresholds. Show the user the
   status, a status-aligned explanation, evidence links, source-group coverage,
   retrieval gaps, and what to do next.

Search plans may contain multiple distinct focused queries in the same
claim/source lane. Deduplicate identical query text, then apply the configured
query budget; lane membership alone is not a reason to discard a distinct
query. When the bounded model packet contains several claims, interleave
excerpts by claim so one claim does not consume the shared context first.
Submitted pages and derivative/copy sources remain visible as context, but
their proposed support or contradiction relationship is persisted as context
and cannot count toward a verdict threshold.

## Source authority

The source registry describes identity, jurisdiction, and stated remit; it is
not a whitelist of truth and is not itself evidence. A domain-wide tier alone
cannot qualify a one-source exception. The settled-fact exception requires a
retrieved, validated excerpt assessed as directly supporting or contradicting
the claim from a registered primary/public-record source whose jurisdiction and
topic match the claim. The excerpt must still make the relevant point. Unknown,
social, and candidate-only sources cannot establish a verdict.

Add sources to the registry by institution and remit, then add topic-specific
search-query guidance. Keep source discovery open: credible unregistered sources
may still be retrieved and assessed, but cannot trigger the one-source
exception until their identity/remit is reviewed. Never make a whole host
automatically decisive. Priority sources for each topic should be curated in
the registry; independent sources remain necessary for corroboration.

## Policy changes (2026-10-28, verified by unit tests)

- **One official source can settle a statistic.** The one-source exception now covers
  `STATISTICAL` as well as `SETTLED_FACT`, but only for a registered primary source whose
  topic and jurisdiction match the claim. A statistic older than the freshness window
  (one year) cannot settle a current figure alone. `CHECKABLE_EVENT` still needs two
  independent groups.
- **An official record can outweigh press reports.** When support and contradiction both
  exist, a side with a topic-fit official group wins only if the other side has none and
  the winning side meets its own threshold. A model proposal that disagrees with the
  dominant side stays unresolved. Confidence is capped below HIGH when any opposing
  evidence exists.
- **Fact-checks are leads.** A new `FACT_CHECK` tier (Africa Check, PesaCheck, AFP Fact
  Check) is context-only and cannot count toward a threshold. Follow it to the records it cites.
- **Shared ownership is one group.** Different domains owned by one organisation
  (`ownership_groups` in `evidence_ledger.json`, for example Wikipedia and Wikidata, or the
  Nation Media Group sites) count once.
- **Wire credit lines group copies.** "Reuters reports", "(Reuters)", "according to Reuters"
  and a trailing credit in an excerpt group copied stories. Incidental mentions do not.
- **Confidence wording.** A decision settled by one official source is MEDIUM ("directly
  addresses the claim; no independent confirmation"). HIGH still needs two independent
  official groups and no opposing evidence.
- **Source list.** The registry now includes IEBC, Judiciary, CBK, Treasury, Controller of
  Budget, Auditor-General and IMF as official sources, and Reuters, AP, AFP, BBC, Business
  Daily, The Star, The EastAfrican and KBC as reputable reporting. These additions are
  pending editorial review.

## Policy changes (2026-11-25, from a review of production cases)

A replay of production evidence showed claims with good evidence ending as "not enough evidence". Changes, each covered by tests:

- **Unregistered sites corroborate with an anchor.** A retrieved, validated passage from an unregistered site now counts as an independent group, but only when a recognised source (official, reference or reputable reporting) supports the same side. Unregistered sites alone never decide. Any decision that uses one is capped at MEDIUM.
- **Inferred tiers.** Government domains (for example `.go.ke`, `.gov`, `.gov.uk`) count as official and academic domains (`.ac.ke`, `.edu`) as reference, without the one-source exception unless registered. LinkedIn and similar platforms are social.
- **Reference works settle settled facts.** For `SETTLED_FACT` only, a reference work (Wikipedia, Britannica) passage that directly supports or contradicts the claim can decide alone, at MEDIUM, if nothing contradicts it.
- **Historical events.** A `CHECKABLE_EVENT` about a year at least two years past, with no future wording, may be settled by one topic-fit official record.
- **Relevance guard.** A SUPPORTS or CONTRADICTS label only counts if the passage shares distinctive terms with the claim.
- **Retrieval.** Up to 14 candidates and 8 pages per case (was 8 and 5); `www.` and non-`www.` URLs are one page; at most 3 candidates and 2 reads per site per round; an earlier pass's read limit no longer blocks later passes. Previously every case stopped after 3 pages.
- **Settled-fact timing.** The reference lookup keeps a 5-second limit, but the assessment now has up to 45 seconds (it previously shared the 5 seconds and often timed out).
- **Settled facts fall through.** The reference lookup is a shortcut, not the final word. If it finds no usable passage, or the passage does not decide the claim, the claim is researched in full (search and page reading) with the reference passage kept as evidence. Wikipedia results are taken in search-rank order, and the passage that best matches the claim is chosen from the top article, not just its first four sentences.
- **Clearer "not enough evidence".** When nothing countable was found, the headline says what was found and why it could not count.

## Verdict gates

- `SUPPORTED` / `CONTRADICTED`: at least two independent eligible groups on the
  same side, or one directly relevant registered primary source for a
  `SETTLED_FACT`; no unresolved material evidence conflict.
- `PARTLY_TRUE`: only when the model identifies materially distinct parts or
  senses, there is eligible evidence on both sides from disjoint independent
  groups, and the explanation cites the evidence. A mere source disagreement
  is unresolved, not proof of a partly true claim. Current policy remains
  conservative because persisted claim components are not yet modeled.
- `INSUFFICIENT_EVIDENCE`: retrieval, relevance, independence, authority, or
  conflict thresholds are not met. Explain whether evidence is consistent with
  the claim, challenges it, or conflicts, and explicitly avoid implying that
  insufficient evidence means false.
- `NOT_VERIFIABLE`: the proposition is opinion/prediction or is not checkable as
  framed.

## Qualitative evidence-confidence rule

This is a decision rubric, not a probability model:

- **LOW:** no eligible evidence, only one independent group, indirect/context
  evidence only, or an unresolved/insufficient finding with material gaps.
- **MEDIUM:** at least two independent groups provide relevant retrieved
  evidence, but topic/jurisdiction authority coverage, directness, or agreement
  is incomplete. This can describe a well-evidenced conflict, not certainty.
- **HIGH:** only a conclusive `SUPPORTED` or `CONTRADICTED` finding with at least
  two independent eligible groups, including at least two topic-fit primary
  authority groups, and no material conflict.

Freshness is evaluated against claim type: a dated historical record does not
become stale merely with age, while current status/statistics require recent
coverage. Search rank, provider agreement, source count before deduplication,
and model self-reported confidence do not increase confidence.

## User-facing consistency

Generate the headline from the final application-owned status and policy
rationale for every finding; never use model prose as the verdict-bearing
summary. Keep citation-validated sentences available as evidence detail. For a
lone supporting group, say the retrieved evidence is consistent with the claim
but does not meet corroboration requirements; explicitly say this is not a
finding that the claim is false. Cite-checked sentences establish traceability,
not semantic entailment, so the relation and final assessment remain bounded
model judgments subject to application thresholds.

## Current limitations and next evolution

The registry is intentionally small; authority fit uses explicit topic tokens
and jurisdiction labels and needs broader reviewed coverage. Evidence
relationships and source groups still depend on bounded model classification
plus deterministic validation. `PARTLY_TRUE` lacks structured claim-component
coverage. The next research-quality phase should add claim components, relation
provenance, structured temporal applicability, source ownership/copy lineage,
and a labeled calibration evaluation before any numeric confidence score is
considered.

## Model-call records and training samples

Every model call records its provider, model, purpose, token counts, latency and a short hash of
its instructions (`prompt_version`), so a change in behaviour can be tied to a prompt change.
When `CAPTURE_STAGE_SAMPLES=true`, a redacted copy of each prompt and structured output is also
stored in `stage_samples` for evaluation and, later, training. Redaction removes emails, phone
numbers and long identifiers. The setting is off by default. Do not enable it until consent,
retention and reviewer-identity decisions are recorded in `docs/OPEN-QUESTIONS.md`.
