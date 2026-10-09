import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.investigation import InputType, InvestigationStatus
from app.modules.investigations.investigator import (
    EvidenceReasoning,
    ModelInvocationFailed,
    ModelRun,
    PlannedClaim,
    ReasonedFinding,
    ResearchPlan,
)
from app.modules.investigations.models import (
    Claim,
    ClaimEvidence,
    Evidence,
    Finding,
    FindingEvidence,
    InvestigationUsage,
    ProcessingJob,
    SearchTrace,
    Source,
    SourceRelationship,
)
from app.modules.investigations.orchestrator import (
    _detect_source_relationships,
    _persist_evidence,
    _persist_findings,
    process_investigation,
)
from app.modules.investigations.provider_errors import FailureCategory
from app.modules.investigations.service import InvestigationService
from app.modules.sources.exa_search import ExaSearchResponse
from app.modules.sources.registry import classify_source, lookup_source
from app.modules.sources.retrieval import RetrievedPage, SourceRetrievalError, parse_reader_response
from app.modules.sources.urls import normalize_source_url

OWNER_ID = UUID("00000000-0000-4000-8000-000000000001")


class UrlSourceIntelligenceTests(unittest.TestCase):
    def test_url_normalization_removes_tracking_and_normalizes_host_and_slashes(self) -> None:
        self.assertEqual(
            normalize_source_url(
                "HTTPS://News.Example:443/story/?utm_source=x&fbclid=abc&ref=homepage#part"
            ),
            "https://news.example/story?ref=homepage",
        )

    def test_registry_classifies_known_sources_without_assigning_a_credibility_score(self) -> None:
        entry = lookup_source("www.knbs.or.ke")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.source_type, "OFFICIAL")
        self.assertEqual(entry.jurisdiction, "Kenya")
        self.assertIn("official statistics published by KNBS", entry.authoritative_for)
        self.assertEqual(classify_source("nation.africa").source_type, "NEWS")
        self.assertEqual(classify_source("unlisted.example").source_type, "UNKNOWN")

    def test_reader_response_separates_metadata_from_article_body(self) -> None:
        page = parse_reader_response(
            "Title: Schools notice\nURL Source: https://education.go.ke/notice/\n"
            "Author: Jane Reporter\nPublished Time: 2026-10-02T09:00:00Z\n"
            "Markdown Content:\nSchools in Nyeri County will remain closed tomorrow."
        )
        self.assertEqual(page.title, "Schools notice")
        self.assertEqual(page.canonical_url, "https://education.go.ke/notice/")
        self.assertEqual(page.author, "Jane Reporter")
        self.assertEqual(page.published_at, "2026-10-02T09:00:00Z")
        self.assertEqual(page.text, "Schools in Nyeri County will remain closed tomorrow.")

    def test_url_pipeline_uses_retrieved_submission_as_context_not_evidence(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        event.listen(
            engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON")
        )
        Base.metadata.create_all(engine)
        session = Session(engine, expire_on_commit=False)
        investigation = InvestigationService(session).create(
            owner_id=OWNER_ID,
            content="https://nation.africa/schools-close?utm_source=mail#top",
            input_type=InputType.URL,
            idempotency_key="url-source-intelligence",
        )
        job = session.scalar(
            select(ProcessingJob).where(ProcessingJob.investigation_id == investigation.id)
        )
        settings = SimpleNamespace(
            exa_api_key=SimpleNamespace(get_secret_value=lambda: "mock-exa"),
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
        object_store: dict[str, bytes] = {}
        calls: list[str] = []

        class FakeGateway:
            def extract_claims_and_queries(self, *, text, **_kwargs):
                calls.append("extract")
                assert "Schools in Nyeri County" in text
                assert "SUBMITTED SOURCE" in text
                return ModelRun(
                    output=ResearchPlan(
                        claims=[
                            PlannedClaim(
                                text="Schools in Nyeri County will remain closed tomorrow.",
                                normalized_text=(
                                    "schools in nyeri county will remain closed tomorrow"
                                ),
                                claim_type="CHECKABLE_EVENT",
                                needs_deep_investigation=True,
                            )
                        ],
                        queries=["Nyeri school closure official notice"],
                    ),
                    provider="openai",
                    model="mock-luna",
                )

            def reason_about_evidence(self, *, session, investigation_id, **_kwargs):
                calls.append("reason")
                assert (
                    session.scalar(
                        select(func.count())
                        .select_from(Source)
                        .where(Source.investigation_id == investigation_id)
                    )
                    == 2
                )
                self.assert_evidence_persisted(session, investigation_id)
                return ModelRun(
                    output=EvidenceReasoning(findings=[]),
                    provider="openai",
                    model="mock-luna",
                )

            @staticmethod
            def assert_evidence_persisted(session, investigation_id):
                assert (
                    session.scalar(
                        select(func.count())
                        .select_from(Evidence)
                        .where(
                            Evidence.investigation_id == investigation_id,
                            Evidence.source_id.is_not(None),
                        )
                    )
                    == 1
                )

        def retrieve(url):
            calls.append("retrieve-submitted" if "nation.africa" in url else "retrieve-candidate")
            if "nation.africa" in url:
                return RetrievedPage(
                    requested_url=url,
                    text="Schools in Nyeri County will remain closed tomorrow, says the article.",
                    title="Schools closure notice",
                    canonical_url="https://nation.africa/schools-close",
                    author="Example Reporter",
                    published_at="2026-10-02",
                )
            return RetrievedPage(
                requested_url=url,
                text="The official county notice confirms the school closure tomorrow.",
            )

        def search(**_kwargs):
            return ExaSearchResponse(
                request_id="mock-search",
                results=[
                    {
                        "url": "https://education.go.ke/notices/schools-close",
                        "title": "Official schools notice",
                        "author": "Ministry of Education",
                    },
                    {
                        "url": "https://EDUCATION.GO.KE/notices/schools-close/?utm_medium=email#top",
                        "title": "Duplicate official result",
                    },
                ],
            )

        with (
            patch("app.modules.investigations.orchestrator.get_settings", return_value=settings),
            patch("app.modules.investigations.orchestrator.ModelGateway", FakeGateway),
            patch("app.modules.investigations.orchestrator.read_public_page", side_effect=retrieve),
            patch("app.modules.investigations.orchestrator.search_exa", side_effect=search),
            patch(
                "app.modules.investigations.orchestrator.put_private_object",
                side_effect=lambda *, key, data, content_type: object_store.__setitem__(key, data),
            ),
            patch(
                "app.modules.investigations.orchestrator.get_private_object",
                side_effect=lambda *, key: object_store[key],
            ),
        ):
            result = process_investigation(session, job_id=job.id)

        self.assertEqual(result, "complete")
        self.assertEqual(calls, ["retrieve-submitted", "extract", "retrieve-candidate", "reason"])
        submitted = session.scalar(select(Source).where(Source.discovery_method == "SUBMITTED_URL"))
        self.assertIsNotNone(submitted)
        self.assertEqual(submitted.source_role, "SUBMITTED")
        self.assertEqual(submitted.source_type, "NEWS")
        self.assertEqual(submitted.title, "Schools closure notice")
        self.assertEqual(submitted.author, "Example Reporter")
        self.assertEqual(submitted.canonical_url, "https://nation.africa/schools-close")
        self.assertEqual(submitted.published_at, "2026-10-02")
        self.assertEqual(
            session.scalar(
                select(func.count()).select_from(Evidence).where(Evidence.source_id == submitted.id)
            ),
            0,
        )
        usage = session.scalar(
            select(InvestigationUsage).where(
                InvestigationUsage.investigation_id == investigation.id
            )
        )
        self.assertEqual(usage.sources_retrieved, 2)
        session.close()

    def test_source_relationships_capture_explicit_citations_and_duplicate_content(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = Session(engine, expire_on_commit=False)
        investigation = InvestigationService(session).create(
            owner_id=OWNER_ID,
            content="A source relationship test.",
            input_type=InputType.TEXT,
            idempotency_key="source-relationships",
        )
        page_text = "This report republishes information from [the original](https://source.example/original)."
        first = Source(
            investigation_id=investigation.id,
            url="https://report.example/copy",
            domain="report.example",
            content_sha256="same-content-hash",
            retrieval_status="RETRIEVED",
        )
        second = Source(
            investigation_id=investigation.id,
            url="https://source.example/original",
            domain="source.example",
            content_sha256="same-content-hash",
            retrieval_status="RETRIEVED",
        )
        session.add_all([first, second])
        session.commit()

        _detect_source_relationships(
            session,
            investigation,
            {first.id: page_text, second.id: page_text},
        )

        found = list(
            session.scalars(
                select(SourceRelationship).where(
                    SourceRelationship.investigation_id == investigation.id
                )
            )
        )
        self.assertIn("CITES", {item.relationship_type for item in found})
        self.assertIn("DUPLICATES", {item.relationship_type for item in found})
        self.assertEqual(second.source_role, "DERIVATIVE")
        session.close()

    def test_duplicate_source_content_does_not_create_independent_evidence(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = Session(engine, expire_on_commit=False)
        investigation = InvestigationService(session).create(
            owner_id=OWNER_ID,
            content="A source independence test.",
            input_type=InputType.TEXT,
            idempotency_key="duplicate-source-evidence",
        )
        claim = Claim(
            investigation_id=investigation.id,
            text="Schools in Nyeri County will remain closed tomorrow.",
            normalized_text="schools in nyeri county will remain closed tomorrow",
            claim_type="CHECKABLE_EVENT",
        )
        first = Source(
            investigation_id=investigation.id,
            url="https://news.example/first",
            domain="news.example",
            content_sha256="matching-content",
            retrieval_status="RETRIEVED",
        )
        second = Source(
            investigation_id=investigation.id,
            url="https://mirror.example/copy",
            domain="mirror.example",
            content_sha256="matching-content",
            retrieval_status="RETRIEVED",
        )
        session.add_all([claim, first, second])
        session.commit()
        page = "Schools in Nyeri County will remain closed tomorrow, according to the notice."
        with patch(
            "app.modules.investigations.orchestrator.get_settings",
            return_value=SimpleNamespace(
                max_source_chars_per_source=6000, max_total_evidence_chars=24000
            ),
        ):
            _detect_source_relationships(session, investigation, {first.id: page, second.id: page})
            _persist_evidence(session, investigation, {first.id: page, second.id: page})
        self.assertEqual(
            session.scalar(
                select(func.count())
                .select_from(Evidence)
                .where(Evidence.investigation_id == investigation.id)
            ),
            1,
        )
        self.assertEqual(second.source_role, "DERIVATIVE")
        session.close()

    def test_support_and_contradiction_are_both_preserved_and_no_evidence_downgrades_support(
        self,
    ) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = Session(engine, expire_on_commit=False)
        investigation = InvestigationService(session).create(
            owner_id=OWNER_ID,
            content="A conflicting evidence test.",
            input_type=InputType.TEXT,
            idempotency_key="conflicting-source-evidence",
        )
        claim = Claim(
            investigation_id=investigation.id,
            text="A factual claim to review.",
            normalized_text="a factual claim to review",
        )
        session.add(claim)
        session.flush()
        evidence_items = []
        for index in range(2):
            source = Source(
                investigation_id=investigation.id,
                url=f"https://source{index}.example/report",
                domain=f"source{index}.example",
                source_type="NEWS",
                retrieval_status="RETRIEVED",
            )
            session.add(source)
            session.flush()
            evidence = Evidence(
                investigation_id=investigation.id,
                source_id=source.id,
                content=f"Retrieved passage {index} describes the event.",
                method="TEST_FIXTURE",
            )
            session.add(evidence)
            session.flush()
            session.add(ClaimEvidence(claim_id=claim.id, evidence_id=evidence.id))
            evidence_items.append(evidence)
        session.commit()

        _persist_findings(
            session,
            investigation,
            EvidenceReasoning(
                findings=[
                    ReasonedFinding(
                        claim_id=str(claim.id),
                        status="PARTLY_TRUE",
                        statement="Evidence supports and contradicts different interpretations.",
                        evidence=[
                            {
                                "evidence_id": str(evidence_items[0].id),
                                "relationship": "SUPPORTS",
                            },
                            {
                                "evidence_id": str(evidence_items[1].id),
                                "relationship": "CONTRADICTS",
                            },
                        ],
                                evidence_confidence="MEDIUM",
            confidence_rationale="Mock finding includes its fixture evidence for contract testing.",
)
                ]
            ),
        )
        finding = session.scalar(select(Finding).where(Finding.claim_id == claim.id))
        self.assertEqual(finding.status, "PARTLY_TRUE")
        self.assertIn("supports and contradicts", finding.statement)
        self.assertEqual(
            {
                item.relationship
                for item in session.scalars(
                    select(ClaimEvidence).where(ClaimEvidence.claim_id == claim.id)
                )
            },
            {"SUPPORTS", "CONTRADICTS"},
        )
        self.assertEqual(
            session.scalar(
                select(func.count())
                .select_from(FindingEvidence)
                .where(FindingEvidence.finding_id == finding.id)
            ),
            2,
        )
        session.close()

    def test_registry_membership_alone_cannot_support_a_finding(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = Session(engine, expire_on_commit=False)
        investigation = InvestigationService(session).create(
            owner_id=OWNER_ID,
            content="A registry-only source test.",
            input_type=InputType.TEXT,
            idempotency_key="registry-is-not-proof",
        )
        claim = Claim(
            investigation_id=investigation.id,
            text="The official statistics claim.",
            normalized_text="the official statistics claim",
        )
        session.add(claim)
        session.commit()
        _persist_findings(
            session,
            investigation,
            EvidenceReasoning(
                findings=[
                    ReasonedFinding(
                        claim_id=str(claim.id),
                        status="SUPPORTED",
                        statement="A trusted registry domain says it is true.",
                                evidence_confidence="MEDIUM",
            confidence_rationale="Mock finding includes its fixture evidence for contract testing.",
)
                ]
            ),
        )
        finding = session.scalar(select(Finding).where(Finding.claim_id == claim.id))
        self.assertEqual(finding.status, "INSUFFICIENT_EVIDENCE")
        self.assertEqual(
            session.scalar(
                select(func.count())
                .select_from(FindingEvidence)
                .where(FindingEvidence.finding_id == finding.id)
            ),
            0,
        )
        session.close()

    def test_submitted_page_retrieval_failure_is_persisted_without_fabricated_claims(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = Session(engine, expire_on_commit=False)
        investigation = InvestigationService(session).create(
            owner_id=OWNER_ID,
            content="https://news.example/missing-story",
            input_type=InputType.URL,
            idempotency_key="url-reader-failure",
        )
        job = session.scalar(
            select(ProcessingJob).where(ProcessingJob.investigation_id == investigation.id)
        )
        settings = SimpleNamespace(
            exa_api_key=None,
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
        with (
            patch("app.modules.investigations.orchestrator.get_settings", return_value=settings),
            patch(
                "app.modules.investigations.orchestrator.read_public_page",
                side_effect=SourceRetrievalError("not found"),
            ),
            patch("app.modules.investigations.orchestrator.ModelGateway") as gateway,
        ):
            result = process_investigation(session, job_id=job.id)
        source = session.scalar(select(Source).where(Source.investigation_id == investigation.id))
        self.assertEqual(result, "complete")
        self.assertEqual(source.retrieval_status, "FAILED")
        self.assertTrue(source.retrieval_failure_reason)
        self.assertEqual(session.scalar(select(func.count()).select_from(Claim)), 0)
        self.assertTrue(
            any(
                (trace.query or "").startswith("site:news.example missing story")
                for trace in session.scalars(
                    select(SearchTrace).where(SearchTrace.investigation_id == investigation.id)
                )
            )
        )
        gateway.assert_not_called()
        session.close()

    def test_model_failure_on_url_flow_preserves_submitted_source_claim_and_evidence(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        event.listen(
            engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON")
        )
        Base.metadata.create_all(engine)
        session = Session(engine, expire_on_commit=False)
        investigation = InvestigationService(session).create(
            owner_id=OWNER_ID,
            content="https://nation.africa/schools-close",
            input_type=InputType.URL,
            idempotency_key="url-model-failure-preserves-work",
        )
        job = session.scalar(
            select(ProcessingJob).where(ProcessingJob.investigation_id == investigation.id)
        )
        submitted = Source(
            investigation_id=investigation.id,
            url="https://nation.africa/schools-close",
            domain="nation.africa",
            source_type="NEWS",
            source_role="SUBMITTED",
            discovery_method="SUBMITTED_URL",
            retrieval_status="RETRIEVED",
            content_storage_key="submitted-page",
        )
        candidate = Source(
            investigation_id=investigation.id,
            url="https://education.go.ke/notices/schools-close",
            domain="education.go.ke",
            source_type="OFFICIAL",
            retrieval_status="RETRIEVED",
            content_storage_key="candidate-page",
        )
        claim = Claim(
            investigation_id=investigation.id,
            text="Schools in Nyeri County will remain closed tomorrow.",
            normalized_text="schools in nyeri county will remain closed tomorrow",
            claim_type="CHECKABLE_EVENT",
        )
        session.add_all([submitted, candidate, claim])
        session.flush()
        evidence = Evidence(
            investigation_id=investigation.id,
            source_id=candidate.id,
            content="The official notice confirms schools will remain closed tomorrow.",
            method="DETERMINISTIC_TERM_OVERLAP_EXCERPT",
        )
        session.add(evidence)
        session.flush()
        session.add_all(
            [
                ClaimEvidence(claim_id=claim.id, evidence_id=evidence.id),
                SearchTrace(
                    investigation_id=investigation.id,
                    provider="EXA",
                    action="search",
                    query="official school notice",
                    sources=[],
                    citations=[],
                ),
            ]
        )
        usage = session.scalar(
            select(InvestigationUsage).where(
                InvestigationUsage.investigation_id == investigation.id
            )
        )
        usage.sources_retrieved = 2
        investigation.status = InvestigationStatus.NEEDS_REVIEW
        investigation.current_stage = "NEEDS_REVIEW"
        job.status = "BLOCKED"
        job.stage = "NEEDS_REVIEW"
        session.commit()
        objects = {
            "submitted-page": b"The article says schools will close tomorrow.",
            "candidate-page": b"The official notice confirms schools will remain closed tomorrow.",
        }

        class FailingGateway:
            def extract_claims_and_queries(self, **_kwargs):
                raise AssertionError("persisted claims and plans should be reused")

            def reason_about_evidence(self, **_kwargs):
                raise ModelInvocationFailed(
                    provider="openai",
                    model="mock-luna",
                    category=FailureCategory.PROVIDER_UNAVAILABLE,
                )

        settings = SimpleNamespace(
            exa_api_key=None,
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
        with (
            patch("app.modules.investigations.orchestrator.get_settings", return_value=settings),
            patch("app.modules.investigations.orchestrator.ModelGateway", FailingGateway),
            patch(
                "app.modules.investigations.orchestrator.get_private_object",
                side_effect=lambda *, key: objects[key],
            ),
        ):
            result = process_investigation(session, job_id=job.id)
        self.assertEqual(result, "needs_review")
        self.assertEqual(
            session.scalar(
                select(func.count())
                .select_from(Source)
                .where(Source.investigation_id == investigation.id)
            ),
            2,
        )
        self.assertEqual(
            session.scalar(
                select(func.count())
                .select_from(Claim)
                .where(Claim.investigation_id == investigation.id)
            ),
            1,
        )
        self.assertEqual(
            session.scalar(
                select(func.count())
                .select_from(Evidence)
                .where(Evidence.investigation_id == investigation.id)
            ),
            1,
        )
        session.close()


if __name__ == "__main__":
    unittest.main()
