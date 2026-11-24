"""Small source identity registry; membership describes a source, not truthfulness."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceRegistryEntry:
    domain: str
    name: str
    source_type: str
    jurisdiction: str | None
    authoritative_for: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()


REGISTRY: tuple[SourceRegistryEntry, ...] = (
    SourceRegistryEntry(
        "go.ke",
        "Kenya public authority domain",
        "OFFICIAL",
        "Kenya",
        ("the institution's own announcements and published records",),
        ("government", "ministry", "county", "public", "authority"),
    ),
    SourceRegistryEntry(
        "education.go.ke",
        "Kenya Ministry of Education",
        "OFFICIAL",
        "Kenya",
        ("official education announcements and directives",),
        ("education", "school", "schools", "student", "students"),
    ),
    SourceRegistryEntry(
        "health.go.ke",
        "Kenya Ministry of Health",
        "OFFICIAL",
        "Kenya",
        ("official health announcements and directives",),
        ("health", "medical", "hospital", "disease"),
    ),
    SourceRegistryEntry(
        "parliament.go.ke",
        "Parliament of Kenya",
        "PUBLIC_RECORD",
        "Kenya",
        ("parliamentary proceedings, bills, and published records",),
        ("parliament", "bill", "legislation", "senate", "assembly"),
    ),
    SourceRegistryEntry(
        "knbs.or.ke",
        "Kenya National Bureau of Statistics",
        "OFFICIAL",
        "Kenya",
        ("official statistics published by KNBS",),
        ("statistics", "population", "census", "economy", "inflation"),
    ),
    SourceRegistryEntry(
        "ca.go.ke",
        "Communications Authority of Kenya",
        "OFFICIAL",
        "Kenya",
        ("official communications-sector statistics, licensing, and regulatory announcements",),
        ("communications", "telecommunications", "smartphone", "mobile", "broadband", "network"),
    ),
    SourceRegistryEntry(
        "kenyalaw.org",
        "Kenya Law",
        "PUBLIC_RECORD",
        "Kenya",
        ("published Kenyan legislation and court decisions",),
        ("law", "court", "judgment", "act", "legal", "independence", "constitutional"),
    ),
    SourceRegistryEntry(
        "presidentiallibrary.go.ke",
        "Kenya Presidential Library and Archives",
        "PUBLIC_RECORD",
        "Kenya",
        ("Kenya's presidential, constitutional, and independence-era records",),
        ("kenya", "historical", "history", "independence", "president", "constitution"),
    ),
    SourceRegistryEntry(
        "mck.or.ke",
        "Media Council of Kenya",
        "OFFICIAL",
        "Kenya",
        ("the council's own media standards, accreditation, and published decisions",),
        ("media", "journalism", "journalist", "press"),
    ),
    SourceRegistryEntry(
        "africacheck.org",
        "Africa Check",
        "FACT_CHECK",
        "Africa",
        ("published fact-checks and methodology",),
    ),
    SourceRegistryEntry("nation.africa", "Nation Africa", "NEWS", "Kenya"),
    SourceRegistryEntry("standardmedia.co.ke", "The Standard", "NEWS", "Kenya"),
    SourceRegistryEntry("citizen.digital", "Citizen Digital", "NEWS", "Kenya"),
    SourceRegistryEntry(
        "uonbi.ac.ke", "University of Nairobi", "ACADEMIC", "Kenya", ("university research",)
    ),
    SourceRegistryEntry("ku.ac.ke", "Kenyatta University", "ACADEMIC", "Kenya"),
    SourceRegistryEntry(
        "who.int",
        "World Health Organization",
        "OFFICIAL",
        "International",
        ("public health guidance, disease information, and international health reporting",),
        ("health", "disease", "public health", "medical", "outbreak", "vaccination"),
    ),
    SourceRegistryEntry(
        "worldbank.org",
        "World Bank",
        "OFFICIAL",
        "International",
        ("published World Bank datasets, economic indicators, and project records",),
        ("economy", "poverty", "development", "economic", "gdp", "gross domestic product"),
    ),
    SourceRegistryEntry(
        "un.org",
        "United Nations",
        "OFFICIAL",
        "International",
        ("UN membership, decolonization records, and UN proceedings",),
        ("kenya", "independence", "decolonization", "united nations", "member state"),
    ),
)


def _words(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


def lookup_source(domain: str) -> SourceRegistryEntry | None:
    normalized = domain.strip().rstrip(".").casefold().removeprefix("www.")
    matches = [
        item
        for item in REGISTRY
        if normalized == item.domain or normalized.endswith(f".{item.domain}")
    ]
    return max(matches, key=lambda item: len(item.domain), default=None)


def classify_source(domain: str) -> SourceRegistryEntry:
    return lookup_source(domain) or SourceRegistryEntry(
        domain=domain.casefold(),
        name=domain.casefold(),
        source_type="UNKNOWN",
        jurisdiction=None,
    )


def role_for_claim(entry: SourceRegistryEntry, claim_text: str, *, submitted: bool = False) -> str:
    if submitted:
        return "SUBMITTED"
    if entry.source_type == "FACT_CHECK":
        return "FACT_CHECK"
    claim_words = _words(claim_text)
    if entry.authoritative_for and any(topic in claim_words for topic in entry.topics):
        return "PRIMARY_AUTHORITY"
    if entry.source_type in {"OFFICIAL", "PUBLIC_RECORD", "ACADEMIC"}:
        return "CONTEXT"
    return "UNKNOWN"


def authority_fits_claim(domain: str | None, claim_text: str) -> bool:
    """Whether a registered primary source has a narrow, claim-relevant remit.

    This is a sufficiency-policy input, not a truth score. Unknown and generic
    domain membership never qualifies for the single-source settled-fact path.
    """
    if not domain:
        return False
    entry = lookup_source(domain)
    if (
        entry is None
        or entry.domain == "go.ke"
        or entry.source_type not in {"OFFICIAL", "PUBLIC_RECORD"}
    ):
        return False
    claim_words = _words(claim_text)
    topic_words = {
        word
        for topic in entry.topics
        for word in _words(topic)
        if len(word) > 3 and word not in {"official", "published", "records", "their"}
    }
    specific_match = bool((claim_words - {"kenya", "the", "and", "in", "of", "for"}) & topic_words)
    jurisdiction_match = (
        entry.jurisdiction is None
        or entry.jurisdiction.casefold() == "international"
        or entry.jurisdiction.casefold() in claim_words
    )
    return bool(entry.authoritative_for and specific_match and jurisdiction_match)
