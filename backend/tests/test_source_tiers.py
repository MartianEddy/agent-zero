import unittest

from app.modules.sources.tiers import source_tier_for_domain


class SourceTierTests(unittest.TestCase):
    def test_wikipedia_is_reference_and_allowlist_is_scoped(self) -> None:
        self.assertEqual(source_tier_for_domain("en.wikipedia.org"), "AUTHORITATIVE_REFERENCE")
        self.assertEqual(source_tier_for_domain("wikidata.org"), "AUTHORITATIVE_REFERENCE")
        self.assertEqual(source_tier_for_domain("parliament.go.ke"), "PRIMARY")
        self.assertEqual(source_tier_for_domain("fake-go.ke.example.net"), "UNKNOWN")
        self.assertEqual(source_tier_for_domain("x.com"), "UNVERIFIED_SOCIAL")


if __name__ == "__main__":
    unittest.main()
