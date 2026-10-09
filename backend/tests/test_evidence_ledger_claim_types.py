"""Database-backed ledger contract integration for every accepted claim type."""

from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.investigation import InputType
from app.modules.investigations.investigator import (
    EvidenceAssessment,
    EvidenceReasoning,
    ExplanationSentence,
    ReasonedFinding,
)
from app.modules.investigations.models import Claim, ClaimEvidence, Evidence, Finding, Source
from app.modules.investigations.orchestrator import _persist_findings
from app.modules.investigations.service import InvestigationService

CLAIM_TYPES = (
    "SETTLED_FACT",
    "CHECKABLE_EVENT",
    "STATISTICAL",
    "MEDIA_CLAIM",
    "CONTESTED",
    "OPINION_OR_PREDICTION",
)


def test_mocked_evidence_packet_is_validated_for_each_claim_type():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        for index, claim_type in enumerate(CLAIM_TYPES):
            investigation = InvestigationService(session).create(
                owner_id=UUID("00000000-0000-4000-8000-000000000001"),
                content=f"Claim fixture {claim_type}",
                input_type=InputType.TEXT,
                idempotency_key=f"ledger-{claim_type}",
            )
            claim = Claim(
                investigation_id=investigation.id,
                text=f"Claim fixture {claim_type}",
                normalized_text=f"claim fixture {claim_type}".lower(),
                claim_type=claim_type,
            )
            session.add(claim)
            session.flush()
            evidence_ids = []
            for source_index, domain in enumerate(("nation.africa", "standardmedia.co.ke")):
                source = Source(
                    investigation_id=investigation.id,
                    url=f"https://{domain}/fixture-{index}-{source_index}",
                    domain=domain,
                    publisher=domain,
                    source_type="NEWS",
                    retrieval_status="RETRIEVED",
                )
                session.add(source)
                session.flush()
                evidence = Evidence(
                    investigation_id=investigation.id,
                    source_id=source.id,
                    content=f"Retrieved source {source_index} supports fixture {claim_type}.",
                    method="TEST_FIXTURE",
                    source_tier="REPUTABLE_REPORTING",
                    stance="SUPPORTS",
                    excerpt_start=0,
                    excerpt_end=len(
                        f"Retrieved source {source_index} supports fixture {claim_type}."
                    ),
                    independence_group_id=f"fixture-group-{source_index}",
                    retrieval_timestamp=source.retrieved_at,
                    run_id=investigation.id,
                    excerpt_validated=True,
                )
                session.add(evidence)
                session.flush()
                session.add(ClaimEvidence(claim_id=claim.id, evidence_id=evidence.id))
                evidence_ids.append(str(evidence.id))
            session.flush()
            _persist_findings(
                session,
                investigation,
                EvidenceReasoning(
                    findings=[
                        ReasonedFinding(
                            claim_id=str(claim.id),
                            status="SUPPORTED",
                            statement="The retrieved sources support the claim.",
                            evidence_confidence="MEDIUM",
                            confidence_rationale=(
                                "Two distinct retrieved fixture sources are linked."
                            ),
                            explanation=[
                                ExplanationSentence(
                                    sentence="The retrieved sources support the claim.",
                                    evidence_ids=evidence_ids,
                                )
                            ],
                            evidence=[
                                EvidenceAssessment(evidence_id=value, relationship="SUPPORTS")
                                for value in evidence_ids
                            ],
                        )
                    ]
                ),
            )
            result = session.scalar(select(Finding).where(Finding.claim_id == claim.id))
            assert result is not None
            assert result.explanation_json[0]["evidence_ids"] == evidence_ids
            expected = "NOT_VERIFIABLE" if claim_type == "OPINION_OR_PREDICTION" else "SUPPORTED"
            assert result.status == expected
