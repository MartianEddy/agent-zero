"""Source evidence tiers from a reviewed, explicit domain allowlist."""

import json
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


def source_tier_for_domain(domain: str | None) -> str:
    normalized = (domain or "").strip().casefold().removeprefix("www.").rstrip(".")
    if not normalized:
        return "UNKNOWN"
    tiers = _domains_by_tier()
    for tier in (
        "PRIMARY",
        "AUTHORITATIVE_REFERENCE",
        "REPUTABLE_REPORTING",
        "SECONDARY_AGGREGATOR",
        "UNVERIFIED_SOCIAL",
    ):
        if any(normalized == allowed or normalized.endswith(f".{allowed}") for allowed in tiers.get(tier, ())):
            return tier
    return "UNKNOWN"
