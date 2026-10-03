"""ClickCast HTTP API adapter for WhatsApp investigation intake and result lookup."""

import hashlib
import hmac
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.domain.investigation import Channel, InputType
from app.modules.investigations.models import Finding, Investigation, Submission, VerificationBrief
from app.modules.investigations.schemas import InvestigationResponse
from app.modules.investigations.service import DEV_USER_ID, InvestigationService

router = APIRouter(prefix="/channels/clickcast", tags=["ClickCast WhatsApp"])


class ClickCastSubmitRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=80)
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
    reference: str = Field(min_length=1, max_length=20)
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
    investigation = InvestigationService(session).create(
        owner_id=_workspace_owner(settings),
        content=body.message,
        input_type=_submission_type(body.message),
        idempotency_key=f"clickcast:{body.event_id}",
        channel=Channel.WHATSAPP,
        source_metadata={
            "platform": "clickcast",
            "event_id": body.event_id,
            "message_type": "TEXT",
            "sender_ref": _sender_reference(body.sender, identity_key),
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
    investigation = session.scalar(
        select(Investigation).where(
            Investigation.reference == body.reference,
            Investigation.owner_id == _workspace_owner(settings),
            Investigation.channel == Channel.WHATSAPP,
        )
    )
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    submission = session.scalar(
        select(Submission).where(
            Submission.investigation_id == investigation.id,
            Submission.channel == Channel.WHATSAPP,
        )
    )
    sender_ref = (
        submission.source_metadata.get("sender_ref")
        if submission and isinstance(submission.source_metadata, dict)
        else None
    )
    if not sender_ref or not hmac.compare_digest(
        str(sender_ref), _sender_reference(body.sender, identity_key)
    ):
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
    return ClickCastResult(
        reference=investigation.reference,
        status=investigation.status.value,
        current_stage=investigation.current_stage,
        ready=brief is not None,
        summary=brief.summary[:1000] if brief else None,
        limitations=brief.limitations[:5] if brief else [],
        findings=[
            ClickCastFinding(status=item.status, statement=item.statement[:500]) for item in findings
        ],
    )
