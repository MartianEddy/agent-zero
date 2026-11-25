"""Separate government sites are separate sources; a catch-all registry name is not a publisher.

Production case "Nairobi is the capital of Kenya.": nairobi.go.ke, nakuru.go.ke and
maarifa.cog.go.ke all supported the claim, but every one was stored with the publisher
"Kenya public authority domain", so the ledger merged them into one group and the case
stopped at "1 independent source group".
"""

from app.modules.investigations.evidence_ledger import independence_groups
from app.modules.investigations.verdict_policy import EvidenceSignal, assess_verdict
from app.modules.sources.registry import authority_fits_claim, publisher_for_domain
from app.modules.sources.tiers import source_tier_for_domain


def test_suffix_entry_does_not_become_the_publisher():
    assert publisher_for_domain("nairobi.go.ke") == "nairobi.go.ke"
    assert publisher_for_domain("www.nakuru.go.ke") == "nakuru.go.ke"
    assert publisher_for_domain("parliament.go.ke") == "Parliament of Kenya"
    assert publisher_for_domain("www.parliament.go.ke") == "Parliament of Kenya"
    assert publisher_for_domain("unregistered.example") == "unregistered.example"


def test_different_government_sites_stay_independent():
    items = [
        {"id": domain, "url": f"https://{domain}/page", "publisher": publisher_for_domain(domain)}
        for domain in ("nairobi.go.ke", "www.nakuru.go.ke", "www.maarifa.cog.go.ke")
    ]
    groups = independence_groups(items)
    assert len(set(groups.values())) == 3


def test_one_publisher_on_two_addresses_is_still_one_source():
    items = [
        {"id": "a", "url": "https://parliament.go.ke/a", "publisher": "Parliament of Kenya"},
        {"id": "b", "url": "https://www.parliament.go.ke/b", "publisher": "Parliament of Kenya"},
    ]
    groups = independence_groups(items)
    assert groups["a"] == groups["b"]


def test_two_county_sites_support_a_settled_fact():
    signals = [
        EvidenceSignal("e1", "SUPPORTS", source_tier_for_domain(d), f"group:{d}", True, False)
        for d in ("nairobi.go.ke", "nakuru.go.ke")
    ]
    result = assess_verdict(
        "SETTLED_FACT", "SUPPORTED", signals, claim_text="Nairobi is the capital of Kenya."
    )
    assert result.verdict == "SUPPORTED"


def test_fifa_settles_its_own_competition_results():
    claim = "Kenya won the 2022 FIFA World Cup."
    assert source_tier_for_domain("inside.fifa.com") == "PRIMARY"
    assert authority_fits_claim("www.fifa.com", claim)
    assert not authority_fits_claim("www.fifa.com", "Kenya's inflation rose in 2022.")
    signals = [EvidenceSignal("e1", "CONTRADICTS", "PRIMARY", "group:fifa", True, True)]
    result = assess_verdict("SETTLED_FACT", "CONTRADICTED", signals, claim_text=claim)
    assert result.verdict == "CONTRADICTED"
    assert result.confidence == "MEDIUM"
