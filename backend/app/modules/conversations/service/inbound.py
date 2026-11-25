"""Conversation state, inbound delivery receipts and sending saved replies."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.conversations.models import (
    WhatsAppConversation,
    WhatsAppInboundEvent,
)
from app.modules.conversations.schemas import ConversationTurn
from app.modules.conversations.service import common, ports
from app.modules.investigations.models import (
    User,
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
            WhatsAppInboundEvent.provider == common.INBOUND_EVENT_PROVIDER,
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
            raise common.ConversationTurnInProgress
        receipt.attempts += 1
        receipt.state = "PROCESSING"
        receipt.reply_text = None
        receipt.lease_expires_at = now + common.INBOUND_EVENT_LEASE
        session.commit()
    else:
        if receipt is None:
            receipt = WhatsAppInboundEvent(
                conversation_id=conversation.id,
                provider=common.INBOUND_EVENT_PROVIDER,
                message_id=event.message_id,
                sender_ref=sender_ref,
                state="PROCESSING",
                attempts=1,
                lease_expires_at=now + common.INBOUND_EVENT_LEASE,
                expires_at=now + timedelta(hours=24),
            )
            session.add(receipt)
        else:
            receipt.conversation_id = conversation.id
            receipt.sender_ref = sender_ref
            receipt.state = "PROCESSING"
            receipt.reply_text = None
            receipt.attempts = 1
            receipt.lease_expires_at = now + common.INBOUND_EVENT_LEASE
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
            WhatsAppInboundEvent.provider == common.INBOUND_EVENT_PROVIDER,
            WhatsAppInboundEvent.message_id == event.message_id,
        )
    )
    if receipt is None:
        raise RuntimeError("WhatsApp inbound receipt disappeared before completion")
    receipt.state = state
    receipt.reply_text = reply[:4096]
    receipt.lease_expires_at = datetime.now(UTC)


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
        await ports.run_in_threadpool(send_message, event.sender, reply, buttons)
    else:
        await ports.run_in_threadpool(send_message, event.sender, reply)
