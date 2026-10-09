import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.investigation import InputType
from app.modules.investigations.investigator import (
    EvidenceReasoning,
    ExplanationSentence,
    ModelGateway,
    ModelInvocationFailed,
    ModelRun,
    PlannedClaim,
    PlannedQuery,
    ReasonedFinding,
    ResearchPlan,
)
from app.modules.investigations.models import (
    AuditEvent,
    Claim,
    ClaimEvidence,
    Evidence,
    Finding,
    FindingEvidence,
    InvestigationUsage,
    ModelUsageRecord,
    OutboxEvent,
    ProcessingJob,
    SearchTrace,
    Source,
)
from app.modules.investigations.orchestrator import (
    _persist_findings,
    _persist_plan,
    _query_for_freshness,
    process_investigation,
)
from app.modules.investigations.provider_errors import FailureCategory
from app.modules.investigations.routes import retry_investigation
from app.modules.investigations.service import InvestigationService
from app.modules.investigations.usage import fail_model_call
from app.modules.sources.exa_search import ExaSearchResponse
from app.modules.sources.openai_web_search import OpenAIWebSearchResponse
from app.modules.sources.retrieval import RetrievedPage

OWNER_ID = UUID("00000000-0000-4000-8000-000000000001")


class CostControlledPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        event.listen(
            engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON")
        )
        Base.metadata.create_all(engine)
        self.session = Session(engine, expire_on_commit=False)
        self.investigation = InvestigationService(self.session).create(
            owner_id=OWNER_ID,
            content="Schools in Nyeri County will remain closed tomorrow.",
            input_type=InputType.TEXT,
            idempotency_key="pipeline-test",
        )
        self.job = self.session.scalar(
            select(ProcessingJob).where(ProcessingJob.investigation_id == self.investigation.id)
        )
        self.object_store: dict[str, bytes] = {}
        self.gateway_call_count = 0
        self.settings = SimpleNamespace(
            ai_primary_provider="openai",
            openai_api_key=SecretStr("mock-openai-key"),
            openai_model="mock-model",
            openai_reasoning_effort="low",
            model_request_timeout_seconds=45,
            exa_api_key=SecretStr("mock-exa-key"),
            source_reader_provider="jina_reader",
            max_model_calls_per_investigation=4,
            max_provider_retries=1,
            max_retry_after_seconds=5,
            max_claims_per_investigation=3,
            max_search_queries=5,
            max_search_results_per_query=5,
            max_sources_per_investigation=8,
            max_retrieved_sources=5,
            max_source_chars_per_source=6000,
            max_total_evidence_chars=24000,
            max_images_to_model=4,
            max_model_input_chars=12000,
            max_model_output_tokens_research=700,
            max_model_output_tokens_synthesis=900,
        )

    def tearDown(self) -> None:
        self.session.close()

    def test_failed_model_attempt_records_safe_retry_diagnostics(self) -> None:
        record = ModelUsageRecord(
            investigation_id=self.investigation.id,
            provider="openai",
            model="mock-model",
            purpose="CLAIM_EXTRACTION",
            status="STARTED",
        )
        self.session.add(record)
        self.session.commit()
        fail_model_call(
            self.session,
            record,
            "PROVIDER_UNAVAILABLE",
            http_status=503,
            request_id="req-safe-id",
            retryable=True,
        )
        event_record = self.session.scalar(
            select(AuditEvent)
            .where(AuditEvent.event_type == "MODEL_CALL_FAILED")
            .order_by(AuditEvent.created_at.desc())
        )
        self.assertEqual(record.failure_category, "PROVIDER_UNAVAILABLE")
        self.assertEqual(event_record.event_metadata["http_status"], 503)
        self.assertEqual(event_record.event_metadata["request_id"], "req-safe-id")
        self.assertTrue(event_record.event_metadata["retryable"])
        self.assertIsNone(record.total_tokens)

    def _provider_patches(
        self, *, final_error: bool = True, queries: list[str | PlannedQuery] | None = None
    ):
        search_counter = 0
        plan = ResearchPlan(
            claims=[
                PlannedClaim(
                    text="Schools in Nyeri County will remain closed tomorrow.",
                    normalized_text="schools in nyeri county will remain closed tomorrow",
                    claim_type="CHECKABLE_EVENT",
                    needs_deep_investigation=True,
                )
            ],
            queries=queries or ["Nyeri County schools closure official notice"],
        )

        class FakeInvestigator:
            def extract_claims_and_queries(inner, **_kwargs):
                self.gateway_call_count += 1
                return ModelRun(output=plan, provider="openai", model="mock-model")

            def reason_about_evidence(inner, *, evidence_packet, session, investigation_id, **_kwargs):
                self.gateway_call_count += 1
                if final_error:
                    raise ModelInvocationFailed(
                        provider="openai",
                        model="mock-model",
                        category=FailureCategory.PROVIDER_UNAVAILABLE,
                    )
                claim = session.scalar(
                    select(Claim).where(Claim.investigation_id == investigation_id)
                )
                evidence = session.scalar(
                    select(Evidence).where(
                        Evidence.investigation_id == investigation_id,
                        Evidence.source_id.is_not(None),
                    )
                )
                return ModelRun(
                    output=EvidenceReasoning(
                        findings=[
                            ReasonedFinding(
                                claim_id=str(claim.id),
                                status="SUPPORTED",
                                statement="The retrieved passage supports the claim.",
                                explanation=[ExplanationSentence(sentence="The retrieved passage supports the claim.", evidence_ids=[str(evidence.id)])],
                                evidence=[
                                    {"evidence_id": str(evidence.id), "relationship": "SUPPORTS"}
                                ],
                                        evidence_confidence="MEDIUM",
            confidence_rationale="Mock finding includes its fixture evidence for contract testing.",
)
                        ]
                    ),
                    provider="openai",
                    model="mock-model",
                )

        def search(**kwargs):
            nonlocal search_counter
            search_counter += 1
            if hasattr(self, "search_queries"):
                self.search_queries.append(kwargs["query"])
            results = [
                {
                    "url": f"https://news.example/story/{search_counter}?utm_source=test#top",
                    "title": f"Nyeri County school notice {search_counter}",
                    "author": "County Desk",
                    "publishedDate": "2026-10-03T08:00:00Z",
                }
            ]
            return ExaSearchResponse(request_id="mock-request", results=results)

        def search_openai(**kwargs):
            return OpenAIWebSearchResponse(
                request_id="mock-openai-request",
                results=[
                    {
                        "url": f"https://news.example/story/{search_counter}?utm_source=test#top",
                        "title": f"Nyeri County school notice {search_counter}",
                        "author": "County Desk",
                        "publishedDate": "2026-10-03T08:00:00Z",
                    }
                ],
                citations=[
                    {
                        "url": f"https://news.example/story/{search_counter}?utm_source=test#top",
                        "title": f"Nyeri County school notice {search_counter}",
                    }
                ],
            )

        def retrieve(_url, **_kwargs):
            return RetrievedPage(
                requested_url="https://news.example/story/1",
                text=(
                    "Schools in Nyeri County will remain closed tomorrow, county officials said. "
                    "The notice was published by the county education office."
                ),
            )

        patches = [
            patch(
                "app.modules.investigations.orchestrator.get_settings", return_value=self.settings
            ),
            patch("app.modules.investigations.orchestrator.ModelGateway", FakeInvestigator),
            patch("app.modules.investigations.orchestrator.search_exa", side_effect=search),
            patch(
                "app.modules.investigations.orchestrator.search_openai_web",
                side_effect=search_openai,
            ),
            patch("app.modules.investigations.orchestrator.read_public_page", side_effect=retrieve),
            patch(
                "app.modules.investigations.orchestrator.put_private_object",
                side_effect=lambda *, key, data, content_type: self.object_store.__setitem__(
                    key, data
                ),
            ),
            patch(
                "app.modules.investigations.orchestrator.get_private_object",
                side_effect=lambda *, key: self.object_store[key],
            ),
        ]
        return patches

    def _run_with_patches(self, patches):
        managers = [item.__enter__() for item in patches]
        try:
            return process_investigation(self.session, job_id=self.job.id)
        finally:
            for item, _manager in zip(patches, managers, strict=True):
                item.__exit__(None, None, None)

    def test_provider_failure_preserves_claims_sources_and_evidence(self) -> None:
        result = self._run_with_patches(self._provider_patches(final_error=True))
        self.assertEqual(result, "needs_review")
        self.assertEqual(self.session.scalar(select(func.count()).select_from(Claim)), 1)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(Source)), 1)
        self.assertEqual(
            self.session.scalar(
                select(func.count()).select_from(Evidence).where(Evidence.source_id.is_not(None))
            ),
            1,
        )
        self.assertEqual(self.session.scalar(select(func.count()).select_from(Finding)), 0)
        self.assertIn(
            "Evidence collected so far has been preserved", self.investigation.failure_reason
        )
        self.assertNotIn("PROVIDER_UNAVAILABLE", self.investigation.failure_reason)

    def test_freshness_intent_is_encoded_in_dispatched_search_query(self) -> None:
        current_query = _query_for_freshness("Mwai Kibaki death report", "CURRENT")
        self.assertIn(
            "latest official updates",
            current_query,
        )
        self.assertEqual(_query_for_freshness(current_query, "CURRENT"), current_query)
        self.assertIn(
            "original records and recent reporting",
            _query_for_freshness("Mwai Kibaki biography", "BALANCED"),
        )
        self.assertEqual(
            _query_for_freshness("Mwai Kibaki presidency 2002 to 2013", "HISTORICAL"),
            "Mwai Kibaki presidency 2002 to 2013",
        )
        self.assertEqual(
            ResearchPlan(
                queries=[PlannedQuery(text="latest cabinet changes", freshness="CURRENT")]
            )
            .queries[0]
            .freshness,
            "CURRENT",
        )

    def test_current_query_dispatch_persists_publication_dates(self) -> None:
        self.search_queries = []
        self._run_with_patches(
            self._provider_patches(
                final_error=True,
                queries=[PlannedQuery(text="Mwai Kibaki death latest", freshness="CURRENT")],
            )
        )
        self.assertIn("latest official updates", self.search_queries[0])
        source = self.session.scalar(select(Source))
        self.assertEqual(source.published_at, "2026-10-03T08:00:00Z")

    def test_normal_text_flow_completes_with_two_model_operations(self) -> None:
        result = self._run_with_patches(self._provider_patches(final_error=False))
        self.assertEqual(result, "complete")
        self.assertEqual(self.gateway_call_count, 2)

    def test_model_gateway_retries_one_transient_openai_failure_and_records_tokens(self) -> None:
        class APIConnectionError(Exception):
            pass

        completed = SimpleNamespace(
            final_output=ResearchPlan(),
            raw_responses=[
                {
                    "usage": {
                        "input_tokens": 31,
                        "output_tokens": 8,
                        "total_tokens": 39,
                        "input_tokens_details": {"cached_tokens": 5},
                    }
                }
            ],
        )
        runner = AsyncMock(side_effect=[APIConnectionError("temporary"), completed])
        client = SimpleNamespace(close=AsyncMock())
        with (
            patch(
                "app.modules.investigations.investigator.get_settings", return_value=self.settings
            ),
            patch("app.modules.investigations.usage.get_settings", return_value=self.settings),
            patch("agents.Runner.run", runner),
            patch("openai.AsyncOpenAI", return_value=client),
            patch("app.modules.investigations.investigator.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = ModelGateway().extract_claims_and_queries(
                text="A bounded test claim.",
                images=[],
                session=self.session,
                investigation_id=self.investigation.id,
            )

        self.assertEqual(result.provider, "openai")
        self.assertEqual(runner.await_count, 2)
        records = list(self.session.scalars(select(ModelUsageRecord)))
        self.assertEqual(len(records), 2)
        self.assertEqual({record.provider for record in records}, {"openai"})
        self.assertEqual(sum(record.input_tokens or 0 for record in records), 31)
        self.assertEqual(sum(record.output_tokens or 0 for record in records), 8)

    def test_search_query_budget_is_enforced_and_sources_persist_before_reasoning(self) -> None:
        self.settings.max_search_queries = 1
        patches = self._provider_patches(final_error=True, queries=["query one", "query two"])
        result = self._run_with_patches(patches)
        self.assertEqual(result, "needs_review")
        self.assertEqual(self.session.scalar(select(func.count()).select_from(SearchTrace)), 2)
        self.assertEqual(
            self.session.scalar(
                select(InvestigationUsage).where(
                    InvestigationUsage.investigation_id == self.investigation.id
                )
            ).search_calls,
            2,
        )
        self.assertEqual(self.session.scalar(select(func.count()).select_from(Source)), 1)

    def test_planned_route_is_persisted_for_both_search_providers(self) -> None:
        plan = ResearchPlan(
            claims=[
                PlannedClaim(
                    text="Kenya gained independence in 1963.",
                    normalized_text="kenya gained independence in 1963",
                    claim_type="SETTLED_FACT",
                    needs_deep_investigation=False,
                )
            ],
            queries=[
                PlannedQuery(
                    text="Kenya independence 1963 primary records",
                    freshness="HISTORICAL",
                    claim_index=0,
                    topic="history",
                    jurisdiction=["Kenya"],
                    source_lane="PRIMARY",
                    widening_reason="Start with primary historical records.",
                )
            ],
        )
        with patch(
            "app.modules.investigations.orchestrator.get_settings", return_value=self.settings
        ):
            _persist_plan(self.session, self.investigation, plan)

        traces = list(
            self.session.scalars(
                select(SearchTrace).where(
                    SearchTrace.investigation_id == self.investigation.id
                )
            )
        )
        self.assertEqual({trace.provider for trace in traces}, {"EXA", "OPENAI_WEB_SEARCH"})
        self.assertTrue(all(trace.route_metadata["source_lane"] == "PRIMARY" for trace in traces))
        self.assertTrue(all(trace.route_metadata["topic"] == "history" for trace in traces))
        self.assertTrue(all(trace.route_metadata["jurisdiction"] == ["Kenya"] for trace in traces))

    def test_retrieval_budget_limits_pages(self) -> None:
        self.settings.max_retrieved_sources = 1
        self._run_with_patches(self._provider_patches(final_error=True, queries=["one", "two"]))
        self.assertEqual(
            self.session.scalar(
                select(func.count())
                .select_from(Source)
                .where(Source.retrieval_status == "RETRIEVED")
            ),
            1,
        )

    def test_retry_endpoint_queues_once_and_preserves_existing_records(self) -> None:
        self._run_with_patches(self._provider_patches(final_error=True))
        before_claims = self.session.scalar(select(func.count()).select_from(Claim))
        with patch("app.modules.investigations.routes.current_owner_id", return_value=OWNER_ID):
            retry_investigation(self.investigation.id, self.session)
            with self.assertRaises(HTTPException) as raised:
                retry_investigation(self.investigation.id, self.session)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(Claim)), before_claims
        )
        self.assertEqual(self.session.scalar(select(func.count()).select_from(OutboxEvent)), 2)

    def test_retry_reuses_completed_search_retrieval_and_evidence(self) -> None:
        self._run_with_patches(self._provider_patches(final_error=True))
        usage = self.session.scalar(
            select(InvestigationUsage).where(
                InvestigationUsage.investigation_id == self.investigation.id
            )
        )
        calls_before_retry = usage.search_calls
        retrieved_before_retry = usage.sources_retrieved
        with patch("app.modules.investigations.routes.current_owner_id", return_value=OWNER_ID):
            retry_investigation(self.investigation.id, self.session)
        self.job = self.session.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.investigation_id == self.investigation.id)
            .order_by(ProcessingJob.created_at.desc())
        )
        result = self._run_with_patches(self._provider_patches(final_error=False))
        self.assertEqual(result, "complete")
        self.assertEqual(usage.search_calls, calls_before_retry)
        self.assertEqual(usage.sources_retrieved, retrieved_before_retry)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(Finding)), 1)

    def test_provider_error_details_are_not_returned_to_users(self) -> None:
        class FakeInvestigator:
            def extract_claims_and_queries(inner, **_kwargs):
                raise ModelInvocationFailed(
                    provider="openai",
                    model="configured-model",
                    category=FailureCategory.QUOTA_EXHAUSTED,
                )

        patches = self._provider_patches(final_error=False)
        patches[1] = patch("app.modules.investigations.orchestrator.ModelGateway", FakeInvestigator)
        self.assertEqual(self._run_with_patches(patches), "needs_review")
        self.assertEqual(
            self.investigation.failure_reason,
            "Investigation paused. Agent 0 could not complete the analysis. "
            "Evidence collected so far has been preserved. "
            "No unsupported verification finding was produced.",
        )
        self.assertNotIn("QUOTA_EXHAUSTED", self.investigation.failure_reason)

    def test_finding_without_matching_evidence_is_downgraded(self) -> None:
        claim = self.session.scalar(
            select(Claim).where(Claim.investigation_id == self.investigation.id)
        )
        if claim is None:
            claim = Claim(
                investigation_id=self.investigation.id,
                text="A specific testable claim.",
                normalized_text="a specific testable claim",
                claim_type="CHECKABLE_EVENT",
            )
            self.session.add(claim)
            self.session.commit()
        _persist_findings(
            self.session,
            self.investigation,
            EvidenceReasoning(
                findings=[
                    ReasonedFinding(
                        claim_id=str(claim.id),
                        status="SUPPORTED",
                        statement="Unsupported assertion.",
                        evidence=[],
                                evidence_confidence="MEDIUM",
            confidence_rationale="Mock finding includes its fixture evidence for contract testing.",
)
                ]
            ),
        )
        finding = self.session.scalar(select(Finding).where(Finding.claim_id == claim.id))
        self.assertEqual(finding.status, "INSUFFICIENT_EVIDENCE")
        self.assertEqual(self.session.scalar(select(func.count()).select_from(FindingEvidence)), 0)

    def test_contradicted_finding_requires_contradicting_evidence(self) -> None:
        claim = Claim(
            investigation_id=self.investigation.id,
            text="A specific testable claim.",
            normalized_text="a specific testable claim",
            claim_type="CHECKABLE_EVENT",
        )
        source = Source(
            investigation_id=self.investigation.id,
            url="https://news.example/report",
            domain="news.example",
            discovery_method="EXA",
        )
        self.session.add_all([claim, source])
        self.session.flush()
        evidence = Evidence(
            investigation_id=self.investigation.id,
            source_id=source.id,
            content="A retrieved excerpt.",
            method="TEST",
        )
        self.session.add(evidence)
        self.session.flush()
        self.session.add(
            ClaimEvidence(claim_id=claim.id, evidence_id=evidence.id, relationship="UNKNOWN")
        )
        self.session.commit()
        _persist_findings(
            self.session,
            self.investigation,
            EvidenceReasoning(
                findings=[
                    ReasonedFinding(
                        claim_id=str(claim.id),
                        status="CONTRADICTED",
                        statement="Unsupported contradiction.",
                        evidence=[{"evidence_id": str(evidence.id), "relationship": "SUPPORTS"}],
                                evidence_confidence="MEDIUM",
            confidence_rationale="Mock finding includes its fixture evidence for contract testing.",
)
                ]
            ),
        )
        finding = self.session.scalar(select(Finding).where(Finding.claim_id == claim.id))
        self.assertEqual(finding.status, "INSUFFICIENT_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
