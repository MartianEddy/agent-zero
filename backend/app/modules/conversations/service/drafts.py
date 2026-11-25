"""Claim previews: building, confirming and loop-breaking helpers."""

from __future__ import annotations

import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.investigation import Channel, InputType
from app.modules.conversations import messages as copy
from app.modules.conversations.models import (
    WhatsAppConversation,
)
from app.modules.conversations.schemas import ConversationTurn
from app.modules.conversations.service import common, identity, inbound, ports
from app.modules.investigations.models import (
    AuditEvent,
    Claim,
    Investigation,
    OutboxEvent,
    ProcessingJob,
    SearchTrace,
)
from app.modules.investigations.triage import normalize_claim_text


def _preview_code_in(text: str) -> str | None:
    match = re.search(r"\b[A-F0-9]{8}\b", text, re.IGNORECASE)
    return match.group(0).upper() if match else None


def _preview_button_code(text: str, action: str) -> str | None:
    match = re.fullmatch(rf"{re.escape(action)}\s+([A-F0-9]{{8}})", text.strip(), re.IGNORECASE)
    return match.group(1).upper() if match else None


def _typed_confirmation_code(conversation, event, command: str) -> str | None:
    """Return the current preview code when the user typed a plain approval.

    Button taps always carry their own code, so a tap from an older preview is still
    rejected. A typed approval can only refer to the latest preview, which expires after
    30 minutes and is replaced whenever the claim is edited.
    """
    if event.message_type != "text" or conversation.state != "AWAITING_CONFIRMATION":
        return None
    normalized = " ".join(command.casefold().strip(" .!?").split())
    return conversation.confirmation_token if normalized in common._STRICT_CONFIRMATIONS else None


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
    } or normalized.startswith(("yes ", "go ahead", "please submit", "confirm ", "submit "))


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
        inbound._clear_conversation_draft(conversation)
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

    idempotency_key = f"meta-wa-confirm:{conversation.id.hex}:{conversation.preview_version}"
    existing_job = session.scalar(
        select(ProcessingJob).where(ProcessingJob.idempotency_key == idempotency_key)
    )
    if existing_job is not None:
        existing = session.get(Investigation, existing_job.investigation_id)
        inbound._clear_conversation_draft(conversation)
        reply = (
            copy.fit("*This check is already underway.*", existing.reference)
            if existing is not None
            else "*This check is already underway.* Reply *STATUS* to see how it’s going."
        )
        inbound._append_turn(
            conversation,
            user_text=user_text,
            reply=reply,
            message_id=event.message_id,
            now=now,
        )
        inbound._complete_inbound_event(session, event=event, reply=reply)
        session.commit()
        return reply, True

    content = conversation.draft_text or "\n".join(
        item["text"] for item in conversation.proposed_claims
    )
    input_type = InputType(conversation.draft_input_type or InputType.TEXT.value)
    investigation = ports.InvestigationService(session).create(
        owner_id=common._owner_id(settings),
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

    for query in (conversation.proposed_queries or [])[: settings.max_search_queries]:
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
    notification_preference = identity._notification_preference(
        session, settings=settings, sender_ref=conversation.sender_ref
    )
    notification_enabled = (
        notification_preference is None or not notification_preference.notifications_disabled
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
    inbound._clear_conversation_draft(conversation)
    if notification_preference is not None and notification_preference.notifications_disabled:
        update_expectation = "Automatic messages are off. Reply *RESULT* when you want to see it."
    elif not getattr(settings, "whatsapp_support_url", None):
        update_expectation = "Reply *RESULT* in a few minutes to see it, or *STATUS* for progress."
    else:
        update_expectation = (
            "I’ll message you here when it’s ready. If you don’t hear from me, reply *RESULT*."
        )
    reply = copy.registered_message(reference, update_expectation)
    inbound._append_turn(
        conversation,
        user_text=user_text,
        reply=reply,
        message_id=event.message_id,
        now=now,
    )
    inbound._complete_inbound_event(session, event=event, reply=reply)
    session.commit()
    return reply, True


def _draft_words(draft_text: str) -> str:
    """The user's own words from a draft, with clarification labels removed."""
    parts = [
        part.strip() for part in draft_text.split(common._CLARIFICATION_MARKER) if part.strip()
    ]
    return " ".join(parts)[:600]


def _clarification_rounds(draft_text: str | None) -> int:
    return (draft_text or "").count(common._CLARIFICATION_MARKER)


def _last_exchange(conversation: WhatsAppConversation) -> tuple[str, str]:
    turns = list(conversation.context_json or [])
    if len(turns) >= 2 and turns[-2].get("role") == "user" and turns[-1].get("role") == "assistant":
        return str(turns[-2].get("content", "")), str(turns[-1].get("content", ""))
    return "", ""


def _prepare_preview(
    session: Session,
    *,
    conversation: WhatsAppConversation,
    settings,
    sender_ref: str,
    claims: list[dict[str, str]],
    queries: list[dict[str, object]],
) -> tuple[str, list[tuple[str, str]]]:
    """Store a claim preview awaiting approval and return its message and buttons."""
    conversation.proposed_claims = claims
    conversation.proposed_queries = queries
    conversation.state = "AWAITING_CONFIRMATION"
    conversation.confirmation_token = secrets.token_hex(4).upper()
    conversation.clarification_question = None
    preference = identity._notification_preference(
        session, settings=settings, sender_ref=sender_ref
    )
    if preference is not None and preference.notifications_disabled:
        notice = "Automatic messages are off, so reply *RESULT* later to see it."
    elif getattr(settings, "whatsapp_support_url", None):
        notice = (
            "I’ll message you here with the result. Reply *STOP* if you’d rather not "
            "get automatic messages."
        )
    else:
        notice = "Reply *RESULT* a few minutes after submitting to see it."
    reply = copy.preview_message([claim["text"] for claim in claims], notification_notice=notice)
    buttons = [
        (f"SUBMIT {conversation.confirmation_token}", "Submit claim"),
        (f"EDIT {conversation.confirmation_token}", "Edit claim"),
        (f"CANCEL {conversation.confirmation_token}", "Cancel"),
    ]
    return reply, buttons


def _offer_check_as_written(conversation: WhatsAppConversation, question: str) -> tuple[str, list]:
    conversation.state = "NEEDS_CLARIFICATION"
    conversation.proposed_claims = []
    conversation.confirmation_token = None
    reply = (
        f"{question}\n\n"
        "If it’s easier, tap *Check as written* and I’ll check your message exactly as you "
        "wrote it. Or reply *CANCEL*. Nothing has started yet."
    )
    return reply, [("CHECK AS IS", "Check as written")]


_GREETING = re.compile(
    r"^(hi|hey|hello|hallo|good (morning|afternoon|evening)|habari|mambo|niaje|sasa|"
    r"vipi|salamu|jambo|hujambo)\b[\s!.,?]*\w{0,12}[\s!.,?]*$",
    re.IGNORECASE,
)


def _reply_without_model(
    session: Session,
    *,
    conversation: WhatsAppConversation,
    settings,
    sender_ref: str,
    command: str,
    pending: bool,
    now: datetime,
) -> tuple[str, list[tuple[str, str]] | None]:
    """A useful reply built from the user's own words when the AI does not answer in time.

    The user never sees an error: a waiting preview is offered again, a greeting gets a
    greeting, and anything that reads like a claim or question becomes a claim preview.
    """
    if (
        pending
        and conversation.state == "AWAITING_CONFIRMATION"
        and conversation.confirmation_token
    ):
        token = conversation.confirmation_token
        claims = "\n".join(f"- {item['text']}" for item in conversation.proposed_claims or [])
        return (
            f"Your claim is ready to check:\n\n{claims}\n\n"
            "Reply *YES* to start, *EDIT* to change it, or *CANCEL*.",
            [
                (f"SUBMIT {token}", "Submit claim"),
                (f"EDIT {token}", "Edit claim"),
                (f"CANCEL {token}", "Cancel"),
            ],
        )
    text = " ".join(command.split())
    if _GREETING.match(text):
        return (
            "Hi! I check claims against public sources. Send me a claim, a link, or a "
            "question you want checked, and I’ll show you what I’ll check before I start.",
            None,
        )
    if len(text.split()) >= 4:
        parsed = urlsplit(text)
        conversation.draft_text = text
        conversation.draft_input_type = (
            InputType.URL.value if parsed.scheme in {"http", "https"} else InputType.TEXT.value
        )
        conversation.preview_version += 1
        conversation.draft_expires_at = now + timedelta(minutes=30)
        return _prepare_preview(
            session,
            conversation=conversation,
            settings=settings,
            sender_ref=sender_ref,
            claims=[{"text": text[:600], "claim_type": "CHECKABLE_EVENT"}],
            queries=[],
        )
    return (
        "What would you like me to check? Send the claim, a link, or the message you "
        "received, and I’ll take it from there.",
        None,
    )
