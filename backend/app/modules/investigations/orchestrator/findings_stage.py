"""Apply the verdict policy to model proposals and write findings and the brief."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.investigations.evidence_ledger import (
    validate_sentence_citations,
)
from app.modules.investigations.investigator import (
    EvidenceReasoning,
    ReasonedFinding,
)
from app.modules.investigations.models import (
    Claim,
    ClaimEvidence,
    Evidence,
    Finding,
    FindingEvidence,
    Investigation,
    Source,
    SourceRelationship,
    VerificationBrief,
)
from app.modules.investigations.orchestrator import common
from app.modules.investigations.summary import finding_result_summary
from app.modules.investigations.verdict_policy import (
    EvidenceSignal,
    VerdictAssessment,
    assess_verdict,
    build_independence_groups,
)
from app.modules.sources.registry import authority_fits_claim
from app.modules.sources.tiers import source_tier_for_domain


def _persist_findings(
    session: Session,
    investigation: Investigation,
    output: EvidenceReasoning,
) -> None:
    claims = list(session.scalars(select(Claim).where(Claim.investigation_id == investigation.id)))
    sources = list(
        session.scalars(select(Source).where(Source.investigation_id == investigation.id))
    )
    source_by_id = {item.id: item for item in sources}
    source_relationships = list(
        session.scalars(
            select(SourceRelationship).where(
                SourceRelationship.investigation_id == investigation.id
            )
        )
    )
    independence_groups = build_independence_groups(
        {str(item.id): item.domain for item in sources},
        [
            (str(item.source_id), str(item.related_source_id), item.relationship_type)
            for item in source_relationships
        ],
    )
    existing = {
        item.claim_id
        for item in session.scalars(
            select(Finding).where(Finding.investigation_id == investigation.id)
        )
    }
    proposed: dict[str, ReasonedFinding] = {}
    duplicate_claim_ids: set[str] = set()
    for finding in output.findings:
        if finding.claim_id in proposed:
            duplicate_claim_ids.add(finding.claim_id)
        else:
            proposed[finding.claim_id] = finding
    for claim_id in duplicate_claim_ids:
        proposed.pop(claim_id, None)
    if duplicate_claim_ids:
        common._audit(
            session,
            investigation.id,
            "DUPLICATE_FINDING_PROPOSALS_REJECTED",
            {"count": len(duplicate_claim_ids)},
        )
    for claim in claims:
        if claim.id in existing:
            continue
        candidate = proposed.get(str(claim.id))
        accepted: list[tuple[UUID, str]] = []
        accepted_methods: dict[UUID, str] = {}
        if candidate is not None:
            for assessment in candidate.evidence:
                if assessment.relationship not in common.ALLOWED_RELATIONSHIPS:
                    continue
                try:
                    evidence_id = UUID(assessment.evidence_id)
                except ValueError:
                    continue
                link = session.scalar(
                    select(ClaimEvidence).where(
                        ClaimEvidence.claim_id == claim.id,
                        ClaimEvidence.evidence_id == evidence_id,
                    )
                )
                if link is None:
                    continue
                evidence = session.scalar(
                    select(Evidence).where(
                        Evidence.id == evidence_id,
                        Evidence.investigation_id == investigation.id,
                        Evidence.method != "MEDIA_FINGERPRINT",
                        (Evidence.source_id.is_not(None) | Evidence.media_asset_id.is_not(None)),
                    )
                )
                if evidence is None:
                    continue
                source = source_by_id.get(evidence.source_id) if evidence.source_id else None
                relationship = assessment.relationship
                if source and (
                    source.discovery_method == "SUBMITTED_URL"
                    or source.source_role in {"SUBMITTED", "DERIVATIVE"}
                ):
                    relationship = "CONTEXTUALIZES"
                link.relationship = relationship
                evidence.stance = {
                    "SUPPORTS": "SUPPORTS",
                    "CONTRADICTS": "CONTRADICTS",
                    "CONTEXTUALIZES": "CONTEXT",
                    "MENTIONS": "CONTEXT",
                    "UNKNOWN": "UNKNOWN",
                }[relationship]
                accepted.append((evidence_id, relationship))
                accepted_methods[evidence_id] = evidence.method
        proposed_status = candidate.status if candidate is not None else "INSUFFICIENT_EVIDENCE"
        signals: list[EvidenceSignal] = []
        off_topic = 0
        for evidence_id, relationship in accepted:
            evidence = session.get(Evidence, evidence_id)
            source = (
                source_by_id.get(evidence.source_id) if evidence and evidence.source_id else None
            )
            if (
                source is None
                or source.retrieval_status != "RETRIEVED"
                or source.discovery_method == "SUBMITTED_URL"
                or source.source_role in {"SUBMITTED", "DERIVATIVE"}
                or not evidence
                or not evidence.excerpt_validated
                or evidence.run_id != investigation.id
            ):
                continue
            if relationship not in {"SUPPORTS", "CONTRADICTS"}:
                continue
            tier = source_tier_for_domain(source.domain)
            if not _passage_addresses_claim(
                claim.text,
                evidence.content,
                rebuttal=relationship == "CONTRADICTS" and tier in RECOGNISED_TIERS,
            ):
                # The model labelled a passage that does not mention the claim's subject
                # (for example a page's sidebar headline). Keep it as context only.
                off_topic += 1
                continue
            group_id = evidence.independence_group_id
            if not group_id or group_id == "unknown":
                group_id = independence_groups.get(str(source.id), "")
            if tier == "SECONDARY_AGGREGATOR" and source.source_type == "UNKNOWN":
                continue
            signals.append(
                EvidenceSignal(
                    evidence_id=str(evidence_id),
                    stance=relationship,
                    source_tier=tier,
                    independence_group_id=group_id,
                    retrieved=True,
                    authority_fits_claim=authority_fits_claim(source.domain, claim.text),
                    is_stale=evidence.is_stale,
                )
            )
        assessment = assess_verdict(
            claim.claim_type, proposed_status, signals, claim_text=claim.text
        )
        evidence_by_id: dict[str, dict[str, object]] = {}
        for evidence_id, _relationship in accepted:
            evidence = session.get(Evidence, evidence_id)
            source = (
                source_by_id.get(evidence.source_id) if evidence and evidence.source_id else None
            )
            if evidence and (source or evidence.media_asset_id):
                if evidence.media_asset_id:
                    # Media observations are stored evidence produced in this run; they are
                    # cited as observations, not as quotations from a source URL.
                    evidence.run_id = investigation.id
                    evidence.excerpt_validated = True
                evidence_by_id[str(evidence_id)] = {
                    "retrieved_url": source.url
                    if source and source.retrieval_status == "RETRIEVED"
                    else None,
                    "is_media": bool(evidence.media_asset_id),
                    "excerpt_validated": evidence.excerpt_validated,
                    "run_id": str(evidence.run_id) if evidence.run_id else None,
                }
        checked_sentences, unsupported_removed = validate_sentence_citations(
            [sentence.model_dump() for sentence in (candidate.explanation if candidate else [])],
            evidence_by_id,
            run_id=str(investigation.id),
        )
        if candidate is not None and not candidate.explanation:
            unsupported_removed = True
        cited_ids = {
            str(evidence_id)
            for sentence in checked_sentences
            for evidence_id in sentence["evidence_ids"]
        }
        if candidate is not None:
            assessment, signals = _judge(
                claim.claim_type, candidate.status, signals, cited_ids, claim_text=claim.text
            )
        citation_signals = signals
        status = assessment.verdict
        support_group_count = len(
            {item.independence_group_id for item in citation_signals if item.stance == "SUPPORTS"}
        )
        contradiction_group_count = len(
            {
                item.independence_group_id
                for item in citation_signals
                if item.stance == "CONTRADICTS"
            }
        )
        if status == "SUPPORTED":
            statement = (
                f"Retrieved evidence meets the support threshold through "
                f"{support_group_count} independent source group(s). Review the linked passages "
                "and context before publication."
            )
            limitations = candidate.limitations if candidate is not None else []
        elif status == "CONTRADICTED":
            statement = (
                f"Retrieved evidence meets the challenge threshold through "
                f"{contradiction_group_count} independent source group(s). Review the linked "
                "passages and context before publication."
            )
            limitations = candidate.limitations if candidate is not None else []
        elif status == "PARTLY_TRUE":
            statement = (
                "Independent retrieved evidence supports and challenges different parts or "
                "interpretations of this claim. Review the cited passages for that distinction."
            )
            limitations = candidate.limitations if candidate is not None else []
        elif status == "INSUFFICIENT_EVIDENCE":
            if support_group_count and not contradiction_group_count:
                statement = (
                    f"Retrieved evidence is consistent with this claim, but it comes from "
                    f"{support_group_count} independent source group(s), below the required "
                    "corroboration threshold. This is not a finding that the claim is false."
                )
            elif contradiction_group_count and not support_group_count:
                statement = (
                    f"Retrieved evidence challenges this claim, but it comes from "
                    f"{contradiction_group_count} independent source group(s), below the "
                    "required corroboration threshold. This is not a conclusive finding that "
                    "the claim is false."
                )
            elif support_group_count and contradiction_group_count:
                statement = (
                    "Retrieved evidence points in conflicting directions, and the available "
                    "sources do not establish a reliable conclusion. Review the cited passages "
                    "and seek independent corroboration."
                )
            else:
                statement = _nothing_countable_statement(session, accepted, source_by_id)
            limitations = [assessment.rationale, assessment.confidence_reason]
        elif status == "NOT_VERIFIABLE":
            statement = (
                "This is an opinion or prediction, so it cannot be verified as a factual claim. "
                "Submit a specific factual statement if you want it checked."
            )
            limitations = ["Opinions and predictions do not have a source-verifiable truth value."]
        evidence_confidence = assessment.confidence
        confidence_rationale = assessment.confidence_reason
        if status == "PARTLY_TRUE" and candidate is not None:
            limitations = candidate.limitations
        if status == "SUPPORTED":
            supporting_methods = {
                accepted_methods[evidence_id]
                for evidence_id, relationship in accepted
                if relationship == "SUPPORTS"
            }
            if supporting_methods == {"MEDIA_PROVENANCE"}:
                cited = [
                    session.get(Evidence, evidence_id)
                    for evidence_id, relationship in accepted
                    if relationship == "SUPPORTS"
                ]
                declares_ai = any(
                    item is not None
                    and "Content Credentials declare generative AI involvement." in item.content
                    for item in cited
                )
                statement = (
                    "The uploaded image contains Content Credentials declaring "
                    "generative-AI involvement."
                    if declares_ai
                    else "The uploaded image contains locally validated Content Credentials."
                )
                limitations = [
                    "Content Credentials are provenance assertions and do not establish the "
                    "truth of depicted events. Local remote-manifest and OCSP checks were disabled."
                ]
                evidence_confidence = "MEDIUM"
                confidence_rationale = (
                    "Local credentials were validated, but they describe provenance and do not "
                    "verify the depicted event."
                )
            elif supporting_methods == {"MEDIA_VISUAL_OBSERVATION"}:
                statement = (
                    "A visual observation in the uploaded image is consistent with this claim; "
                    "visual interpretation is not forensic verification."
                )
                limitations = [
                    "Visual observations may be mistaken and do not independently establish the "
                    "truth of the depicted event."
                ]
                evidence_confidence = "LOW"
                confidence_rationale = (
                    "This is a fallible visual observation and is not independent verification."
                )
        finding = Finding(
            investigation_id=investigation.id,
            claim_id=claim.id,
            status=status,
            statement=statement,
            evidence_confidence=evidence_confidence,
            confidence_rationale=confidence_rationale[:1000],
            explanation_json=checked_sentences,
            unsupported_statements_removed=unsupported_removed,
            limitations="; ".join(limitations)[:2000] or None,
        )
        session.add(finding)
        session.flush()
        session.add_all(
            [
                FindingEvidence(finding_id=finding.id, evidence_id=evidence_id)
                for evidence_id, _ in accepted
            ]
        )
    session.commit()
    common._audit(session, investigation.id, "FINDINGS_CREATED", {"count": len(claims)})


def _judge(
    claim_type: str,
    proposal: str,
    signals: list[EvidenceSignal],
    cited_ids: set[str],
    *,
    claim_text: str,
) -> tuple[VerdictAssessment, list[EvidenceSignal]]:
    """Apply the verdict policy to a model proposal; return the verdict and counted signals.

    Every validated, on-topic passage the model labelled counts toward the threshold, but
    the explanation must cite at least one passage on the side that decides the verdict.
    Otherwise only the passages the explanation cites are judged.
    """
    assessment = assess_verdict(claim_type, proposal, signals, claim_text=claim_text)
    decided_stance = {"SUPPORTED": "SUPPORTS", "CONTRADICTED": "CONTRADICTS"}.get(
        assessment.verdict
    )
    if assessment.verdict == "PARTLY_TRUE" or any(
        signal.evidence_id in cited_ids and signal.stance == decided_stance
        for signal in signals
    ):
        return assessment, signals
    cited = [signal for signal in signals if signal.evidence_id in cited_ids]
    return assess_verdict(claim_type, proposal, cited, claim_text=claim_text), cited


def _record_deterministic_finding(
    session: Session,
    investigation: Investigation,
    claim: Claim,
    *,
    status: str,
    statement: str,
    confidence_reason: str,
    limitation: str | None = None,
) -> None:
    if session.scalar(select(Finding.id).where(Finding.claim_id == claim.id).limit(1)):
        return
    session.add(
        Finding(
            investigation_id=investigation.id,
            claim_id=claim.id,
            status=status,
            statement=statement,
            evidence_confidence="LOW",
            confidence_rationale=confidence_reason,
            limitations=limitation,
        )
    )
    session.commit()


def _create_unverified_findings(session: Session, investigation: Investigation) -> None:
    claims = list(session.scalars(select(Claim).where(Claim.investigation_id == investigation.id)))
    existing = {
        item.claim_id
        for item in session.scalars(
            select(Finding).where(Finding.investigation_id == investigation.id)
        )
    }
    for claim in claims:
        if claim.id not in existing:
            session.add(
                Finding(
                    investigation_id=investigation.id,
                    claim_id=claim.id,
                    status="INSUFFICIENT_EVIDENCE",
                    statement=(
                        "Agent 0 could not verify this claim because no retrieved, claim-linked "
                        "evidence was available. Review the listed source candidates or provide "
                        "an accessible primary source."
                    ),
                    evidence_confidence="LOW",
                    confidence_rationale=(
                        "The available evidence is insufficient or not traceably linked to this claim."
                    ),
                    limitations="No retrieved source excerpt was available for assessment.",
                )
            )
    session.commit()
    common._audit(
        session,
        investigation.id,
        "FINDINGS_CREATED",
        {"count": len(claims), "mode": "deterministic_inconclusive"},
    )


def _build_brief(
    session: Session, investigation: Investigation, *, summary_override: str | None = None
) -> None:
    if session.scalar(
        select(VerificationBrief.id).where(VerificationBrief.investigation_id == investigation.id)
    ):
        return
    usage = common._usage(session, investigation.id)
    findings = list(
        session.scalars(select(Finding).where(Finding.investigation_id == investigation.id))
    )
    claims = list(session.scalars(select(Claim).where(Claim.investigation_id == investigation.id)))
    media_counts = {
        method: session.scalar(
            select(func.count(Evidence.id)).where(
                Evidence.investigation_id == investigation.id,
                Evidence.method == method,
            )
        )
        or 0
        for method in ("MEDIA_PROVENANCE", "MEDIA_TECHNICAL_METADATA", "MEDIA_VISUAL_OBSERVATION")
    }
    media_labels = {
        "MEDIA_PROVENANCE": "image provenance",
        "MEDIA_TECHNICAL_METADATA": "image file details",
        "MEDIA_VISUAL_OBSERVATION": "visible image content",
    }
    present_media = [media_labels[name] for name, count in media_counts.items() if count]
    summary = summary_override or finding_result_summary(findings)
    if present_media and not summary_override:
        summary += "\n\nMedia reviewed: " + ", ".join(present_media) + "."
    limitations = list(usage.limitations)
    if not findings and claims:
        limitations.append("Findings are unavailable because evidence reasoning did not complete.")
    if any(item.status in {"PARTLY_TRUE", "INSUFFICIENT_EVIDENCE"} for item in findings):
        limitations.append(
            "Recommended next step: review the cited sources and seek confirmation from an "
            "independent, authoritative source before publication. This is a recommendation, "
            "not evidence."
        )
    brief = VerificationBrief(
        investigation_id=investigation.id,
        summary=summary,
        limitations=list(dict.fromkeys(limitations)),
        version=1,
    )
    session.add(brief)
    session.commit()
    common._audit(session, investigation.id, "BRIEF_GENERATED", {"finding_count": len(findings)})


_GENERIC = {
    "said",
    "says",
    "will",
    "would",
    "have",
    "been",
    "were",
    "they",
    "their",
    "there",
    "which",
    "about",
    "into",
    "over",
    "also",
    "than",
    "then",
    "some",
    "more",
    "most",
    "kenya",
    "kenyan",
    "true",
    "false",
}


# Tiers whose rebuttals may name the true answer instead of the claim's subject.
RECOGNISED_TIERS = frozenset({"PRIMARY", "AUTHORITATIVE_REFERENCE", "REPUTABLE_REPORTING"})


def _passage_addresses_claim(claim_text: str, passage: str, *, rebuttal: bool = False) -> bool:
    """Whether a passage shares enough distinctive terms with the claim to judge it.

    A cheap, deterministic check on the model's stance label: at least two of the claim's
    distinctive terms (one, if the claim only has one or two) must appear in the passage.
    A rebuttal from a recognised source needs one: "Nairobi, the capital" rebuts
    "Mombasa is the capital city" without naming Mombasa.
    """
    from app.modules.investigations.orchestrator.search_stage import _relevance_terms

    claim_terms = _relevance_terms(claim_text) - _GENERIC
    if not claim_terms:
        return True
    passage_terms = _relevance_terms(passage)
    stems = {term[:6] for term in passage_terms}
    shared = {term for term in claim_terms if term in passage_terms or term[:6] in stems}
    needed = 1 if len(claim_terms) <= 2 or rebuttal else 2
    return len(shared) >= needed


def _nothing_countable_statement(session: Session, accepted, source_by_id) -> str:
    """Say what was found and why it could not count, instead of a generic message."""
    domains: dict[str, set[str]] = {"SUPPORTS": set(), "CONTRADICTS": set()}
    media_only = bool(accepted)
    for evidence_id, relationship in accepted:
        item = session.get(Evidence, evidence_id)
        if item is None or not item.media_asset_id:
            media_only = False
        if relationship not in domains:
            continue
        evidence = session.get(Evidence, evidence_id)
        source = source_by_id.get(evidence.source_id) if evidence and evidence.source_id else None
        if source is not None and source.domain:
            domains[relationship].add(source.domain.removeprefix("www."))
    if media_only:
        return (
            "The checks on the attached file did not establish this claim on their own, so no "
            "conclusion was reached. File details and content credentials describe a file's "
            "history; they do not prove what it shows. This is not a finding that the claim "
            "is false."
        )
    found = sorted(domains["SUPPORTS"] | domains["CONTRADICTS"])
    if found:
        listed = ", ".join(found[:3])
        return (
            f"Some passages on {listed} relate to this claim, but they come from social media, "
            "the claim's own subject, or sources that could not be confirmed as independent. "
            "Agent 0 needs two independent sources, or one official record, before it reaches a "
            "conclusion. This is not a finding that the claim is false."
        )
    return (
        "The pages Agent 0 could read did not directly address this claim, so no conclusion "
        "was reached. This is not a finding that the claim is false. Try adding a date, a "
        "place or a link to the original source."
    )
