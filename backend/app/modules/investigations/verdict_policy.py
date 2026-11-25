"""Deterministic verdict sufficiency rules; model proposals are advisory only."""

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.modules.investigations.evidence_ledger import owner_key

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
    "UNKNOWN",
    "PRIMARY",
    "AUTHORITATIVE_REFERENCE",
    "REPUTABLE_REPORTING",
    "FACT_CHECK",
    "SECONDARY_AGGREGATOR",
    "UNVERIFIED_SOCIAL",
]

# Tiers that can never establish a verdict. Fact-checks are leads that must be followed
# to the records they cite; social and unknown sources are context only.
CONTEXT_ONLY_TIERS = frozenset({"UNVERIFIED_SOCIAL", "FACT_CHECK"})
# Unregistered sites can corroborate, but only alongside a recognised source on the same
# side: two unknown sites agreeing is never enough on its own.
ANCHOR_REQUIRED_TIERS = frozenset({"UNKNOWN"})
_FUTURE_WORDS = re.compile(r"\b(will|plans?|planned|to be|upcoming|next|tomorrow|soon)\b", re.I)
_YEAR = re.compile(r"\b(1[6-9][0-9]{2}|20[0-9]{2})\b")


def is_historical_event(claim_text: str, *, today: date | None = None) -> bool:
    """A claim about something that happened in a past year (two or more years ago)."""
    years = [int(year) for year in _YEAR.findall(claim_text or "")]
    current = (today or date.today()).year
    return bool(years) and max(years) <= current - 2 and not _FUTURE_WORDS.search(claim_text)


# Claim types where one directly relevant official source may settle the question.
ONE_SOURCE_CLAIM_TYPES = frozenset({"SETTLED_FACT", "STATISTICAL"})


@dataclass(frozen=True)
class EvidenceSignal:
    evidence_id: str
    stance: Stance
    source_tier: SourceTier
    independence_group_id: str
    retrieved: bool = True
    authority_fits_claim: bool = False
    # True when a statistic is older than the freshness window for its claim type.
    is_stale: bool | None = None


@dataclass(frozen=True)
class VerdictAssessment:
    verdict: Verdict
    confidence: Confidence
    confidence_reason: str
    rationale: str


def _is_authoritative(item: EvidenceSignal, claim_type: str) -> bool:
    """A source that can settle the claim on its own.

    A topic-fit official record, or, for settled facts (definitions, common knowledge,
    stable history), an established reference work such as an encyclopedia. Stale
    statistics cannot settle a current number.
    """
    if claim_type == "SETTLED_FACT" and item.source_tier == "AUTHORITATIVE_REFERENCE":
        return True
    if item.source_tier != "PRIMARY" or not item.authority_fits_claim:
        return False
    return not (claim_type == "STATISTICAL" and item.is_stale is True)


def _counted_groups(items: list[EvidenceSignal]) -> set[str]:
    """Independent groups that count toward a threshold on one side."""
    anchored = {
        i.independence_group_id for i in items if i.source_tier not in ANCHOR_REQUIRED_TIERS
    }
    if not anchored:
        return set()
    return anchored | {
        i.independence_group_id for i in items if i.source_tier in ANCHOR_REQUIRED_TIERS
    }


def assess_verdict(
    claim_type: str,
    proposed_verdict: str,
    evidence: list[EvidenceSignal],
    *,
    claim_text: str = "",
) -> VerdictAssessment:
    """Apply evidence-count, independence and authority rules to a model proposal.

    The model can only propose. The final verdict is never stronger than the proposal and
    never stronger than the evidence allows.
    """
    eligible = [
        item
        for item in evidence
        if item.retrieved
        and item.source_tier not in CONTEXT_ONLY_TIERS
        and item.stance in {"SUPPORTS", "CONTRADICTS"}
        and item.independence_group_id
        and item.independence_group_id != "unknown"
    ]
    supporting = [item for item in eligible if item.stance == "SUPPORTS"]
    contradicting = [item for item in eligible if item.stance == "CONTRADICTS"]
    support_groups = _counted_groups(supporting)
    contradiction_groups = _counted_groups(contradicting)
    uses_unregistered = any(
        item.source_tier in ANCHOR_REQUIRED_TIERS
        and item.independence_group_id in (support_groups | contradiction_groups)
        for item in eligible
    )
    support_authority = {
        item.independence_group_id for item in supporting if _is_authoritative(item, claim_type)
    }
    contradiction_authority = {
        item.independence_group_id for item in contradicting if _is_authoritative(item, claim_type)
    }
    one_source_allowed = claim_type in ONE_SOURCE_CLAIM_TYPES or (
        claim_type == "CHECKABLE_EVENT" and is_historical_event(claim_text)
    )

    def meets_threshold(groups: set[str], authority: set[str]) -> bool:
        return len(groups) >= 2 or (bool(authority) and one_source_allowed)

    single_authority_used = False
    if claim_type == "OPINION_OR_PREDICTION":
        verdict: Verdict = "NOT_VERIFIABLE"
        rationale = "This is an opinion or prediction and cannot be checked as a factual claim."
    elif support_groups and contradiction_groups:
        if support_groups.isdisjoint(contradiction_groups) and proposed_verdict == "PARTLY_TRUE":
            verdict = "PARTLY_TRUE"
            rationale = (
                "Independent retrieved sources support materially different parts or "
                "interpretations; review the cited passages."
            )
        elif (
            support_authority
            and not contradiction_authority
            and meets_threshold(support_groups, support_authority)
            and proposed_verdict == "SUPPORTED"
        ):
            verdict = "SUPPORTED"
            single_authority_used = len(support_groups) < 2
            rationale = (
                "A directly relevant official record supports the claim and the conflicting "
                "sources are not official records on this topic."
            )
        elif (
            contradiction_authority
            and not support_authority
            and meets_threshold(contradiction_groups, contradiction_authority)
            and proposed_verdict == "CONTRADICTED"
        ):
            verdict = "CONTRADICTED"
            single_authority_used = len(contradiction_groups) < 2
            rationale = (
                "A directly relevant official record contradicts the claim and the conflicting "
                "sources are not official records on this topic."
            )
        else:
            verdict = "INSUFFICIENT_EVIDENCE"
            rationale = (
                "Retrieved sources conflict or do not establish distinct parts of the claim; "
                "the assessment remains unresolved."
            )
    elif proposed_verdict == "PARTLY_TRUE":
        verdict = "INSUFFICIENT_EVIDENCE"
        rationale = (
            "The retrieved evidence does not establish both sides needed for a mixed assessment."
        )
    elif proposed_verdict == "SUPPORTED":
        if meets_threshold(support_groups, support_authority):
            verdict = "SUPPORTED"
            single_authority_used = len(support_groups) < 2
            rationale = (
                "Eligible retrieved evidence meets the support and independence requirement."
            )
        else:
            verdict = "INSUFFICIENT_EVIDENCE"
            rationale = (
                "The retrieved evidence does not meet the independent-source requirement for "
                "support."
            )
    elif proposed_verdict == "CONTRADICTED":
        if meets_threshold(contradiction_groups, contradiction_authority):
            verdict = "CONTRADICTED"
            single_authority_used = len(contradiction_groups) < 2
            rationale = (
                "Eligible retrieved evidence meets the contradiction and independence requirement."
            )
        else:
            verdict = "INSUFFICIENT_EVIDENCE"
            rationale = (
                "The retrieved evidence does not meet the independent-source requirement for "
                "contradiction."
            )
    elif proposed_verdict == "NOT_VERIFIABLE":
        verdict = "NOT_VERIFIABLE"
        rationale = "The claim cannot be checked as framed."
    else:
        verdict = "INSUFFICIENT_EVIDENCE"
        rationale = "The retrieved evidence does not meet the minimum sufficiency requirement."

    relevant_groups = support_groups | contradiction_groups
    authoritative_groups = support_authority | contradiction_authority
    decided = verdict in {"SUPPORTED", "CONTRADICTED"}
    opposed = bool(contradiction_groups if verdict == "SUPPORTED" else support_groups) and decided

    if verdict == "NOT_VERIFIABLE" or not relevant_groups:
        confidence: Confidence = "LOW"
        confidence_reason = "No eligible retrieved source evidence can establish this claim."
    elif decided and len(authoritative_groups) >= 2 and not opposed and not uses_unregistered:
        confidence = "HIGH"
        confidence_reason = (
            "Multiple independent official source groups provide relevant retrieved evidence."
        )
    elif decided and single_authority_used and not opposed:
        confidence = "MEDIUM"
        confidence_reason = (
            "One official source that matches the topic directly addresses the claim; "
            "no independent confirmation was found."
        )
    elif len(relevant_groups) >= 2:
        confidence = "MEDIUM"
        confidence_reason = (
            "Two or more independent source groups provide relevant retrieved evidence, but "
            "some conflict or authority gaps remain."
            if (opposed or not decided)
            else "Two or more independent source groups provide relevant retrieved evidence."
        )
    else:
        confidence = "LOW"
        confidence_reason = (
            "Only one independent source group provides relevant retrieved evidence."
        )

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
        registrable = owner_key(value)
        if registrable:
            previous = owners_by_domain.setdefault(registrable, source_id)
            union(previous, source_id)

    for source_id, related_id, relation in relationships:
        if relation in {"CITES", "DUPLICATES"}:
            union(source_id, related_id)

    return {source_id: root(source_id) for source_id in source_domains}
