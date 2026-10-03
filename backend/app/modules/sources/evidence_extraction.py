import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

STOP_WORDS = {
    "about",
    "after",
    "again",
    "against",
    "among",
    "because",
    "before",
    "being",
    "between",
    "could",
    "from",
    "have",
    "into",
    "more",
    "most",
    "other",
    "over",
    "same",
    "should",
    "some",
    "such",
    "than",
    "that",
    "their",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "under",
    "very",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
    "will",
    "were",
    "them",
    "then",
    "also",
    "according",
    "authority",
    "based",
    "reported",
    "reports",
    "report",
    "said",
    "stated",
    "shows",
    "showed",
    "result",
    "results",
    "data",
    "information",
    "connected",
    "connection",
    "connections",
    "reached",
    "reaches",
    "million",
    "billion",
    "thousand",
    "percent",
    "percentage",
    "quarter",
    "year",
}

MONTHS = {
    "january": "jan",
    "february": "feb",
    "march": "mar",
    "april": "apr",
    "may": "may",
    "june": "jun",
    "july": "jul",
    "august": "aug",
    "september": "sep",
    "october": "oct",
    "november": "nov",
    "december": "dec",
    "jan": "jan",
    "feb": "feb",
    "mar": "mar",
    "apr": "apr",
    "jun": "jun",
    "jul": "jul",
    "aug": "aug",
    "sep": "sep",
    "sept": "sep",
    "oct": "oct",
    "nov": "nov",
    "dec": "dec",
}
MONTH_NUMBER = {
    name: index
    for index, name in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
        start=1,
    )
}
MONTH_PATTERN = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b", re.I)
NUMBER_PATTERN = re.compile(r"(?<![\w])\d+(?:,\d{3})*(?:\.\d+)?(?![\w])")
UNIT_PATTERN = re.compile(
    r"\s*(million|billion|thousand|m|bn|b|k|%|percent|gigabytes?|gb|terabytes?|tb)(?![a-z])",
    re.I,
)
BOILERPLATE_PATTERNS = (
    re.compile(r"\btable\s+of\s+contents\b|\bcontents\s*$", re.I),
    re.compile(r"\b(disclaimer|copyright|all rights reserved|terms of use)\b", re.I),
    re.compile(r"\b(contact|telephone|tel\.?|email|e-mail|address)\s*[:|]", re.I),
    re.compile(r"\b(cookie|privacy policy|subscribe|navigation|menu)\b", re.I),
)


@dataclass(frozen=True)
class EvidenceCandidate:
    claim_id: str
    excerpt: str


@dataclass(frozen=True)
class EvidenceRegion:
    """A bounded raw-document region selected before fine passage localization."""

    claim_id: str
    text: str
    start: int
    end: int
    page_number: int | None = None


@dataclass(frozen=True)
class ClaimAnchors:
    terms: frozenset[str]
    numbers: tuple[str, ...]
    months: frozenset[str]
    years: frozenset[str]
    entity_phrases: tuple[str, ...]


@dataclass(frozen=True)
class _Passage:
    text: str
    excerpt: str
    heading: str = ""
    heading_context: str = ""
    is_table: bool = False
    is_contents: bool = False


def _terms(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\w'-]+", value.casefold())
        if len(token) >= 3 and token not in STOP_WORDS
    }


def extract_claim_anchors(value: str) -> ClaimAnchors:
    """Return bounded deterministic anchors; this does not assess claim truth."""
    terms = _terms(value)
    numbers = tuple(
        dict.fromkeys(
            _canonical_number(match.group(0))
            for match in NUMBER_PATTERN.finditer(value)
            if not _is_year(match.group(0))
        )
    )
    months = frozenset(MONTHS[match.group(1).casefold()] for match in MONTH_PATTERN.finditer(value))
    years = frozenset(re.findall(r"\b(?:19|20)\d{2}\b", value))
    entity_phrases = tuple(
        dict.fromkeys(
            " ".join(match.group(0).casefold().split())
            for match in re.finditer(
                r"\b(?:[A-Z][\w&'-]+)(?:\s+(?:of|the|and|[A-Z][\w&'-]+)){1,5}",
                value,
            )
            if len(_terms(match.group(0)) & terms) >= 2
        )
    )
    return ClaimAnchors(terms, numbers, months, years, entity_phrases)


def _canonical_number(value: str) -> str:
    try:
        return format(Decimal(value.replace(",", "")).normalize(), "f")
    except InvalidOperation:
        return value.casefold()


def _is_year(value: str) -> bool:
    digits = value.replace(",", "").split(".", maxsplit=1)[0]
    return len(digits) == 4 and digits[:2] in {"19", "20"}


def _number_variants(number: str, claim_text: str) -> set[str]:
    variants = {number, number.replace(".", ",") if "." not in number else number}
    tail = claim_text.casefold()
    unit = ""
    for match in NUMBER_PATTERN.finditer(claim_text):
        if _canonical_number(match.group(0)) != number:
            continue
        following = tail[match.end() :]
        unit_match = UNIT_PATTERN.match(following)
        if unit_match:
            unit = unit_match.group(1).casefold()
            compact_unit = {
                "million": "m",
                "billion": "b",
                "thousand": "k",
                "gigabytes": "gb",
                "gigabyte": "gb",
                "terabytes": "tb",
                "terabyte": "tb",
            }.get(unit, unit)
            variants.add(f"{number}{compact_unit}")
        break
    multiplier = {
        "million": 1_000_000,
        "m": 1_000_000,
        "billion": 1_000_000_000,
        "bn": 1_000_000_000,
        "b": 1_000_000_000,
        "thousand": 1_000,
        "k": 1_000,
    }
    if unit in multiplier:
        try:
            expanded = Decimal(number) * multiplier[unit]
            if expanded == expanded.to_integral_value():
                variants.add(format(expanded.quantize(Decimal("1")), ","))
                variants.add(format(expanded.quantize(Decimal("1")), "f"))
        except InvalidOperation:
            pass
    return variants


def _numeric_matches(claim_text: str, passage: str) -> tuple[int, bool]:
    passage_numbers = {
        _canonical_number(match.group(0)): match.group(0)
        for match in NUMBER_PATTERN.finditer(passage)
        if not _is_year(match.group(0))
    }
    matches = 0
    for number in extract_claim_anchors(claim_text).numbers:
        if number in passage_numbers:
            matches += 1
            continue
        variants = _number_variants(number, claim_text)
        if any(
            re.search(rf"(?<![\w]){re.escape(variant)}(?![\w])", passage, re.I)
            for variant in variants
        ):
            matches += 1
    return matches, bool(passage_numbers)


def _temporal_match(claim_text: str, passage: str) -> int:
    claim_years = set(re.findall(r"\b(?:19|20)\d{2}\b", claim_text))
    passage_years = set(re.findall(r"\b(?:19|20)\d{2}\b", passage))
    claim_months = {MONTHS[m.group(1).casefold()] for m in MONTH_PATTERN.finditer(claim_text)}
    passage_months = {MONTHS[m.group(1).casefold()] for m in MONTH_PATTERN.finditer(passage)}
    score = 0
    if claim_years & passage_years:
        score += 3
    if claim_months & passage_months:
        score += 3
    if claim_months and claim_years:
        quarter = re.search(r"\bQ([1-4])\s+FY\s*(20\d{2})\s*[/\-]\s*(\d{2}|20\d{2})", passage, re.I)
        if quarter:
            q = int(quarter.group(1))
            first = int(quarter.group(2))
            last_text = quarter.group(3)
            last = int(last_text) if len(last_text) == 4 else (first // 100) * 100 + int(last_text)
            expected_months = {
                1: {"jul", "aug", "sep"},
                2: {"oct", "nov", "dec"},
                3: {"jan", "feb", "mar"},
                4: {"apr", "may", "jun"},
            }[q]
            expected_year = first if q <= 2 else last
            if claim_months & expected_months and str(expected_year) in claim_years:
                score += 6
    return score


def _segments(page_text: str) -> list[_Passage]:
    lines = page_text.splitlines()
    passages: list[_Passage] = []
    document_heading = ""
    report_heading = ""
    section_heading = ""
    section_heading_raw = ""
    contents_section = False
    paragraph: list[str] = []

    def emit(lines_to_emit: list[str], *, table: bool = False) -> None:
        body = "\n".join(line.strip() for line in lines_to_emit if line.strip())
        if not body:
            return
        normalized_body = " ".join(body.split())
        heading = " ".join(
            dict.fromkeys(
                part for part in (document_heading, report_heading, section_heading) if part
            )
        )
        if len(normalized_body) < 24:
            return
        passages.append(
            _Passage(
                text=f"{heading}\n{normalized_body}" if heading else normalized_body,
                excerpt=normalized_body,
                heading=heading,
                heading_context=section_heading_raw,
                is_table=table,
                is_contents=contents_section,
            )
        )

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            body = " ".join(line.strip() for line in paragraph if line.strip())
            # Keep sentence-sized windows while retaining table and paragraph context.
            sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9|])", body)
            for sentence in sentences:
                emit([sentence])
            paragraph = []

    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if line.startswith("#"):
            flush_paragraph()
            heading = re.sub(r"^#{1,6}\s*", "", line).strip()
            contents_section = bool(re.search(r"table of contents|^contents$", heading, re.I))
            if not contents_section:
                if not document_heading:
                    document_heading = heading
                if re.search(
                    r"\b(report|statistics|quarterly|annual|FY\s*20\d{2})\b", heading, re.I
                ):
                    report_heading = heading
                section_heading = heading
                section_heading_raw = line
            index += 1
            continue
        if line.startswith("|"):
            flush_paragraph()
            table_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            emit(table_lines, table=True)
            continue
        if not line:
            flush_paragraph()
        else:
            paragraph.append(line)
        index += 1
    flush_paragraph()
    return passages


def _passage_score(claim_text: str, passage: _Passage) -> int | None:
    anchors = extract_claim_anchors(claim_text)
    passage_terms = _terms(passage.text)
    matching_terms = anchors.terms & passage_terms
    number_hits, passage_has_numbers = _numeric_matches(claim_text, passage.text)
    temporal = _temporal_match(claim_text, passage.text)
    entity_hits = sum(1 for phrase in anchors.entity_phrases if phrase in passage.text.casefold())
    unit_terms = {"million", "billion", "thousand", "percent", "gigabyte", "gigabytes", "gb", "tb"}
    unit_hits = len((anchors.terms & unit_terms) & passage_terms)

    if anchors.numbers:
        if number_hits and not (matching_terms or temporal or unit_hits):
            return None
        contextual_terms = matching_terms - anchors.months - anchors.years
        if not number_hits and (len(contextual_terms) < 1 or (temporal == 0 and entity_hits == 0)):
            return None
    elif len(matching_terms) < 2 and entity_hits == 0:
        return None

    score = len(matching_terms) * 2 + number_hits * 10 + temporal + entity_hits * 4 + unit_hits * 2
    if passage.is_table and (number_hits or unit_hits):
        score += 3
    if passage.heading and len(anchors.terms & _terms(passage.heading)):
        score += 2
    if passage.is_contents:
        score -= 14
    if any(pattern.search(passage.text) for pattern in BOILERPLATE_PATTERNS):
        score -= 12
    if passage_has_numbers and anchors.numbers and not number_hits:
        score -= 8
    return score


_PAGE_MARKER = re.compile(
    r"(?:<!--\s*page(?:_number)?\s*[:=]\s*(\d+)\s*-->|\[\s*page\s+(\d+)\s*\])",
    re.I,
)


def select_claim_relevant_regions(
    *,
    claim_id: str,
    claim_text: str,
    document_text: str,
    max_regions: int = 4,
    region_chars: int = 6_000,
) -> list[EvidenceRegion]:
    """Coarsely scan a bounded full document, then return only its best local regions.

    This stage only chooses document locations. `extract_candidate_excerpts` remains
    responsible for fine passage ranking, and neither stage assigns evidential polarity.
    """
    if max_regions <= 0 or region_chars < 100 or not document_text:
        return []
    step = max(1, region_chars - min(500, region_chars // 4))
    ranked: list[tuple[int, int, int, int | None, str]] = []
    for start in range(0, len(document_text), step):
        end = min(len(document_text), start + region_chars)
        if end - start < 24:
            continue
        region = document_text[start:end]
        # Align the outer edges to complete lines and retain nearby page/section labels.
        if start:
            newline = region.find("\n")
            if newline >= 0:
                start += newline + 1
                region = document_text[start:end]
        if end < len(document_text):
            newline = region.rfind("\n")
            if newline >= 0:
                end = start + newline
                region = document_text[start:end]
        prior_heading = re.search(
            r"(?m)^#{1,6}[^\n]*\n?", document_text[max(0, start - 300) : start]
        )
        prefix = document_text[max(0, start - 300) : start]
        page_match = list(_PAGE_MARKER.finditer(prefix + region))
        page_number = None
        if page_match:
            page_number = int(page_match[-1].group(1) or page_match[-1].group(2))
        context = ""
        if prior_heading:
            context = prior_heading.group(0).strip()
        elif page_number is not None:
            context = f"[Page {page_number}]"
        score = _passage_score(
            claim_text,
            _Passage(
                text=f"{context}\n{region}" if context else region,
                excerpt=region,
                heading=context,
                is_contents=bool(
                    re.search(r"table\s+of\s+contents|^contents\s*$", region, re.I | re.M)
                ),
            ),
        )
        if score is not None:
            ranked.append((score, start, end, page_number, region))

    selected: list[EvidenceRegion] = []
    occupied: list[tuple[int, int]] = []
    for _score, start, end, page_number, region in sorted(
        ranked, key=lambda item: (-item[0], item[1])
    ):
        if any(
            start < previous_end and end > previous_start
            for previous_start, previous_end in occupied
        ):
            continue
        selected.append(
            EvidenceRegion(
                claim_id=claim_id,
                text=region,
                start=start,
                end=end,
                page_number=page_number,
            )
        )
        occupied.append((start, end))
        if len(selected) >= max_regions:
            break
    return sorted(selected, key=lambda item: item.start)


def extract_candidate_excerpts(
    *,
    claims: list[tuple[str, str]],
    page_text: str,
    max_chars: int,
    remaining_total_chars: int,
    max_windows: int = 2,
) -> list[EvidenceCandidate]:
    """Select bounded claim-relevant passages; it does not assign factual polarity."""
    passages = _segments(page_text)
    output: list[EvidenceCandidate] = []
    budget = remaining_total_chars
    for claim_id, claim_text in claims:
        if not extract_claim_anchors(claim_text).terms or budget < 24 or max_windows <= 0:
            continue
        ranked = sorted(
            (
                (score, index, passage)
                for index, passage in enumerate(passages)
                if (score := _passage_score(claim_text, passage)) is not None
            ),
            key=lambda item: (-item[0], item[1]),
        )
        selected: list[str] = []
        selected_terms: list[set[str]] = []
        for _, _, passage in ranked:
            excerpt = passage.excerpt.strip()
            if passage.heading_context:
                contextual = f"{passage.heading_context}\n{excerpt}"
                normalized_contextual = " ".join(contextual.casefold().split())
                normalized_source = " ".join(page_text.casefold().split())
                if len(normalized_contextual) >= 24 and normalized_contextual in normalized_source:
                    excerpt = contextual
            excerpt = excerpt[: min(max_chars, budget)].strip()
            if len(excerpt) < 24:
                continue
            excerpt_terms = _terms(excerpt)
            if any(
                len(excerpt_terms & previous) / max(1, len(excerpt_terms | previous)) >= 0.65
                for previous in selected_terms
            ):
                continue
            output.append(EvidenceCandidate(claim_id=claim_id, excerpt=excerpt))
            selected.append(excerpt)
            selected_terms.append(excerpt_terms)
            budget -= len(excerpt)
            if len(selected) >= max_windows or budget < 24:
                break
    return output
