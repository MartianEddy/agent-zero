import json
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.investigation import InputType
from app.modules.investigations.investigator import (
    EvidenceReasoning,
    ExplanationSentence,
    ReasonedFinding,
    VisualAnalysis,
    VisualObservation,
)
from app.modules.investigations.models import (
    Claim,
    ClaimEvidence,
    Evidence,
    Finding,
    FindingEvidence,
    MediaAsset,
    Source,
)
from app.modules.investigations.orchestrator import (
    _evidence_packet,
    _has_claim_linked_evidence,
    _link_unclaimed_media_evidence,
    _persist_findings,
    _persist_visual_observations,
)
from app.modules.investigations.routes import get_investigation_results
from app.modules.investigations.service import InvestigationService


class MediaEvidenceGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        event.listen(
            engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON")
        )
        Base.metadata.create_all(engine)
        self.session = Session(engine, expire_on_commit=False)
        self.investigation = InvestigationService(self.session).create(
            owner_id=UUID("00000000-0000-4000-8000-000000000001"),
            content="What does this image establish?",
            input_type=InputType.IMAGE,
            idempotency_key=f"media-evidence-{uuid4()}",
        )
        self.claim = Claim(
            investigation_id=self.investigation.id,
            text="The image shows a public demonstration.",
            normalized_text="the image shows a public demonstration",
            claim_type="MEDIA_CLAIM",
        )
        self.asset = MediaAsset(
            investigation_id=self.investigation.id,
            storage_key=f"private/{uuid4().hex}",
            media_type="IMAGE",
            mime_type="image/jpeg",
            size_bytes=1024,
            sha256="a" * 64,
            metadata_json={"original_filename": "private-name.jpg"},
        )
        self.source = Source(
            investigation_id=self.investigation.id,
            url="https://news.example/photo",
            title="Photo context",
            domain="news.example",
            source_type="NEWS",
        )
        self.session.add_all([self.claim, self.asset, self.source])
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def add_evidence(self, *, source: bool, media: bool, content: str = "Observation") -> Evidence:
        evidence = Evidence(
            investigation_id=self.investigation.id,
            source_id=self.source.id if source else None,
            media_asset_id=self.asset.id if media else None,
            content=content,
            method="MEDIA_METADATA" if media else "SOURCE_EXCERPT",
            limitations="Observation only.",
        )
        self.session.add(evidence)
        self.session.flush()
        self.session.add(
            ClaimEvidence(claim_id=self.claim.id, evidence_id=evidence.id, relationship="UNKNOWN")
        )
        self.session.commit()
        return evidence

    def packet(self) -> dict:
        packet = _evidence_packet(self.session, self.investigation)
        return json.loads(packet)

    def test_source_only_evidence_is_included_and_can_support_finding(self) -> None:
        evidence = self.add_evidence(source=True, media=False)
        packet_item = self.packet()["evidence"][0]
        self.assertEqual(packet_item["origin"]["source_id"], str(self.source.id))
        self.assertIsNone(packet_item["origin"]["media_asset_id"])
        self.persist_finding(evidence, "SUPPORTS", "SUPPORTED")

    def test_media_only_evidence_is_included_and_can_support_finding_when_related(self) -> None:
        evidence = self.add_evidence(source=False, media=True)
        evidence.method = "MEDIA_VISUAL_OBSERVATION"
        evidence.content = "The image visibly shows a public demonstration."
        self.session.commit()
        packet_item = self.packet()["evidence"][0]
        self.assertIsNone(packet_item["origin"]["source_id"])
        self.assertEqual(packet_item["origin"]["media_asset_id"], str(self.asset.id))
        self.assertEqual(packet_item["media_asset"]["id"], str(self.asset.id))
        self.persist_finding(evidence, "SUPPORTS", "SUPPORTED")

    def test_metadata_alone_cannot_support_a_factual_finding(self) -> None:
        evidence = self.add_evidence(source=False, media=True)
        self.persist_finding(evidence, "SUPPORTS", "SUPPORTED")
        finding = self.session.scalar(select(Finding).where(Finding.claim_id == self.claim.id))
        self.assertEqual(finding.status, "INSUFFICIENT_EVIDENCE")

    def test_mixed_origin_evidence_serializes_both_origins(self) -> None:
        self.add_evidence(source=True, media=True)
        packet_item = self.packet()["evidence"][0]
        self.assertEqual(packet_item["origin"]["source_id"], str(self.source.id))
        self.assertEqual(packet_item["origin"]["media_asset_id"], str(self.asset.id))

    def test_source_and_media_origins_each_satisfy_evidence_gate(self) -> None:
        self.assertFalse(_has_claim_linked_evidence(self.session, self.investigation))
        media_evidence = self.add_evidence(source=False, media=True)
        self.assertTrue(_has_claim_linked_evidence(self.session, self.investigation))
        self.session.delete(media_evidence)
        self.session.commit()
        source_evidence = self.add_evidence(source=True, media=False)
        self.assertTrue(_has_claim_linked_evidence(self.session, self.investigation))
        self.session.delete(source_evidence)
        self.session.commit()
        self.add_evidence(source=True, media=True)
        self.assertTrue(_has_claim_linked_evidence(self.session, self.investigation))

    def test_database_rejects_evidence_without_origin(self) -> None:
        evidence = Evidence(
            investigation_id=self.investigation.id,
            content="Orphan",
            method="TEST",
        )
        self.session.add(evidence)
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()

    def test_unlinked_media_observation_without_claim_overlap_stays_unlinked(self) -> None:
        evidence = Evidence(
            investigation_id=self.investigation.id,
            media_asset_id=self.asset.id,
            content="Image metadata was examined.",
            method="MEDIA_METADATA",
        )
        self.session.add(evidence)
        self.session.commit()
        _link_unclaimed_media_evidence(self.session, self.investigation)
        link = self.session.scalar(
            select(ClaimEvidence).where(ClaimEvidence.evidence_id == evidence.id)
        )
        self.assertIsNone(link)

    def test_media_packet_projection_is_bounded_private_and_preserves_sources(self) -> None:
        source = Evidence(
            investigation_id=self.investigation.id,
            source_id=self.source.id,
            content="Authoritative source supports the public demonstration date.",
            method="SOURCE_EXCERPT",
        )
        c2pa = Evidence(
            investigation_id=self.investigation.id,
            media_asset_id=self.asset.id,
            content=(
                "A locally validated C2PA manifest is present. "
                "Content Credentials declare generative AI involvement. PRIVATE_SIGNER "
                "https://private.example/certificate"
            ),
            method="MEDIA_PROVENANCE",
        )
        metadata = Evidence(
            investigation_id=self.investigation.id,
            media_asset_id=self.asset.id,
            content=(
                "Allowlisted technical metadata was present. Safe decoded fields: "
                '{"format":"jpeg","width":800,"height":600,"gps_present":true}. '
                "Analyzed original; GPS 1.2,3.4 SERIAL-SECRET"
            ),
            method="MEDIA_TECHNICAL_METADATA",
        )
        phash = Evidence(
            investigation_id=self.investigation.id,
            media_asset_id=self.asset.id,
            content="pHash c0ffee1234567890",
            method="MEDIA_FINGERPRINT",
        )
        rows = [source, c2pa, metadata, phash] + [
            Evidence(
                investigation_id=self.investigation.id,
                media_asset_id=self.asset.id,
                content="Structured visual observations " + ("x" * 1200),
                method="MEDIA_VISUAL_OBSERVATION",
            )
            for _ in range(10)
        ]
        self.session.add_all(rows)
        self.session.flush()
        self.session.add_all(
            [
                ClaimEvidence(claim_id=self.claim.id, evidence_id=row.id, relationship="UNKNOWN")
                for row in [source, c2pa, metadata, phash, *rows[4:]]
            ]
        )
        self.session.commit()
        packet_text = _evidence_packet(self.session, self.investigation)
        packet = json.loads(packet_text)
        media = [item for item in packet["evidence"] if item["media_asset_id"]]
        self.assertIn(str(source.id), [item["evidence_id"] for item in packet["evidence"]])
        self.assertLessEqual(sum(len(item["excerpt"]) for item in media), 6000)
        self.assertLessEqual(sum(len(item["excerpt"]) for item in packet["evidence"]), 24000)
        self.assertNotIn("MEDIA_FINGERPRINT", [item["kind"] for item in packet["evidence"]])
        for private in ("GPS", "1.2,3.4", "SERIAL-SECRET", "PRIVATE_SIGNER", "certificate"):
            self.assertNotIn(private, packet_text)
        self.assertIn("generative-AI", packet_text)

    def test_visual_observation_is_persisted_before_synthesis_and_failure_is_safe(self) -> None:
        normalized = MediaAsset(
            investigation_id=self.investigation.id,
            parent_asset_id=self.asset.id,
            asset_role="DERIVED",
            artifact_type="NORMALIZED_IMAGE",
            transformation_version="image-normalization-v1",
            storage_key=f"private-derived/{uuid4().hex}",
            media_type="IMAGE",
            mime_type="image/png",
            size_bytes=100,
            sha256="b" * 64,
            metadata_json={},
        )
        self.session.add(normalized)
        self.session.commit()

        class Gateway:
            def analyze_visual_content(inner, **kwargs):
                from app.modules.investigations.investigator import ModelRun

                return ModelRun(
                    output=VisualAnalysis(
                        observations=[
                            VisualObservation(
                                observation="A banner reads Public Demonstration",
                                confidence="MODERATE",
                                relevance="The claim concerns the demonstration.",
                            )
                        ]
                    ),
                    provider="openai",
                    model="mock-model",
                )

        _persist_visual_observations(
            self.session, self.investigation, [("image/png", b"normalized")], Gateway()
        )
        visual = self.session.scalar(
            select(Evidence).where(Evidence.method == "MEDIA_VISUAL_OBSERVATION")
        )
        self.assertIsNotNone(visual)
        self.assertIsNotNone(
            self.session.scalar(select(ClaimEvidence).where(ClaimEvidence.evidence_id == visual.id))
        )
        self.persist_finding_id(str(visual.id), "SUPPORTS", "SUPPORTED")
        self.assertIsNotNone(
            self.session.scalar(
                select(FindingEvidence).where(FindingEvidence.evidence_id == visual.id)
            )
        )

        class BrokenGateway:
            def analyze_visual_content(inner, **kwargs):
                raise RuntimeError("mock failure")

        second = InvestigationService(self.session).create(
            owner_id=UUID("00000000-0000-4000-8000-000000000001"),
            content="Another visual investigation",
            input_type=InputType.IMAGE,
            idempotency_key=f"visual-failure-{uuid4()}",
        )
        original = MediaAsset(
            investigation_id=second.id,
            asset_role="ORIGINAL",
            storage_key=f"private/{uuid4().hex}",
            media_type="IMAGE",
            mime_type="image/png",
            size_bytes=100,
            sha256="c" * 64,
            metadata_json={},
        )
        self.session.add(original)
        self.session.flush()
        child = MediaAsset(
            investigation_id=second.id,
            parent_asset_id=original.id,
            asset_role="DERIVED",
            artifact_type="NORMALIZED_IMAGE",
            transformation_version="image-normalization-v1",
            storage_key=f"private-derived/{uuid4().hex}",
            media_type="IMAGE",
            mime_type="image/png",
            size_bytes=100,
            sha256="d" * 64,
            metadata_json={},
        )
        self.session.add_all(
            [
                child,
                Claim(
                    investigation_id=second.id,
                    text="The image shows a public demonstration.",
                    normalized_text="the image shows a public demonstration",
                    claim_type="FACTUAL",
                ),
            ]
        )
        retained = Evidence(
            investigation_id=second.id,
            media_asset_id=original.id,
            content="A metadata observation remains persisted.",
            method="MEDIA_METADATA",
        )
        source = Source(
            investigation_id=second.id,
            url="https://official.example/report",
            title="Official report",
            domain="official.example",
            source_type="OFFICIAL",
        )
        self.session.add(source)
        self.session.flush()
        retained_source = Evidence(
            investigation_id=second.id,
            source_id=source.id,
            content="Source evidence remains persisted.",
            method="SOURCE_EXCERPT",
        )
        self.session.add_all([retained, retained_source])
        self.session.commit()
        _persist_visual_observations(
            self.session, second, [("image/png", b"normalized")], BrokenGateway()
        )
        self.assertIsNotNone(self.session.get(Evidence, retained.id))
        self.assertIsNotNone(self.session.get(Evidence, retained_source.id))

    def test_results_api_exposes_safe_media_origin_without_storage_metadata(self) -> None:
        evidence = self.add_evidence(source=False, media=True)
        with patch(
            "app.modules.investigations.routes.current_owner_id",
            return_value=self.investigation.owner_id,
        ):
            response = get_investigation_results(self.investigation.id, self.session)
        item = next(row for row in response["evidence"] if row["id"] == str(evidence.id))
        self.assertEqual(item["origin"]["media_asset_id"], str(self.asset.id))
        self.assertEqual(item["media_asset"]["media_type"], "IMAGE")
        self.assertNotIn("storage_key", item["media_asset"])
        self.assertNotIn("metadata_json", item["media_asset"])
        self.assertNotIn("private-name.jpg", json.dumps(item))
        serialized_asset = next(
            asset for asset in response["media_assets"] if asset["id"] == str(self.asset.id)
        )
        self.assertEqual(serialized_asset["role"], "ORIGINAL")
        self.assertNotIn("storage_key", serialized_asset)
        self.assertNotIn("sha256", serialized_asset)

    def test_unrelated_media_evidence_cannot_magically_support_claim(self) -> None:
        evidence = self.add_evidence(source=False, media=True)
        self.persist_finding(evidence, "UNKNOWN", "SUPPORTED")
        finding = self.session.scalar(select(Finding).where(Finding.claim_id == self.claim.id))
        self.assertEqual(finding.status, "INSUFFICIENT_EVIDENCE")

    def test_unknown_evidence_id_is_rejected(self) -> None:
        self.persist_finding_id(str(uuid4()), "SUPPORTS", "SUPPORTED")
        finding = self.session.scalar(select(Finding).where(Finding.claim_id == self.claim.id))
        self.assertEqual(finding.status, "INSUFFICIENT_EVIDENCE")
        self.assertIsNone(self.session.scalar(select(FindingEvidence.id)))

    def test_evidence_from_another_investigation_is_rejected(self) -> None:
        other = InvestigationService(self.session).create(
            owner_id=self.investigation.owner_id,
            content="Another investigation",
            input_type=InputType.TEXT,
            idempotency_key=f"other-{uuid4()}",
        )
        other_asset = MediaAsset(
            investigation_id=other.id,
            storage_key=f"private/{uuid4().hex}",
            media_type="IMAGE",
            mime_type="image/png",
            size_bytes=100,
            sha256="b" * 64,
            metadata_json={},
        )
        self.session.add(other_asset)
        self.session.flush()
        other_evidence = Evidence(
            investigation_id=other.id,
            media_asset_id=other_asset.id,
            content="Other case observation",
            method="MEDIA_METADATA",
        )
        self.session.add(other_evidence)
        self.session.flush()
        self.session.add(
            ClaimEvidence(
                claim_id=self.claim.id,
                evidence_id=other_evidence.id,
                relationship="UNKNOWN",
            )
        )
        self.session.commit()
        self.persist_finding(other_evidence, "SUPPORTS", "SUPPORTED")
        finding = self.session.scalar(select(Finding).where(Finding.claim_id == self.claim.id))
        self.assertEqual(finding.status, "INSUFFICIENT_EVIDENCE")
        self.assertIsNone(self.session.scalar(select(FindingEvidence.id)))

    def persist_finding(self, evidence: Evidence, relationship: str, status: str) -> None:
        self.persist_finding_id(str(evidence.id), relationship, status)

    def persist_finding_id(self, evidence_id: str, relationship: str, status: str) -> None:
        _persist_findings(
            self.session,
            self.investigation,
            EvidenceReasoning(
                findings=[
                    ReasonedFinding(
                        claim_id=str(self.claim.id),
                        status=status,
                        statement="Model proposed assessment.",
                        explanation=[ExplanationSentence(sentence="The evidence is relevant to this claim.", evidence_ids=[evidence_id])],
                        evidence=[{"evidence_id": evidence_id, "relationship": relationship}],
                                evidence_confidence="MEDIUM",
            confidence_rationale="Mock finding includes its fixture evidence for contract testing.",
)
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
