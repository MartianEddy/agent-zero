"""Fast path for settled facts and opinions, using reference sources."""

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.investigations.investigator import (
    ModelInvocationFailed,
)
from app.modules.investigations.models import (
    Claim,
    ClaimEvidence,
    Evidence,
    Investigation,
    SearchTrace,
    Source,
    SourceRelationship,
    utcnow,
)
from app.modules.investigations.orchestrator import common, findings_stage, ports
from app.modules.investigations.usage import (
    ModelCallBudgetExceeded,
)
from app.modules.investigations.verdict_policy import (
    build_independence_groups,
)
from app.modules.sources.tiers import source_tier_for_domain
from app.modules.sources.urls import normalize_source_url


def _persist_settled_reference_evidence(
    session: Session,
    investigation: Investigation,
    claim: Claim,
    result,
    *,
    claim_index: int,
) -> None:
    """Persist reference API passages directly; this path does not use Jina Reader."""
    provider_names = {"wikipedia_api": "WIKIPEDIA_API", "wikidata_api": "WIKIDATA_API"}
    traces: dict[str, SearchTrace] = {}
    for provider, label in provider_names.items():
        provider_excerpts = [item for item in result.excerpts if item.provider == provider]
        unavailable = any(label.replace("_", " ").title() in note for note in result.unavailable)
        trace = SearchTrace(
            investigation_id=investigation.id,
            provider=label,
            action="search" if provider_excerpts else "unavailable" if unavailable else "empty",
            query=claim.text,
            route_metadata={
                "claim_index": claim_index,
                "topic": "settled fact reference lookup",
                "jurisdiction": [],
                "freshness": "BALANCED",
                "source_lane": "PRIMARY",
                "widening_reason": "Bounded settled-fact reference route; Wikipedia is a reference, not a primary source.",
            },
            sources=[{"title": item.title, "url": item.url} for item in provider_excerpts],
            citations=[{"title": item.title, "url": item.url} for item in provider_excerpts],
        )
        session.add(trace)
        session.flush()
        traces[provider] = trace
        if provider_excerpts:
            common._usage(session, investigation.id).search_calls += 1

    for item in result.excerpts:
        try:
            normalized_url = normalize_source_url(item.url)
        except ValueError:
            continue
        source = session.scalar(
            select(Source).where(
                Source.investigation_id == investigation.id,
                Source.url == normalized_url,
            )
        )
        domain = common._source_domain(normalized_url)
        if source is None:
            source = Source(
                investigation_id=investigation.id,
                url=normalized_url,
                title=item.title[:2000],
                publisher="Wikipedia" if item.provider == "wikipedia_api" else "Wikidata",
                domain=domain,
                source_type="REFERENCE",
                source_role="AUTHORITATIVE_REFERENCE",
                discovery_method="SETTLED_FACT_REFERENCE",
                discovery_trace_id=traces[item.provider].id,
                retrieval_status="RETRIEVED",
                retrieval_provider=item.provider,
                content_sha256=hashlib.sha256(item.excerpt.encode("utf-8")).hexdigest(),
                retrieved_at=utcnow(),
            )
            session.add(source)
            session.flush()
            common._usage(session, investigation.id).sources_discovered += 1
        else:
            source.retrieval_status = "RETRIEVED"
            source.retrieval_provider = item.provider
            source.retrieved_at = utcnow()
            source.discovery_trace_id = traces[item.provider].id
        evidence = Evidence(
            investigation_id=investigation.id,
            source_id=source.id,
            content=item.excerpt[: ports.get_settings().max_source_chars_per_source],
            method="REFERENCE_API_EXCERPT",
            source_tier="AUTHORITATIVE_REFERENCE",
            stance="UNKNOWN",
            excerpt_start=0,
            excerpt_end=len(item.excerpt[: ports.get_settings().max_source_chars_per_source]),
            independence_group_id=f"source-group:{source.id}",
            published_date=source.published_at,
            retrieval_timestamp=source.retrieved_at,
            run_id=investigation.id,
            excerpt_validated=bool(item.excerpt.strip()),
            limitations=(
                "Retrieved through the provider's public API. Wikipedia is a secondary reference; "
                "Wikidata entity descriptions are context only and do not establish the claim."
            ),
        )
        session.add(evidence)
        session.flush()
        session.add(
            ClaimEvidence(claim_id=claim.id, evidence_id=evidence.id, relationship="UNKNOWN")
        )
    if result.unavailable:
        usage = common._usage(session, investigation.id)
        usage.limitations = list(dict.fromkeys([*usage.limitations, *result.unavailable]))
    session.commit()


def _settled_claim_packet(session: Session, claim: Claim) -> str:
    rows = list(
        session.execute(
            select(Evidence, ClaimEvidence, Source)
            .join(ClaimEvidence, ClaimEvidence.evidence_id == Evidence.id)
            .join(Source, Source.id == Evidence.source_id)
            .where(ClaimEvidence.claim_id == claim.id)
            .order_by(Evidence.created_at)
        )
    )
    relationships = list(
        session.scalars(
            select(SourceRelationship).where(
                SourceRelationship.investigation_id == claim.investigation_id
            )
        )
    )
    source_domains = {str(source.id): source.domain for _, _, source in rows}
    groups = build_independence_groups(
        source_domains,
        [
            (str(item.source_id), str(item.related_source_id), item.relationship_type)
            for item in relationships
        ],
    )
    return json.dumps(
        {
            "claims": [{"id": str(claim.id), "text": claim.text, "claim_type": claim.claim_type}],
            "evidence": [
                {
                    "evidence_id": str(evidence.id),
                    "claim_id": str(link.claim_id),
                    "excerpt": evidence.content,
                    "title": source.title,
                    "publisher": source.publisher,
                    "url": source.url,
                    "source_tier": source_tier_for_domain(source.domain),
                    "independence_group_id": groups.get(str(source.id)),
                    "stance": "CONTEXT",
                    "retrieval_status": source.retrieval_status,
                }
                for evidence, link, source in rows
            ],
            "limitations": common._usage(session, claim.investigation_id).limitations,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _settled_claims_packet(session: Session, claims: list[Claim]) -> str:
    """One evidence packet covering several settled-fact claims (one model call, not one each)."""
    merged: dict[str, object] = {"claims": [], "evidence": [], "limitations": []}
    for claim in claims:
        packet = json.loads(_settled_claim_packet(session, claim))
        merged["claims"].extend(packet["claims"])  # type: ignore[union-attr]
        merged["evidence"].extend(packet["evidence"])  # type: ignore[union-attr]
        merged["limitations"] = packet["limitations"]
    return json.dumps(merged, ensure_ascii=False, separators=(",", ":"))


def _assess_settled_claims(
    session: Session,
    investigation: Investigation,
    claims: list[Claim],
    *,
    case_deadline: float,
) -> None:
    """Assess all retrieved settled-fact claims with a single bounded reasoning call."""
    remaining = case_deadline - ports.monotonic()
    if remaining <= 0:
        for claim in claims:
            findings_stage._record_deterministic_finding(
                session,
                investigation,
                claim,
                status="INSUFFICIENT_EVIDENCE",
                statement=(
                    "A reference page was retrieved, but the evidence assessment could not be "
                    "completed in time."
                ),
                confidence_reason="The retrieved reference passage was not assessed.",
                limitation="The evidence assessment could not be completed in time.",
            )
        return
    try:
        output = ports.ModelGateway().reason_about_evidence(
            evidence_packet=_settled_claims_packet(session, claims),
            session=session,
            investigation_id=investigation.id,
            timeout_seconds=remaining,
        )
        findings_stage._persist_findings(session, investigation, output.output)
    except (ModelInvocationFailed, ModelCallBudgetExceeded) as exc:
        ports.add_limitation(
            session,
            investigation.id,
            "The evidence-assessment step was unavailable or took too long to finish.",
        )
        reason = getattr(getattr(exc, "category", None), "value", "provider error")
        for claim in claims:
            findings_stage._record_deterministic_finding(
                session,
                investigation,
                claim,
                status="INSUFFICIENT_EVIDENCE",
                statement=(
                    "A reference passage was retrieved, but the evidence assessment step was "
                    "unavailable. The claim remains unchecked."
                ),
                confidence_reason="The retrieved reference was not assessed by the evidence-reasoning step.",
                limitation=f"Evidence assessment unavailable ({reason}).",
            )


def _run_fast_path_claims(
    session: Session,
    investigation: Investigation,
    *,
    case_deadline: float,
    lookup_deadline: float | None = None,
) -> set[int]:
    """Assess settled facts from reference sources; never use model memory alone.

    The reference lookup is bounded by lookup_deadline (a few seconds); the evidence
    assessment that follows may use the rest of the case deadline.
    """
    lookup_deadline = case_deadline if lookup_deadline is None else lookup_deadline
    claims = list(
        session.scalars(
            select(Claim)
            .where(Claim.investigation_id == investigation.id)
            .order_by(Claim.created_at, Claim.id)
        )
    )
    fast_indexes: set[int] = set()
    ready: list[Claim] = []
    for index, claim in enumerate(claims):
        if claim.claim_type == "OPINION_OR_PREDICTION":
            findings_stage._record_deterministic_finding(
                session,
                investigation,
                claim,
                status="NOT_VERIFIABLE",
                statement=(
                    "This is an opinion or prediction, so it cannot be verified as a factual claim. "
                    "Submit a specific factual statement if you want it checked."
                ),
                confidence_reason="Opinions and predictions have no source-verifiable truth value.",
            )
            fast_indexes.add(index)
            continue
        if claim.claim_type != "SETTLED_FACT" or claim.needs_deep_investigation:
            continue
        fast_indexes.add(index)
        remaining = lookup_deadline - ports.monotonic()
        if remaining <= 0:
            findings_stage._record_deterministic_finding(
                session,
                investigation,
                claim,
                status="INSUFFICIENT_EVIDENCE",
                statement="The reference check did not finish in time to assess this claim.",
                confidence_reason="No usable authoritative reference passage was retrieved.",
                limitation="The reference-source check could not finish in time.",
            )
            continue
        result = ports.lookup_settled_fact(claim.text, deadline_seconds=remaining)
        _persist_settled_reference_evidence(
            session, investigation, claim, result, claim_index=index
        )
        wiki_evidence = session.scalar(
            select(Evidence.id)
            .join(Source, Source.id == Evidence.source_id)
            .join(ClaimEvidence, ClaimEvidence.evidence_id == Evidence.id)
            .where(
                Evidence.investigation_id == investigation.id,
                Evidence.method == "REFERENCE_API_EXCERPT",
                Source.retrieval_provider == "wikipedia_api",
                ClaimEvidence.evidence_id == Evidence.id,
                ClaimEvidence.claim_id == claim.id,
            )
            .limit(1)
        )
        if wiki_evidence is None:
            unavailable = (
                "; ".join(result.unavailable) or "No relevant Wikipedia article text was returned."
            )
            findings_stage._record_deterministic_finding(
                session,
                investigation,
                claim,
                status="INSUFFICIENT_EVIDENCE",
                statement=f"I couldn’t complete an authoritative reference check: {unavailable} No conclusion was drawn from model knowledge alone.",
                confidence_reason="No retrieved authoritative reference passage was available for this claim.",
                limitation=unavailable,
            )
            continue
        ready.append(claim)

    if ready:
        _assess_settled_claims(session, investigation, ready, case_deadline=case_deadline)
    return fast_indexes
