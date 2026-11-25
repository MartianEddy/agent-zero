"""Shared constants and case-state helpers: stages, audit events, usage and dates."""

import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.investigation import InvestigationStatus, validate_transition
from app.modules.investigations.models import (
    AuditEvent,
    Investigation,
    InvestigationUsage,
    MediaAsset,
    ProcessingJob,
)
from app.modules.investigations.orchestrator import ports
from app.modules.investigations.usage import (
    get_or_create_usage,
)

logger = logging.getLogger(__name__)


_WHATSAPP_NOTIFICATION_NAMESPACE = UUID("f4d50920-2994-46ee-92be-b50fed3a5eb3")


ALLOWED_RELATIONSHIPS = {"SUPPORTS", "CONTRADICTS", "CONTEXTUALIZES", "MENTIONS", "UNKNOWN"}


ALLOWED_FINDING_STATUSES = {
    "SUPPORTED",
    "CONTRADICTED",
    "PARTLY_TRUE",
    "INSUFFICIENT_EVIDENCE",
    "NOT_VERIFIABLE",
}


MEDIA_PACKET_METHODS = {
    "MEDIA_PROVENANCE",
    "MEDIA_TECHNICAL_METADATA",
    "MEDIA_METADATA",
    "MEDIA_VISUAL_OBSERVATION",
}


MAX_MEDIA_EVIDENCE_CHARS = 6_000


USER_FAILURE_MESSAGE = (
    "Investigation paused. Agent 0 could not complete the analysis. "
    "Evidence collected so far has been preserved. "
    "No unsupported verification finding was produced."
)


CURRENT_QUERY_MARKER = "prioritize current information and dated sources"


HISTORICAL_QUERY_MARKER = "prioritize historical context and original records"


class MediaStorageError(RuntimeError):
    """Private object storage failed during media processing."""


def _get_media_object(key: str) -> bytes:
    try:
        return ports.get_private_object(key=key)
    except Exception as exc:
        raise MediaStorageError("Media object could not be read") from exc


def _original_media_assets(session: Session, investigation_id: UUID) -> list[MediaAsset]:
    return list(
        session.scalars(
            select(MediaAsset).where(
                MediaAsset.investigation_id == investigation_id,
                MediaAsset.asset_role == "ORIGINAL",
            )
        )
    )


def _stage(session: Session, investigation: Investigation, stage: InvestigationStatus) -> None:
    if investigation.status != stage:
        validate_transition(investigation.status, stage)
    investigation.status = stage
    investigation.current_stage = stage.value
    job = session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.investigation_id == investigation.id)
        .order_by(ProcessingJob.created_at.desc())
    )
    if job is not None:
        job.stage = stage.value
        job.status = "RUNNING"
    session.add(
        AuditEvent(
            investigation_id=investigation.id,
            event_type=f"STAGE_{stage.value}",
            actor="system",
            event_metadata={},
        )
    )
    session.commit()


def _audit(session: Session, investigation_id: UUID, event_type: str, metadata: dict) -> None:
    session.add(
        AuditEvent(
            investigation_id=investigation_id,
            event_type=event_type,
            actor="system",
            event_metadata=metadata,
        )
    )


def _usage(session: Session, investigation_id: UUID) -> InvestigationUsage:
    return get_or_create_usage(session, investigation_id)


def _source_domain(url: str) -> str | None:
    return (urlsplit(url).hostname or "").casefold() or None


def _valid_publication_date(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value[:80]


def _relative_date_context(text: str, received_at: datetime) -> str:
    """Resolve common relative dates deterministically against intake UTC date."""
    utc_received = (
        received_at.astimezone(timezone.utc)
        if received_at.tzinfo
        else received_at.replace(tzinfo=timezone.utc)
    )
    reference_date = utc_received.date()
    normalized = []
    if re.search(r"\btoday\b", text, re.I):
        normalized.append(f"'today' means {reference_date.isoformat()} UTC.")
    if re.search(r"\byesterday\b", text, re.I):
        normalized.append(f"'yesterday' means {reference_date - timedelta(days=1):%Y-%m-%d} UTC.")
    if re.search(r"\b(\d{1,2})\s+days?\s+ago\b", text, re.I):
        for match in re.finditer(r"\b(\d{1,2})\s+days?\s+ago\b", text, re.I):
            days = int(match.group(1))
            if days <= 3650:
                normalized.append(
                    f"'{match.group(0)}' means {reference_date - timedelta(days=days):%Y-%m-%d} UTC."
                )
    if re.search(r"\blast week\b", text, re.I):
        start_of_week = reference_date - timedelta(days=reference_date.weekday() + 7)
        normalized.append(
            f"'last week' is interpreted as {start_of_week:%Y-%m-%d} through "
            f"{start_of_week + timedelta(days=6):%Y-%m-%d} UTC calendar week."
        )
    if not normalized:
        return ""
    return (
        "Relative-date normalization: "
        + " ".join(normalized)
        + " This is a UTC calendar basis; the submitter timezone is unknown and may shift "
        "the date near midnight. State this ambiguity if it could affect the conclusion."
    )
