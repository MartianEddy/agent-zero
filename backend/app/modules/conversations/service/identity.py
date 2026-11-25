"""Per-user identity: keyed sender references, encrypted reply routes and preferences."""

from __future__ import annotations

import base64
import hashlib
import hmac
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.investigation import Channel
from app.modules.conversations.models import (
    WhatsAppConversation,
    WhatsAppNotificationPreference,
)
from app.modules.conversations.schemas import ConversationTurn
from app.modules.conversations.service import common
from app.modules.investigations.models import (
    Investigation,
    Submission,
)


def _sender_reference(sender: str, identity_key: str) -> str:
    return hmac.new(identity_key.encode(), sender.encode(), hashlib.sha256).hexdigest()


def _identity_refs(event: ConversationTurn, identity_key: str) -> tuple[str, str | None]:
    """Return (identity ref, legacy phone ref).

    Meta includes the business-scoped user ID (BSUID) in every webhook, but hides the
    phone number for users with a username. Keying on the BSUID keeps one conversation
    and one case history per person. The phone-based ref is returned so history saved
    before BSUIDs were used can be moved across once.
    """
    if event.user_id:
        legacy = event.sender if event.sender != event.user_id else None
        return (
            _sender_reference(event.user_id, identity_key),
            _sender_reference(legacy, identity_key) if legacy else None,
        )
    return _sender_reference(event.sender, identity_key), None


def _adopt_legacy_identity(
    session: Session, *, owner_id: UUID, sender_ref: str, legacy_ref: str
) -> None:
    """Move a phone-keyed conversation, preference and cases to the BSUID key, once."""
    if legacy_ref == sender_ref:
        return
    has_new = session.scalar(
        select(WhatsAppConversation.id).where(
            WhatsAppConversation.owner_id == owner_id,
            WhatsAppConversation.sender_ref == sender_ref,
        )
    )
    legacy = session.scalar(
        select(WhatsAppConversation)
        .where(
            WhatsAppConversation.owner_id == owner_id,
            WhatsAppConversation.sender_ref == legacy_ref,
        )
        .with_for_update()
    )
    moved = False
    if legacy is not None and has_new is None:
        legacy.sender_ref = sender_ref
        moved = True
    preference = session.scalar(
        select(WhatsAppNotificationPreference).where(
            WhatsAppNotificationPreference.owner_id == owner_id,
            WhatsAppNotificationPreference.sender_ref == legacy_ref,
        )
    )
    if (
        preference is not None
        and _notification_preference_for(session, owner_id, sender_ref) is None
    ):
        preference.sender_ref = sender_ref
        moved = True
    submissions = list(
        session.scalars(
            select(Submission)
            .join(Investigation, Investigation.id == Submission.investigation_id)
            .where(
                Investigation.owner_id == owner_id,
                Submission.channel == Channel.WHATSAPP,
                Submission.source_metadata["sender_ref"].as_string() == legacy_ref,
            )
        )
    )
    for submission in submissions:
        submission.source_metadata = {
            **(submission.source_metadata or {}),
            "sender_ref": sender_ref,
        }
        moved = True
    if moved:
        session.commit()
        common.logger.info(
            "WhatsApp identity moved to BSUID conversation=%s preference=%s cases=%s",
            legacy is not None and has_new is None,
            preference is not None,
            len(submissions),
        )


def _notification_preference_for(session: Session, owner_id: UUID, sender_ref: str):
    return session.scalar(
        select(WhatsAppNotificationPreference).where(
            WhatsAppNotificationPreference.owner_id == owner_id,
            WhatsAppNotificationPreference.sender_ref == sender_ref,
        )
    )


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
            WhatsAppNotificationPreference.owner_id == common._owner_id(settings),
            WhatsAppNotificationPreference.sender_ref == sender_ref,
        )
    )
