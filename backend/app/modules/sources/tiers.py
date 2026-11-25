"""Source evidence tiers from a reviewed, explicit domain allowlist."""

import json
import re
from functools import lru_cache
from pathlib import Path

TIER_CONFIG = Path(__file__).with_name("source_tiers.json")


@lru_cache(maxsize=1)
def _domains_by_tier() -> dict[str, tuple[str, ...]]:
    value = json.loads(TIER_CONFIG.read_text(encoding="utf-8"))
    return {
        tier: tuple(str(domain).casefold().removeprefix("www.") for domain in domains)
        for tier, domains in value.items()
        if isinstance(domains, list)
    }


# Government and academic domains that are not in the reviewed registry. They count as
# corroborating evidence, but cannot settle a claim alone: the one-source rule still
# needs a registered source whose remit matches the claim (registry.authority_fits_claim).
_GOVERNMENT = re.compile(
    r"(^|\.)(gov|go|gob|gouv|gv|govt|mil)\.[a-z]{2}$|(^|\.)(gov|mil|int)$|(^|\.)gc\.ca$"
)
_ACADEMIC = re.compile(r"(^|\.)(ac|edu)\.[a-z]{2}$|(^|\.)edu$")


def source_tier_for_domain(domain: str | None) -> str:
    normalized = (domain or "").strip().casefold().removeprefix("www.").rstrip(".")
    if not normalized:
        return "UNKNOWN"
    tiers = _domains_by_tier()
    for tier in (
        "PRIMARY",
        "FACT_CHECK",
        "AUTHORITATIVE_REFERENCE",
        "REPUTABLE_REPORTING",
        "SECONDARY_AGGREGATOR",
        "UNVERIFIED_SOCIAL",
    ):
        if any(
            normalized == allowed or normalized.endswith(f".{allowed}")
            for allowed in tiers.get(tier, ())
        ):
            return tier
    if _GOVERNMENT.search(normalized):
        return "PRIMARY"
    if _ACADEMIC.search(normalized):
        return "AUTHORITATIVE_REFERENCE"
    return "UNKNOWN"
