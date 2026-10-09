"""Small source identity registry; membership describes a source, not truthfulness."""

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
        ("law", "court", "judgment", "act", "legal"),
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
    SourceRegistryEntry("who.int", "World Health Organization", "OFFICIAL", "International"),
    SourceRegistryEntry("worldbank.org", "World Bank", "OFFICIAL", "International"),
    SourceRegistryEntry(
        "un.org",
        "United Nations",
        "OFFICIAL",
        "International",
        ("UN membership, decolonization records, and UN proceedings",),
        ("kenya", "independence", "decolonization", "united nations", "member state"),
    ),
)


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
    claim_words = set(claim_text.casefold().replace("-", " ").split())
    if entry.authoritative_for and any(topic in claim_words for topic in entry.topics):
        return "PRIMARY_AUTHORITY"
    if entry.source_type in {"OFFICIAL", "PUBLIC_RECORD", "ACADEMIC"}:
        return "CONTEXT"
    return "UNKNOWN"
