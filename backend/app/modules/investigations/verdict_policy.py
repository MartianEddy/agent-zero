"""Deterministic verdict sufficiency rules; model proposals are advisory only."""

from dataclasses import dataclass
from urllib.parse import urlsplit
from typing import Literal

Verdict = Literal[
    "SUPPORTED",
    "CONTRADICTED",
    "PARTLY_TRUE",
    "INSUFFICIENT_EVIDENCE",
    "NOT_VERIFIABLE",
]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]
Stance = Literal["SUPPORTS", "CONTRADICTS", "CONTEXT", "UNRELATED"]
SourceTier = Literal[
    "PRIMARY",
    "AUTHORITATIVE_REFERENCE",
    "REPUTABLE_REPORTING",
    "SECONDARY_AGGREGATOR",
    "UNVERIFIED_SOCIAL",
]


@dataclass(frozen=True)
class EvidenceSignal:
    evidence_id: str
    stance: Stance
    source_tier: SourceTier
    independence_group_id: str
    retrieved: bool = True


@dataclass(frozen=True)
class VerdictAssessment:
    verdict: Verdict
    confidence: Confidence
    confidence_reason: str
    rationale: str


def assess_verdict(
    claim_type: str,
    proposed_verdict: str,
    evidence: list[EvidenceSignal],
) -> VerdictAssessment:
    """Apply minimum evidence-count and independence requirements to a model proposal."""
    eligible = [
        item for item in evidence
        if item.retrieved
        and item.source_tier != "UNVERIFIED_SOCIAL"
        and item.stance in {"SUPPORTS", "CONTRADICTS"}
        and item.independence_group_id
    ]
    supporting = [item for item in eligible if item.stance == "SUPPORTS"]
    contradicting = [item for item in eligible if item.stance == "CONTRADICTS"]
    support_groups = {item.independence_group_id for item in supporting}
    contradiction_groups = {item.independence_group_id for item in contradicting}
    settled_authority = claim_type == "SETTLED_FACT" and any(
        item.source_tier in {"PRIMARY", "AUTHORITATIVE_REFERENCE"}
        for item in supporting + contradicting
    )

    if claim_type == "OPINION_OR_PREDICTION":
        verdict: Verdict = "NOT_VERIFIABLE"
        rationale = "This is an opinion or prediction and cannot be checked as a factual claim."
    elif support_groups and contradiction_groups:
        verdict = "PARTLY_TRUE"
        rationale = "Retrieved evidence supports different parts or interpretations of the claim."
    elif proposed_verdict == "PARTLY_TRUE":
        verdict = "INSUFFICIENT_EVIDENCE"
        rationale = "The retrieved evidence does not establish both sides needed for a mixed assessment."
    elif proposed_verdict == "SUPPORTED":
        if len(support_groups) >= 2 or (support_groups and settled_authority):
            verdict = "SUPPORTED"
            rationale = "Eligible retrieved evidence meets the support and independence requirement."
        else:
            verdict = "INSUFFICIENT_EVIDENCE"
            rationale = "The retrieved evidence does not meet the independent-source requirement for support."
    elif proposed_verdict == "CONTRADICTED":
        if len(contradiction_groups) >= 2 or (contradiction_groups and settled_authority):
            verdict = "CONTRADICTED"
            rationale = "Eligible retrieved evidence meets the contradiction and independence requirement."
        else:
            verdict = "INSUFFICIENT_EVIDENCE"
            rationale = "The retrieved evidence does not meet the independent-source requirement for contradiction."
    elif proposed_verdict == "NOT_VERIFIABLE":
        verdict = "NOT_VERIFIABLE"
        rationale = "The claim cannot be checked as framed."
    else:
        verdict = "INSUFFICIENT_EVIDENCE"
        rationale = "The retrieved evidence does not meet the minimum sufficiency requirement."

    relevant_groups = support_groups | contradiction_groups
    authoritative_groups = {
        item.independence_group_id
        for item in eligible
        if item.source_tier in {"PRIMARY", "AUTHORITATIVE_REFERENCE"}
    }
    if verdict == "NOT_VERIFIABLE" or not relevant_groups:
        confidence: Confidence = "LOW"
        confidence_reason = "No eligible retrieved source evidence can establish this claim."
    elif len(relevant_groups) >= 2 and len(authoritative_groups) >= 2:
        confidence = "HIGH"
        confidence_reason = "Multiple independent authoritative source groups provide relevant retrieved evidence."
    elif len(relevant_groups) >= 2:
        confidence = "MEDIUM"
        confidence_reason = "Two or more independent source groups provide relevant retrieved evidence."
    else:
        confidence = "LOW"
        confidence_reason = "Only one independent source group provides relevant retrieved evidence."

    return VerdictAssessment(verdict, confidence, confidence_reason, rationale)


def build_independence_groups(
    source_domains: dict[str, str | None],
    relationships: list[tuple[str, str, str]],
) -> dict[str, str]:
    """Collapse same-publisher domains and known citation/copy chains conservatively."""
    parent = {source_id: source_id for source_id in source_domains}

    def root(source_id: str) -> str:
        while parent[source_id] != source_id:
            parent[source_id] = parent[parent[source_id]]
            source_id = parent[source_id]
        return source_id

    def union(first: str, second: str) -> None:
        if first not in parent or second not in parent:
            return
        a, b = root(first), root(second)
        if a != b:
            parent[max(a, b)] = min(a, b)

    owners_by_domain: dict[str, str] = {}
    for source_id, value in source_domains.items():
        host = urlsplit(value or "").hostname or (value or "")
        host = host.casefold().removeprefix("www.")
        labels = host.split(".")
        # Preserve common second-level country domains (for example, co.ke).
        registrable = ".".join(labels[-3:]) if len(labels) >= 3 and labels[-2] in {"co", "go", "ac", "or", "gov"} else ".".join(labels[-2:])
        if registrable:
            previous = owners_by_domain.setdefault(registrable, source_id)
            union(previous, source_id)

    for source_id, related_id, relation in relationships:
        if relation in {"CITES", "DUPLICATES"}:
            union(source_id, related_id)

    return {source_id: root(source_id) for source_id in source_domains}
