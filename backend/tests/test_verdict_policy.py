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
        authoritative = [EvidenceSignal("a", "SUPPORTS", "AUTHORITATIVE_REFERENCE", "wiki")]
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
