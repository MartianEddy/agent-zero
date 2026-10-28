import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from pydantic import SecretStr

from app.domain.investigation import Channel
from app.modules.conversations.schemas import ConversationTurn
from app.modules.conversations.service import (
    _case_list_message,
    _decrypt_recipient,
    _encrypt_recipient,
    _sender_reference,
)


def _settings():
    return SimpleNamespace(
        whatsapp_identity_key=SecretStr("identity-key-for-unit-test-0123456789"),
        whatsapp_support_url="https://support.example.test/contact",
    )


def test_recipient_route_is_encrypted_and_round_trips():
    settings = _settings()

    ciphertext = _encrypt_recipient("254700000000", settings)

    assert "254700000000" not in ciphertext
    assert _decrypt_recipient(ciphertext, settings) == "254700000000"


def test_case_history_lists_reference_status_claim_and_next_actions():
    session = MagicMock()
    case = SimpleNamespace(
        id=UUID(int=1),
        reference="AZ-261028-ED24C0",
        status=SimpleNamespace(value="RESEARCHING"),
    )
    session.scalars.return_value = [case]
    session.scalar.return_value = "Kenya became independent on 12 December 1963."

    response = _case_list_message(
        session,
        settings=SimpleNamespace(whatsapp_owner_id=None),
        sender_ref="sender-hmac",
    )

    assert "AZ-261028-ED24C0" in response
    assert "researching" in response
    assert "Kenya became independent" in response
    assert "RESULT <reference>" in response
    assert "STATUS <reference>" in response


def test_history_command_routes_directly_to_sender_scoped_case_list():
    from app.modules.conversations.service import _handle_turn

    now = datetime.now(UTC)
    conversation = SimpleNamespace(
        id=UUID(int=13),
        sender_ref="sender-hmac",
        state="IDLE",
        draft_expires_at=None,
        processed_events=[],
        context_json=[],
        expires_at=now + timedelta(hours=24),
        recipient_encrypted=None,
    )
    settings = SimpleNamespace(
        whatsapp_identity_key=SecretStr("identity-key-for-unit-test-0123456789"),
        whatsapp_owner_id=None,
    )
    session = MagicMock()
    turn = ConversationTurn(
        message_id="wamid.history",
        sender="254700000000",
        message_type="text",
        text="HISTORY",
    )

    with (
        patch(
            "app.modules.conversations.service._conversation_for_sender",
            return_value=conversation,
        ),
        patch("app.modules.conversations.service._claim_inbound_event", return_value=None),
        patch(
            "app.modules.conversations.service._case_list_message",
            return_value="Your checks, page 1.",
        ) as case_list,
        patch("app.modules.conversations.service._send_saved_reply", new=AsyncMock()),
    ):
        handled = asyncio.run(_handle_turn(session, turn, settings, MagicMock()))

    assert handled is True
    expected_sender_ref = _sender_reference(
        "254700000000", settings.whatsapp_identity_key.get_secret_value()
    )
    case_list.assert_called_once_with(
        session, settings=settings, sender_ref=expected_sender_ref, page=1
    )


def test_stop_persists_sender_scoped_notification_opt_out():
    from app.modules.conversations.models import WhatsAppNotificationPreference
    from app.modules.conversations.service import _handle_turn

    now = datetime.now(UTC)
    conversation = SimpleNamespace(
        id=UUID(int=14),
        sender_ref="sender-hmac",
        state="IDLE",
        draft_expires_at=None,
        processed_events=[],
        context_json=[],
        expires_at=now + timedelta(hours=24),
        recipient_encrypted=None,
    )
    settings = SimpleNamespace(
        whatsapp_identity_key=SecretStr("identity-key-for-unit-test-0123456789"),
        whatsapp_owner_id=None,
    )
    session = MagicMock()
    turn = ConversationTurn(
        message_id="wamid.stop",
        sender="254700000000",
        message_type="text",
        text="STOP",
    )

    with (
        patch(
            "app.modules.conversations.service._conversation_for_sender",
            return_value=conversation,
        ),
        patch("app.modules.conversations.service._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service._notification_preference", return_value=None),
        patch("app.modules.conversations.service._send_saved_reply", new=AsyncMock()),
    ):
        handled = asyncio.run(_handle_turn(session, turn, settings, MagicMock()))

    assert handled is True
    preference = session.add.call_args.args[0]
    assert isinstance(preference, WhatsAppNotificationPreference)
    assert preference.sender_ref == _sender_reference(
        "254700000000", settings.whatsapp_identity_key.get_secret_value()
    )
    assert preference.notifications_disabled is True


def test_whatsapp_terminal_job_queues_one_sender_neutral_outbox_event():
    from app.modules.investigations.models import OutboxEvent
    from app.modules.investigations.orchestrator import _queue_whatsapp_result_notification

    session = MagicMock()
    session.get.return_value = None
    investigation = SimpleNamespace(id=UUID(int=2), channel=Channel.WHATSAPP)
    job = SimpleNamespace(id=UUID(int=3))

    _queue_whatsapp_result_notification(session, investigation, job)

    event = session.add.call_args.args[0]
    assert isinstance(event, OutboxEvent)
    assert event.event_type == "WHATSAPP_RESULT_READY"
    assert event.aggregate_id == investigation.id
    assert event.payload == {"job_id": str(job.id), "delivery_state": "PENDING"}
    assert "254" not in str(event.payload)


def test_outbox_dispatch_routes_completion_to_notification_worker():
    from app.tasks import dispatch_outbox

    event = SimpleNamespace(
        id=UUID(int=15),
        event_type="WHATSAPP_RESULT_READY",
        payload={"delivery_state": "PENDING"},
        dispatched_at=None,
    )
    session = MagicMock()
    session.scalars.return_value = [event]

    with (
        patch("app.tasks.SessionLocal") as session_factory,
        patch("app.tasks.celery_app.send_task") as send_task,
    ):
        session_factory.return_value.__enter__.return_value = session
        count = dispatch_outbox()

    assert count == 1
    assert event.dispatched_at is not None
    send_task.assert_called_once_with(
        "agent_zero.send_whatsapp_result_notification",
        args=[str(event.id)],
        task_id=str(event.id),
    )


def test_completion_notification_sends_saved_result_inside_reply_window():
    from app.tasks import send_whatsapp_result_notification

    now = datetime.now(UTC)
    event = SimpleNamespace(
        id=UUID(int=4),
        aggregate_id=UUID(int=5),
        payload={"delivery_state": "PENDING", "job_id": str(UUID(int=40))},
    )
    investigation = SimpleNamespace(
        id=event.aggregate_id,
        owner_id=UUID(int=6),
        channel=Channel.WHATSAPP,
        reference="AZ-261028-ED24C0",
    )
    submission = SimpleNamespace(source_metadata={"sender_ref": "sender-hmac"})
    conversation = SimpleNamespace(
        owner_id=investigation.owner_id,
        sender_ref="sender-hmac",
        recipient_encrypted="opaque-ciphertext",
        last_inbound_at=now - timedelta(minutes=2),
        expires_at=now + timedelta(hours=23),
    )
    session = MagicMock()
    session.get.side_effect = [event, investigation]
    session.scalar.side_effect = [submission, conversation, None, SimpleNamespace(id=UUID(int=40))]

    with (
        patch("app.tasks.SessionLocal") as session_factory,
        patch("app.tasks.get_settings", return_value=_settings()),
        patch("app.tasks._configured_settings", return_value=_settings(), create=True),
        patch("app.modules.channels.whatsapp._configured_settings", return_value=_settings()),
        patch("app.modules.conversations.service._decrypt_recipient", return_value="254700000000"),
        patch("app.modules.conversations.service._result_message", return_value="Grounded result with sources.") as result,
        patch("app.modules.channels.whatsapp.send_text_message") as send,
    ):
        session_factory.return_value.__enter__.return_value = session
        status = send_whatsapp_result_notification(str(event.id))

    assert status == "sent"
    result.assert_called_once()
    send.assert_called_once_with(
        "254700000000",
        "Your result is ready. Reference: AZ-261028-ED24C0.\n\n"
        "Grounded result with sources.\n\nNeed human help? https://support.example.test/contact",
    )
    assert event.payload["delivery_state"] == "SENT"


def test_completion_notification_skips_after_whatsapp_reply_window():
    from app.tasks import send_whatsapp_result_notification

    now = datetime.now(UTC)
    event = SimpleNamespace(
        id=UUID(int=7),
        aggregate_id=UUID(int=8),
        payload={"delivery_state": "PENDING", "job_id": str(UUID(int=70))},
    )
    investigation = SimpleNamespace(
        id=event.aggregate_id,
        owner_id=UUID(int=9),
        channel=Channel.WHATSAPP,
    )
    submission = SimpleNamespace(source_metadata={"sender_ref": "sender-hmac"})
    conversation = SimpleNamespace(
        owner_id=investigation.owner_id,
        sender_ref="sender-hmac",
        recipient_encrypted="opaque-ciphertext",
        last_inbound_at=now - timedelta(hours=24, seconds=5),
        expires_at=now - timedelta(seconds=5),
    )
    session = MagicMock()
    session.get.side_effect = [event, investigation]
    session.scalar.side_effect = [submission, conversation, None, SimpleNamespace(id=UUID(int=70))]

    with (
        patch("app.tasks.SessionLocal") as session_factory,
        patch("app.modules.channels.whatsapp.send_text_message") as send,
    ):
        session_factory.return_value.__enter__.return_value = session
        status = send_whatsapp_result_notification(str(event.id))

    assert status == "skipped"
    assert event.payload["delivery_state"] == "SKIPPED"
    send.assert_not_called()


def test_completion_notification_respects_persistent_stop_preference():
    from app.tasks import send_whatsapp_result_notification

    now = datetime.now(UTC)
    event = SimpleNamespace(
        id=UUID(int=10),
        aggregate_id=UUID(int=11),
        payload={"delivery_state": "PENDING", "job_id": str(UUID(int=100))},
    )
    investigation = SimpleNamespace(
        id=event.aggregate_id,
        owner_id=UUID(int=12),
        channel=Channel.WHATSAPP,
    )
    submission = SimpleNamespace(source_metadata={"sender_ref": "sender-hmac"})
    conversation = SimpleNamespace(
        owner_id=investigation.owner_id,
        sender_ref="sender-hmac",
        recipient_encrypted="opaque-ciphertext",
        last_inbound_at=now - timedelta(minutes=2),
        expires_at=now + timedelta(hours=23),
    )
    preference = SimpleNamespace(notifications_disabled=True)
    session = MagicMock()
    session.get.side_effect = [event, investigation]
    session.scalar.side_effect = [submission, conversation, preference, SimpleNamespace(id=UUID(int=100))]

    with (
        patch("app.tasks.SessionLocal") as session_factory,
        patch("app.modules.channels.whatsapp.send_text_message") as send,
    ):
        session_factory.return_value.__enter__.return_value = session
        status = send_whatsapp_result_notification(str(event.id))

    assert status == "skipped"
    assert event.payload["delivery_state"] == "SKIPPED"
    send.assert_not_called()
