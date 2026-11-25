"""Image and video checks: inspection, metadata, credentials and visual observations."""

import hashlib
import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.investigations.investigator import (
    VisualAnalysis,
)
from app.modules.investigations.media.analyzers import analyze_image_assets
from app.modules.investigations.models import (
    Claim,
    ClaimEvidence,
    Evidence,
    Investigation,
    MediaAsset,
)
from app.modules.investigations.orchestrator import common, ports, search_stage


def _load_or_inspect_media(
    session: Session,
    investigation: Investigation,
    assets: list[MediaAsset],
) -> list[tuple[str, bytes]]:
    settings = ports.get_settings()
    images: list[tuple[str, bytes]] = []
    for asset in assets:
        metadata = dict(asset.metadata_json or {})
        cached = metadata.get("analysis_object_keys")
        derived_asset = None
        if asset.media_type == "IMAGE":
            derived_asset = session.scalar(
                select(MediaAsset).where(
                    MediaAsset.parent_asset_id == asset.id,
                    MediaAsset.artifact_type == "NORMALIZED_IMAGE",
                    MediaAsset.transformation_version == "image-normalization-v1",
                )
            )
        if isinstance(cached, list):
            for key in cached:
                if len(images) >= settings.max_images_to_model:
                    break
                mime = "image/png" if asset.media_type == "IMAGE" else "image/jpeg"
                images.append((mime, common._get_media_object(str(key))))
            if derived_asset is not None:
                analyze_image_assets(
                    session,
                    investigation_id=investigation.id,
                    original=asset,
                    normalized=derived_asset,
                    original_loader=lambda key=asset.storage_key: common._get_media_object(key),
                    normalized_loader=lambda key=derived_asset.storage_key: (
                        common._get_media_object(key)
                    ),
                )
        else:
            data = common._get_media_object(asset.storage_key)
            extracted_metadata, extracted_frames, limitations = ports.inspect_media(
                data=data,
                media_type=asset.media_type,
                mime_type=asset.mime_type,
            )
            keys: list[str] = []
            if derived_asset is not None:
                extracted_frames = [
                    (derived_asset.mime_type, common._get_media_object(derived_asset.storage_key))
                ]
            for index, (mime, frame) in enumerate(extracted_frames):
                ext = "png" if mime == "image/png" else "jpg"
                key = (
                    derived_asset.storage_key
                    if derived_asset is not None
                    else f"private-derived/{asset.id}/normalized-image-v1.{ext}"
                    if asset.media_type == "IMAGE"
                    else f"private-derived/{investigation.id}/{asset.id}/{index}.{ext}"
                )
                if derived_asset is None:
                    try:
                        ports.put_private_object(key=key, data=frame, content_type=mime)
                    except Exception as exc:
                        raise common.MediaStorageError("Derived media could not be stored") from exc
                if derived_asset is None and asset.media_type == "IMAGE":
                    child = MediaAsset(
                        investigation_id=asset.investigation_id,
                        parent_asset_id=asset.id,
                        asset_role="DERIVED",
                        artifact_type="NORMALIZED_IMAGE",
                        transformation_version="image-normalization-v1",
                        transformation_metadata=extracted_metadata.get("normalization", {}),
                        storage_key=key,
                        media_type="IMAGE",
                        mime_type=mime,
                        size_bytes=len(frame),
                        sha256=hashlib.sha256(frame).hexdigest(),
                        metadata_json={},
                    )
                    session.add(child)
                    session.flush()
                    derived_asset = child
                keys.append(key)
                if len(images) < settings.max_images_to_model:
                    images.append((mime, frame))
            metadata.update(extracted_metadata)
            metadata["analysis_object_keys"] = keys
            asset.metadata_json = metadata
            if not session.scalar(
                select(Evidence.id).where(
                    Evidence.media_asset_id == asset.id,
                    Evidence.method == "MEDIA_METADATA",
                )
            ):
                session.add(
                    Evidence(
                        investigation_id=investigation.id,
                        media_asset_id=asset.id,
                        content=(
                            f"Uploaded {asset.media_type.lower()} media; SHA-256 {asset.sha256}; "
                            f"metadata: {json.dumps(extracted_metadata, sort_keys=True)}"
                        ),
                        method="MEDIA_METADATA",
                        limitations=(
                            "File metadata does not establish whether the recorded event "
                            "is authentic."
                        ),
                    )
                )
            for limitation in limitations:
                ports.add_limitation(session, investigation.id, limitation)
            session.commit()
            if derived_asset is not None and asset.media_type == "IMAGE":
                normalized_data = (
                    frame
                    if extracted_frames
                    else common._get_media_object(derived_asset.storage_key)
                )
                analyze_image_assets(
                    session,
                    investigation_id=investigation.id,
                    original=asset,
                    normalized=derived_asset,
                    original_loader=lambda image_data=data: image_data,
                    normalized_loader=lambda image_data=normalized_data: image_data,
                )
    return images[: settings.max_images_to_model]


def _link_unclaimed_media_evidence(session: Session, investigation: Investigation) -> None:
    """Link media context only when deterministic terms overlap a claim."""
    claims = list(session.scalars(select(Claim).where(Claim.investigation_id == investigation.id)))
    if not claims:
        return
    media_evidence = list(
        session.scalars(
            select(Evidence).where(
                Evidence.investigation_id == investigation.id,
                Evidence.media_asset_id.is_not(None),
            )
        )
    )
    for evidence in media_evidence:
        existing_claim_ids = set(
            session.scalars(
                select(ClaimEvidence.claim_id).where(ClaimEvidence.evidence_id == evidence.id)
            )
        )
        evidence_terms = search_stage._relevance_terms(evidence.content)
        for claim in claims:
            if claim.id not in existing_claim_ids:
                claim_terms = search_stage._relevance_terms(claim.text)
                if not (evidence_terms & claim_terms):
                    continue
                session.add(
                    ClaimEvidence(
                        claim_id=claim.id,
                        evidence_id=evidence.id,
                        relationship="UNKNOWN",
                    )
                )
    session.commit()


def _media_packet_excerpt(evidence: Evidence) -> str:
    """Project persisted media Evidence through an allowlisted, privacy-safe summary."""
    if evidence.method == "MEDIA_PROVENANCE":
        states = {
            "A locally validated C2PA manifest is present.": "VALID",
            "No supported C2PA manifest was detected in the original uploaded image.": (
                "NOT_PRESENT"
            ),
            "C2PA data was present, but local validation did not succeed.": "INVALID",
            "The local C2PA SDK does not support this asset or manifest.": "UNSUPPORTED",
            (
                "C2PA provenance was present or suspected, "
                "but local analysis could not fully validate it."
            ): "INDETERMINATE",
            "Local C2PA analysis could not be completed.": "ERROR",
        }
        state = next(
            (value for prefix, value in states.items() if evidence.content.startswith(prefix)),
            "INDETERMINATE",
        )
        text = f"Local C2PA state: {state}. This does not establish depicted event truth."
        if "Content Credentials declare generative AI involvement." in evidence.content:
            text += " Content Credentials declare generative-AI involvement."
        return text + (
            " Local offline validation; remote manifest retrieval and "
            "OCSP/revocation checks were disabled."
        )
    if evidence.method == "MEDIA_VISUAL_OBSERVATION":
        return evidence.content[:1000]
    if evidence.method == "MEDIA_TECHNICAL_METADATA":
        marker = "Safe decoded fields: "
        try:
            payload = evidence.content.split(marker, 1)[1].split(". Analyzed", 1)[0]
            fields = json.loads(payload)
        except (IndexError, json.JSONDecodeError):
            return "Allowlisted image metadata was recorded; private fields are omitted."
        safe = {key: fields[key] for key in ("format", "width", "height") if key in fields}
        return (
            "Allowlisted technical metadata reports "
            + json.dumps(safe, separators=(",", ":"))
            + ". Metadata is editable and does not establish manipulation, origin, or event time."
        )[:700]
    if evidence.method == "MEDIA_METADATA":
        return (
            "A media observation was recorded. Metadata can be edited and does not establish "
            "manipulation, origin, or event time."
        )
    return ""


def _persist_visual_observations(
    session: Session,
    investigation: Investigation,
    images: list[tuple[str, bytes]],
    gateway: ports.ModelGateway,
) -> None:
    if not images or not session.scalar(
        select(Claim.id).where(Claim.investigation_id == investigation.id)
    ):
        return
    if session.scalar(
        select(Evidence.id).where(
            Evidence.investigation_id == investigation.id,
            Evidence.method == "MEDIA_VISUAL_OBSERVATION",
        )
    ):
        return
    original = session.scalar(
        select(MediaAsset)
        .where(
            MediaAsset.investigation_id == investigation.id,
            MediaAsset.asset_role == "ORIGINAL",
            MediaAsset.media_type.in_(["IMAGE", "VIDEO"]),
        )
        .order_by(MediaAsset.created_at)
    )
    if original is None:
        return
    if original.media_type == "IMAGE":
        normalized = session.scalar(
            select(MediaAsset).where(
                MediaAsset.parent_asset_id == original.id,
                MediaAsset.artifact_type == "NORMALIZED_IMAGE",
            )
        )
        if normalized is None:
            return
        visual_frames = [(normalized.mime_type, images[0][1])]
    else:
        # Bounded frames are normalized JPEGs extracted locally by inspect_media.
        visual_frames = images[:4]
    claim = session.scalar(
        select(Claim).where(Claim.investigation_id == investigation.id).order_by(Claim.created_at)
    )
    if claim is None:
        return
    claim_text = claim.text.casefold()
    visual_cues = (
        "shows",
        "depicts",
        "visible",
        "sign",
        "banner",
        "text",
        "logo",
        "scene",
        "weather",
        "landmark",
        "reads",
        "says",
        "screenshot",
        "what is in",
        "what appears in",
    )
    if not any(cue in claim_text for cue in visual_cues):
        return
    try:
        result = gateway.analyze_visual_content(
            images=visual_frames,
            claim_text=claim.text,
            session=session,
            investigation_id=investigation.id,
        )
        if not isinstance(result.output, VisualAnalysis):
            raise ValueError("Invalid visual analysis output")
    except Exception as exc:
        ports.add_limitation(
            session,
            investigation.id,
            "Visual interpretation was unavailable; deterministic media and source evidence "
            "were retained.",
        )
        common._audit(
            session,
            investigation.id,
            "MEDIA_VISUAL_ANALYSIS_FAILED",
            {"category": getattr(getattr(exc, "category", None), "value", "ANALYSIS_FAILED")},
        )
        session.commit()
        return
    observations = []
    for item in result.output.observations[:12]:
        text = re.sub(r"(?:https?://|www\.)\S+|[\w.+-]+@[\w.-]+", "[redacted]", item.observation)
        text = re.sub(r"[\x00-\x1f<>]", " ", text).strip()[:300]
        if text:
            observations.append(
                {
                    "observation": text,
                    "uncertainty": item.confidence,
                    "relevance": item.relevance[:200],
                    "limitations": [value[:200] for value in item.limitations[:5]],
                }
            )
    if not observations:
        return
    evidence = Evidence(
        investigation_id=investigation.id,
        media_asset_id=original.id,
        content="Structured visual observations (not forensic findings): "
        + json.dumps(observations, ensure_ascii=False, separators=(",", ":")),
        method="MEDIA_VISUAL_OBSERVATION",
        limitations=(
            "Visual descriptions may be mistaken and do not establish authenticity, "
            "manipulation, event truth, or synthetic generation."
        ),
    )
    session.add(evidence)
    session.flush()
    session.commit()
    _link_unclaimed_media_evidence(session, investigation)
