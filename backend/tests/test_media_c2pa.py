from __future__ import annotations

import base64
import hashlib
import io
import json
import subprocess
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.investigation import InputType
from app.modules.investigations.investigator import EvidenceReasoning, ExplanationSentence, ReasonedFinding
from app.modules.investigations.media.analyzers import analyze_image_assets
from app.modules.investigations.media.provenance import (
    ANALYZER_ID,
    ANALYZER_VERSION,
    inspect_c2pa_bounded,
    inspect_c2pa_bytes,
    public_provenance_summary,
)
from app.modules.investigations.models import (
    Claim,
    ClaimEvidence,
    Evidence,
    Finding,
    MediaAnalysisRun,
    MediaAsset,
)
from app.modules.investigations.orchestrator import (
    _evidence_packet,
    _has_claim_linked_evidence,
    _persist_findings,
)
from app.modules.investigations.routes import get_investigation_results
from app.modules.investigations.service import InvestigationService

_PNG_WITHOUT_CREDENTIALS = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/pR8AAAAASUVORK5CYII="
)
_C2PA_EKU = x509.ObjectIdentifier("1.3.6.1.5.5.7.3.36")


def _image_fixture(codec: str) -> bytes:
    return subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=red:s=8x8",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            codec,
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    ).stdout


def _signed_ai_fixture() -> tuple[bytes, str]:
    """Create a locally signed test image using the official c2pa-python SDK."""
    from c2pa import Builder, C2paSigningAlg, Context, Signer

    now = datetime.now(UTC)
    root_key = ec.generate_private_key(ec.SECP256R1())
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Agent 0 test root")])
    root = (
        x509.CertificateBuilder()
        .subject_name(root_name)
        .issuer_name(root_name)
        .public_key(root_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(root_key.public_key()), critical=False
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(root_key, hashes.SHA256())
    )
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Agent 0 fixture signer")])
    leaf = (
        x509.CertificateBuilder()
        .subject_name(leaf_name)
        .issuer_name(root_name)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=90))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([_C2PA_EKU, ExtendedKeyUsageOID.EMAIL_PROTECTION]),
            critical=False,
        )
        .sign(root_key, hashes.SHA256())
    )
    root_pem = root.public_bytes(serialization.Encoding.PEM).decode()
    cert_chain = leaf.public_bytes(serialization.Encoding.PEM).decode() + root_pem

    def sign(payload: bytes) -> bytes:
        return leaf_key.sign(payload, ec.ECDSA(hashes.SHA256()))

    manifest = {
        "claim_generator_info": [{"name": "Agent 0 test builder", "version": "1"}],
        "format": "image/png",
        "assertions": [
            {
                "label": "c2pa.actions",
                "data": {
                    "actions": [
                        {
                            "action": "c2pa.created",
                            "digitalSourceType": (
                                "http://cv.iptc.org/newscodes/digitalsourcetype/"
                                "trainedAlgorithmicMedia"
                            ),
                        }
                    ]
                },
            },
            {
                "label": "org.example.privateFixture",
                "data": {
                    "user_id": "PRIVATE_C2PA_USER_7f3a",
                    "embedded_url": "https://private.example/credential?token=fixture",
                    "certificate": "PRIVATE_FIXTURE_CERTIFICATE_BLOB",
                },
            },
        ],
    }
    source = _image_fixture("png")
    signed = io.BytesIO()
    with Context.from_dict(
        {"verify": {"remote_manifest_fetch": False, "ocsp_fetch": False}}
    ) as context:
        with Signer.from_callback(sign, C2paSigningAlg.ES256, cert_chain) as signer:
            with Builder(manifest, context) as builder:
                builder.sign(signer, "image/png", io.BytesIO(source), signed)
    return signed.getvalue(), root_pem


@pytest.fixture(scope="module")
def signed_fixture() -> tuple[bytes, str]:
    return _signed_ai_fixture()


def test_no_credentials_is_not_present_and_not_an_authenticity_claim() -> None:
    result = inspect_c2pa_bytes(_PNG_WITHOUT_CREDENTIALS, "image/png", uuid4())

    assert result["state"] == "NOT_PRESENT"
    assert result["manifest_present"] is False
    assert "synthetic" not in json.dumps(result).lower()
    assert "authentic" not in json.dumps(result).lower()


@pytest.mark.parametrize(
    ("codec", "mime_type"),
    [("mjpeg", "image/jpeg"), ("png", "image/png"), ("libwebp", "image/webp")],
)
def test_m1_image_formats_are_supported_for_manifest_absence(codec: str, mime_type: str) -> None:
    result = inspect_c2pa_bytes(_image_fixture(codec), mime_type, uuid4())

    assert result["state"] == "NOT_PRESENT"


def test_signed_fixture_validates_and_ai_disclosure_is_a_declaration(
    signed_fixture: tuple[bytes, str],
) -> None:
    signed, root_pem = signed_fixture
    result = inspect_c2pa_bytes(signed, "image/png", uuid4(), trust_anchors=root_pem)
    serialized = json.dumps(result, sort_keys=True)

    assert result["state"] == "VALID"
    assert result["manifest_present"] is True
    assert result["signature_state"] == "VALIDATED"
    assert result["ai_disclosures"] == ["GENERATIVE_AI_CREATION_DECLARED"]
    assert "declared" in serialized.lower()
    assert "detected" not in serialized.lower()
    assert "fake" not in serialized.lower()
    assert "-----BEGIN CERTIFICATE-----" not in serialized
    assert "Agent 0 fixture signer" in serialized
    assert "PRIVATE_C2PA_USER_7f3a" not in serialized
    assert "private.example" not in serialized
    assert "PRIVATE_FIXTURE_CERTIFICATE_BLOB" not in serialized
    public = json.dumps(public_provenance_summary(result), sort_keys=True)
    assert "Agent 0 fixture signer" not in public


def test_tampered_manifest_is_not_reported_valid(signed_fixture: tuple[bytes, str]) -> None:
    signed, root_pem = signed_fixture
    tampered = bytearray(signed)
    tampered[-32] ^= 0x01
    result = inspect_c2pa_bytes(bytes(tampered), "image/png", uuid4(), trust_anchors=root_pem)

    assert result["manifest_present"] is True
    assert result["state"] in {"INVALID", "INDETERMINATE"}
    assert result["state"] != "VALID"


def test_bounded_reader_runs_in_child_process_with_offline_policy() -> None:
    result = inspect_c2pa_bounded(_PNG_WITHOUT_CREDENTIALS, "image/png", uuid4())

    assert result["state"] == "NOT_PRESENT"


def test_bounded_reader_returns_error_when_timeout_is_exhausted() -> None:
    with patch("app.modules.investigations.media.provenance.ANALYSIS_TIMEOUT_SECONDS", 0):
        result = inspect_c2pa_bounded(_PNG_WITHOUT_CREDENTIALS, "image/png", uuid4())

    assert result["state"] == "ERROR"
    assert any("time limit" in item for item in result["limitations"])


def test_c2pa_analysis_uses_original_and_retry_reuses_run(
    signed_fixture: tuple[bytes, str],
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(
        engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON")
    )
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    signed, _ = signed_fixture
    normalized_bytes = _PNG_WITHOUT_CREDENTIALS
    original_id = UUID("00000000-0000-4000-8000-000000000011")
    try:
        investigation = InvestigationService(session).create(
            owner_id=UUID("00000000-0000-4000-8000-000000000001"),
            content="Inspect image provenance",
            input_type=InputType.IMAGE,
            idempotency_key=f"c2pa-{uuid4()}",
        )
        original = MediaAsset(
            id=original_id,
            investigation_id=investigation.id,
            asset_role="ORIGINAL",
            storage_key=f"private/{uuid4().hex}",
            media_type="IMAGE",
            mime_type="image/png",
            size_bytes=len(signed),
            sha256=hashlib.sha256(signed).hexdigest(),
            metadata_json={},
        )
        session.add(original)
        session.flush()
        normalized = MediaAsset(
            investigation_id=investigation.id,
            parent_asset_id=original.id,
            asset_role="DERIVED",
            artifact_type="NORMALIZED_IMAGE",
            transformation_version="image-normalization-v1",
            transformation_metadata={"operation": "normalize_image"},
            storage_key=f"private-derived/{original.id}/normalized.png",
            media_type="IMAGE",
            mime_type="image/png",
            size_bytes=len(normalized_bytes),
            sha256=hashlib.sha256(normalized_bytes).hexdigest(),
            metadata_json={},
        )
        session.add(normalized)
        session.commit()
        observation = {
            "analyzer_id": ANALYZER_ID,
            "analyzer_version": ANALYZER_VERSION,
            "asset_id": str(original.id),
            "state": "VALID",
            "manifest_present": True,
            "validation_state": "Trusted",
            "signature_state": "VALIDATED",
            "signer_identity": "Fixture Organization",
            "generator": {"name": "Fixture Editor", "version": "1"},
            "actions": [
                {"action": "c2pa.created", "digital_source_type": "trainedAlgorithmicMedia"}
            ],
            "actions_truncated": False,
            "ai_disclosures": ["GENERATIVE_AI_CREATION_DECLARED"],
            "ingredient_count": 0,
            "ingredients_truncated": False,
            "validation_codes": ["claimSignature.validated"],
            "limitations": ["C2PA credentials do not establish factual truth."],
        }

        def inspect_original(data: bytes, mime_type: str, asset_id: UUID) -> dict[str, object]:
            assert data == signed
            assert mime_type == "image/png"
            assert asset_id == original.id
            return observation

        with patch(
            "app.modules.investigations.media.analyzers.inspect_c2pa_bounded",
            side_effect=inspect_original,
        ):
            analyze_image_assets(
                session,
                investigation_id=investigation.id,
                original=original,
                normalized=normalized,
                original_loader=lambda: signed,
                normalized_loader=lambda: normalized_bytes,
            )

        c2pa_run = session.scalar(
            select(MediaAnalysisRun).where(MediaAnalysisRun.analyzer_id == "C2PA")
        )
        c2pa_evidence = session.scalar(
            select(Evidence).where(Evidence.method == "MEDIA_PROVENANCE")
        )
        assert c2pa_run is not None and c2pa_run.status == "COMPLETED"
        assert c2pa_run.media_asset_id == original.id
        assert c2pa_run.observations_json["asset_id"] == str(original.id)
        assert c2pa_evidence is not None
        assert c2pa_evidence.media_asset_id == original.id
        assert c2pa_evidence.media_analysis_run_id == c2pa_run.id
        assert "declare generative AI involvement" in c2pa_evidence.content
        assert "detected" not in c2pa_evidence.content.lower()
        assert "fake" not in c2pa_evidence.content.lower()

        claim = Claim(
            investigation_id=investigation.id,
            text="This image depicts an event.",
            normalized_text="this image depicts an event",
            claim_type="MEDIA_CLAIM",
        )
        session.add(claim)
        session.flush()
        session.add(
            ClaimEvidence(claim_id=claim.id, evidence_id=c2pa_evidence.id, relationship="UNKNOWN")
        )
        session.commit()
        assert _has_claim_linked_evidence(session, investigation) is True
        packet = json.loads(_evidence_packet(session, investigation))
        assert any(item["kind"] == "MEDIA_PROVENANCE" for item in packet["evidence"])
        _persist_findings(
            session,
            investigation,
            EvidenceReasoning(
                findings=[
                    ReasonedFinding(
                        claim_id=str(claim.id),
                        status="SUPPORTED",
                        statement="This image is real.",
                        explanation=[ExplanationSentence(sentence="The credentials describe provenance, not whether the event is real.", evidence_ids=[str(c2pa_evidence.id)])],
                        evidence=[
                            {"evidence_id": str(c2pa_evidence.id), "relationship": "SUPPORTS"}
                        ],
                                evidence_confidence="MEDIUM",
            confidence_rationale="Mock finding includes its fixture evidence for contract testing.",
)
                ]
            ),
        )
        finding = session.scalar(select(Finding).where(Finding.claim_id == claim.id))
        assert finding.status == "INSUFFICIENT_EVIDENCE"
        assert finding.statement != "This image is real."
        declaration_claim = Claim(
            investigation_id=investigation.id,
            text="Content Credentials declare generative AI involvement.",
            normalized_text="content credentials declare generative ai involvement",
            claim_type="CHECKABLE_EVENT",
        )
        session.add(declaration_claim)
        session.flush()
        session.add(
            ClaimEvidence(
                claim_id=declaration_claim.id,
                evidence_id=c2pa_evidence.id,
                relationship="UNKNOWN",
            )
        )
        session.commit()
        _persist_findings(
            session,
            investigation,
            EvidenceReasoning(
                findings=[
                    ReasonedFinding(
                        claim_id=str(declaration_claim.id),
                        status="SUPPORTED",
                        statement="The image is AI-generated.",
                        explanation=[ExplanationSentence(sentence="The credentials declare generative AI involvement.", evidence_ids=[str(c2pa_evidence.id)])],
                        evidence=[
                            {"evidence_id": str(c2pa_evidence.id), "relationship": "SUPPORTS"}
                        ],
                                evidence_confidence="MEDIUM",
            confidence_rationale="Mock finding includes its fixture evidence for contract testing.",
)
                ]
            ),
        )
        declaration_finding = session.scalar(
            select(Finding).where(Finding.claim_id == declaration_claim.id)
        )
        assert declaration_finding.status == "INSUFFICIENT_EVIDENCE"
        assert declaration_finding.statement == "The credentials declare generative AI involvement."
        result = get_investigation_results(investigation.id, session)
        c2pa_result = next(
            item for item in result["evidence"] if item["method"] == "MEDIA_PROVENANCE"
        )
        assert c2pa_result["provenance"]["status"] == "VALID"
        assert c2pa_result["provenance"]["credentials_present"] is True
        assert c2pa_result["provenance"]["signer_identity_available"] is True
        result_json = json.dumps(result, sort_keys=True)
        assert "Fixture Organization" not in result_json
        assert "-----BEGIN CERTIFICATE-----" not in result_json
        assert "storage_key" not in result_json
        assert "raw_manifest" not in result_json
        assert "MEDIA_PROVENANCE" in result_json

        with patch(
            "app.modules.investigations.media.analyzers.inspect_c2pa_bounded",
            side_effect=AssertionError("completed C2PA run should be reused"),
        ):
            analyze_image_assets(
                session,
                investigation_id=investigation.id,
                original=original,
                normalized=normalized,
                original_loader=lambda: (_ for _ in ()).throw(
                    AssertionError("run should be cached")
                ),
                normalized_loader=lambda: (_ for _ in ()).throw(
                    AssertionError("run should be cached")
                ),
            )
        assert len(list(session.scalars(select(MediaAnalysisRun)))) == 3
        assert (
            len(
                list(
                    session.scalars(
                        select(Evidence).where(Evidence.media_analysis_run_id.is_not(None))
                    )
                )
            )
            == 3
        )
    finally:
        session.close()


def test_c2pa_error_is_persisted_without_removing_other_m2_observations() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(
        engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON")
    )
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        investigation = InvestigationService(session).create(
            owner_id=UUID("00000000-0000-4000-8000-000000000001"),
            content="Inspect image provenance",
            input_type=InputType.IMAGE,
            idempotency_key=f"c2pa-error-{uuid4()}",
        )
        image = _image_fixture("png")
        original = MediaAsset(
            investigation_id=investigation.id,
            storage_key=f"private/{uuid4().hex}",
            media_type="IMAGE",
            mime_type="image/png",
            size_bytes=len(image),
            sha256=hashlib.sha256(image).hexdigest(),
            metadata_json={},
        )
        session.add(original)
        session.flush()
        normalized = MediaAsset(
            investigation_id=investigation.id,
            parent_asset_id=original.id,
            asset_role="DERIVED",
            artifact_type="NORMALIZED_IMAGE",
            transformation_version="image-normalization-v1",
            storage_key=f"private-derived/{original.id}/normalized.png",
            media_type="IMAGE",
            mime_type="image/png",
            size_bytes=len(image),
            sha256=hashlib.sha256(image).hexdigest(),
            metadata_json={},
        )
        session.add(normalized)
        session.commit()
        with patch(
            "app.modules.investigations.media.analyzers.inspect_c2pa_bounded",
            side_effect=RuntimeError("untrusted SDK details must not escape"),
        ):
            analyze_image_assets(
                session,
                investigation_id=investigation.id,
                original=original,
                normalized=normalized,
                original_loader=lambda: image,
                normalized_loader=lambda: image,
            )
        runs = list(session.scalars(select(MediaAnalysisRun)))
        c2pa_run = next(run for run in runs if run.analyzer_id == "C2PA")
        assert c2pa_run.status == "FAILED"
        assert c2pa_run.observations_json["state"] == "ERROR"
        assert {run.analyzer_id for run in runs} == {"FILE_METADATA", "PERCEPTUAL_HASH", "C2PA"}
        evidence = session.scalar(
            select(Evidence).where(Evidence.media_analysis_run_id == c2pa_run.id)
        )
        assert evidence is not None and evidence.method == "MEDIA_PROVENANCE"
        assert "untrusted SDK details" not in evidence.content
        recovered = {
            **c2pa_run.observations_json,
            "state": "NOT_PRESENT",
            "manifest_present": False,
        }
        with patch(
            "app.modules.investigations.media.analyzers.inspect_c2pa_bounded",
            return_value=recovered,
        ):
            analyze_image_assets(
                session,
                investigation_id=investigation.id,
                original=original,
                normalized=normalized,
                original_loader=lambda: image,
                normalized_loader=lambda: image,
            )
        session.refresh(c2pa_run)
        assert c2pa_run.status == "COMPLETED"
        assert c2pa_run.observations_json["state"] == "NOT_PRESENT"
        assert len(list(session.scalars(select(MediaAnalysisRun)))) == 3
        assert (
            len(
                list(
                    session.scalars(
                        select(Evidence).where(Evidence.media_analysis_run_id.is_not(None))
                    )
                )
            )
            == 3
        )
    finally:
        session.close()
