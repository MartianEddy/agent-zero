"""ClickCast HTTP API adapter for WhatsApp investigation intake and result lookup."""

import hashlib
import hmac
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.domain.investigation import Channel, InputType, InvestigationStatus
from app.modules.investigations.models import Finding, Investigation, Submission, VerificationBrief
from app.modules.investigations.schemas import InvestigationResponse
from app.modules.investigations.service import DEV_USER_ID, InvestigationService
from app.modules.investigations.summary import journalist_assessment_summary

router = APIRouter(prefix="/channels/clickcast", tags=["ClickCast WhatsApp"])


class ClickCastSubmitRequest(BaseModel):
    # ClickCast currently exposes subscriber identifiers but no incoming
    # message/event identifier in its HTTP API variable picker. Keep event_id
    # optional so each accepted call can still start an investigation.
    event_id: str | None = Field(default=None, min_length=1, max_length=80)
    sender: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=20_000)

    @field_validator("message")
    @classmethod
    def non_blank_message(cls, value: str) -> str:
        content = value.strip()
        if not content:
            raise ValueError("message must not be blank")
        return content

    @field_validator("sender")
    @classmethod
    def normalize_sender(cls, value: str) -> str:
        normalized = value.strip().lstrip("+")
        if not normalized or len(normalized) > 120:
            raise ValueError("sender identifier is invalid")
        return normalized


class ClickCastResultRequest(BaseModel):
    # Supplying a reference checks that exact investigation. If ClickCast
    # cannot reliably retain/pass it into a separate keyword flow, omit it to
    # retrieve the latest investigation belonging to this sender.
    reference: str | None = Field(default=None, min_length=1, max_length=20)
    sender: str = Field(min_length=1, max_length=120)

    @field_validator("sender")
    @classmethod
    def normalize_sender(cls, value: str) -> str:
        normalized = value.strip().lstrip("+")
        if not normalized or len(normalized) > 120:
            raise ValueError("sender identifier is invalid")
        return normalized


class ClickCastFinding(BaseModel):
    status: str
    statement: str


class ClickCastResult(BaseModel):
    reference: str
    status: str
    current_stage: str
    ready: bool
    summary: str | None
    limitations: list[str]
    findings: list[ClickCastFinding]


@router.get("/health")
def clickcast_health(authorization: str | None = Header(default=None)) -> dict[str, str]:
    settings = get_settings()
    _configured_clickcast_secrets(settings, authorization)
    return {"status": "ready", "integration": "clickcast", "accepts": "text_and_url"}


def _sender_reference(sender: str, identity_key: str) -> str:
    """Create a stable sender reference without persisting a phone number."""
    digest = hmac.new(identity_key.encode(), sender.encode(), hashlib.sha256).hexdigest()
    return digest


def _configured_clickcast_secrets(settings, authorization: str | None) -> str:
    configured_token = (
        settings.clickcast_api_token.get_secret_value()
        if settings.clickcast_api_token
        else ""
    )
    identity_key = (
        settings.clickcast_identity_key.get_secret_value()
        if settings.clickcast_identity_key
        else ""
    )
    scheme, _, supplied_token = (authorization or "").partition(" ")
    if (
        scheme.lower() != "bearer"
        or not supplied_token.isascii()
        or not configured_token
        or not identity_key
        or not hmac.compare_digest(configured_token, supplied_token)
    ):
        raise HTTPException(status_code=404, detail="Integration not found")
    return identity_key


def _workspace_owner(settings):
    return settings.clickcast_owner_id or DEV_USER_ID


def _submission_type(message: str) -> InputType:
    candidate = message.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme in {"http", "https"}:
        if not parsed.hostname or parsed.username or parsed.password:
            raise HTTPException(status_code=422, detail="URL submission is invalid")
        return InputType.URL
    return InputType.TEXT


@router.post(
    "/investigations",
    response_model=InvestigationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_from_clickcast(
    body: ClickCastSubmitRequest,
    session: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> InvestigationResponse:
    settings = get_settings()
    identity_key = _configured_clickcast_secrets(settings, authorization)
    sender_ref = _sender_reference(body.sender, identity_key)
    # The current ClickCast variable picker has no stable message/event ID.
    # Avoid starting duplicate work when it retries the same exact submission
    # while that investigation is still active. Once terminal, a new request
    # may intentionally submit the same text again.
    if body.event_id is None:
        terminal_statuses = {
            InvestigationStatus.COMPLETE,
            InvestigationStatus.NEEDS_REVIEW,
            InvestigationStatus.FAILED,
            InvestigationStatus.CANCELLED,
        }
        existing_in_progress = session.scalar(
            select(Investigation)
            .join(Submission, Submission.investigation_id == Investigation.id)
            .where(
                Investigation.owner_id == _workspace_owner(settings),
                Investigation.channel == Channel.WHATSAPP,
                Investigation.status.not_in(terminal_statuses),
                Submission.channel == Channel.WHATSAPP,
                Submission.original_text == body.message,
                Submission.source_metadata["sender_ref"].as_string() == sender_ref,
            )
            .order_by(Investigation.created_at.desc())
            .limit(1)
        )
        if existing_in_progress is not None:
            return InvestigationResponse.model_validate(existing_in_progress)

    investigation = InvestigationService(session).create(
        owner_id=_workspace_owner(settings),
        content=body.message,
        input_type=_submission_type(body.message),
        # Preserve retry idempotency when ClickCast supplies an event ID. In
        # its absence, create a unique key; this avoids collisions between
        # different messages from the same subscriber.
        idempotency_key=f"clickcast:{body.event_id or uuid4().hex}",
        channel=Channel.WHATSAPP,
        source_metadata={
            "platform": "clickcast",
            "event_id": body.event_id,
            "message_type": "TEXT",
            "sender_ref": sender_ref,
        },
    )
    return InvestigationResponse.model_validate(investigation)


@router.post(
    "/result",
    response_model=ClickCastResult,
    status_code=status.HTTP_200_OK,
)
def get_result_from_clickcast(
    body: ClickCastResultRequest,
    session: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> ClickCastResult:
    settings = get_settings()
    identity_key = _configured_clickcast_secrets(settings, authorization)
    sender_ref = _sender_reference(body.sender, identity_key)
    statement = (
        select(Investigation)
        .join(Submission, Submission.investigation_id == Investigation.id)
        .where(
            Investigation.owner_id == _workspace_owner(settings),
            Investigation.channel == Channel.WHATSAPP,
            Submission.channel == Channel.WHATSAPP,
            Submission.source_metadata["sender_ref"].as_string() == sender_ref,
        )
    )
    if body.reference:
        statement = statement.where(Investigation.reference == body.reference)
    else:
        statement = statement.order_by(Investigation.created_at.desc()).limit(1)
    investigation = session.scalar(statement)
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    brief = session.scalar(
        select(VerificationBrief).where(VerificationBrief.investigation_id == investigation.id)
    )
    findings = list(
        session.scalars(
            select(Finding)
            .where(Finding.investigation_id == investigation.id)
            .order_by(Finding.created_at)
            .limit(5)
        )
    )
    terminal_statuses = {
        InvestigationStatus.COMPLETE,
        InvestigationStatus.NEEDS_REVIEW,
        InvestigationStatus.FAILED,
        InvestigationStatus.CANCELLED,
    }
    terminal_summary = {
        InvestigationStatus.NEEDS_REVIEW: (
            "This check is ready for human review. The available evidence does not support a "
            "final assessment. Review the cited sources before publication."
        ),
        InvestigationStatus.FAILED: (
            "We could not complete this check, so there is no assessment to share. Please try "
            "again later or review the sources directly."
        ),
        InvestigationStatus.CANCELLED: "This check was cancelled before an assessment was ready.",
        InvestigationStatus.COMPLETE: (
            "This check is ready, but no summary was produced. No conclusion is available; "
            "please review the cited sources directly."
        ),
    }
    return ClickCastResult(
        reference=investigation.reference,
        status=investigation.status.value,
        current_stage=investigation.current_stage,
        ready=brief is not None or investigation.status in terminal_statuses,
        # Rebuild from persisted findings so existing investigations also get
        # the journalist-facing copy after this code is deployed; stored briefs
        # are immutable snapshots and may contain the older system-focused text.
        summary=(
            journalist_assessment_summary(item.status for item in findings)[:1000]
            if brief
            else terminal_summary.get(investigation.status)
        ),
        limitations=brief.limitations[:5] if brief else [],
        findings=[
            ClickCastFinding(status=item.status, statement=item.statement[:500])
            for item in findings
        ],
    )
