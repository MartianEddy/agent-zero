import unittest
from uuid import UUID

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.investigation import Channel, InputType, InvestigationStatus
from app.modules.investigations.models import Investigation, InvestigationUsage
from app.modules.investigations.provider_errors import (
    FailureCategory,
    classify_provider_error,
    is_retryable,
)
from app.modules.investigations.usage import (
    ModelCallBudget,
    ModelCallBudgetExceeded,
    token_usage,
)
from app.modules.sources.urls import normalize_source_url


class SourceUrlNormalizationTests(unittest.TestCase):
    def test_deduplicates_tracking_parameters_fragments_and_trailing_slashes(self) -> None:
        self.assertEqual(
            normalize_source_url("HTTPS://News.Example/story/?utm_source=x&b=2#top"),
            "https://news.example/story?b=2",
        )

    def test_preserves_meaningful_query_parameters(self) -> None:
        self.assertEqual(
            normalize_source_url("https://news.example/story?id=42"),
            "https://news.example/story?id=42",
        )


class ProviderFailureClassificationTests(unittest.TestCase):
    def test_distinguishes_quota_429_from_rate_limit_429(self) -> None:
        class Error(Exception):
            status_code = 429

            def __init__(self, message: str) -> None:
                super().__init__(message)
                self.message = message

        self.assertEqual(
            classify_provider_error(Error("You exceeded your quota")),
            FailureCategory.QUOTA_EXHAUSTED,
        )
        self.assertEqual(
            classify_provider_error(Error("Too many requests")),
            FailureCategory.RATE_LIMITED,
        )

    def test_maps_authentication_and_server_failures(self) -> None:
        class Error(Exception):
            def __init__(self, status_code: int) -> None:
                self.status_code = status_code

        self.assertEqual(classify_provider_error(Error(401)), FailureCategory.AUTHENTICATION_FAILED)
        self.assertEqual(classify_provider_error(Error(503)), FailureCategory.PROVIDER_UNAVAILABLE)

    def test_quota_and_authentication_failures_are_not_retryable(self) -> None:
        self.assertFalse(is_retryable(FailureCategory.QUOTA_EXHAUSTED))
        self.assertFalse(is_retryable(FailureCategory.AUTHENTICATION_FAILED))
        self.assertTrue(is_retryable(FailureCategory.RATE_LIMITED))


class ModelUsageBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        event.listen(
            engine,
            "connect",
            lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
        )
        Base.metadata.create_all(engine)
        self.session = Session(engine)
        owner = UUID("00000000-0000-4000-8000-000000000001")
        from app.modules.investigations.models import User

        self.session.add(User(id=owner, external_subject="test"))
        self.session.flush()
        self.investigation_id = UUID("00000000-0000-4000-8000-000000000002")
        self.session.add(
            Investigation(
                id=self.investigation_id,
                reference="AZ-TEST-000001",
                owner_id=owner,
                channel=Channel.WEB,
                input_type=InputType.TEXT,
                status=InvestigationStatus.RECEIVED,
                current_stage="RECEIVED",
            )
        )
        self.session.add(InvestigationUsage(investigation_id=self.investigation_id))
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def test_budget_counts_attempts_and_stops_before_exceeding_limit(self) -> None:
        budget = ModelCallBudget(self.session, self.investigation_id)
        original_limit = budget.limit
        budget.limit = 1
        budget.begin(provider="openai", model="configured", purpose="CLAIM_EXTRACTION")
        with self.assertRaises(ModelCallBudgetExceeded):
            budget.begin(provider="openai", model="configured", purpose="EVIDENCE_REASONING")
        self.assertEqual(
            self.session.scalar(
                select(InvestigationUsage).where(
                    InvestigationUsage.investigation_id == self.investigation_id
                )
            ).model_calls,
            1,
        )
        budget.limit = original_limit

    def test_token_usage_is_unknown_when_provider_does_not_return_it(self) -> None:
        self.assertEqual(token_usage([]), (None, None, None, None))

    def test_token_usage_reads_responses_api_usage(self) -> None:
        raw = {
            "response": {
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 4,
                    "total_tokens": 14,
                    "input_tokens_details": {"cached_tokens": 3},
                }
            }
        }
        self.assertEqual(token_usage([raw]), (10, 3, 4, 14))


if __name__ == "__main__":
    unittest.main()
