"""Small, explainable source ordering for bounded retrieval.

The internal score only chooses which candidates to retrieve first. It is not a
credibility score and must never be used to infer a finding or evidence polarity.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.modules.sources.evidence_extraction import extract_claim_anchors
from app.modules.sources.registry import lookup_source
from app.modules.sources.urls import normalize_source_url

ROLE_PRIORITY = {
    "ORIGINAL_SOURCE": 8,
    "PRIMARY_AUTHORITY": 7,
    "PUBLIC_RECORD": 5,
    "FACT_CHECK": 4,
    "INDEPENDENT_CORROBORATION": 3,
    "CONTEXT": 1,
    "SUBMITTED": 0,
    "DERIVATIVE": -100,
    "UNKNOWN": 0,
}
TYPE_PRIORITY = {
    "OFFICIAL": 2,
    "PUBLIC_RECORD": 3,
    "FACT_CHECK": 3,
    "ACADEMIC": 2,
    "NEWS": 1,
    "SOCIAL": -2,
    "AGGREGATOR": -2,
    "BLOG": 0,
    "UNKNOWN": 0,
}
MONTH_NAMES = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
MONTH_PATTERN = re.compile(
    r"\b(" + "|".join(sorted(MONTH_NAMES, key=len, reverse=True)) + r")\b", re.I
)


def _words(value: str) -> set[str]:
    words = set(re.findall(r"[\w]+", value.casefold()))
    return {word[:-1] if len(word) > 4 and word.endswith("s") else word for word in words}


def _normalized_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return normalize_source_url(value)
    except ValueError:
        return None


def _periods(value: str) -> set[tuple[int, int]]:
    years = [int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", value)]
    months = [MONTH_NAMES[match.group(1).casefold()] for match in MONTH_PATTERN.finditer(value)]
    periods = {(year, month) for year in years for month in months}
    fy = re.search(r"\bFY\s*(20\d{2})\s*[/\-]\s*(\d{2}|20\d{2})", value, re.I)
    quarter = re.search(r"\bQ([1-4])\b", value, re.I)
    if fy and quarter:
        first = int(fy.group(1))
        last_text = fy.group(2)
        last = int(last_text) if len(last_text) == 4 else (first // 100) * 100 + int(last_text)
        q = int(quarter.group(1))
        quarter_months = {
            1: [(first, 7), (first, 8), (first, 9)],
            2: [(first, 10), (first, 11), (first, 12)],
            3: [(last, 1), (last, 2), (last, 3)],
            4: [(last, 4), (last, 5), (last, 6)],
        }
        periods.update(quarter_months[q])
    return periods


def _claim_text_score(claim: str, source_text: str) -> int:
    anchors = extract_claim_anchors(claim)
    source_words = _words(source_text)
    score = 2 * len({_singular(term) for term in anchors.terms} & source_words)
    source_numbers = {
        re.sub(r",", "", number)
        for number in re.findall(r"(?<!\w)\d+(?:,\d{3})*(?:\.\d+)?(?!\w)", source_text)
    }
    score += 5 * len(set(anchors.numbers) & source_numbers)
    if anchors.months and anchors.years:
        claim_periods = _periods(claim)
        matching_period = bool(claim_periods & _periods(source_text))
        if matching_period:
            score += 7
        elif set(anchors.years) & set(re.findall(r"\b(?:19|20)\d{2}\b", source_text)):
            score += 2
    else:
        score += 2 * len(_periods(claim) & _periods(source_text))
    return score


def _singular(term: str) -> str:
    return term[:-1] if len(term) > 4 and term.endswith("s") else term


def retrieval_priority(
    source: Any,
    claims: Sequence[str],
    search_context: str = "",
) -> int:
    """Return an internal ordering score based on role and claim relevance."""
    role = str(getattr(source, "source_role", "UNKNOWN") or "UNKNOWN").upper()
    source_type = str(getattr(source, "source_type", "UNKNOWN") or "UNKNOWN").upper()
    score = ROLE_PRIORITY.get(role, 0) + TYPE_PRIORITY.get(source_type, 0)
    source_text = " ".join(
        str(value or "")
        for value in (
            getattr(source, "title", None),
            getattr(source, "publisher", None),
            search_context,
        )
    )
    domain = str(getattr(source, "domain", None) or "")
    registry = lookup_source(domain)
    for claim in claims:
        claim_words = _words(claim)
        score = max(score, ROLE_PRIORITY.get(role, 0) + TYPE_PRIORITY.get(source_type, 0))
        if registry:
            topic_match = any(_words(topic) & claim_words for topic in registry.topics)
            if registry.authoritative_for and topic_match:
                score += 8
        score += _claim_text_score(claim, source_text)
    if role == "DERIVATIVE":
        return -100
    return score


def prioritize_sources(
    sources: Sequence[Any],
    claims: Sequence[str],
    *,
    context_by_source: Mapping[object, str] | None = None,
) -> list[Any]:
    """Sort candidates by retrieval relevance and collapse known effective URLs."""
    context = context_by_source or {}
    best_by_url: dict[str, tuple[int, int, Any]] = {}
    seen_ids: set[object] = set()
    for index, source in enumerate(sources):
        source_id = getattr(source, "id", None)
        if source_id is not None and source_id in seen_ids:
            continue
        if source_id is not None:
            seen_ids.add(source_id)
        if str(getattr(source, "source_role", "")).upper() == "DERIVATIVE":
            continue
        source_context = context.get(source_id, "")
        priority = retrieval_priority(source, claims, source_context)
        if str(getattr(source, "retrieval_status", "")).upper() == "RETRIEVED":
            priority += 10_000
        url = _normalized_url(getattr(source, "canonical_url", None)) or _normalized_url(
            getattr(source, "url", None)
        )
        key = url or f"source:{source_id or index}"
        current = best_by_url.get(key)
        if current is None or priority > current[0]:
            best_by_url[key] = (priority, index, source)
    return [item[2] for item in sorted(best_by_url.values(), key=lambda item: (-item[0], item[1]))]
