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
        for status in ("SUPPORTED", "CONTRADICTED", "UNVERIFIED", "INCONCLUSIVE")
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
    elif present == {"INCONCLUSIVE"}:
        review_count = counts["INCONCLUSIVE"]
        review_text = (
            "One finding needs human review."
            if review_count == 1
            else f"{review_count} findings need human review."
        )
        summary = "\n\n".join(
            (
                "Assessment: Inconclusive.",
                "The evidence reviewed so far does not confirm or refute the claim. "
                + review_text,
                "Before publication, verify the claim with an independent, authoritative source.",
            )
        )
    elif present == {"UNVERIFIED"}:
        count = counts["UNVERIFIED"]
        finding_text = (
            "One finding remains unverified."
            if count == 1
            else f"{count} findings remain unverified."
        )
        summary = "\n\n".join(
            (
                "Assessment: Not verified.",
                "The evidence reviewed so far does not establish whether the claim is accurate. "
                + finding_text,
                "Before publication, seek confirmation from an independent, authoritative source.",
            )
        )
    elif present == {"SUPPORTED"}:
        count = counts["SUPPORTED"]
        summary = (
            "Assessment: Evidence supports the claim.\n\n"
            f"Review the {count} supporting finding{'s' if count != 1 else ''} and cited source "
            "context before publication."
        )
    elif present == {"CONTRADICTED"}:
        count = counts["CONTRADICTED"]
        summary = (
            "Assessment: Evidence challenges the claim.\n\n"
            f"Review the {count} contradicting finding{'s' if count != 1 else ''} and cited "
            "source context before publication."
        )
    else:
        count_phrases = {
            "SUPPORTED": ("supports the claim", "support the claim"),
            "CONTRADICTED": ("challenges the claim", "challenge the claim"),
            "UNVERIFIED": ("is unverified", "are unverified"),
            "INCONCLUSIVE": ("is inconclusive", "are inconclusive"),
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
                "Assessment: Mixed evidence.",
                "Findings: " + "; ".join(findings) + ".",
                "Review each finding and its cited sources before publication; the evidence does "
                "not support a single conclusion.",
            )
        )

    media = list(media_reviews)
    if media:
        summary += "\n\nMedia reviewed: " + ", ".join(media) + "."
    return summary
