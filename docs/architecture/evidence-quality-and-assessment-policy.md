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
