# Agent 0 investigation flow and evidence contract

**Status:** Implementation design for the MVP brief, 2026-10-09. This document describes intended behavior. A capability is considered available in the product only after its implementation and verification are recorded.

## Product boundary

Agent 0 assists journalists, editors, and fact-checkers by turning a submission into bounded claims, finding and retrieving relevant evidence, and drafting a source-linked assessment. It does not publish, claim exhaustive search, or replace editorial judgment. Search output is a lead; only content actually retrieved during the investigation can enter the evidence ledger. Retrieved web content is untrusted input and cannot change system instructions or route policy.

## User flow

1. **Submit:** one input accepts text, a public URL, or supported image/video. The interface shows what media formats are actually supported and that video audio is not transcribed. Unsupported audio/document inputs receive an explicit unsupported-input response.
2. **Triage:** before search, normalize input into one or more atomic claims. Return validated structured data: `claim_text`, `claim_type`, and `needs_deep_investigation`. Types are `SETTLED_FACT`, `CHECKABLE_EVENT`, `STATISTICAL`, `MEDIA_CLAIM`, `CONTESTED`, and `OPINION_OR_PREDICTION`. Ambiguous input yields a clarification question and does not silently create a claim. Users may edit or split proposed claims before continuing.
3. **Route:** settled facts use a bounded fast path to relevant authoritative references. Other checkable claims use a full investigation: primary/topic-authoritative material first; independent references and reporting to corroborate or fill a named gap; prior fact-checks as context; social platforms only when the claim concerns a post, account, circulation, or firsthand social report. OpenAI and Exa are independent search providers, both invoked when configured; one provider's failure does not silently substitute for the other. Each lane and reason is visible.
4. **Retrieve:** normalize and validate public URLs, retrieve pages through the configured retrieval adapter, record retrieval time and metadata, and admit evidence only from successful retrieval or explicitly typed media observations. Search snippets and titles remain leads. Bound requests, bytes, source count, model calls and time; cache retrieval within the case. Treat fetched text as untrusted data.
5. **Compare:** assign each evidence item a tier, stance, exact excerpt/location, source date/staleness, and independence group. Detect duplicate or derivative reports and do not count them as independent. Preserve disagreement in explicit contradiction pairs. Record gaps, what could change the assessment, and useful human next steps.
6. **Assess:** apply deterministic verdict sufficiency rules before rendering. Keep verdict and confidence separate. Unsupported, inaccessible, or conflicting evidence must remain explicit; no absence-of-search result becomes proof of falsity.
7. **Review and save:** show the draft answer first, citations inline, confidence rationale, ledger, provenance trace, contradictions, gaps and plain-language uncertainty. A human may record Publish, Hold, or Needs more work with rationale and optional verdict override. The decision is separate from the AI assessment and append-only in the audit trail.
8. **Export:** preserve original input, normalized claims, model/provider identifiers, prompts or prompt versions, route and search traces, retrieved source IDs, evidence, verdicts, timestamps and human decisions. Export structured JSON; PDF is a presentation of that same case record.

## Verdict and confidence rules

Verdict is exactly one of:

- `SUPPORTED`
- `CONTRADICTED`
- `PARTLY_TRUE`
- `INSUFFICIENT_EVIDENCE`
- `NOT_VERIFIABLE`

Confidence is a separate `HIGH`, `MEDIUM`, or `LOW` evidence-strength judgment, with one sentence grounded in evidence coverage, source quality, independence and recency. It is not a probability that a claim is true.

- `SUPPORTED` or `CONTRADICTED` requires two independent eligible sources, or one primary/authoritative source for a `SETTLED_FACT`.
- `PARTLY_TRUE` represents material mixed evidence or a proposition whose parts/senses produce different outcomes; explain each side and preserve the disagreement.
- `INSUFFICIENT_EVIDENCE` means retrieved evidence does not meet the rule. It does not imply the claim is false.
- `NOT_VERIFIABLE` is for opinion/prediction or a proposition that cannot be checked as framed; explain why and suggest a checkable reformulation when useful.
- When credible evidence conflicts, show the disagreement; never average it into a definitive answer.
- Every factual sentence in the explanation must link to one or more eligible evidence IDs. A cited URL must belong to a source successfully retrieved in this run, and a quoted excerpt must be validated against that retrieved content.
- No evidence item may be fabricated from model memory, a search-result snippet, a title, or a provider-generated summary.

## Data model additions required

The existing case, claim, source, evidence, finding and audit entities remain the foundation. The implementation needs explicit records/fields for:

- Claim triage type, deep-investigation flag, triage schema/version, and clarification state.
- Evidence source tier, stance, exact excerpt location, independence group, publication date, staleness, and run-scoped retrieval provenance.
- Verdict enum and independent confidence level/reason.
- Claim-to-sentence citation mapping and validation result.
- Provenance events/timeline and explicit contradiction pairs.
- Append-only reviewer decision, actor, rationale, override, and timestamp.
- Case export manifest and model/provider/prompt version trace.

Schema changes require an Alembic migration and a rollback/recovery note. Legacy records must be mapped conservatively; unknown legacy values must not be upgraded to a stronger verdict or confidence.

## MVP implementation assumptions

- Keep the current FastAPI/SQLAlchemy/Celery/Next.js stack and existing Pydantic/OpenAI/Exa/Jina adapters where possible.
- Do not add social SDKs until one platform and its access/data rules are selected. Keep the lane explicitly unavailable meanwhile.
- Treat `SETTLED_FACT` as a classifier decision that still requires one retrieved authoritative reference; it is not a no-search model-knowledge bypass.
- A media claim may use retrieved primary source pages and typed media observations, but visual appearance alone cannot establish event truth, identity, origin, or manipulation.
- If provider keys or retrieval are missing, say which step was unavailable. Do not represent model knowledge as a completed source investigation.
- Public demo remains non-sensitive and shared until authentication, access isolation, retention/deletion and provider handling are implemented and approved.


## Slice 1 implementation notes (2026-10-09)

Text, URL, and media submissions now use a structured triage draft. The draft is persisted without queueing research; the workspace lets the reviewer edit or split up to three claims and confirms before the worker is queued. Media uploads attach to that confirmed draft before queueing. `SETTLED_FACT` claims use the bounded Wikipedia/Wikidata reference adapter, independent of Jina; Wikipedia is an authoritative reference tier, while Wikidata descriptions are context. The case fast-path budget is five seconds and failure is recorded as insufficient evidence with a named limitation. Source tiers are configured in `backend/app/modules/sources/source_tiers.json`.

The sufficiency policy is applied in application code after structured model output. Opinion/prediction claims are always `NOT_VERIFIABLE`; unsupported or insufficiently independent model verdicts are downgraded. The tomato and similar sense-dependent behavior is instructed in the evidence-reasoning schema prompt; a dedicated deterministic semantic classifier is deferred because it would assert meaning without retrieved reference evidence.

Evaluation uses `evals/golden_claims.json` and `evals/run_eval.py`. The runner scores captured outputs and does not invoke a model or retrieval provider. `evals/RESULTS.md` reports no measured model scores because no live provider evaluation was run under the repository's provider sandbox rules.
