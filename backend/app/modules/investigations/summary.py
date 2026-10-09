"""Plain-language summaries for journalist-facing investigation results."""

from collections.abc import Iterable

from app.modules.investigations.models import Finding


def finding_result_summary(findings: Iterable[Finding], *, max_chars: int = 3000) -> str:
    items = list(findings)
    sections = [journalist_assessment_summary(item.status for item in items)]
    answer_limit = 100 if len(items) > 1 else 700
    rationale_limit = 40 if len(items) > 1 else 300
    for item in items:
        if item.evidence_confidence == "UNASSESSED":
            confidence = "Evidence confidence was not assessed for this earlier result."
        else:
            confidence = (
                "Evidence confidence (qualitative, not a probability): "
                f"{item.evidence_confidence.title()}. "
                f"{item.confidence_rationale[:rationale_limit]}"
            )
        sections.append(f"{item.statement[:answer_limit]}\n{confidence}")
    return "\n\n".join(sections)[:max_chars]


def journalist_assessment_summary(
    statuses: Iterable[str], *, media_reviews: Iterable[str] = ()
) -> str:
    counts = {
        status: 0
        for status in (
            "SUPPORTED",
            "CONTRADICTED",
            "PARTLY_TRUE",
            "INSUFFICIENT_EVIDENCE",
            "NOT_VERIFIABLE",
        )
    }
    for status in statuses:
        if status in counts:
            counts[status] += 1

    present = {status for status, count in counts.items() if count}
    if not present:
        summary = (
            "No assessment is available. The review did not produce a claim-level finding. "
            "Please review the cited sources directly; no conclusion has been reached."
        )
    elif present == {"PARTLY_TRUE"}:
        summary = (
            "Assessment: Partly true. The evidence supports some parts or interpretations and challenges others."
        )
    elif present == {"INSUFFICIENT_EVIDENCE"}:
        summary = (
            "Assessment: Not enough evidence yet. The retrieved sources do not establish whether the claim is accurate."
        )
    elif present == {"NOT_VERIFIABLE"}:
        summary = "Assessment: Not verifiable. The request is an opinion or prediction, not a checkable factual claim."
    elif present == {"SUPPORTED"}:
        summary = (
            "Assessment: The evidence supports the claim. Review the linked sources and context "
            "before publication."
        )
    elif present == {"CONTRADICTED"}:
        summary = (
            "Assessment: The evidence challenges the claim. Review the linked sources and context "
            "before publication."
        )
    else:
        count_phrases = {
            "SUPPORTED": ("supports the claim", "support the claim"),
            "CONTRADICTED": ("challenges the claim", "challenge the claim"),
            "PARTLY_TRUE": ("is partly true", "are partly true"),
            "INSUFFICIENT_EVIDENCE": ("needs more evidence", "need more evidence"),
            "NOT_VERIFIABLE": ("is not verifiable", "are not verifiable"),
        }
        findings = []
        for status, (singular, plural) in count_phrases.items():
            count = counts[status]
            if count:
                noun = "finding" if count == 1 else "findings"
                phrase = singular if count == 1 else plural
                findings.append(f"{count} {noun} {phrase}")
        summary = "\n\n".join(
            (
                "Assessment: Mixed findings.",
                "Findings: " + "; ".join(findings) + ".",
                "Review each finding and its cited sources before publication; the evidence does "
                "not support a single conclusion.",
            )
        )

    media = list(media_reviews)
    if media:
        summary += "\n\nMedia reviewed: " + ", ".join(media) + "."
    return summary
