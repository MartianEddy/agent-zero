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
        assessment = assess_verdict(claim.claim_type, proposed_status, signals)
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
        citation_signals = [signal for signal in signals if signal.evidence_id in cited_ids]
        if candidate is not None:
            assessment = assess_verdict(claim.claim_type, candidate.status, citation_signals)
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
                statement = (
                    "The cited material did not meet the requirements for claim evidence, so "
                    "Agent 0 could not establish a conclusion. Review the linked material and "
                    "seek a direct, independent source."
                )
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
