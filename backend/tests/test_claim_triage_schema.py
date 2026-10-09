import unittest

from pydantic import ValidationError

from app.modules.investigations.investigator import PlannedClaim


class ClaimTriageSchemaTests(unittest.TestCase):
    def test_accepts_only_supported_claim_types_and_requires_route_flag(self) -> None:
        item = PlannedClaim(
            text="Kenya gained independence in 1963.",
            normalized_text="kenya gained independence in 1963",
            claim_type="SETTLED_FACT",
            needs_deep_investigation=False,
        )
        self.assertEqual(item.claim_type, "SETTLED_FACT")
        self.assertFalse(item.needs_deep_investigation)

        with self.assertRaises(ValidationError):
            PlannedClaim(
                text="Kenya gained independence in 1963.",
                normalized_text="kenya gained independence in 1963",
                claim_type="FACTUAL",
                needs_deep_investigation=True,
            )

        with self.assertRaises(ValidationError):
            PlannedClaim(
                text="Kenya gained independence in 1963.",
                normalized_text="kenya gained independence in 1963",
                claim_type="SETTLED_FACT",
            )


if __name__ == "__main__":
    unittest.main()
