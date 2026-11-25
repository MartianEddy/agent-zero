"""Database-backed tests for moving phone-keyed WhatsApp history to the BSUID key."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.investigation import Channel, InputType
from app.modules.conversations.models import (
    WhatsAppConversation,
    WhatsAppNotificationPreference,
)
from app.modules.conversations.service import _adopt_legacy_identity
from app.modules.investigations.models import Submission, User
from app.modules.investigations.service import InvestigationService

OWNER = UUID(int=9)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(engine, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    session.add(User(id=OWNER, external_subject="local:test"))
    session.commit()
    return session


def _case(session: Session, sender_ref: str) -> None:
    InvestigationService(session).create(
        owner_id=OWNER,
        content="Nairobi is the capital of Kenya.",
        input_type=InputType.TEXT,
        idempotency_key=f"k-{sender_ref}-{datetime.now(UTC).timestamp()}",
        channel=Channel.WHATSAPP,
        source_metadata={"sender_ref": sender_ref, "platform": "meta_cloud_api"},
    )


def test_phone_keyed_history_moves_to_the_bsuid_key_once() -> None:
    session = _session()
    session.add_all([
        WhatsAppConversation(owner_id=OWNER, sender_ref="phone-ref",
                             expires_at=datetime.now(UTC) + timedelta(hours=24)),
        WhatsAppNotificationPreference(owner_id=OWNER, sender_ref="phone-ref",
                                       notifications_disabled=True),
    ])
    session.commit()
    _case(session, "phone-ref")
    _case(session, "phone-ref")
    _case(session, "someone-else")

    _adopt_legacy_identity(session, owner_id=OWNER, sender_ref="bsuid-ref", legacy_ref="phone-ref")

    conversation = session.scalar(select(WhatsAppConversation))
    assert conversation.sender_ref == "bsuid-ref"
    assert session.scalar(select(WhatsAppNotificationPreference)).sender_ref == "bsuid-ref"
    refs = sorted(item.source_metadata["sender_ref"] for item in session.scalars(select(Submission)))
    assert refs == ["bsuid-ref", "bsuid-ref", "someone-else"]

    # Running again is a no-op.
    _adopt_legacy_identity(session, owner_id=OWNER, sender_ref="bsuid-ref", legacy_ref="phone-ref")
    assert session.scalar(select(WhatsAppConversation)).sender_ref == "bsuid-ref"


def test_existing_bsuid_conversation_is_kept_and_not_overwritten() -> None:
    session = _session()
    session.add_all([
        WhatsAppConversation(owner_id=OWNER, sender_ref="phone-ref",
                             expires_at=datetime.now(UTC) + timedelta(hours=24)),
        WhatsAppConversation(owner_id=OWNER, sender_ref="bsuid-ref",
                             expires_at=datetime.now(UTC) + timedelta(hours=24)),
    ])
    session.commit()
    _case(session, "phone-ref")

    _adopt_legacy_identity(session, owner_id=OWNER, sender_ref="bsuid-ref", legacy_ref="phone-ref")

    refs = sorted(item.sender_ref for item in session.scalars(select(WhatsAppConversation)))
    assert refs == ["bsuid-ref", "phone-ref"]
    # Cases still follow the person, so HISTORY and RESULT keep working.
    assert session.scalar(select(Submission)).source_metadata["sender_ref"] == "bsuid-ref"
