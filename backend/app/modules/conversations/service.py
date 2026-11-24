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
from app.modules.conversations import messages as copy
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

_FAILURE_COPY = copy.FAILURE_REASONS


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


def _source_pairs(sources: list[Source]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
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
            pairs.append((label, safe_url))
    return pairs


def _source_bullets(sources: list[Source]) -> str:
    return "\n".join(f"• {label}: {url}" for label, url in _source_pairs(sources))


def _factual_answer_message(answer: str, citations: tuple[dict[str, str], ...]) -> str:
    clean_citations: list[tuple[str, str]] = []
    seen: set[str] = set()
    for citation in citations:
        url = citation.get("url", "").strip()
        title = " ".join(citation.get("title", "").split())[:100]
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or url in seen
        ):
            continue
        seen.add(url)
        clean_citations.append((title or parsed.hostname, url))
        if len(clean_citations) >= 3:
            break

    text = " ".join(answer.split()).strip()[:1400]
    if not text or not clean_citations:
        return (
            "I couldn’t find a cited source for a reliable quick answer, so I won’t guess. "
            "No investigation was started. Ask me to investigate the question for a fuller check."
        )
    header = "Quick answer from a fresh web search (not a full investigation):\n\n"
    source_header = "\n\nSources:\n"
    footer = "\n\nAsk me to investigate this question for a fuller evidence review."
    source_lines: list[str] = []
    for title, url in clean_citations:
        line = f"• {title}: {url}"
        candidate = header + text + source_header + "\n".join([*source_lines, line]) + footer
        if len(candidate) <= 3900:
            source_lines.append(line)
    if not source_lines:
        return (
            "I couldn’t fit a cited source into a reliable quick answer, so I won’t guess. "
            "No investigation was started. Ask me to investigate the question for a fuller check."
        )
    return header + text + source_header + "\n".join(source_lines) + footer


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
                "I’ve hit my chat limit for now. I’ll be back at "
                f"{reset_label}. I got your message, but nothing was started."
            )
        return (
            "I’ve hit my chat limit for now. I got your message, but nothing was started. "
            "Please try again later."
        )
    return (
        "Sorry, I’m having trouble right now and couldn’t answer. Nothing was started. "
        "Please try again in a few minutes."
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
        return copy.no_check_found()

    brief = session.scalar(
        select(VerificationBrief).where(VerificationBrief.investigation_id == investigation.id)
    )
    if brief is None:
        job = session.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.investigation_id == investigation.id)
            .order_by(ProcessingJob.created_at.desc())
        )
        in_progress = investigation.status not in {
            InvestigationStatus.FAILED,
            InvestigationStatus.CANCELLED,
            InvestigationStatus.NEEDS_REVIEW,
            InvestigationStatus.COMPLETE,
        }
        if in_progress:
            return copy.status_message(
                getattr(investigation, "current_stage", None),
                investigation.status.value,
                investigation.reference,
                queued_retry=False,
            )
        if investigation.status == InvestigationStatus.CANCELLED:
            return copy.fit("*This check was cancelled.*", investigation.reference)
        if investigation.status == InvestigationStatus.COMPLETE:
            return copy.fit(
                "*This check finished without a saved summary.* No conclusion is "
                "available. Please try again or contact support.",
                investigation.reference,
            )
        claims = list(
            session.scalars(
                select(Claim)
                .where(Claim.investigation_id == investigation.id)
                .order_by(Claim.created_at)
                .limit(3)
            )
        )
        category = job.error_code if job is not None else None
        retrieved = _retrieved_sources(session, investigation_id=investigation.id)
        if _retry_available(session, investigation):
            retry_line = (
                "To try again without resending the claim, reply "
                f"*RETRY {investigation.reference}*."
            )
        else:
            retry_line = (
                "A retry isn’t available right now. Keep the reference below if you "
                "contact support."
            )
        return copy.fit(
            copy.failed_without_summary(
                claims=[claim.text for claim in claims],
                reason=copy.failure_reason(category),
                sources=_source_bullets(retrieved),
                retry_line=retry_line,
            ),
            investigation.reference,
        )

    findings = list(
        session.scalars(
            select(Finding)
            .where(Finding.investigation_id == investigation.id)
            .order_by(Finding.created_at)
            .limit(5)
        )
    )
    stopped_early = investigation.status in {
        InvestigationStatus.NEEDS_REVIEW,
        InvestigationStatus.FAILED,
    }
    stopped_reason = None
    retry_hint = None
    if stopped_early:
        latest_job = session.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.investigation_id == investigation.id)
            .order_by(ProcessingJob.created_at.desc())
        )
        stopped_reason = copy.failure_reason(latest_job.error_code if latest_job else None)
        if _retry_available(session, investigation):
            retry_hint = f"Reply *RETRY {investigation.reference}* to try again."
    claims_by_id = {
        claim.id: claim.text
        for claim in session.scalars(
            select(Claim).where(Claim.investigation_id == investigation.id)
        )
    }
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
    return copy.result_message(
        [
            copy.FindingView(
                status=item.status,
                claim=claims_by_id.get(item.claim_id, ""),
                headline=item.statement,
                confidence=item.evidence_confidence,
                confidence_reason=item.confidence_rationale or "",
            )
            for item in findings
        ],
        sources=_source_pairs(linked_sources),
        limitations=[item for item in (brief.limitations or [])[:2] if item],
        reference=investigation.reference,
        stopped_early=stopped_early,
        stopped_reason=stopped_reason,
        retry_hint=retry_hint,
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
        return copy.no_check_found()

    latest_job = session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.investigation_id == investigation.id)
        .order_by(ProcessingJob.created_at.desc())
    )
    if latest_job is not None and not is_retryable_failure_code(latest_job.error_code):
        return copy.fit(
            "This kind of problem can’t be fixed by trying again. "
            "Send the claim again as a new check, or contact support.",
            investigation.reference,
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
                "This check can’t be retried from here. Please send the claim again as a "
                "new check, or contact support."
            ),
            "job_missing": (
                "I couldn’t find a saved run to retry. Please send the claim again."
            ),
            "already_running": (
                "A retry is already on its way. No need to send it again."
            ),
            "budget_exhausted": (
                "This check has used up its allowance, so it can’t be retried right now."
            ),
        }
        return copy.fit(messages[exc.reason], investigation.reference)

    return copy.fit(
        "*I’m trying again with your saved claim.* No need to resend it.\n"
        "Reply *STATUS* to see how it’s going.",
        investigation.reference,
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
        return copy.no_check_found()
    latest_job = session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.investigation_id == investigation.id)
        .order_by(ProcessingJob.created_at.desc())
    )
    retry_hint = None
    if investigation.status in {InvestigationStatus.NEEDS_REVIEW, InvestigationStatus.FAILED}:
        if _retry_available(session, investigation):
            retry_hint = f"Reply *RETRY {investigation.reference}* to try again."
        else:
            retry_hint = "A retry isn’t available right now."
    return copy.status_message(
        getattr(investigation, "current_stage", None),
        investigation.status.value,
        investigation.reference,
        queued_retry=latest_job is not None and latest_job.status == "QUEUED"
        and investigation.status
        in {InvestigationStatus.NEEDS_REVIEW, InvestigationStatus.FAILED},
        retry_hint=retry_hint,
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
            return "There are no older checks. Reply *HISTORY* to see your newest ones."
        return "You haven’t asked me to check anything yet. Send me a claim or a link to start."
    rows = []
    for case in cases:
        claim = session.scalar(
            select(Claim.text)
            .where(Claim.investigation_id == case.id)
            .order_by(Claim.created_at)
            .limit(1)
        )
        rows.append((case.reference, copy.case_status_label(case.status.value), claim or ""))
    return copy.history_message(rows, page=page)


def _preview_code_in(text: str) -> str | None:
    match = re.search(r"\b[A-F0-9]{8}\b", text, re.IGNORECASE)
    return match.group(0).upper() if match else None


def _preview_button_code(text: str, action: str) -> str | None:
    match = re.fullmatch(rf"{re.escape(action)}\s+([A-F0-9]{{8}})", text.strip(), re.IGNORECASE)
    return match.group(1).upper() if match else None


# Typed phrases that unambiguously approve the preview currently on screen. Deliberately
# excludes "ok" and "sawa", which people also use to acknowledge a message. Anything that
# adds a condition ("yes but change the date") is not a confirmation.
_STRICT_CONFIRMATIONS = frozenset({
    "yes", "yes please", "yes submit", "yes submit it", "yes go ahead", "go ahead",
    "go ahead and investigate", "submit", "submit claim", "confirm", "start", "proceed",
    "ndiyo", "ndio", "endelea", "tuma", "anza",
})


def _typed_confirmation_code(conversation, event, command: str) -> str | None:
    """Return the current preview code when the user typed a plain approval.

    Button taps always carry their own code, so a tap from an older preview is still
    rejected. A typed approval can only refer to the latest preview, which expires after
    30 minutes and is replaced whenever the claim is edited.
    """
    if event.message_type != "text" or conversation.state != "AWAITING_CONFIRMATION":
        return None
    normalized = " ".join(command.casefold().strip(" .!?").split())
    return conversation.confirmation_token if normalized in _STRICT_CONFIRMATIONS else None


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
            "That preview has expired. Send the claim again and I’ll prepare a fresh one.",
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
            "To start, tap *Submit claim* or reply *YES*. Nothing has started yet.",
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
            copy.fit("*This check is already underway.*", existing.reference)
            if existing is not None
            else "*This check is already underway.* Reply *STATUS* to see how it’s going."
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
            "Automatic messages are off. Reply *RESULT* when you want to see it."
        )
    elif not getattr(settings, "whatsapp_support_url", None):
        update_expectation = (
            "Reply *RESULT* in a few minutes to see it, or *STATUS* for progress."
        )
    else:
        update_expectation = (
            "I’ll message you here when it’s ready. If you don’t hear from me, reply *RESULT*."
        )
    reply = copy.registered_message(reference, update_expectation)
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
                "I can only read text and links in this chat for now. "
                "Paste the claim or a link and I’ll take a look."
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
                f"That message is too long for me. Please send the key part, under "
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

    command = copy.normalize_command_alias(command)
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
                "There’s nothing to submit yet. Tell me the claim you want checked and I’ll "
                "show you what I understood first. Nothing has started."
            ),
        )
        return True
    if folded == "help":
        reply = copy.help_message()
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
            "*Automatic result messages are off.* Your checks will still run. "
            "Reply *ALERTS ON* to turn them back on, or *HISTORY* to see your checks."
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
                "*Automatic result messages are on.* I’ll send each result here when it’s "
                "ready, as long as you’ve messaged me in the last 24 hours. Reply *STOP* any time."
            )
        else:
            reply = (
                "I’ve saved your choice, but automatic result messages aren’t available yet. "
                "Reply *RESULT* any time to see your latest result."
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
            reply = "To retry, reply *RETRY* or *RETRY* followed by the reference."
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
            reply = "To see a result, reply *RESULT* or *RESULT* followed by the reference."
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
            reply = "To check progress, reply *STATUS* or *STATUS* followed by the reference."
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
            "Reply *HISTORY* for your latest checks, or *HISTORY 2* for older ones."
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
                    "That button is from an older preview, so I ignored it. "
                    "Use the latest preview, or reply *CANCEL* to start over."
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
            reply="Cancelled. Nothing was started. Send another claim whenever you’re ready.",
        )
        return True
    if folded == "cancel":
        if pending:
            _clear_conversation_draft(conversation)
            reply = "Cancelled. Nothing was started. Send another claim whenever you’re ready."
        else:
            reply = (
                "There’s nothing waiting to cancel, and your existing checks are untouched."
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
                "That button is from an older preview, so I ignored it. "
                "Use the latest preview, or reply *EDIT* followed by your correction."
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
                "Send the corrected claim in your next message and I’ll show you a new "
                "preview before anything starts. Reply *CANCEL* to stop."
            ),
        )
        return True
    if pending and conversation.state == "AWAITING_CONFIRMATION":
        folded_prefix = folded.split(maxsplit=1)[0] if folded else ""
        typed_code = _typed_confirmation_code(conversation, event, command)
        if folded_prefix in {"submit", "confirm"} or typed_code is not None:
            code = _preview_code_in(command) or typed_code
            if code is None:
                reply = (
                    "Tap *Submit claim* below to start, or reply *YES*. "
                    "Nothing has started yet."
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
    gateway = ModelGateway()
    try:
        model_run = await gateway.interpret_whatsapp_turn(
            text=command,
            context=context,
            active_draft=draft_text,
            draft_state=conversation.state if pending else None,
            confirmation_token=conversation.confirmation_token if pending else None,
            session=session,
            conversation_id=conversation.id,
        )
        factual_run = None
        if model_run.output.intent == "FACTUAL_ANSWER_REQUEST" and not pending:
            factual_run = await gateway.answer_whatsapp_factual_question(
                text=command,
                context=context,
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
        code = _preview_code_in(command) or _typed_confirmation_code(conversation, event, command)
        if not pending or conversation.state != "AWAITING_CONFIRMATION":
            reply = (
                "There’s nothing to submit yet. Send me the claim you want checked first."
            )
        elif code is None:
            reply = (
                "Tap *Submit claim* below to start, or reply *YES*. "
                "Nothing has started yet."
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
    elif output.intent == "FACTUAL_ANSWER_REQUEST":
        if pending:
            reply = (
                "There’s a claim preview waiting in this chat. Approve, edit, or cancel it first; "
                "I won’t change its scope while it’s awaiting your decision."
            )
        else:
            answer = factual_run.output.answer if factual_run else ""
            citations = factual_run.citations if factual_run else ()
            reply = _factual_answer_message(answer, citations)
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
            reply = "Cancelled. Nothing was started. Send another claim whenever you’re ready."
        else:
            reply = (
                "There’s nothing waiting to cancel, and your existing checks are untouched."
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
                preference = _notification_preference(
                    session, settings=settings, sender_ref=sender_ref
                )
                if preference is not None and preference.notifications_disabled:
                    notification_notice = (
                        "Automatic messages are off, so reply *RESULT* later to see it."
                    )
                elif getattr(settings, "whatsapp_support_url", None):
                    notification_notice = (
                        "I’ll message you here with the result. Reply *STOP* if you’d rather not "
                        "get automatic messages."
                    )
                else:
                    notification_notice = (
                        "Reply *RESULT* a few minutes after submitting to see it."
                    )
                reply = copy.preview_message(
                    [claim.text for claim in output.claims],
                    notification_notice=notification_notice,
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
