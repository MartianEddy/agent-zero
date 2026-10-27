import unittest

from pydantic import ValidationError

from app.modules.investigations.investigator import PlannedClaim


class ClaimTriageSchemaTests(unittest.TestCase):
    def test_model_claim_schema_contains_only_model_owned_fields(self) -> None:
        self.assertEqual(set(PlannedClaim.model_fields), {"text", "claim_type"})

    def test_model_normalized_claim_text_is_recomputed_from_the_claim(self) -> None:
        item = PlannedClaim(
            text="  KENYA gained independence   in 1963. ",
            claim_type="SETTLED_FACT",
        )

        self.assertEqual(item.text, "  KENYA gained independence   in 1963. ")

    def test_accepts_only_supported_claim_types(self) -> None:
        item = PlannedClaim(
            text="Kenya gained independence in 1963.",
            claim_type="SETTLED_FACT",
        )
        self.assertEqual(item.claim_type, "SETTLED_FACT")

        with self.assertRaises(ValidationError):
            PlannedClaim(
                text="Kenya gained independence in 1963.",
                claim_type="FACTUAL",
            )


if __name__ == "__main__":
    unittest.main()
