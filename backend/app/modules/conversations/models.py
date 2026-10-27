from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base

JSON_DOCUMENT = JSON().with_variant(JSONB, "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class WhatsAppConversation(Base):
    """Short-lived dialogue and unconfirmed draft; never an investigation itself."""

    __tablename__ = "whatsapp_conversations"
    __table_args__ = (
        UniqueConstraint("owner_id", "sender_ref", name="uq_whatsapp_conversation_sender"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    sender_ref: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[str] = mapped_column(String(32), default="IDLE")
    context_json: Mapped[list[dict[str, str]]] = mapped_column(JSON_DOCUMENT, default=list)
    processed_events: Mapped[list[dict[str, str]]] = mapped_column(JSON_DOCUMENT, default=list)
    draft_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_input_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    proposed_claims: Mapped[list[dict[str, str]]] = mapped_column(JSON_DOCUMENT, default=list)
    proposed_queries: Mapped[list[dict[str, object]]] = mapped_column(JSON_DOCUMENT, default=list)
    clarification_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmation_token: Mapped[str | None] = mapped_column(String(24), nullable=True)
    preview_version: Mapped[int] = mapped_column(Integer, default=0)
    draft_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    model_calls: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class WhatsAppInboundEvent(Base):
    """Durable idempotency receipt for one provider message delivery."""

    __tablename__ = "whatsapp_inbound_events"
    __table_args__ = (
        UniqueConstraint("provider", "message_id", name="uq_whatsapp_inbound_provider_message"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("whatsapp_conversations.id", ondelete="CASCADE"),
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(40))
    message_id: Mapped[str] = mapped_column(String(200))
    sender_ref: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(20), default="PROCESSING")
    reply_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
