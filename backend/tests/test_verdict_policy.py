import unittest

from app.modules.investigations.verdict_policy import (
    EvidenceSignal,
    assess_verdict,
    build_independence_groups,
)


class VerdictPolicyTests(unittest.TestCase):
    def test_supported_requires_two_independent_sources_except_settled_fact(self) -> None:
        sparse = [EvidenceSignal("a", "SUPPORTS", "REPUTABLE_REPORTING", "news-a")]
        self.assertEqual(assess_verdict("CHECKABLE_EVENT", "SUPPORTED", sparse).verdict,
                         "INSUFFICIENT_EVIDENCE")
        authoritative = [
            EvidenceSignal("a", "SUPPORTS", "PRIMARY", "archive", authority_fits_claim=True)
        ]
        self.assertEqual(assess_verdict("SETTLED_FACT", "SUPPORTED", authoritative).verdict,
                         "SUPPORTED")

    def test_same_independence_group_does_not_count_twice(self) -> None:
        copied = [
            EvidenceSignal("a", "SUPPORTS", "REPUTABLE_REPORTING", "shared-report"),
            EvidenceSignal("b", "SUPPORTS", "REPUTABLE_REPORTING", "shared-report"),
        ]
        result = assess_verdict("CHECKABLE_EVENT", "SUPPORTED", copied)
        self.assertEqual(result.verdict, "INSUFFICIENT_EVIDENCE")
        self.assertEqual(result.confidence, "LOW")

    def test_partly_true_requires_mixed_independent_evidence(self) -> None:
        mixed = [
            EvidenceSignal("a", "SUPPORTS", "AUTHORITATIVE_REFERENCE", "sense-a"),
            EvidenceSignal("b", "CONTRADICTS", "AUTHORITATIVE_REFERENCE", "sense-b"),
        ]
        self.assertEqual(assess_verdict("CONTESTED", "PARTLY_TRUE", mixed).verdict,
                         "PARTLY_TRUE")
        only_one_side = [mixed[0]]
        self.assertEqual(assess_verdict("CONTESTED", "PARTLY_TRUE", only_one_side).verdict,
                         "INSUFFICIENT_EVIDENCE")

    def test_opinion_is_never_verifiable(self) -> None:
        result = assess_verdict("OPINION_OR_PREDICTION", "SUPPORTED", [])
        self.assertEqual(result.verdict, "NOT_VERIFIABLE")
        self.assertEqual(result.confidence, "LOW")

    def test_domain_and_citation_chains_collapse(self) -> None:
        groups = build_independence_groups(
            {"a": "https://www.news.example/story", "b": "https://news.example/other",
             "c": "https://wire.example/report"},
            [("b", "c", "CITES")],
        )
        self.assertEqual(groups["a"], groups["b"])
        self.assertEqual(groups["b"], groups["c"])


if __name__ == "__main__":
    unittest.main()


class VerdictPolicyV2Tests(unittest.TestCase):
    def test_one_official_source_can_settle_a_statistic(self) -> None:
        official = [EvidenceSignal("a", "CONTRADICTS", "PRIMARY", "knbs", authority_fits_claim=True, is_stale=False)]
        result = assess_verdict("STATISTICAL", "CONTRADICTED", official)
        self.assertEqual(result.verdict, "CONTRADICTED")
        self.assertEqual(result.confidence, "MEDIUM")

    def test_stale_statistic_cannot_settle_a_current_number_alone(self) -> None:
        stale = [EvidenceSignal("a", "CONTRADICTS", "PRIMARY", "knbs", authority_fits_claim=True, is_stale=True)]
        self.assertEqual(
            assess_verdict("STATISTICAL", "CONTRADICTED", stale).verdict, "INSUFFICIENT_EVIDENCE"
        )

    def test_one_official_source_is_not_enough_for_an_event_claim(self) -> None:
        official = [EvidenceSignal("a", "SUPPORTS", "PRIMARY", "gov", authority_fits_claim=True)]
        self.assertEqual(
            assess_verdict("CHECKABLE_EVENT", "SUPPORTED", official).verdict, "INSUFFICIENT_EVIDENCE"
        )

    def test_official_record_outweighs_conflicting_press_reports(self) -> None:
        evidence = [
            EvidenceSignal("rec", "CONTRADICTS", "PRIMARY", "knbs", authority_fits_claim=True, is_stale=False),
            EvidenceSignal("n1", "SUPPORTS", "REPUTABLE_REPORTING", "news-a"),
            EvidenceSignal("n2", "SUPPORTS", "REPUTABLE_REPORTING", "news-b"),
        ]
        result = assess_verdict("STATISTICAL", "CONTRADICTED", evidence)
        self.assertEqual(result.verdict, "CONTRADICTED")
        self.assertNotEqual(result.confidence, "HIGH")

    def test_model_proposal_that_disagrees_with_dominant_record_stays_unresolved(self) -> None:
        evidence = [
            EvidenceSignal("rec", "CONTRADICTS", "PRIMARY", "knbs", authority_fits_claim=True, is_stale=False),
            EvidenceSignal("n1", "SUPPORTS", "REPUTABLE_REPORTING", "news-a"),
        ]
        self.assertEqual(
            assess_verdict("STATISTICAL", "SUPPORTED", evidence).verdict, "INSUFFICIENT_EVIDENCE"
        )

    def test_conflict_between_equals_stays_unresolved_with_no_high_confidence(self) -> None:
        evidence = [
            EvidenceSignal("a", "SUPPORTS", "REPUTABLE_REPORTING", "news-a"),
            EvidenceSignal("b", "SUPPORTS", "REPUTABLE_REPORTING", "news-b"),
            EvidenceSignal("c", "CONTRADICTS", "REPUTABLE_REPORTING", "news-c"),
        ]
        result = assess_verdict("CHECKABLE_EVENT", "SUPPORTED", evidence)
        self.assertEqual(result.verdict, "INSUFFICIENT_EVIDENCE")
        self.assertNotEqual(result.confidence, "HIGH")

    def test_fact_checks_are_context_not_evidence(self) -> None:
        evidence = [
            EvidenceSignal("a", "SUPPORTS", "FACT_CHECK", "africacheck"),
            EvidenceSignal("b", "SUPPORTS", "FACT_CHECK", "pesacheck"),
        ]
        self.assertEqual(
            assess_verdict("CHECKABLE_EVENT", "SUPPORTED", evidence).verdict, "INSUFFICIENT_EVIDENCE"
        )

    def test_two_official_groups_give_high_confidence(self) -> None:
        evidence = [
            EvidenceSignal("a", "SUPPORTS", "PRIMARY", "g1", authority_fits_claim=True),
            EvidenceSignal("b", "SUPPORTS", "PRIMARY", "g2", authority_fits_claim=True),
        ]
        result = assess_verdict("CHECKABLE_EVENT", "SUPPORTED", evidence)
        self.assertEqual((result.verdict, result.confidence), ("SUPPORTED", "HIGH"))

    def test_sibling_domains_with_one_owner_are_one_group(self) -> None:
        groups = build_independence_groups(
            {"a": "https://en.wikipedia.org/wiki/Kenya", "b": "https://www.wikidata.org/wiki/Q114",
             "c": "https://nation.africa/x", "d": "https://nationmedia.com/y",
             "e": "https://reuters.com/z"},
            [],
        )
        self.assertEqual(groups["a"], groups["b"])
        self.assertEqual(groups["c"], groups["d"])
        self.assertNotEqual(groups["a"], groups["e"])


class SourceTierTests(unittest.TestCase):
    def test_fact_checkers_have_their_own_tier_and_wires_are_reputable(self) -> None:
        from app.modules.sources.tiers import source_tier_for_domain

        self.assertEqual(source_tier_for_domain("africacheck.org"), "FACT_CHECK")
        self.assertEqual(source_tier_for_domain("factcheck.afp.com"), "FACT_CHECK")
        self.assertEqual(source_tier_for_domain("www.reuters.com"), "REPUTABLE_REPORTING")
        self.assertEqual(source_tier_for_domain("iebc.or.ke"), "PRIMARY")
        self.assertEqual(source_tier_for_domain("random-blog.example"), "UNKNOWN")
