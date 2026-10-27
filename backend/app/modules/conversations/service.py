"""Channel-neutral WhatsApp conversation and investigation handoff service."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.investigation import Channel, InputType, InvestigationStatus
from app.modules.conversations.models import WhatsAppConversation, WhatsAppInboundEvent
from app.modules.conversations.schemas import ConversationTurn
from app.modules.investigations.investigator import ModelGateway, ModelInvocationFailed
from app.modules.investigations.models import (
    AuditEvent,
    Claim,
    Finding,
    Investigation,
    OutboxEvent,
    ProcessingJob,
    SearchTrace,
    Submission,
    User,
    VerificationBrief,
)
from app.modules.investigations.service import DEV_USER_ID, InvestigationService
from app.modules.investigations.summary import finding_result_summary
from app.modules.investigations.triage import normalize_claim_text
from app.modules.investigations.usage import ModelCallBudgetExceeded

logger = logging.getLogger(__name__)
MAX_MESSAGE_CHARS = 20_000
INBOUND_EVENT_PROVIDER = "meta_whatsapp_cloud"
INBOUND_EVENT_LEASE = timedelta(minutes=3)


class ConversationTurnInProgress(RuntimeError):
    """A prior delivery of this inbound event is still being processed."""


def _sender_reference(sender: str, identity_key: str) -> str:
    return hmac.new(identity_key.encode(), sender.encode(), hashlib.sha256).hexdigest()


def _owner_id(settings) -> UUID:
    return settings.whatsapp_owner_id or DEV_USER_ID


def _result_message(
    session: Session,
    *,
    settings,
    sender_ref: str,
    reference: str | None,
) -> str:
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
    if reference:
        statement = statement.where(Investigation.reference == reference)
    else:
        statement = statement.order_by(Investigation.created_at.desc()).limit(1)
    investigation = session.scalar(statement)
    if investigation is None:
        return (
            "I couldn't find a check for this WhatsApp number. "
            "Send a claim or public URL to start one."
        )

    brief = session.scalar(
        select(VerificationBrief).where(VerificationBrief.investigation_id == investigation.id)
    )
    if brief is None:
        if investigation.status == InvestigationStatus.FAILED:
            message = "This check could not be completed. You can send the claim again later."
        elif investigation.status == InvestigationStatus.CANCELLED:
            message = "This check was cancelled before an assessment was ready."
        elif investigation.status == InvestigationStatus.NEEDS_REVIEW:
            message = (
                "This check needs a human review. No final assessment is available yet; "
                "please review the case in Agent Zero."
            )
        elif investigation.status == InvestigationStatus.COMPLETE:
            message = (
                "This check finished without a saved summary. No conclusion is available; "
                "please review the case in Agent Zero."
            )
        else:
            message = "This check is still processing. Send RESULT again in a little while."
        return f"{message}\nReference: {investigation.reference}"

    findings = list(
        session.scalars(
            select(Finding)
            .where(Finding.investigation_id == investigation.id)
            .order_by(Finding.created_at)
            .limit(5)
        )
    )
    summary = finding_result_summary(findings, max_chars=2600)
    limitations = [item[:260] for item in (brief.limitations or [])[:3] if item]
    limitation_text = "\n\nLimitations: " + "; ".join(limitations) if limitations else ""
    return f"{summary}{limitation_text}\n\nReference: {investigation.reference}"[:3900]


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
    labels = {
        "RECEIVED": "queued",
        "PROCESSING": "processing",
        "ANALYZING": "analyzing the claim",
        "RESEARCHING": "reviewing sources",
        "CORROBORATING": "comparing evidence",
        "GENERATING_BRIEF": "preparing the assessment",
        "COMPLETE": "complete",
        "NEEDS_REVIEW": "needs human review; no final assessment is ready",
        "FAILED": "could not be completed; no conclusion is available",
        "CANCELLED": "cancelled",
    }
    label = labels.get(investigation.status.value, "in progress")
    return (
        f"Your investigation is {label}. This status does not establish whether the claim is "
        f"true.\n"
        f"Reference: {investigation.reference}"
    )


def _case_list_message(session: Session, *, settings, sender_ref: str) -> str:
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
            .order_by(Investigation.created_at.desc())
            .limit(5)
        )
    )
    if not cases:
        return "You don't have an investigation yet. Tell me what you'd like me to look into."
    lines = ["Your recent investigations:"]
    for case in cases:
        status = case.current_stage.replace("_", " ").lower()
        lines.append(f"• {case.reference} — {status}")
    return "\n".join(lines)


def _preview_code_in(text: str) -> str | None:
    match = re.search(r"\b[A-F0-9]{8}\b", text, re.IGNORECASE)
    return match.group(0).upper() if match else None


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


def _conversation_reply(text: str) -> str:
    normalized = " ".join(text.casefold().split())
    standard_greeting = normalized in {
        "hi",
        "hello",
        "hey",
        "good morning",
        "good afternoon",
    }
    if standard_greeting or normalized.startswith(("hi ", "hello ", "hey ")):
        return (
            "Hi, I’m Agent Zero. I can talk through what you’ve shared or help investigate a "
            "factual claim using public evidence. What are you looking into?"
        )
    capability_phrases = ("what can you do", "how can you help", "who are you")
    if any(phrase in normalized for phrase in capability_phrases):
        return (
            "I can help frame and investigate factual claims, then report what the available "
            "evidence supports and what remains uncertain. I won’t start an investigation until "
            "you approve its preview."
        )
    if "?" in text:
        return (
            "I haven’t checked that yet. If you’d like an evidence-based answer, ask me to "
            "investigate the claim and I’ll show you a preview first."
        )
    return "Thanks for the context. What would you like me to help investigate?"


async def _send_saved_reply(
    session: Session,
    *,
    conversation: WhatsAppConversation,
    event: ConversationTurn,
    user_text: str,
    reply: str,
    send_message,
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
        investigation_id=investigation.id,
        stage="RECEIVED",
        status="QUEUED",
        idempotency_key=idempotency_key,
    )
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
                },
            ),
        ]
    )
    investigation.current_stage = "RECEIVED"
    reference = investigation.reference
    _clear_conversation_draft(conversation)
    reply = (
        "Your investigation has been registered. I’ll assess the available evidence and show "
        f"what remains uncertain.\nReference: {reference}\nAsk me for an update at any time."
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
    if folded == "help":
        reply = (
            "Hi, I’m Agent Zero. I can talk through a story or investigate a factual claim "
            "using public evidence. I’ll show you the claim before starting an investigation. "
            "You can ask naturally, or send RESULT / STATUS to check your latest case."
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
    if folded == "result" or folded.startswith("result "):
        reference = command[6:].strip() or None
        if reference and not re.fullmatch(
            r"AZ-[0-9]{6}-[A-F0-9]{6}", reference, re.IGNORECASE
        ):
            reply = "Send RESULT or RESULT followed by the case reference."
        else:
            reply = _result_message(
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
    if folded in {"my investigations", "my cases", "list investigations"}:
        reply = _case_list_message(session, settings=settings, sender_ref=sender_ref)
        await _send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=reply,
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
    if pending and conversation.state == "AWAITING_CONFIRMATION":
        folded_prefix = folded.split(maxsplit=1)[0] if folded else ""
        if folded_prefix in {"submit", "confirm"}:
            code = _preview_code_in(command)
            if code is None:
                reply = (
                    "To approve this exact preview, reply "
                    f"SUBMIT {conversation.confirmation_token}. No investigation has started."
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
        reply = (
            "I’m having trouble understanding that message right now. "
            "No investigation was started. Please try again shortly."
        )
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
    if output.intent == "CONFIRM_DRAFT":
        code = _preview_code_in(command)
        if not pending or conversation.state != "AWAITING_CONFIRMATION":
            reply = (
                "There is no current claim preview to approve. "
                "Ask me to investigate a claim first."
            )
        elif code is None:
            reply = (
                "I can approve this preview once you include its code: "
                f"SUBMIT {conversation.confirmation_token}. No investigation has started."
            )
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
                reply = (
                    f"Here’s what I understand you want investigated:\n\n{claim_lines}\n\n"
                    "I’ll look for relevant public evidence and explain important gaps. "
                    "No investigation has started yet. To approve this exact preview, reply "
                    f"SUBMIT {conversation.confirmation_token}. You can also confirm naturally "
                    "with that code, EDIT followed by your correction, or CANCEL."
                )
    else:
        reply = _conversation_reply(command)

    await _send_saved_reply(
        session,
        conversation=conversation,
        event=event,
        send_message=send_message,
        user_text=event.text,
        reply=reply,
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
