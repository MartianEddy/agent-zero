"""Channel-neutral WhatsApp conversation and investigation handoff service."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.investigation import Channel, InputType, InvestigationStatus
from app.modules.conversations.models import (
    WhatsAppConversation,
    WhatsAppInboundEvent,
    WhatsAppNotificationPreference,
)
from app.modules.conversations.schemas import ConversationTurn
from app.modules.investigations.investigator import ModelGateway, ModelInvocationFailed
from app.modules.investigations.models import (
    AuditEvent,
    Claim,
    Evidence,
    Finding,
    FindingEvidence,
    Investigation,
    InvestigationUsage,
    OutboxEvent,
    ProcessingJob,
    SearchTrace,
    Source,
    Submission,
    User,
    VerificationBrief,
)
from app.modules.investigations.service import (
    DEV_USER_ID,
    InvestigationRetryUnavailable,
    InvestigationService,
    is_retryable_failure_code,
    queue_investigation_retry,
)
from app.modules.investigations.summary import finding_result_summary
from app.modules.investigations.triage import normalize_claim_text
from app.modules.investigations.usage import ModelCallBudgetExceeded

logger = logging.getLogger(__name__)
MAX_MESSAGE_CHARS = 20_000
INBOUND_EVENT_PROVIDER = "meta_whatsapp_cloud"
INBOUND_EVENT_LEASE = timedelta(minutes=3)
_UNRESOLVED_CLAIM_PATTERN = re.compile(
    r"(?:\[[^\]\n]{1,100}\]|\b(?:tbd|todo|placeholder|lorem ipsum)\b|"
    r"\b(?:particular|specific|certain|unknown|unspecified|some)\s+"
    r"(?:date|year|time|person|place|number|amount|event)\b)",
    re.IGNORECASE,
)

_FAILURE_COPY = {
    "RATE_LIMITED": "A research service rate limit interrupted the check.",
    "QUOTA_EXHAUSTED": "The research service quota was unavailable.",
    "AUTHENTICATION_FAILED": "A research service could not authorize this check.",
    "PROVIDER_UNAVAILABLE": "A research service was temporarily unavailable.",
    "TIMEOUT": "A research step took too long to finish.",
    "INVALID_MODEL_OUTPUT": "A research step returned an unusable response.",
    "BUDGET_EXCEEDED": "The check reached its AI usage limit.",
    "PIPELINE_ERROR": "A processing step stopped unexpectedly.",
    "DERIVATION_FAILED": "The submitted material could not be prepared for review.",
    "STORAGE_FAILED": "The system could not safely save research material.",
}


def _retrieved_sources(
    session: Session, *, investigation_id: UUID, limit: int = 3
) -> list[Source]:
    return list(
        session.scalars(
            select(Source)
            .where(
                Source.investigation_id == investigation_id,
                Source.retrieval_status == "RETRIEVED",
            )
            .order_by(Source.retrieved_at.desc().nullslast(), Source.id)
            .limit(limit)
        )
    )


def _source_bullets(sources: list[Source]) -> str:
    lines = []
    for source in sources:
        label = (source.title or source.publisher or source.domain or "Retrieved source").strip()
        label = " ".join(label.split())[:100]
        url = source.canonical_url or source.url
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            continue
        safe_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if len(safe_url) <= 350:
            lines.append(f"• {label}: {safe_url}")
    return "\n".join(lines)


def _with_reference(message: str, reference: str) -> str:
    suffix = f"\n\nReference: {reference}"
    return message[: 3900 - len(suffix)].rstrip() + suffix


def _retry_available(session: Session, investigation: Investigation) -> bool:
    job = session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.investigation_id == investigation.id)
        .order_by(ProcessingJob.created_at.desc())
    )
    if (
        investigation.status not in {InvestigationStatus.NEEDS_REVIEW, InvestigationStatus.FAILED}
        or job is None
        or job.status in {"QUEUED", "RUNNING"}
        or not is_retryable_failure_code(job.error_code)
    ):
        return False
    usage = session.scalar(
        select(InvestigationUsage).where(
            InvestigationUsage.investigation_id == investigation.id
        )
    )
    return usage is None or usage.model_calls < get_settings().max_model_calls_per_investigation


class ConversationTurnInProgress(RuntimeError):
    """A prior delivery of this inbound event is still being processed."""


def _model_unavailable_reply(error: Exception) -> str:
    if isinstance(error, ModelCallBudgetExceeded):
        if error.reset_at is not None:
            local_reset = error.reset_at.astimezone(ZoneInfo("Africa/Nairobi"))
            reset_label = local_reset.strftime("%-I:%M %p EAT on %a, %b %-d")
            return (
                "I’ve reached the chat’s AI reply limit for now. It resets at "
                f"{reset_label}. Your message was received, but no investigation was started."
            )
        return (
            "I’ve reached the chat’s AI reply limit for now. Your message was received, but no "
            "investigation was started. Please try again later."
        )
    return (
        "I’m temporarily unable to reach my reasoning service. Your message was received, but "
        "no investigation was started. Please try again shortly."
    )


def _sender_reference(sender: str, identity_key: str) -> str:
    return hmac.new(identity_key.encode(), sender.encode(), hashlib.sha256).hexdigest()


def _recipient_cipher(settings) -> Fernet:
    identity_key = settings.whatsapp_identity_key.get_secret_value().encode()
    key = hmac.new(identity_key, b"agent-zero:whatsapp-recipient:v1", hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _encrypt_recipient(sender: str, settings) -> str:
    return _recipient_cipher(settings).encrypt(sender.encode()).decode()


def _decrypt_recipient(value: str, settings) -> str | None:
    try:
        return _recipient_cipher(settings).decrypt(value.encode()).decode()
    except (InvalidToken, UnicodeDecodeError, ValueError):
        return None


def _notification_preference(session: Session, *, settings, sender_ref: str):
    return session.scalar(
        select(WhatsAppNotificationPreference).where(
            WhatsAppNotificationPreference.owner_id == _owner_id(settings),
            WhatsAppNotificationPreference.sender_ref == sender_ref,
        )
    )


def _owner_id(settings) -> UUID:
    return settings.whatsapp_owner_id or DEV_USER_ID


def _result_message(
    session: Session,
    *,
    settings,
    sender_ref: str,
    reference: str | None,
    conversation_id: UUID | None = None,
) -> str:
    reference = reference.upper() if reference else None
    statement = (
        select(Investigation)
        .join(Submission, Submission.investigation_id == Investigation.id)
        .where(
            Investigation.owner_id == _owner_id(settings),
            Investigation.channel == Channel.WHATSAPP,
            Submission.channel == Channel.WHATSAPP,
            Submission.source_metadata["sender_ref"].as_string() == sender_ref,
        )
    )
    if reference is not None:
        statement = statement.where(Investigation.reference == reference)
    else:
        statement = statement.order_by(Investigation.created_at.desc()).limit(1)
    investigation = session.scalar(statement)
    if investigation is None and conversation_id is not None:
        # A persisted case is also bound to the conversation that approved it.
        # Use that durable relation if legacy or malformed submission metadata
        # omitted the sender HMAC; keep owner, channel, and exact reference scope.
        conversation_statement = (
            select(Investigation)
            .join(Submission, Submission.investigation_id == Investigation.id)
            .where(
                Investigation.owner_id == _owner_id(settings),
                Investigation.channel == Channel.WHATSAPP,
                Submission.channel == Channel.WHATSAPP,
                Submission.source_metadata["conversation_id"].as_string()
                == str(conversation_id),
            )
        )
        if reference is not None:
            conversation_statement = conversation_statement.where(
                Investigation.reference == reference
            )
        else:
            conversation_statement = conversation_statement.order_by(
                Investigation.created_at.desc()
            ).limit(1)
        investigation = session.scalar(conversation_statement)
    if investigation is None:
        return (
            "I couldn't find a check for this WhatsApp number. "
            "Send a claim or public URL to start one."
        )

    brief = session.scalar(
        select(VerificationBrief).where(VerificationBrief.investigation_id == investigation.id)
    )
    if brief is None:
        job = session.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.investigation_id == investigation.id)
            .order_by(ProcessingJob.created_at.desc())
        )
        if investigation.status == InvestigationStatus.FAILED:
            message = (
                "This check stopped before an assessment was ready. No conclusion is available."
            )
        elif investigation.status == InvestigationStatus.CANCELLED:
            message = "This check was cancelled before an assessment was ready."
        elif investigation.status == InvestigationStatus.NEEDS_REVIEW:
            message = (
                "The automated check stopped before saving an assessment. "
                "No conclusion is available."
            )
        elif investigation.status == InvestigationStatus.COMPLETE:
            message = (
                "This check finished without a saved summary. No conclusion is available; "
                "please review the case in Agent Zero."
            )
        else:
            stage_messages = {
                "RECEIVED": "Your check is queued for research.",
                "PROCESSING": "Research is underway on your check.",
                "ANALYZING": "I’m reviewing the claim and preparing the research plan.",
                "RESEARCHING": "I’m gathering public evidence for your check.",
                "CORROBORATING": "I’m comparing the available evidence.",
                "GENERATING_BRIEF": "I’m preparing your evidence summary.",
            }
            stage = getattr(investigation, "current_stage", None)
            message = stage_messages.get(
                stage,
                "Your check is still in progress.",
            )
            message = (
                f"{message} You don’t need to resend the claim. "
                f"Check again later with RESULT {investigation.reference}."
            )
        details = []
        if investigation.status in {
            InvestigationStatus.NEEDS_REVIEW,
            InvestigationStatus.FAILED,
        }:
            claims = list(
                session.scalars(
                    select(Claim)
                    .where(Claim.investigation_id == investigation.id)
                    .order_by(Claim.created_at)
                    .limit(3)
                )
            )
            if claims:
                details.append(
                    "Claim submitted:\n"
                    + "\n".join(f"• {claim.text[:240]}" for claim in claims)
                )
            category = job.error_code if job is not None else None
            if category:
                details.append(
                    _FAILURE_COPY.get(category, "A processing step could not be completed.")
                )
            retrieved = _retrieved_sources(session, investigation_id=investigation.id)
            source_bullets = _source_bullets(retrieved)
            if source_bullets:
                details.append(
                    "Pages retrieved before the check stopped "
                    "(not yet confirmed as supporting evidence):\n"
                    + source_bullets
                )
            if _retry_available(session, investigation):
                details.append(
                    f"To retry this saved check, reply RETRY {investigation.reference}. "
                    "You do not need to resend the claim."
                )
            else:
                details.append(
                    "A retry is not available for this case right now. "
                    "Keep the reference for support."
                )
        return _with_reference("\n\n".join([message, *details]), investigation.reference)

    findings = list(
        session.scalars(
            select(Finding)
            .where(Finding.investigation_id == investigation.id)
            .order_by(Finding.created_at)
            .limit(5)
        )
    )
    stopped_prefix = ""
    if investigation.status in {InvestigationStatus.NEEDS_REVIEW, InvestigationStatus.FAILED}:
        latest_job = session.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.investigation_id == investigation.id)
            .order_by(ProcessingJob.created_at.desc())
        )
        stopped_prefix = (
            "The latest automated run stopped before completion. The saved assessment below "
            "may be incomplete and should be treated as preliminary."
        )
        if latest_job is not None and latest_job.error_code:
            stopped_prefix += " " + _FAILURE_COPY.get(
                latest_job.error_code, "A processing step could not be completed."
            )
        if _retry_available(session, investigation):
            stopped_prefix += f" Reply RETRY {investigation.reference} to queue another run."
    summary = finding_result_summary(findings, max_chars=1300)
    claims = list(
        session.scalars(
            select(Claim)
            .where(Claim.investigation_id == investigation.id)
            .order_by(Claim.created_at)
            .limit(3)
        )
    )
    finding_evidence_ids = list(
        session.scalars(
            select(FindingEvidence.evidence_id)
            .join(Finding, Finding.id == FindingEvidence.finding_id)
            .where(Finding.investigation_id == investigation.id)
        )
    )
    source_ids = {
        source_id
        for source_id in session.scalars(
            select(Evidence.source_id).where(
                Evidence.id.in_(finding_evidence_ids), Evidence.source_id.is_not(None)
            )
        )
        if source_id is not None
    }
    linked_sources = list(
        session.scalars(
            select(Source)
            .where(
                Source.id.in_(source_ids),
                Source.retrieval_status == "RETRIEVED",
            )
            .order_by(Source.retrieved_at.desc().nullslast(), Source.id)
            .limit(3)
        )
    )
    claim_text = "\n".join(f"• {item.text[:160]}" for item in claims)
    source_text = _source_bullets(linked_sources)
    limitations = [item[:150] for item in (brief.limitations or [])[:2] if item]
    limitation_text = "\n\nLimitations: " + "; ".join(limitations) if limitations else ""
    claim_section = f"Claim checked:\n{claim_text}\n\n" if claim_text else ""
    source_section = (
        "\n\nSources linked to the assessment:\n" + source_text
        if source_text
        else "\n\nNo source link was available in this WhatsApp summary. "
        "Open the case to inspect its evidence."
    )
    return _with_reference(
        f"{stopped_prefix}\n\n{claim_section}{summary}{source_section}{limitation_text}",
        investigation.reference,
    )


def _retry_message(
    session: Session,
    *,
    settings,
    sender_ref: str,
    reference: str | None,
) -> str:
    reference = reference.upper() if reference else None
    if reference is None:
        return "To avoid retrying the wrong check, send RETRY followed by its case reference."
    statement = (
        select(Investigation)
        .join(Submission, Submission.investigation_id == Investigation.id)
        .where(
            Investigation.owner_id == _owner_id(settings),
            Investigation.channel == Channel.WHATSAPP,
            Submission.channel == Channel.WHATSAPP,
            Submission.source_metadata["sender_ref"].as_string() == sender_ref,
        )
    )
    statement = statement.where(Investigation.reference == reference)
    investigation = session.scalar(statement.with_for_update())
    if investigation is None:
        return (
            "I couldn't find a check for this WhatsApp number. "
            "Send RETRY with its case reference."
        )

    latest_job = session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.investigation_id == investigation.id)
        .order_by(ProcessingJob.created_at.desc())
    )
    if latest_job is not None and not is_retryable_failure_code(latest_job.error_code):
        return (
            "This failure is not transient, so I can't retry it from WhatsApp. "
            "After the service issue is corrected, start a fresh check or contact support.\n"
            f"Reference: {investigation.reference}"
        )

    try:
        queue_investigation_retry(
            session,
            investigation=investigation,
            actor="whatsapp-user",
            max_model_calls=settings.max_model_calls_per_investigation,
        )
    except InvestigationRetryUnavailable as exc:
        messages = {
            "not_retryable": (
                "This failure type cannot be safely retried here. Open the case in Agent Zero "
                "or contact support."
            ),
            "job_missing": (
                "I couldn't find a saved run to retry. Please open the case in Agent Zero."
            ),
            "already_running": (
                "A retry is already queued or running. You don't need to send it again."
            ),
            "budget_exhausted": (
                "This check has reached its AI usage limit. It cannot be retried right now."
            ),
        }
        return f"{messages[exc.reason]}\nReference: {investigation.reference}"

    return (
        "I’ve queued another run using the saved claim. No new assessment is available yet; "
        "send STATUS to check progress.\n"
        f"Reference: {investigation.reference}"
    )


def _conversation_for_sender(
    session: Session, *, owner_id: UUID, sender_ref: str, now: datetime
) -> WhatsAppConversation:
    conversation = session.scalar(
        select(WhatsAppConversation)
        .where(
            WhatsAppConversation.owner_id == owner_id,
            WhatsAppConversation.sender_ref == sender_ref,
        )
        .with_for_update()
    )
    if conversation is None:
        try:
            if session.get(User, owner_id) is None:
                session.add(User(id=owner_id, external_subject=f"local:{owner_id}"))
                session.flush()
            session.add(
                WhatsAppConversation(
                    owner_id=owner_id,
                    sender_ref=sender_ref,
                    expires_at=now + timedelta(hours=24),
                )
            )
            session.commit()
        except IntegrityError:
            session.rollback()
            # Concurrent first messages can race on the owner/sender unique key.
            conversation = session.scalar(
                select(WhatsAppConversation)
                .where(
                    WhatsAppConversation.owner_id == owner_id,
                    WhatsAppConversation.sender_ref == sender_ref,
                )
                .with_for_update()
            )
            if conversation is None:
                raise
            return conversation
        conversation = session.scalar(
            select(WhatsAppConversation)
            .where(
                WhatsAppConversation.owner_id == owner_id,
                WhatsAppConversation.sender_ref == sender_ref,
            )
            .with_for_update()
        )
        if conversation is None:
            raise RuntimeError("WhatsApp conversation insert was not visible")
        return conversation

    expiry = conversation.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    if expiry <= now:
        conversation.context_json = []
        conversation.processed_events = []
        conversation.model_calls = 0
        conversation.input_tokens = 0
        conversation.output_tokens = 0
        _clear_conversation_draft(conversation)
    return conversation


def _clear_conversation_draft(conversation: WhatsAppConversation) -> None:
    conversation.state = "IDLE"
    conversation.draft_text = None
    conversation.draft_input_type = None
    conversation.proposed_claims = []
    conversation.proposed_queries = []
    conversation.clarification_question = None
    conversation.confirmation_token = None
    conversation.draft_expires_at = None


def _append_turn(
    conversation: WhatsAppConversation,
    *,
    user_text: str,
    reply: str,
    message_id: str,
    now: datetime,
) -> None:
    turns = list(conversation.context_json or [])
    turns.extend(
        [
            {"role": "user", "content": user_text[:1200]},
            {"role": "assistant", "content": reply[:1200]},
        ]
    )
    conversation.context_json = turns[-8:]
    processed = list(conversation.processed_events or [])
    processed.append({"message_id": message_id, "reply": reply[:3900]})
    conversation.processed_events = processed[-50:]
    conversation.expires_at = now + timedelta(hours=24)
    conversation.last_inbound_at = now


def _claim_inbound_event(
    session: Session,
    *,
    conversation: WhatsAppConversation,
    event: ConversationTurn,
    sender_ref: str,
    now: datetime,
) -> str | None:
    """Persist a unique event claim before model work; return a saved reply on replay."""
    receipt = session.scalar(
        select(WhatsAppInboundEvent)
        .where(
            WhatsAppInboundEvent.provider == INBOUND_EVENT_PROVIDER,
            WhatsAppInboundEvent.message_id == event.message_id,
        )
        .with_for_update()
    )
    receipt_expiry = receipt.expires_at if receipt is not None else None
    if receipt_expiry is not None and receipt_expiry.tzinfo is None:
        receipt_expiry = receipt_expiry.replace(tzinfo=UTC)
    if receipt is not None and receipt_expiry is not None and receipt_expiry > now:
        if receipt.conversation_id != conversation.id or receipt.sender_ref != sender_ref:
            session.rollback()
            raise ValueError("WhatsApp provider event identity collision")
        if receipt.state == "COMPLETED":
            return receipt.reply_text or "I already handled that message."
        if receipt.state == "IGNORED":
            return ""
        lease_expiry = receipt.lease_expires_at
        if lease_expiry.tzinfo is None:
            lease_expiry = lease_expiry.replace(tzinfo=UTC)
        if lease_expiry > now:
            session.rollback()
            raise ConversationTurnInProgress
        receipt.attempts += 1
        receipt.state = "PROCESSING"
        receipt.reply_text = None
        receipt.lease_expires_at = now + INBOUND_EVENT_LEASE
        session.commit()
    else:
        if receipt is None:
            receipt = WhatsAppInboundEvent(
                conversation_id=conversation.id,
                provider=INBOUND_EVENT_PROVIDER,
                message_id=event.message_id,
                sender_ref=sender_ref,
                state="PROCESSING",
                attempts=1,
                lease_expires_at=now + INBOUND_EVENT_LEASE,
                expires_at=now + timedelta(hours=24),
            )
            session.add(receipt)
        else:
            receipt.conversation_id = conversation.id
            receipt.sender_ref = sender_ref
            receipt.state = "PROCESSING"
            receipt.reply_text = None
            receipt.attempts = 1
            receipt.lease_expires_at = now + INBOUND_EVENT_LEASE
            receipt.expires_at = now + timedelta(hours=24)
        session.commit()

    # Receipt commit makes the event claim durable. Reacquire and hold the
    # conversation row lock through triage and the final state/reply commit.
    conversation = session.scalar(
        select(WhatsAppConversation)
        .where(WhatsAppConversation.id == conversation.id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if conversation is None:
        raise RuntimeError("WhatsApp conversation disappeared while claiming an event")
    return None


def _complete_inbound_event(
    session: Session,
    *,
    event: ConversationTurn,
    reply: str,
    state: str = "COMPLETED",
) -> None:
    receipt = session.scalar(
        select(WhatsAppInboundEvent).where(
            WhatsAppInboundEvent.provider == INBOUND_EVENT_PROVIDER,
            WhatsAppInboundEvent.message_id == event.message_id,
        )
    )
    if receipt is None:
        raise RuntimeError("WhatsApp inbound receipt disappeared before completion")
    receipt.state = state
    receipt.reply_text = reply[:4096]
    receipt.lease_expires_at = datetime.now(UTC)


def _latest_case(
    session: Session, *, settings, sender_ref: str
) -> Investigation | None:
    return session.scalar(
        select(Investigation)
        .join(Submission, Submission.investigation_id == Investigation.id)
        .where(
            Investigation.owner_id == _owner_id(settings),
            Investigation.channel == Channel.WHATSAPP,
            Submission.channel == Channel.WHATSAPP,
            Submission.source_metadata["sender_ref"].as_string() == sender_ref,
        )
        .order_by(Investigation.created_at.desc())
        .limit(1)
    )


def _status_message(
    session: Session, *, settings, sender_ref: str, reference: str | None
) -> str:
    reference = reference.upper() if reference else None
    investigation = _latest_case(session, settings=settings, sender_ref=sender_ref)
    if reference:
        investigation = session.scalar(
            select(Investigation)
            .join(Submission, Submission.investigation_id == Investigation.id)
            .where(
                Investigation.owner_id == _owner_id(settings),
                Investigation.channel == Channel.WHATSAPP,
                Investigation.reference == reference,
                Submission.channel == Channel.WHATSAPP,
                Submission.source_metadata["sender_ref"].as_string() == sender_ref,
            )
        )
    if investigation is None:
        return (
            "I couldn't find an investigation for this conversation. "
            "Tell me what you'd like me to investigate."
        )
    latest_job = session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.investigation_id == investigation.id)
        .order_by(ProcessingJob.created_at.desc())
    )
    if latest_job is not None and latest_job.status == "QUEUED":
        return (
            "Your investigation retry is queued. No new assessment is available yet; "
            "you do not need to send the claim again.\n"
            f"Reference: {investigation.reference}"
        )
    labels = {
        "RECEIVED": "queued",
        "PROCESSING": "processing",
        "ANALYZING": "analyzing the claim",
        "RESEARCHING": "reviewing sources",
        "CORROBORATING": "comparing evidence",
        "GENERATING_BRIEF": "preparing the assessment",
        "COMPLETE": "complete",
        "NEEDS_REVIEW": "stopped before a final assessment was saved",
        "FAILED": "could not be completed; no conclusion is available",
        "CANCELLED": "cancelled",
    }
    label = labels.get(investigation.status.value, "in progress")
    recovery = ""
    if investigation.status in {InvestigationStatus.NEEDS_REVIEW, InvestigationStatus.FAILED}:
        recovery = " Send RESULT to see what was gathered."
        recovery += (
            f" Reply RETRY {investigation.reference} to queue another run."
            if _retry_available(session, investigation)
            else " A retry is not available right now."
        )
    return (
        f"Your investigation is {label}. This status does not establish whether the claim is "
        f"true.{recovery}\n"
        f"Reference: {investigation.reference}"
    )


def _case_list_message(
    session: Session, *, settings, sender_ref: str, page: int = 1
) -> str:
    cases = list(
        session.scalars(
            select(Investigation)
            .join(Submission, Submission.investigation_id == Investigation.id)
            .where(
                Investigation.owner_id == _owner_id(settings),
                Investigation.channel == Channel.WHATSAPP,
                Submission.channel == Channel.WHATSAPP,
                Submission.source_metadata["sender_ref"].as_string() == sender_ref,
            )
            .order_by(Investigation.created_at.desc(), Investigation.id.desc())
            .offset((page - 1) * 10)
            .limit(10)
        )
    )
    if not cases:
        if page > 1:
            return "There are no older cases on that page. Send HISTORY to see your newest cases."
        return "You don't have an investigation yet. Tell me what you'd like me to look into."
    lines = [f"Your checks, page {page} (newest first):"]
    for case in cases:
        status = case.status.value.replace("_", " ").lower()
        claim = session.scalar(
            select(Claim.text)
            .where(Claim.investigation_id == case.id)
            .order_by(Claim.created_at)
            .limit(1)
        )
        detail = f" — {claim[:100]}" if claim else ""
        lines.append(f"• {case.reference} — {status}{detail}")
    lines.append(
        f"Send RESULT <reference> for an assessment, STATUS <reference> for progress, "
        f"or HISTORY {page + 1} for older cases."
    )
    return "\n".join(lines)


def _preview_code_in(text: str) -> str | None:
    match = re.search(r"\b[A-F0-9]{8}\b", text, re.IGNORECASE)
    return match.group(0).upper() if match else None


def _preview_button_code(text: str, action: str) -> str | None:
    match = re.fullmatch(rf"{re.escape(action)}\s+([A-F0-9]{{8}})", text.strip(), re.IGNORECASE)
    return match.group(1).upper() if match else None


def _looks_like_confirmation(text: str) -> bool:
    normalized = " ".join(text.casefold().strip().split())
    return normalized in {
        "submit",
        "submit claim",
        "start",
        "start investigation",
        "confirm",
        "yes",
        "yes submit",
        "yes submit it",
        "yes go ahead",
        "go ahead",
        "go ahead and investigate",
    } or normalized.startswith(
        ("yes ", "go ahead", "please submit", "confirm ", "submit ")
    )


async def _send_saved_reply(
    session: Session,
    *,
    conversation: WhatsAppConversation,
    event: ConversationTurn,
    user_text: str,
    reply: str,
    send_message,
    buttons: list[tuple[str, str]] | None = None,
) -> None:
    _append_turn(
        conversation,
        user_text=user_text,
        reply=reply,
        message_id=event.message_id,
        now=datetime.now(UTC),
    )
    _complete_inbound_event(session, event=event, reply=reply)
    session.commit()
    if buttons:
        await run_in_threadpool(send_message, event.sender, reply, buttons)
    else:
        await run_in_threadpool(send_message, event.sender, reply)


async def _confirm_conversation_draft(
    session: Session,
    *,
    conversation: WhatsAppConversation,
    event: ConversationTurn,
    settings,
    user_text: str,
    confirmation_code: str | None,
) -> tuple[str, bool]:
    now = datetime.now(UTC)
    draft_expiry = conversation.draft_expires_at
    if draft_expiry is not None and draft_expiry.tzinfo is None:
        draft_expiry = draft_expiry.replace(tzinfo=UTC)
    if (
        conversation.state != "AWAITING_CONFIRMATION"
        or not conversation.proposed_claims
        or draft_expiry is None
        or draft_expiry <= now
    ):
        _clear_conversation_draft(conversation)
        return (
            "I don't have a current claim preview to submit. "
            "Tell me what you'd like investigated and I'll prepare one.",
            False,
        )

    if (
        confirmation_code is None
        or conversation.confirmation_token is None
        or not hmac.compare_digest(
            confirmation_code.casefold(), conversation.confirmation_token.casefold()
        )
    ):
        return (
            "To approve this exact preview, include its code: "
            f"SUBMIT {conversation.confirmation_token}. No investigation has started.",
            False,
        )

    idempotency_key = (
        f"meta-wa-confirm:{conversation.id.hex}:{conversation.preview_version}"
    )
    existing_job = session.scalar(
        select(ProcessingJob).where(ProcessingJob.idempotency_key == idempotency_key)
    )
    if existing_job is not None:
        existing = session.get(Investigation, existing_job.investigation_id)
        _clear_conversation_draft(conversation)
        reply = (
            f"Your investigation is registered.\nReference: {existing.reference}"
            if existing is not None
            else "Your investigation is already registered. Send STATUS to check its progress."
        )
        _append_turn(
            conversation,
            user_text=user_text,
            reply=reply,
            message_id=event.message_id,
            now=now,
        )
        _complete_inbound_event(session, event=event, reply=reply)
        session.commit()
        return reply, True

    content = conversation.draft_text or "\n".join(
        item["text"] for item in conversation.proposed_claims
    )
    input_type = InputType(conversation.draft_input_type or InputType.TEXT.value)
    investigation = InvestigationService(session).create(
        owner_id=_owner_id(settings),
        content=content,
        input_type=input_type,
        idempotency_key=idempotency_key,
        channel=Channel.WHATSAPP,
        source_metadata={
            "platform": "meta_cloud_api",
            "sender_ref": conversation.sender_ref,
            "message_type": "TEXT",
            "conversation_id": str(conversation.id),
            "approved_preview_version": conversation.preview_version,
        },
        enqueue=False,
        commit=False,
    )
    claims = [
        Claim(
            investigation_id=investigation.id,
            text=item["text"],
            normalized_text=normalize_claim_text(item["text"]),
            claim_type=item["claim_type"],
            needs_deep_investigation=item["claim_type"] != "SETTLED_FACT",
        )
        for item in conversation.proposed_claims
    ]
    queries: list[tuple[str, dict[str, object]]] = []
    valid_freshness = {"CURRENT", "HISTORICAL", "BALANCED"}
    valid_lanes = {"PRIMARY", "REFERENCE_REPORTING", "FACT_CHECK", "SOCIAL"}
    from app.modules.investigations.orchestrator import _query_for_freshness

    for query in (conversation.proposed_queries or [])[
        : settings.max_search_queries
    ]:
        text = query.get("text")
        claim_index = query.get("claim_index", 0)
        freshness = query.get("freshness", "BALANCED")
        source_lane = query.get("source_lane", "PRIMARY")
        if (
            not isinstance(text, str)
            or not text.strip()
            or not isinstance(claim_index, int)
            or not 0 <= claim_index < len(claims)
            or not isinstance(freshness, str)
            or freshness not in valid_freshness
            or not isinstance(source_lane, str)
            or source_lane not in valid_lanes
        ):
            continue
        route_metadata: dict[str, object] = {
            "claim_index": claim_index,
            "freshness": freshness,
            "topic": str(query.get("topic", "general"))[:80],
            "jurisdiction": [
                str(value)[:80]
                for value in query.get("jurisdiction", [])[:5]
                if isinstance(value, str)
            ],
            "source_lane": source_lane,
            "widening_reason": str(query.get("widening_reason", ""))[:240],
        }
        queries.append((_query_for_freshness(text.strip(), freshness), route_metadata))
    if not queries:
        queries = [
            (
                item["text"][:500],
                {
                    "claim_index": index,
                    "freshness": "BALANCED",
                    "topic": "general",
                    "jurisdiction": [],
                    "source_lane": "PRIMARY",
                    "widening_reason": "Initial primary-source pass for the confirmed claim.",
                },
            )
            for index, item in enumerate(conversation.proposed_claims)
        ]
    for query_text, route_metadata in queries:
        for provider in ("EXA", "OPENAI_WEB_SEARCH"):
            session.add(
                SearchTrace(
                    investigation_id=investigation.id,
                    provider=provider,
                    action="planned",
                    query=query_text,
                    route_metadata=route_metadata,
                    sources=[],
                    citations=[],
                )
            )
    job = ProcessingJob(
        id=uuid4(),
        investigation_id=investigation.id,
        stage="RECEIVED",
        status="QUEUED",
        idempotency_key=idempotency_key,
    )
    notification_preference = _notification_preference(
        session, settings=settings, sender_ref=conversation.sender_ref
    )
    notification_enabled = (
        notification_preference is None
        or not notification_preference.notifications_disabled
    ) and bool(getattr(settings, "whatsapp_support_url", None))
    session.add_all(
        [
            *claims,
            job,
            OutboxEvent(
                aggregate_id=investigation.id,
                event_type="INVESTIGATION_RECEIVED",
                payload={
                    "investigation_id": str(investigation.id),
                    "job_id": str(job.id),
                },
            ),
            AuditEvent(
                investigation_id=investigation.id,
                event_type="WHATSAPP_CLAIM_CONFIRMED",
                actor="whatsapp-user",
                event_metadata={
                    "conversation_id": str(conversation.id),
                    "preview_version": conversation.preview_version,
                    "completion_notification_consent": (
                        "opted_out"
                        if notification_preference is not None
                        and notification_preference.notifications_disabled
                        else "preview_submit_v1"
                        if notification_enabled
                        else "support_path_unavailable"
                    ),
                },
            ),
        ]
    )
    investigation.current_stage = "RECEIVED"
    reference = investigation.reference
    _clear_conversation_draft(conversation)
    if notification_preference is not None and notification_preference.notifications_disabled:
        update_expectation = (
            "Automatic updates are off. Send HISTORY or RESULT <reference> when you want "
            "the result."
        )
    elif not getattr(settings, "whatsapp_support_url", None):
        update_expectation = (
            "Automatic result messages are not available yet. Send HISTORY or "
            "RESULT <reference> when you want an update."
        )
    else:
        update_expectation = (
            "I’ll message you here with the result when it’s ready, if it finishes within "
            "WhatsApp’s 24-hour reply window. If you don’t receive it, send HISTORY or "
            "RESULT <reference>."
        )
    reply = (
        "Your investigation is registered. I’ll assess the available evidence and explain "
        f"what remains uncertain.\nReference: {reference}\n{update_expectation}"
    )
    _append_turn(
        conversation,
        user_text=user_text,
        reply=reply,
        message_id=event.message_id,
        now=now,
    )
    _complete_inbound_event(session, event=event, reply=reply)
    session.commit()
    return reply, True


async def _handle_turn(
    session: Session, event: ConversationTurn, settings, send_message
) -> bool:
    """Handle conversation turns separately from investigation records."""
    sender_ref = _sender_reference(
        event.sender, settings.whatsapp_identity_key.get_secret_value()
    )
    now = datetime.now(UTC)
    conversation = _conversation_for_sender(
        session, owner_id=_owner_id(settings), sender_ref=sender_ref, now=now
    )
    saved_reply = _claim_inbound_event(
        session,
        conversation=conversation,
        event=event,
        sender_ref=sender_ref,
        now=now,
    )
    if saved_reply is not None:
        if saved_reply:
            await run_in_threadpool(send_message, event.sender, saved_reply)
        return True

    conversation.recipient_encrypted = _encrypt_recipient(event.sender, settings)
    conversation.last_inbound_at = now

    if event.message_type not in {"text", "interactive"} or event.text is None:
        await _send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            user_text="[unsupported message type]",
            reply=(
                "I can chat about an investigation or help check a factual claim. "
                "Text and public URLs are supported for starting a check."
            ),
            send_message=send_message,
        )
        return True

    command = event.text.strip()
    if len(command) > MAX_MESSAGE_CHARS:
        await _send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            user_text=command,
            reply=(
                f"That message is too long. Please keep it under "
                f"{MAX_MESSAGE_CHARS:,} characters."
            ),
            send_message=send_message,
        )
        return True

    previous_reply = next(
        (
            item.get("reply", "")
            for item in reversed(conversation.processed_events or [])
            if item.get("message_id") == event.message_id
        ),
        None,
    )
    if previous_reply is not None:
        _complete_inbound_event(session, event=event, reply=previous_reply)
        session.commit()
        await run_in_threadpool(send_message, event.sender, previous_reply)
        return True

    normalized_command = " ".join(command.casefold().split())
    if any(
        normalized_command == " ".join(item.get("reply", "").casefold().split())
        for item in (conversation.processed_events or [])
    ):
        # Some inbox automation replays the agent's own outbound text as inbound.
        _complete_inbound_event(session, event=event, reply="", state="IGNORED")
        session.commit()
        return True

    pending = conversation.state in {"NEEDS_CLARIFICATION", "AWAITING_CONFIRMATION"}
    draft_expiry = conversation.draft_expires_at
    if draft_expiry is not None and draft_expiry.tzinfo is None:
        draft_expiry = draft_expiry.replace(tzinfo=UTC)
    if pending and (draft_expiry is None or draft_expiry <= now):
        _clear_conversation_draft(conversation)
        if _looks_like_confirmation(command):
            await _send_saved_reply(
                session,
                conversation=conversation,
                event=event,
                send_message=send_message,
                user_text=command,
                reply=(
                    "That preview expired, so I didn't start an investigation. "
                    "Please send the claim again and I'll prepare a fresh preview."
                ),
            )
            return True
        pending = False

    folded = command.casefold()
    if not pending and folded in {
        "start",
        "start investigation",
        "submit",
        "submit claim",
        "confirm",
        "yes",
    }:
        await _send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=(
                "There isn’t a claim preview to start yet. Tell me the specific claim you want "
                "checked, and I’ll prepare one for you to review. Nothing has started."
            ),
        )
        return True
    if folded == "help":
        reply = (
            "Hi, I’m Agent Zero. I can talk through a story or investigate a factual claim "
            "using public evidence. I’ll show you the claim before starting an investigation. "
            "Send HISTORY to see your recent case references, RESULT for the latest result "
            "or RESULT <reference> for one case, "
            "or STATUS <reference> for progress. Send STOP to turn off automatic result "
            "messages."
        )
        await _send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=reply,
        )
        return True
    if folded in {"stop", "mute", "alerts off", "notifications off"}:
        preference = _notification_preference(
            session, settings=settings, sender_ref=sender_ref
        )
        if preference is None:
            session.add(
                WhatsAppNotificationPreference(
                    owner_id=_owner_id(settings),
                    sender_ref=sender_ref,
                    notifications_disabled=True,
                )
            )
        else:
            preference.notifications_disabled = True
        reply = (
            "Automatic result messages are off. Your checks will continue. Send ALERTS ON "
            "to turn them back on, or HISTORY to see your case references."
        )
        await _send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=reply,
        )
        return True
    if folded in {"alerts on", "notifications on"}:
        preference = _notification_preference(
            session, settings=settings, sender_ref=sender_ref
        )
        if preference is not None:
            session.delete(preference)
        if getattr(settings, "whatsapp_support_url", None):
            reply = (
                "Automatic result messages are on for checks you submit. I’ll send the result "
                "here if it finishes within WhatsApp’s 24-hour reply window. Send STOP any time."
            )
        else:
            reply = (
                "I’ve saved your preference, but automatic result messages are not available "
                "yet. Send HISTORY or RESULT <reference> to check a case."
            )
        await _send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=reply,
        )
        return True
    if folded == "retry" or folded == "try again" or folded.startswith("retry "):
        reference = command[5:].strip() if folded.startswith("retry ") else None
        if reference and not re.fullmatch(
            r"AZ-[0-9]{6}-[A-F0-9]{6}", reference, re.IGNORECASE
        ):
            reply = "Send RETRY or RETRY followed by the case reference."
        else:
            reply = _retry_message(
                session, settings=settings, sender_ref=sender_ref, reference=reference
            )
        await _send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=reply,
        )
        return True
    if folded in {"result", "results"} or folded.startswith(("result ", "results ")):
        reference = re.sub(r"^results?\s*", "", command, flags=re.IGNORECASE).strip() or None
        if reference and not re.fullmatch(
            r"AZ-[0-9]{6}-[A-F0-9]{6}", reference, re.IGNORECASE
        ):
            reply = "Send RESULT or RESULT followed by the case reference."
        else:
            reply = _result_message(
                session,
                settings=settings,
                sender_ref=sender_ref,
                reference=reference,
                conversation_id=conversation.id,
            )
        await _send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=reply,
        )
        return True
    if folded == "status" or folded.startswith("status "):
        reference = command[6:].strip() or None
        if reference and not re.fullmatch(
            r"AZ-[0-9]{6}-[A-F0-9]{6}", reference, re.IGNORECASE
        ):
            reply = "Send STATUS or STATUS followed by the case reference."
        else:
            reply = _status_message(
                session, settings=settings, sender_ref=sender_ref, reference=reference
            )
        await _send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=reply,
        )
        return True
    if folded in {
        "history",
        "case history",
        "cases",
        "my checks",
        "my investigations",
        "my cases",
        "list investigations",
    } or folded in {"history more", "cases more"} or folded.startswith("history "):
        if folded in {"history more", "cases more"}:
            page = 2
        elif folded in {
            "history",
            "case history",
            "cases",
            "my checks",
            "my investigations",
            "my cases",
            "list investigations",
        }:
            page = 1
        else:
            page_text = command.split(maxsplit=1)[1]
            if page_text.isdigit() and 1 <= int(page_text) <= 100:
                page = int(page_text)
            else:
                page = 0
        reply = (
            "Send HISTORY, HISTORY MORE, or HISTORY followed by a page number."
            if page == 0
            else _case_list_message(
                session, settings=settings, sender_ref=sender_ref, page=page
            )
        )
        await _send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=reply,
        )
        return True
    interactive_cancel = event.message_type == "interactive" and folded.startswith("cancel")
    if interactive_cancel:
        code = _preview_button_code(command, "CANCEL")
        if (
            not pending
            or conversation.state != "AWAITING_CONFIRMATION"
            or code != conversation.confirmation_token
        ):
            await _send_saved_reply(
                session,
                conversation=conversation,
                event=event,
                send_message=send_message,
                user_text=command,
                reply=(
                    "That action belongs to an older preview, so I didn’t change anything. "
                    "Review the latest preview or send CANCEL to discard the current draft."
                ),
            )
            return True
        _clear_conversation_draft(conversation)
        await _send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply="Cancelled the draft. No investigation was started.",
        )
        return True
    if folded == "cancel":
        if pending:
            _clear_conversation_draft(conversation)
            reply = "Cancelled the draft. No investigation was started."
        else:
            reply = (
                "There’s no unsubmitted investigation draft to cancel. "
                "Your existing investigations are unchanged."
            )
        await _send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=reply,
        )
        return True
    interactive_edit = event.message_type == "interactive" and folded.startswith("edit")
    if interactive_edit and (
        not pending
        or conversation.state != "AWAITING_CONFIRMATION"
        or _preview_button_code(command, "EDIT") != conversation.confirmation_token
    ):
        await _send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=(
                "That action belongs to an older preview, so I didn’t change anything. "
                "Review the latest preview or send EDIT followed by your correction."
            ),
        )
        return True
    if pending and conversation.state == "AWAITING_CONFIRMATION" and (
        folded in {"edit", "edit claim"} or interactive_edit
    ):
        conversation.state = "NEEDS_CLARIFICATION"
        conversation.proposed_claims = []
        conversation.proposed_queries = []
        conversation.confirmation_token = None
        conversation.preview_version += 1
        conversation.clarification_question = "Send the corrected claim or missing detail."
        conversation.draft_expires_at = now + timedelta(minutes=30)
        await _send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=(
                "Send the corrected claim or missing detail in your next message. "
                "I’ll prepare a new preview before anything starts. "
                "Send CANCEL to discard the draft."
            ),
        )
        return True
    if pending and conversation.state == "AWAITING_CONFIRMATION":
        folded_prefix = folded.split(maxsplit=1)[0] if folded else ""
        if folded_prefix in {"submit", "confirm"}:
            code = _preview_code_in(command)
            if code is None:
                reply = (
                    "Tap Submit claim below to approve this exact preview, or reply "
                    f"SUBMIT {conversation.confirmation_token}. No investigation has started."
                )
                await _send_saved_reply(
                    session,
                    conversation=conversation,
                    event=event,
                    send_message=send_message,
                    user_text=command,
                    reply=reply,
                    buttons=[
                        (f"SUBMIT {conversation.confirmation_token}", "Submit claim"),
                        (f"EDIT {conversation.confirmation_token}", "Edit claim"),
                        (f"CANCEL {conversation.confirmation_token}", "Cancel"),
                    ],
                )
                return True
            reply, saved = await _confirm_conversation_draft(
                session,
                conversation=conversation,
                event=event,
                settings=settings,
                user_text=command,
                confirmation_code=code,
            )
            if saved:
                await run_in_threadpool(send_message, event.sender, reply)
            else:
                await _send_saved_reply(
                    session,
                    conversation=conversation,
                    event=event,
                    send_message=send_message,
                    user_text=command,
                    reply=reply,
                )
            return True

    draft_text = conversation.draft_text if pending else None
    if pending and folded.startswith("edit "):
        command = command[5:].strip()
        draft_text = command
        _clear_conversation_draft(conversation)
        pending = False

    context = list(conversation.context_json or [])
    if draft_text:
        context.append(
            {
                "role": "assistant",
                "content": f"Active investigation draft: {draft_text[:1200]}",
            }
        )
    try:
        model_run = await ModelGateway().interpret_whatsapp_turn(
            text=command,
            context=context,
            active_draft=draft_text,
            draft_state=conversation.state if pending else None,
            confirmation_token=conversation.confirmation_token if pending else None,
            session=session,
            conversation_id=conversation.id,
        )
    except (ModelInvocationFailed, ModelCallBudgetExceeded) as exc:
        logger.warning(
            "WhatsApp conversational model unavailable category=%s", type(exc).__name__
        )
        reply = _model_unavailable_reply(exc)
        await _send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=event.text,
            reply=reply,
        )
        return True

    output = model_run.output
    logger.info(
        "WhatsApp conversation classified intent=%s draft_pending=%s",
        output.intent,
        pending,
    )
    reply_buttons: list[tuple[str, str]] | None = None
    if output.intent == "CONFIRM_DRAFT":
        code = _preview_code_in(command)
        if not pending or conversation.state != "AWAITING_CONFIRMATION":
            reply = (
                "There is no current claim preview to approve. "
                "Ask me to investigate a claim first."
            )
        elif code is None:
            reply = (
                "Tap Submit claim below to approve this exact preview, or reply "
                f"SUBMIT {conversation.confirmation_token}. No investigation has started."
            )
            reply_buttons = [
                (f"SUBMIT {conversation.confirmation_token}", "Submit claim"),
                (f"EDIT {conversation.confirmation_token}", "Edit claim"),
                (f"CANCEL {conversation.confirmation_token}", "Cancel"),
            ]
        else:
            reply, saved = await _confirm_conversation_draft(
                session,
                conversation=conversation,
                event=event,
                settings=settings,
                user_text=command,
                confirmation_code=code,
            )
            if saved:
                await run_in_threadpool(send_message, event.sender, reply)
                return True
            await _send_saved_reply(
                session,
                conversation=conversation,
                event=event,
                send_message=send_message,
                user_text=command,
                reply=reply,
            )
            return True
    elif output.intent == "CONVERSATION":
        # Luna owns the wording for ordinary conversation. Application policy
        # still owns intents, authorization, case creation, and all side effects.
        reply = output.reply.strip() or "I’m here. What would you like to talk about?"
    elif output.intent == "CASE_LIST_REQUEST":
        reply = _case_list_message(session, settings=settings, sender_ref=sender_ref)
    elif output.intent == "STATUS_REQUEST":
        reply = _status_message(
            session,
            settings=settings,
            sender_ref=sender_ref,
            reference=output.reference,
        )
    elif output.intent == "RESULT_REQUEST":
        reply = _result_message(
            session,
            settings=settings,
            sender_ref=sender_ref,
            reference=output.reference,
        )
    elif output.intent == "CANCEL_DRAFT":
        if pending:
            _clear_conversation_draft(conversation)
            reply = "Cancelled the draft. No investigation was started."
        else:
            reply = (
                "There’s no unsubmitted investigation draft to cancel. "
                "Your existing investigations are unchanged."
            )
    elif output.intent == "INVESTIGATION_REQUEST" and any(
        _UNRESOLVED_CLAIM_PATTERN.search(claim.text) for claim in output.claims
    ):
        conversation.draft_text = (
            f"{draft_text}\nClarification: {command}"
            if pending and draft_text
            else (draft_text or command)
        )
        conversation.proposed_claims = []
        conversation.proposed_queries = []
        conversation.confirmation_token = None
        conversation.preview_version += 1
        conversation.draft_expires_at = now + timedelta(minutes=30)
        conversation.clarification_question = (
            "Which exact entity or public source should I use to identify this subject?"
        )
        conversation.state = "NEEDS_CLARIFICATION"
        reply = (
            "I can’t prepare a reliable claim preview from that question without filling in "
            "missing facts. Please share a public URL or enough context to identify the exact "
            "subject. I won’t guess at a date or what kind of entity it is. "
            "No investigation has started."
        )
    elif output.intent == "INVESTIGATION_REQUEST":
        conversation.draft_text = (
            f"{draft_text}\nClarification: {command}"
            if pending and draft_text
            else (draft_text or command)
        )
        parsed = urlsplit(conversation.draft_text.strip())
        if parsed.scheme in {"http", "https"} and (
            not parsed.hostname or parsed.username or parsed.password
        ):
            _clear_conversation_draft(conversation)
            reply = (
                "That link doesn’t look valid. Send a public http or https URL or "
                "describe the claim in your own words."
            )
        else:
            conversation.draft_input_type = (
                InputType.URL.value
                if parsed.scheme in {"http", "https"}
                else InputType.TEXT.value
            )
            conversation.preview_version += 1
            conversation.draft_expires_at = now + timedelta(minutes=30)
            conversation.clarification_question = output.clarification_question
            if not output.claims:
                conversation.proposed_claims = []
                conversation.confirmation_token = None
                conversation.state = (
                    "NEEDS_CLARIFICATION" if output.clarification_question else "IDLE"
                )
                if output.clarification_question:
                    reply = (
                        f"{output.clarification_question}\n\n"
                        "No investigation has started. Reply with the missing detail or CANCEL."
                    )
                else:
                    _clear_conversation_draft(conversation)
                    reply = (
                        "I couldn't identify a clear factual claim to investigate from that. "
                        "Please send a specific claim or ask a focused question."
                    )
            else:
                conversation.proposed_claims = [
                    {"text": claim.text, "claim_type": claim.claim_type}
                    for claim in output.claims
                ]
                conversation.proposed_queries = [
                    {
                        "text": query.text,
                        "claim_index": query.claim_index,
                        "freshness": query.freshness,
                        "topic": query.topic,
                        "jurisdiction": query.jurisdiction,
                        "source_lane": query.source_lane,
                        "widening_reason": query.widening_reason,
                    }
                    for query in output.queries
                ]
                conversation.state = "AWAITING_CONFIRMATION"
                conversation.confirmation_token = secrets.token_hex(4).upper()
                claim_lines = "\n".join(f"• {claim.text}" for claim in output.claims)
                preference = _notification_preference(
                    session, settings=settings, sender_ref=sender_ref
                )
                if preference is not None and preference.notifications_disabled:
                    notification_notice = (
                        "Automatic result messages are off. Send ALERTS ON to opt back in; "
                        "otherwise use HISTORY or RESULT <reference>. "
                    )
                elif getattr(settings, "whatsapp_support_url", None):
                    notification_notice = (
                        "Submitting opts you into one WhatsApp result message when ready, "
                        "while the 24-hour reply window is open. Send STOP to turn it off. "
                    )
                else:
                    notification_notice = (
                        "Automatic result messages are not available yet. Use HISTORY or "
                        "RESULT <reference> to check later. "
                    )
                reply = (
                    f"Here’s what I understand you want investigated:\n\n{claim_lines}\n\n"
                    "I’ll look for relevant public evidence and explain important gaps. "
                    f"{notification_notice}"
                    "No investigation has started. Choose an action below. If buttons aren’t "
                    f"available, reply SUBMIT {conversation.confirmation_token}, EDIT followed "
                    "by your correction, or CANCEL."
                )
                reply_buttons = [
                    (f"SUBMIT {conversation.confirmation_token}", "Submit claim"),
                    (f"EDIT {conversation.confirmation_token}", "Edit claim"),
                    (f"CANCEL {conversation.confirmation_token}", "Cancel"),
                ]
    await _send_saved_reply(
        session,
        conversation=conversation,
        event=event,
        send_message=send_message,
        user_text=event.text,
        reply=reply,
        buttons=reply_buttons,
    )
    return True


class ConversationService:
    """Application boundary for channel-neutral conversation state transitions."""

    def __init__(self, session: Session, settings) -> None:
        self.session = session
        self.settings = settings

    async def handle_turn(
        self, turn: ConversationTurn, send_message
    ) -> bool:
        return await _handle_turn(self.session, turn, self.settings, send_message)
