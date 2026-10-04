import asyncio
import hashlib
import json
import struct
import subprocess
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.investigation import InputType
from app.modules.investigations.image_safety import (
    ImageValidationError,
    normalize_image,
    validate_image,
)
from app.modules.investigations.media.analyzers import _evidence_content, analyze_image_assets
from app.modules.investigations.media.fingerprints import hamming_distance, perceptual_hash
from app.modules.investigations.media.metadata import extract_metadata
from app.modules.investigations.media_analysis import inspect_media
from app.modules.investigations.models import (
    Claim,
    ClaimEvidence,
    Evidence,
    MediaAnalysisRun,
    MediaAsset,
)
from app.modules.investigations.orchestrator import (
    _evidence_packet,
    _has_claim_linked_evidence,
    _load_or_inspect_media,
    _original_media_assets,
)
from app.modules.investigations.routes import create_media_investigation, get_investigation_results
from app.modules.investigations.service import InvestigationService


def fixture_image(
    fmt: str,
    width: int = 8,
    height: int = 6,
    *,
    source: str | None = None,
    quality: int | None = None,
) -> bytes:
    encoder = {"png": "png", "jpeg": "mjpeg", "webp": "libwebp"}[fmt]
    source = source or f"color=red:s={width}x{height}"
    command = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", source, "-frames:v", "1"]
    if quality is not None:
        command.extend(["-q:v", str(quality)])
    command.extend(["-f", "image2pipe", "-vcodec", encoder, "pipe:1"])
    result = subprocess.run(
        command,
        capture_output=True,
        check=True,
    )
    return result.stdout


def jpeg_with_allowlisted_exif() -> bytes:
    image = fixture_image("jpeg")
    root_offset = 8
    root_count = 8
    cursor = root_offset + 2 + root_count * 12 + 4
    strings: list[tuple[int, bytes]] = []
    offsets: dict[int, int] = {}
    for tag, value in (
        (0x010F, b"ExampleCam\x00"),
        (0x0110, b"ModelX\x00"),
        (0x0131, b"Editor 1\x00"),
        (0x0132, b"2025:10:02 12:34:56\x00"),
        (0xC7A1, b"DO-NOT-PROPAGATE\x00"),
    ):
        offsets[tag] = cursor
        strings.append((tag, value))
        cursor += len(value)
    exif_ifd_offset = cursor
    exif_ifd_end = exif_ifd_offset + 18
    original_time_offset = exif_ifd_end
    original_time = b"2025:10:02 12:34:56\x00"
    gps_ifd_offset = original_time_offset + len(original_time)

    def entry(tag: int, kind: int, count: int, value: int | bytes) -> bytes:
        if isinstance(value, int):
            value_field = struct.pack("<I", value)
        else:
            value_field = value.ljust(4, b"\x00")
        return struct.pack("<HHI", tag, kind, count) + value_field

    root = b"".join(
        [
            entry(0x010F, 2, len(b"ExampleCam\x00"), offsets[0x010F]),
            entry(0x0110, 2, len(b"ModelX\x00"), offsets[0x0110]),
            entry(0x0112, 3, 1, struct.pack("<H", 6)),
            entry(0x0131, 2, len(b"Editor 1\x00"), offsets[0x0131]),
            entry(0x0132, 2, len(b"2025:10:02 12:34:56\x00"), offsets[0x0132]),
            entry(0x8769, 4, 1, exif_ifd_offset),
            entry(0x8825, 4, 1, gps_ifd_offset),
            entry(0xC7A1, 2, len(b"DO-NOT-PROPAGATE\x00"), offsets[0xC7A1]),
        ]
    )
    exif_ifd = (
        struct.pack("<H", 1)
        + entry(0x9003, 2, len(original_time), original_time_offset)
        + b"\x00" * 4
    )
    gps_ifd = struct.pack("<H", 1) + entry(0x0002, 5, 3, gps_ifd_offset + 18) + b"\x00" * 4
    gps_coordinates = struct.pack("<IIIIII", 12, 1, 34, 1, 56, 1)
    tiff = (
        b"II*\x00"
        + struct.pack("<I", root_offset)
        + struct.pack("<H", root_count)
        + root
        + b"\x00" * 4
        + b"".join(value for _, value in strings)
        + exif_ifd
        + original_time
        + gps_ifd
        + gps_coordinates
    )
    exif_payload = b"Exif\x00\x00" + tiff
    app1 = b"\xff\xe1" + struct.pack(">H", len(exif_payload) + 2) + exif_payload
    return image[:2] + app1 + image[2:]


@pytest.mark.parametrize(
    ("fmt", "mime"), [("png", "image/png"), ("jpeg", "image/jpeg"), ("webp", "image/webp")]
)
def test_supported_images_are_decoded_with_dimensions(fmt: str, mime: str) -> None:
    data = fixture_image(fmt)
    result = validate_image(data, mime, 100)
    assert result["mime_type"] == mime
    assert (result["width"], result["height"]) == (8, 6)


def test_fake_image_and_mime_mismatch_are_rejected() -> None:
    with pytest.raises(ImageValidationError):
        validate_image(b"not an image", "image/png", 100)
    with pytest.raises(ImageValidationError) as error:
        validate_image(fixture_image("png"), "image/jpeg", 100)
    assert error.value.code == "INVALID_MEDIA"


def test_pixel_limit_and_boundary() -> None:
    image = fixture_image("png", 10, 10)
    assert validate_image(image, "image/png", 100)["width"] == 10
    with pytest.raises(ImageValidationError) as error:
        validate_image(image, "image/png", 99)
    assert error.value.code == "IMAGE_PIXEL_LIMIT_EXCEEDED"


def test_normalization_is_png_and_does_not_mutate_original() -> None:
    import hashlib

    original = fixture_image("jpeg")
    before = hashlib.sha256(original).hexdigest()
    normalized, metadata = normalize_image(original)
    assert normalized.startswith(b"\x89PNG\r\n\x1a\n")
    assert metadata["metadata"] == "not copied"
    assert hashlib.sha256(original).hexdigest() == before


def test_media_analysis_reuses_normalized_image() -> None:
    data = fixture_image("jpeg")
    metadata, images, limitations = inspect_media(
        data=data, media_type="IMAGE", mime_type="image/jpeg"
    )
    assert metadata["inspection"] == "metadata-stripped-analysis-copy"
    assert images[0][0] == "image/png"
    assert images[0][1].startswith(b"\x89PNG\r\n\x1a\n")
    assert limitations
    assert "separate metadata and C2PA analyzers" in limitations[0]
    assert "EXIF and C2PA provenance were not analyzed" not in limitations[0]


def test_fingerprints_are_deterministic_recompression_tolerant_and_distinguishable() -> None:
    source = "testsrc2=s=64x48"
    png = fixture_image("png", source=source)
    jpeg_high_quality = fixture_image("jpeg", source=source, quality=2)
    jpeg_low_quality = fixture_image("jpeg", source=source, quality=20)
    other = fixture_image("png", source="color=red:s=64x48")
    first = perceptual_hash(png)
    assert len(first) == 16
    assert first == perceptual_hash(png)
    assert hamming_distance(first, perceptual_hash(jpeg_high_quality)) <= 8
    assert hamming_distance(first, perceptual_hash(jpeg_low_quality)) <= 8
    assert hamming_distance(first, perceptual_hash(other)) > 8


def test_exact_sha256_is_the_identity_of_original_bytes() -> None:
    original = fixture_image("png")
    assert hashlib.sha256(original).hexdigest() == hashlib.sha256(bytes(original)).hexdigest()
    changed = original[:-1] + bytes([original[-1] ^ 1])
    assert hashlib.sha256(original).hexdigest() != hashlib.sha256(changed).hexdigest()


def test_metadata_allowlist_and_privacy_classification() -> None:
    plain = extract_metadata(fixture_image("png"))
    assert plain["exif_present"] is False
    assert plain["safe"]["gps_present"] is False
    assert plain["supported_exif_present"] is False
    absence_text, absence_limitation = _evidence_content(
        "FILE_METADATA", uuid4(), {**plain, "safe": plain["safe"]}
    )
    assert "No supported EXIF metadata was present" in absence_text
    assert "does not establish authenticity" in absence_limitation

    tagged = extract_metadata(jpeg_with_allowlisted_exif())
    assert tagged["safe"]["format"] == "jpeg"
    assert tagged["safe"]["orientation_present"] is True
    assert tagged["safe"]["gps_present"] is True
    assert tagged["internal"]["make"] == "ExampleCam"
    assert tagged["internal"]["model"] == "ModelX"
    assert tagged["internal"]["software"] == "Editor 1"
    assert tagged["sensitive"]["timestamps"] == [
        {"source_tag": "DateTime", "value": "2025:10:02 12:34:56"},
        {"source_tag": "DateTimeOriginal", "value": "2025:10:02 12:34:56"},
    ]
    serialized = json.dumps(tagged, sort_keys=True)
    assert "DO-NOT-PROPAGATE" not in serialized
    assert "GPSLatitude" not in serialized
    assert "12/1,34/1,56/1" not in serialized


def test_invalid_and_oversized_uploads_stop_before_investigation_or_storage(monkeypatch) -> None:
    async def call_upload(data: bytes, mime: str):
        class StubUpload:
            content_type = mime

            async def read(self, _size: int) -> bytes:
                return data

        upload = StubUpload()
        return await create_media_investigation(session=None, file=upload)

    monkeypatch.setattr(
        "app.modules.investigations.routes.current_owner_id",
        lambda: "00000000-0000-4000-8000-000000000001",
    )
    monkeypatch.setattr(
        "app.modules.investigations.routes.get_settings",
        lambda: SimpleNamespace(max_media_bytes=1000, max_image_pixels=20_000_000),
    )
    with (
        patch("app.modules.investigations.routes.put_private_object") as store,
        patch("app.modules.investigations.routes.InvestigationService.create") as create,
    ):
        with pytest.raises(HTTPException) as invalid:
            asyncio.run(call_upload(fixture_image("png")[:-4], "image/png"))
        assert invalid.value.status_code == 422
        with pytest.raises(HTTPException) as oversized:
            asyncio.run(call_upload(b"x" * 1001, "image/png"))
        assert oversized.value.status_code == 413
        store.assert_not_called()
        create.assert_not_called()


def test_storage_failure_does_not_create_investigation(monkeypatch) -> None:
    async def call_upload(data: bytes):
        class StubUpload:
            content_type = "image/png"

            async def read(self, _size: int) -> bytes:
                return data

        return await create_media_investigation(
            session=None,
            file=StubUpload(),
            prompt="A public landmark claim",
        )

    monkeypatch.setattr(
        "app.modules.investigations.routes.current_owner_id",
        lambda: "00000000-0000-4000-8000-000000000001",
    )
    monkeypatch.setattr(
        "app.modules.investigations.routes.get_settings",
        lambda: SimpleNamespace(max_media_bytes=25_000_000, max_image_pixels=20_000_000),
    )
    with (
        patch(
            "app.modules.investigations.routes.put_private_object",
            side_effect=RuntimeError("storage unavailable"),
        ) as store,
        patch("app.modules.investigations.routes.InvestigationService.create") as create,
        patch("app.modules.investigations.routes.delete_private_object") as delete,
    ):
        with pytest.raises(HTTPException) as failure:
            asyncio.run(call_upload(fixture_image("png")))

    assert failure.value.status_code == 503
    assert failure.value.detail == {
        "code": "STORAGE_FAILED",
        "message": "Media storage is unavailable",
    }
    store.assert_called_once()
    create.assert_not_called()
    delete.assert_called_once()


def test_normalized_derivative_lineage_and_retry_are_idempotent() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(
        engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON")
    )
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        investigation = InvestigationService(session).create(
            owner_id=UUID("00000000-0000-4000-8000-000000000001"),
            content="Inspect this image",
            input_type=InputType.IMAGE,
            idempotency_key=f"image-lineage-{uuid4()}",
        )
        original = fixture_image("png")
        asset = MediaAsset(
            investigation_id=investigation.id,
            storage_key=f"private/{uuid4().hex}",
            media_type="IMAGE",
            mime_type="image/png",
            size_bytes=len(original),
            sha256=hashlib.sha256(original).hexdigest(),
            metadata_json={},
        )
        session.add(asset)
        session.commit()
        normalized = fixture_image("png", 4, 4)
        with (
            patch(
                "app.modules.investigations.orchestrator.get_private_object", return_value=original
            ) as get,
            patch("app.modules.investigations.orchestrator.put_private_object") as put,
            patch(
                "app.modules.investigations.orchestrator.inspect_media",
                return_value=(
                    {"normalization": {"operation": "normalize_image"}},
                    [("image/png", normalized)],
                    [],
                ),
            ) as inspect,
        ):
            _load_or_inspect_media(session, investigation, [asset])
            _load_or_inspect_media(session, investigation, [asset])
        children = list(
            session.scalars(select(MediaAsset).where(MediaAsset.parent_asset_id == asset.id))
        )
        assert len(children) == 1
        child = children[0]
        assert child.asset_role == "DERIVED"
        assert child.artifact_type == "NORMALIZED_IMAGE"
        assert child.transformation_metadata == {"operation": "normalize_image"}
        assert child.storage_key != asset.storage_key
        assert _original_media_assets(session, investigation.id) == [asset]
        put.assert_called_once()
        inspect.assert_called_once()
        get.assert_called()
        assert asset.asset_role == "ORIGINAL"
    finally:
        session.close()


def test_analysis_runs_evidence_traceability_privacy_and_retry() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(
        engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON")
    )
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        investigation = InvestigationService(session).create(
            owner_id=UUID("00000000-0000-4000-8000-000000000001"),
            content="Inspect this image",
            input_type=InputType.IMAGE,
            idempotency_key=f"m2-analysis-{uuid4()}",
        )
        original_bytes = jpeg_with_allowlisted_exif()
        normalized_bytes = fixture_image("png", source="testsrc2=s=32x32")
        original = MediaAsset(
            investigation_id=investigation.id,
            storage_key=f"private/{uuid4().hex}",
            media_type="IMAGE",
            mime_type="image/jpeg",
            size_bytes=len(original_bytes),
            sha256=hashlib.sha256(original_bytes).hexdigest(),
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
        analyze_image_assets(
            session,
            investigation_id=investigation.id,
            original=original,
            normalized=normalized,
            original_loader=lambda: original_bytes,
            normalized_loader=lambda: normalized_bytes,
        )
        runs = list(
            session.scalars(
                select(MediaAnalysisRun).where(
                    MediaAnalysisRun.investigation_id == investigation.id
                )
            )
        )
        evidence = list(
            session.scalars(select(Evidence).where(Evidence.media_analysis_run_id.is_not(None)))
        )
        assert len(runs) == len(evidence) == 3
        metadata_run = next(run for run in runs if run.analyzer_id == "FILE_METADATA")
        phash_run = next(run for run in runs if run.analyzer_id == "PERCEPTUAL_HASH")
        c2pa_run = next(run for run in runs if run.analyzer_id == "C2PA")
        assert metadata_run.media_asset_id == original.id
        assert phash_run.media_asset_id == normalized.id
        assert c2pa_run.media_asset_id == original.id
        assert c2pa_run.observations_json["state"] == "NOT_PRESENT"
        assert phash_run.observations_json["analyzed_asset_id"] == str(normalized.id)
        assert phash_run.observations_json["algorithm"] == "pHash DCT"
        assert metadata_run.observations_json["internal"]["make"] == "ExampleCam"
        assert metadata_run.observations_json["safe"]["gps_present"] is True
        assert "12/1,34/1,56/1" not in json.dumps(metadata_run.observations_json)
        assert all(item.media_asset_id in {original.id, normalized.id} for item in evidence)
        assert original.sha256 == hashlib.sha256(original_bytes).hexdigest()
        assert normalized.sha256 == hashlib.sha256(normalized_bytes).hexdigest()
        for item in evidence:
            assert item.media_analysis_run_id is not None
            assert "ExampleCam" not in item.content
            assert "2025:10:02" not in item.content

        analyze_image_assets(
            session,
            investigation_id=investigation.id,
            original=original,
            normalized=normalized,
            original_loader=lambda: (_ for _ in ()).throw(AssertionError("cache miss")),
            normalized_loader=lambda: (_ for _ in ()).throw(AssertionError("cache miss")),
        )
        assert session.scalar(select(MediaAnalysisRun.id).where(MediaAnalysisRun.id == runs[0].id))
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

        claim = Claim(
            investigation_id=investigation.id,
            text="The image depicts an event in 2025.",
            normalized_text="the image depicts an event in 2025",
            claim_type="FACTUAL",
        )
        session.add(claim)
        session.flush()
        session.add_all(
            [
                ClaimEvidence(claim_id=claim.id, evidence_id=item.id, relationship="UNKNOWN")
                for item in evidence
            ]
        )
        session.commit()
        assert _has_claim_linked_evidence(session, investigation)
        packet = json.loads(_evidence_packet(session, investigation))
        assert all(
            item["kind"]
            != "MEDIA_FINGERPRINT"
            for item in packet["evidence"]
        )
        response = get_investigation_results(investigation.id, session)
        serialized_response = json.dumps(response, sort_keys=True)
        assert "ExampleCam" not in serialized_response
        assert "2025:10:02 12:34:56" not in serialized_response
        assert "12/1,34/1,56/1" not in serialized_response
        assert "storage_key" not in serialized_response

        original2_bytes = fixture_image("jpeg")
        original2 = MediaAsset(
            investigation_id=investigation.id,
            storage_key=f"private/{uuid4().hex}",
            media_type="IMAGE",
            mime_type="image/jpeg",
            size_bytes=len(original2_bytes),
            sha256=hashlib.sha256(original2_bytes).hexdigest(),
            metadata_json={},
        )
        session.add(original2)
        session.flush()
        normalized2_bytes = fixture_image("png", source="testsrc2=s=32x32")
        normalized2 = MediaAsset(
            investigation_id=investigation.id,
            parent_asset_id=original2.id,
            asset_role="DERIVED",
            artifact_type="NORMALIZED_IMAGE",
            transformation_version="image-normalization-v1",
            transformation_metadata={"operation": "normalize_image"},
            storage_key=f"private-derived/{original2.id}/normalized.png",
            media_type="IMAGE",
            mime_type="image/png",
            size_bytes=len(normalized2_bytes),
            sha256=hashlib.sha256(normalized2_bytes).hexdigest(),
            metadata_json={},
        )
        session.add(normalized2)
        session.commit()
        with patch(
            "app.modules.investigations.media.analyzers.extract_metadata",
            side_effect=ImageValidationError("METADATA_EXTRACTION_FAILED", "metadata unavailable"),
        ):
            analyze_image_assets(
                session,
                investigation_id=investigation.id,
                original=original2,
                normalized=normalized2,
                original_loader=lambda: original2_bytes,
                normalized_loader=lambda: normalized2_bytes,
            )
        failed_metadata = session.scalar(
            select(MediaAnalysisRun).where(
                MediaAnalysisRun.media_asset_id == original2.id,
                MediaAnalysisRun.analyzer_id == "FILE_METADATA",
            )
        )
        successful_phash = session.scalar(
            select(MediaAnalysisRun).where(
                MediaAnalysisRun.media_asset_id == normalized2.id,
                MediaAnalysisRun.analyzer_id == "PERCEPTUAL_HASH",
            )
        )
        assert failed_metadata.status == "FAILED"
        assert failed_metadata.failure_category == "METADATA_EXTRACTION_FAILED"
        assert successful_phash.status == "COMPLETED"
    finally:
        session.close()
