"""Versioned analyzer execution and safe Evidence persistence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.investigations.media.fingerprints import (
    ANALYZER_ID as PHASH_ID,
)
from app.modules.investigations.media.fingerprints import (
    ANALYZER_VERSION as PHASH_VERSION,
)
from app.modules.investigations.media.fingerprints import (
    CONFIG_DIGEST as PHASH_CONFIG,
)
from app.modules.investigations.media.fingerprints import (
    perceptual_hash,
)
from app.modules.investigations.media.metadata import (
    ANALYZER_ID as METADATA_ID,
)
from app.modules.investigations.media.metadata import (
    ANALYZER_VERSION as METADATA_VERSION,
)
from app.modules.investigations.media.metadata import (
    CONFIG_DIGEST as METADATA_CONFIG,
)
from app.modules.investigations.media.metadata import (
    extract_metadata,
)
from app.modules.investigations.media.provenance import (
    ANALYZER_ID as C2PA_ID,
)
from app.modules.investigations.media.provenance import (
    ANALYZER_VERSION as C2PA_VERSION,
)
from app.modules.investigations.media.provenance import (
    config_digest_input as c2pa_config_digest_input,
)
from app.modules.investigations.media.provenance import (
    inspect_c2pa_bounded,
)
from app.modules.investigations.models import Evidence, MediaAnalysisRun, MediaAsset, utcnow
from app.modules.investigations.usage import add_limitation


def _cache_key(asset: MediaAsset, analyzer_id: str, version: str, config: str) -> tuple[str, str]:
    config_digest = hashlib.sha256(config.encode("utf-8")).hexdigest()
    identity = f"{asset.id}:{asset.sha256}:{analyzer_id}:{version}:{config_digest}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest(), config_digest


def _evidence_content(
    analyzer_id: str, asset_id: UUID, observations: dict[str, object]
) -> tuple[str, str]:
    if analyzer_id == C2PA_ID:
        state = observations.get("state")
        content = {
            "VALID": "A locally validated C2PA manifest is present.",
            "NOT_PRESENT": (
                "No supported C2PA manifest was detected in the original uploaded image."
            ),
            "INVALID": "C2PA data was present, but local validation did not succeed.",
            "UNSUPPORTED": "The local C2PA SDK does not support this asset or manifest.",
            "INDETERMINATE": (
                "C2PA provenance was present or suspected, but local analysis could not fully "
                "validate it."
            ),
            "ERROR": "Local C2PA analysis could not be completed.",
        }.get(str(state), "Local C2PA analysis could not determine a provenance state.")
        limitation = (
            "C2PA credentials are provenance assertions, not evidence that depicted content is "
            "factually true. Absence or invalidity does not establish that an image is synthetic."
        )
        if observations.get("ai_disclosures"):
            content += " Attached Content Credentials declare generative AI involvement."
        content += f" Analyzed original MediaAsset {asset_id}."
    elif analyzer_id == METADATA_ID:
        safe = observations["safe"]
        assert isinstance(safe, dict)
        if observations.get("supported_exif_present"):
            description = "Allowlisted technical metadata was present."
        else:
            description = "No supported EXIF metadata was present in the analyzed asset."
        content = (
            f"{description} Safe decoded fields: "
            f"{json.dumps(safe, sort_keys=True, separators=(',', ':'))}. "
            f"Analyzed MediaAsset {asset_id}."
        )
        limitation = (
            "Metadata is user-editable and does not establish authenticity, origin, or event time."
        )
    else:
        fingerprint = str(observations["hash"])
        content = (
            f"Perceptual similarity fingerprint (pHash v{PHASH_VERSION}) for normalized "
            f"MediaAsset {asset_id}: {fingerprint}. This value is a similarity aid only."
        )
        limitation = "A pHash similarity value does not establish authenticity, origin, or context."
    return content, limitation


def _run_analyzer(
    session: Session,
    *,
    investigation_id: UUID,
    asset: MediaAsset,
    analyzer_id: str,
    version: str,
    config: str,
    observation_factory: Callable[[], dict[str, object]],
) -> None:
    cache_key, config_digest = _cache_key(asset, analyzer_id, version, config)
    run = session.scalar(
        select(MediaAnalysisRun).where(MediaAnalysisRun.cache_key == cache_key).with_for_update()
    )
    if run is not None and run.status == "COMPLETED":
        return
    if run is None:
        run = MediaAnalysisRun(
            investigation_id=investigation_id,
            media_asset_id=asset.id,
            analyzer_id=analyzer_id,
            analyzer_version=version,
            config_digest=config_digest,
            status="RUNNING",
            cache_key=cache_key,
            limitations=[],
        )
        session.add(run)
        session.flush()
    else:
        run.status = "RUNNING"
        run.started_at = utcnow()
        run.completed_at = None
        run.failure_category = None
        run.limitations = []
        run.observations_json = None
    try:
        observations = observation_factory()
    except Exception as exc:
        error_code = getattr(exc, "code", None)
        run.status = "FAILED"
        run.completed_at = datetime.now(UTC)
        run.failure_category = (
            error_code
            if error_code in {"METADATA_EXTRACTION_FAILED", "PERCEPTUAL_HASH_FAILED"}
            else "ANALYZER_FAILED"
        )
        limitation = f"{analyzer_id} analysis failed; no observation was produced."
        run.limitations = [limitation]
        session.commit()
        add_limitation(session, investigation_id, limitation)
        return

    is_c2pa_error = analyzer_id == C2PA_ID and observations.get("state") == "ERROR"
    run.status = "FAILED" if is_c2pa_error else "COMPLETED"
    run.failure_category = "C2PA_ANALYSIS_ERROR" if is_c2pa_error else None
    run.completed_at = datetime.now(UTC)
    run.observations_json = observations
    content, limitation = _evidence_content(analyzer_id, asset.id, observations)
    run.limitations = [limitation]
    existing_evidence = session.scalar(
        select(Evidence).where(Evidence.media_analysis_run_id == run.id)
    )
    if existing_evidence is None:
        session.add(
            Evidence(
                investigation_id=investigation_id,
                media_asset_id=asset.id,
                media_analysis_run_id=run.id,
                content=content,
                method=(
                    "MEDIA_PROVENANCE"
                    if analyzer_id == C2PA_ID
                    else "MEDIA_TECHNICAL_METADATA"
                    if analyzer_id == METADATA_ID
                    else "MEDIA_FINGERPRINT"
                ),
                limitations=limitation,
            )
        )
    else:
        existing_evidence.content = content
        existing_evidence.limitations = limitation
    session.commit()
    if is_c2pa_error:
        add_limitation(
            session,
            investigation_id,
            "Local C2PA analysis could not be completed; other image evidence remains available.",
        )


def analyze_image_assets(
    session: Session,
    *,
    investigation_id: UUID,
    original: MediaAsset,
    normalized: MediaAsset,
    original_loader: Callable[[], bytes],
    normalized_loader: Callable[[], bytes],
) -> None:
    """Persist metadata, pHash, and C2PA observations for their exact assets."""
    _run_analyzer(
        session,
        investigation_id=investigation_id,
        asset=original,
        analyzer_id=METADATA_ID,
        version=METADATA_VERSION,
        config=METADATA_CONFIG,
        observation_factory=lambda: extract_metadata(original_loader()),
    )

    def phash_observations() -> dict[str, object]:
        return {
            "algorithm": "pHash DCT",
            "algorithm_version": PHASH_VERSION,
            "analyzed_asset_id": str(normalized.id),
            "hash": perceptual_hash(normalized_loader()),
        }

    _run_analyzer(
        session,
        investigation_id=investigation_id,
        asset=normalized,
        analyzer_id=PHASH_ID,
        version=PHASH_VERSION,
        config=PHASH_CONFIG,
        observation_factory=phash_observations,
    )

    c2pa_config = c2pa_config_digest_input()

    def c2pa_observations() -> dict[str, object]:
        try:
            return inspect_c2pa_bounded(original_loader(), original.mime_type, original.id)
        except Exception:
            return {
                "analyzer_id": C2PA_ID,
                "analyzer_version": C2PA_VERSION,
                "asset_id": str(original.id),
                "state": "ERROR",
                "manifest_present": False,
                "validation_state": None,
                "signature_state": "UNKNOWN",
                "signer_identity": None,
                "generator": {"name": None, "version": None},
                "actions": [],
                "actions_truncated": False,
                "ai_disclosures": [],
                "ingredient_count": 0,
                "ingredients_truncated": False,
                "validation_codes": [],
                "limitations": [
                    "C2PA credentials do not establish factual truth.",
                    "Local C2PA analysis failed; no authenticity conclusion was drawn.",
                ],
            }

    _run_analyzer(
        session,
        investigation_id=investigation_id,
        asset=original,
        analyzer_id=C2PA_ID,
        version=C2PA_VERSION,
        config=c2pa_config,
        observation_factory=c2pa_observations,
    )
