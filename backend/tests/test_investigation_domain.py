import unittest

from app.domain.investigation import InvestigationStatus, validate_transition


class InvestigationLifecycleTests(unittest.TestCase):
    def test_normal_processing_path(self) -> None:
        steps = [
            InvestigationStatus.RECEIVED,
            InvestigationStatus.PROCESSING,
            InvestigationStatus.ANALYZING,
            InvestigationStatus.RESEARCHING,
            InvestigationStatus.CORROBORATING,
            InvestigationStatus.GENERATING_BRIEF,
            InvestigationStatus.COMPLETE,
        ]
        for current, target in zip(steps, steps[1:]):
            with self.subTest(current=current, target=target):
                validate_transition(current, target)

    def test_foundation_can_stop_for_review(self) -> None:
        validate_transition(InvestigationStatus.RECEIVED, InvestigationStatus.PROCESSING)
        validate_transition(InvestigationStatus.PROCESSING, InvestigationStatus.NEEDS_REVIEW)

    def test_complete_is_terminal(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid investigation transition"):
            validate_transition(InvestigationStatus.COMPLETE, InvestigationStatus.PROCESSING)

    def test_technical_failure_is_not_claim_verdict(self) -> None:
        self.assertNotEqual(InvestigationStatus.FAILED.value, "UNVERIFIED")
        self.assertNotEqual(InvestigationStatus.FAILED.value, "CONTRADICTED")


if __name__ == "__main__":
    unittest.main()
