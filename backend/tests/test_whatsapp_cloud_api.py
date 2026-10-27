import asyncio
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from app.core.config import Settings
from app.modules.channels.whatsapp import (
    IncomingWhatsAppMessage,
    _handle_message,
    parse_message_events,
    receive_webhook,
    verify_webhook,
    verify_webhook_signature,
)
from app.modules.conversations.schemas import ConversationTurn
from app.modules.conversations.service import _conversation_reply, _result_message


def test_meta_signature_is_verified_against_raw_request_body() -> None:
    body = b'{"object":"whatsapp_business_account"}'
    secret = "app-secret"
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verify_webhook_signature(body, f"sha256={digest}", secret)
    assert not verify_webhook_signature(body + b" ", f"sha256={digest}", secret)
    assert not verify_webhook_signature(body, f"sha1={digest}", secret)
    assert not verify_webhook_signature(body, None, secret)


def test_parser_extracts_only_supported_text_messages_with_stable_ids() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": "12345"},
                            "messages": [
                                {
                                    "id": "wamid.abc",
                                    "from": "254700000000",
                                    "type": "text",
                                    "text": {"body": "  Check this claim  "},
                                },
                                {
                                    "id": "wamid.media",
                                    "from": "254700000000",
                                    "type": "image",
                                    "image": {"id": "media-id"},
                                },
                                {
                                    "from": "254700000000",
                                    "type": "text",
                                    "text": {"body": "missing stable id"},
                                },
                            ],
                        },
                    }
                ]
            }
        ],
    }

    events = parse_message_events(payload)

    assert events == [
        IncomingWhatsAppMessage(
            message_id="wamid.abc",
            sender="254700000000",
            phone_number_id="12345",
            message_type="text",
            text="Check this claim",
        ),
        IncomingWhatsAppMessage(
            message_id="wamid.media",
            sender="254700000000",
            phone_number_id="12345",
            message_type="image",
            text=None,
        ),
    ]


def test_parser_accepts_business_scoped_user_id_as_sender() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": "12345"},
                    "messages": [{
                        "id": "wamid.bsuid",
                        "from": "KE.opaqueABC123",
                        "type": "text",
                        "text": {"body": "Check this claim"},
                    }],
                },
            }],
        }],
    }

    events = parse_message_events(payload)

    assert len(events) == 1
    assert events[0].sender == "KE.opaqueABC123"


def test_parser_accepts_parent_business_scoped_user_id_as_sender() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": "12345"},
                    "messages": [{
                        "id": "wamid.parent-bsuid",
                        "from": "KE.ENT.opaqueABC123",
                        "type": "text",
                        "text": {"body": "Check this claim"},
                    }],
                },
            }],
        }],
    }

    events = parse_message_events(payload)

    assert len(events) == 1
    assert events[0].sender == "KE.ENT.opaqueABC123"


def test_parser_uses_message_scoped_bsuid_when_phone_sender_is_omitted() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": "12345"},
                    "messages": [{
                        "id": "wamid.message-user-id",
                        "from_user_id": "KE.opaqueABC123",
                        "type": "text",
                        "text": {"body": "Check this claim"},
                    }],
                },
            }],
        }],
    }

    events = parse_message_events(payload)

    assert len(events) == 1
    assert events[0].sender == "KE.opaqueABC123"


def test_parser_uses_contact_scoped_parent_bsuid_when_phone_sender_is_omitted() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": "12345"},
                    "contacts": [{"parent_user_id": "KE.ENT.opaqueABC123"}],
                    "messages": [{
                        "id": "wamid.contact-user-id",
                        "type": "text",
                        "text": {"body": "Check this claim"},
                    }],
                },
            }],
        }],
    }

    events = parse_message_events(payload)

    assert len(events) == 1
    assert events[0].sender == "KE.ENT.opaqueABC123"


def test_parser_does_not_guess_between_multiple_contacts_without_message_sender() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": "12345"},
                    "contacts": [
                        {"user_id": "KE.opaqueOne"},
                        {"user_id": "KE.opaqueTwo"},
                    ],
                    "messages": [{
                        "id": "wamid.ambiguous-contact",
                        "type": "text",
                        "text": {"body": "Check this claim"},
                    }],
                },
            }],
        }],
    }

    assert parse_message_events(payload) == []


def test_parser_normalizes_e164_sender_for_cloud_api_reply() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": "12345"},
                    "messages": [{
                        "id": "wamid.plus-phone",
                        "from": "+254700000000",
                        "type": "text",
                        "text": {"body": "Check this claim"},
                    }],
                },
            }],
        }],
    }

    events = parse_message_events(payload)

    assert len(events) == 1
    assert events[0].sender == "254700000000"


@pytest.mark.parametrize("sender", ["KE.", "KE.has-dash", "K.opaque", "2547-00000000"])
def test_parser_rejects_malformed_sender_identifiers(sender: str) -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": "12345"},
                    "messages": [{
                        "id": "wamid.bad-sender",
                        "from": sender,
                        "type": "text",
                        "text": {"body": "Check this claim"},
                    }],
                },
            }],
        }],
    }

    assert parse_message_events(payload) == []


def test_parser_ignores_non_message_webhook_fields() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "statuses", "value": {"statuses": []}}]}],
    }

    assert parse_message_events(payload) == []


def test_cloud_api_send_uses_configured_version_and_bearer_auth() -> None:
    from app.modules.channels.whatsapp import send_text_message

    response = type(
        "Response", (), {"status": 200, "read": lambda self, _size: b'{"messages":[]}'}
    )()
    with (
        patch("app.modules.channels.whatsapp.get_settings") as get_settings,
        patch("app.modules.channels.whatsapp.build_opener") as build_opener,
    ):
        settings = type(
            "Settings",
            (),
            {
                "whatsapp_access_token": type(
                    "Secret", (), {"get_secret_value": lambda self: "access-token"}
                )(),
                    "whatsapp_app_secret": type(
                        "Secret", (), {"get_secret_value": lambda self: "app-secret"}
                    )(),
                    "whatsapp_verify_token": type(
                        "Secret", (), {"get_secret_value": lambda self: "verify-token"}
                    )(),
                    "whatsapp_identity_key": type(
                        "Secret", (), {"get_secret_value": lambda self: "x" * 32}
                    )(),
                "whatsapp_phone_number_id": "12345",
                "whatsapp_graph_api_version": "v25.0",
            },
        )()
        get_settings.return_value = settings
        build_opener.return_value.open.return_value.__enter__.return_value = response

        send_text_message("254700000000", "Received")

        request = build_opener.return_value.open.call_args.args[0]
        assert request.full_url == "https://graph.facebook.com/v25.0/12345/messages"
        assert request.get_header("Authorization") == "Bearer access-token"
        assert json.loads(request.data) == {
            "messaging_product": "whatsapp",
            "to": "254700000000",
            "type": "text",
            "text": {"body": "Received"},
        }


def test_cloud_api_send_accepts_business_scoped_user_id() -> None:
    from app.modules.channels.whatsapp import send_text_message

    response = type("Response", (), {"status": 200, "read": lambda self, _size: b"{}"})()
    with (
        patch("app.modules.channels.whatsapp.get_settings") as get_settings,
        patch("app.modules.channels.whatsapp.build_opener") as build_opener,
    ):
        get_settings.return_value = SimpleNamespace(
            whatsapp_access_token=SimpleNamespace(get_secret_value=lambda: "access-token"),
            whatsapp_app_secret=SimpleNamespace(get_secret_value=lambda: "app-secret"),
            whatsapp_verify_token=SimpleNamespace(get_secret_value=lambda: "verify-token"),
            whatsapp_identity_key=SimpleNamespace(get_secret_value=lambda: "i" * 32),
            whatsapp_phone_number_id="12345",
            whatsapp_graph_api_version="v25.0",
        )
        build_opener.return_value.open.return_value.__enter__.return_value = response

        send_text_message("KE.opaqueABC123", "Received")

        request = build_opener.return_value.open.call_args.args[0]
        assert json.loads(request.data)["to"] == "KE.opaqueABC123"


def test_cloud_api_send_accepts_parent_business_scoped_user_id() -> None:
    from app.modules.channels.whatsapp import send_text_message

    response = type("Response", (), {"status": 200, "read": lambda self, _size: b"{}"})()
    with (
        patch("app.modules.channels.whatsapp.get_settings") as get_settings,
        patch("app.modules.channels.whatsapp.build_opener") as build_opener,
    ):
        get_settings.return_value = SimpleNamespace(
            whatsapp_access_token=SimpleNamespace(get_secret_value=lambda: "access-token"),
            whatsapp_app_secret=SimpleNamespace(get_secret_value=lambda: "app-secret"),
            whatsapp_verify_token=SimpleNamespace(get_secret_value=lambda: "verify-token"),
            whatsapp_identity_key=SimpleNamespace(get_secret_value=lambda: "i" * 32),
            whatsapp_phone_number_id="12345",
            whatsapp_graph_api_version="v25.0",
        )
        build_opener.return_value.open.return_value.__enter__.return_value = response

        send_text_message("KE.ENT.opaqueABC123", "Received")

        request = build_opener.return_value.open.call_args.args[0]
        assert json.loads(request.data)["to"] == "KE.ENT.opaqueABC123"


def test_cloud_api_send_normalizes_plus_prefixed_phone_recipient() -> None:
    from app.modules.channels.whatsapp import send_text_message

    response = type("Response", (), {"status": 200, "read": lambda self, _size: b"{}"})()
    with (
        patch("app.modules.channels.whatsapp.get_settings") as get_settings,
        patch("app.modules.channels.whatsapp.build_opener") as build_opener,
    ):
        get_settings.return_value = SimpleNamespace(
            whatsapp_access_token=SimpleNamespace(get_secret_value=lambda: "access-token"),
            whatsapp_app_secret=SimpleNamespace(get_secret_value=lambda: "app-secret"),
            whatsapp_verify_token=SimpleNamespace(get_secret_value=lambda: "verify-token"),
            whatsapp_identity_key=SimpleNamespace(get_secret_value=lambda: "i" * 32),
            whatsapp_phone_number_id="12345",
            whatsapp_graph_api_version="v25.0",
        )
        build_opener.return_value.open.return_value.__enter__.return_value = response

        send_text_message("+254700000000", "Received")

        request = build_opener.return_value.open.call_args.args[0]
        assert json.loads(request.data)["to"] == "254700000000"


def test_cloud_api_configuration_rejects_partial_credentials() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="test", whatsapp_access_token="configured")


def _settings():
    return SimpleNamespace(
        whatsapp_access_token=SimpleNamespace(get_secret_value=lambda: "access-token"),
        whatsapp_app_secret=SimpleNamespace(get_secret_value=lambda: "app-secret"),
        whatsapp_verify_token=SimpleNamespace(get_secret_value=lambda: "verify-token"),
        whatsapp_identity_key=SimpleNamespace(get_secret_value=lambda: "i" * 32),
        whatsapp_phone_number_id="12345",
        whatsapp_graph_api_version="v25.0",
        whatsapp_conversation_enabled=True,
        max_search_queries=5,
        whatsapp_owner_id=UUID("00000000-0000-4000-8000-000000000123"),
    )


def _request_with_body(body: bytes) -> Request:
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {"type": "http", "method": "POST", "path": "/webhook", "headers": []},
        receive,
    )


def test_meta_get_verification_returns_challenge_only_for_matching_token() -> None:
    with patch("app.modules.channels.whatsapp.get_settings", return_value=_settings()):
        response = verify_webhook("subscribe", "verify-token", "challenge-value")

    assert response.body == b"challenge-value"


def test_webhook_route_authenticates_raw_body_before_processing_events() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "statuses", "value": {"statuses": []}}]}],
    }
    raw_body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"app-secret", raw_body, hashlib.sha256).hexdigest()
    session = MagicMock()
    with (
        patch("app.modules.channels.whatsapp.get_settings", return_value=_settings()),
        patch("app.modules.channels.whatsapp._handle_message") as handle,
    ):
        handle.return_value = None
        result = asyncio.run(receive_webhook(_request_with_body(raw_body), session, signature))

    assert result == {"status": "ok"}
    handle.assert_not_called()


def test_webhook_logs_status_callback_shape_without_sensitive_payload(caplog) -> None:
    private_text = "private webhook content"
    private_sender = "254700000000"
    private_message_id = "wamid.private-status-id"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": "12345"},
            "statuses": [{
                "id": private_message_id,
                "recipient_id": private_sender,
                "status": "failed",
                "errors": [{"code": 131026, "title": private_text}],
            }],
            "messages": [],
            "diagnostic": private_text,
        }}]}],
    }
    raw_body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"app-secret", raw_body, hashlib.sha256).hexdigest()
    caplog.set_level(logging.INFO, logger="app.modules.channels.whatsapp")

    with (
        patch("app.modules.channels.whatsapp.get_settings", return_value=_settings()),
        patch("app.modules.channels.whatsapp._handle_message") as handle,
    ):
        result = asyncio.run(receive_webhook(_request_with_body(raw_body), MagicMock(), signature))

    assert result == {"status": "ok"}
    handle.assert_not_called()
    assert "fields=messages" in caplog.text
    assert "raw_messages=0" in caplog.text
    assert "statuses=1" in caplog.text
    assert "parsed_messages=0" in caplog.text
    assert "status_states=failed:1" in caplog.text
    assert "status_error_codes=131026:1" in caplog.text
    assert private_text not in caplog.text
    assert private_sender not in caplog.text
    assert private_message_id not in caplog.text


def test_webhook_logs_supported_message_shape_without_content_or_identity(caplog) -> None:
    private_text = "A private test claim"
    private_sender = "254700000000"
    private_id = "wamid.private-message-id"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": "12345"},
            "messages": [{
                "id": private_id,
                "from": private_sender,
                "type": "text",
                "text": {"body": private_text},
            }],
        }}]}],
    }
    raw_body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"app-secret", raw_body, hashlib.sha256).hexdigest()
    caplog.set_level(logging.INFO, logger="app.modules.channels.whatsapp")

    with (
        patch("app.modules.channels.whatsapp.get_settings", return_value=_settings()),
        patch("app.modules.channels.whatsapp._handle_message", return_value=True) as handle,
    ):
        result = asyncio.run(receive_webhook(_request_with_body(raw_body), MagicMock(), signature))

    assert result == {"status": "ok"}
    handle.assert_called_once()
    assert "fields=messages" in caplog.text
    assert "raw_messages=1" in caplog.text
    assert "parsed_messages=1" in caplog.text
    assert "message_types=text" in caplog.text
    assert private_text not in caplog.text
    assert private_sender not in caplog.text
    assert private_id not in caplog.text


def test_webhook_logs_parser_rejection_reason_without_message_values(caplog) -> None:
    private_text = "A private test claim"
    private_sender = "254700000000"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": "12345"},
            "messages": [{
                "from": private_sender,
                "type": "text",
                "text": {"body": private_text},
            }],
        }}]}],
    }
    raw_body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"app-secret", raw_body, hashlib.sha256).hexdigest()
    caplog.set_level(logging.INFO, logger="app.modules.channels.whatsapp")

    with (
        patch("app.modules.channels.whatsapp.get_settings", return_value=_settings()),
        patch("app.modules.channels.whatsapp._handle_message") as handle,
    ):
        result = asyncio.run(receive_webhook(_request_with_body(raw_body), MagicMock(), signature))

    assert result == {"status": "ok"}
    handle.assert_not_called()
    assert "raw_messages=1" in caplog.text
    assert "parsed_messages=0" in caplog.text
    assert "rejections=invalid_message_id:1" in caplog.text
    assert private_text not in caplog.text
    assert private_sender not in caplog.text


def test_webhook_logs_only_a_low_cardinality_invalid_sender_shape(caplog) -> None:
    private_text = "A private test claim"
    private_sender = "private-sender-123"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": "12345"},
            "messages": [{
                "id": "wamid.sender-shape",
                "from": private_sender,
                "type": "text",
                "text": {"body": private_text},
            }],
        }}]}],
    }
    raw_body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"app-secret", raw_body, hashlib.sha256).hexdigest()
    caplog.set_level(logging.INFO, logger="app.modules.channels.whatsapp")

    with (
        patch("app.modules.channels.whatsapp.get_settings", return_value=_settings()),
        patch("app.modules.channels.whatsapp._handle_message") as handle,
    ):
        result = asyncio.run(receive_webhook(_request_with_body(raw_body), MagicMock(), signature))

    assert result == {"status": "ok"}
    handle.assert_not_called()
    assert "rejections=invalid_sender_format:1" in caplog.text
    assert "sender_shapes=other_string:1" in caplog.text
    assert "sender_fallback_fields=none" in caplog.text
    assert private_text not in caplog.text
    assert private_sender not in caplog.text


def test_webhook_route_rejects_bad_signature_before_parsing_or_processing() -> None:
    session = MagicMock()
    with (
        patch("app.modules.channels.whatsapp.get_settings", return_value=_settings()),
        patch("app.modules.channels.whatsapp._handle_message") as handle,
        pytest.raises(HTTPException) as error,
    ):
        asyncio.run(receive_webhook(_request_with_body(b"{}"), session, "sha256=bad"))

    assert error.value.status_code == 401
    handle.assert_not_called()


def _conversation_fixture(**overrides):
    from datetime import UTC, datetime, timedelta

    values = {
        "id": UUID(int=100),
        "owner_id": UUID(int=1),
        "sender_ref": "hmac-sender",
        "state": "IDLE",
        "context_json": [],
        "processed_events": [],
        "draft_text": None,
        "draft_input_type": None,
        "proposed_claims": [],
        "proposed_queries": [],
        "clarification_question": None,
        "preview_version": 0,
        "model_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "draft_expires_at": None,
        "confirmation_token": None,
        "expires_at": datetime.now(UTC) + timedelta(hours=24),
    }
    values.update(overrides)
    return SimpleNamespace(**values)



def test_inbound_receipt_is_committed_before_any_model_work_and_replays_reply() -> None:
    from app.modules.conversations.models import WhatsAppInboundEvent
    from app.modules.conversations.service import _claim_inbound_event

    conversation = _conversation_fixture(id=UUID(int=8))
    event = ConversationTurn(
        message_id="wamid.receipt", sender="254700000000", message_type="text", text="Hi"
    )
    now = datetime.now(UTC)
    session = MagicMock()
    session.scalar.side_effect = [None, conversation]

    assert _claim_inbound_event(
        session, conversation=conversation, event=event, sender_ref="sender-hmac", now=now
    ) is None
    receipt = next(
        item
        for item in session.add.call_args_list[0].args
        if isinstance(item, WhatsAppInboundEvent)
    )
    assert receipt.message_id == event.message_id
    assert receipt.state == "PROCESSING"
    assert receipt.sender_ref == "sender-hmac"
    session.commit.assert_called_once()

    receipt.state = "COMPLETED"
    receipt.reply_text = "Saved response"
    replay_session = MagicMock()
    replay_session.scalar.return_value = receipt
    assert _claim_inbound_event(
        replay_session,
        conversation=conversation,
        event=event,
        sender_ref="sender-hmac",
        now=now,
    ) == "Saved response"
    replay_session.commit.assert_not_called()


def test_natural_confirmation_requires_the_code_for_the_active_preview() -> None:
    from app.modules.conversations.service import ConversationService

    session = MagicMock()
    conversation = _conversation_fixture(
        state="AWAITING_CONFIRMATION",
        draft_text="Investigate the procurement timeline",
        proposed_claims=[
            {"text": "Company X won the contract early.", "claim_type": "CHECKABLE_EVENT"}
        ],
        confirmation_token="89ABCDEF",
        draft_expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    session.scalar.return_value = conversation
    turn = IncomingWhatsAppMessage(
        message_id="wamid.natural-confirm",
        sender="254700000000",
        phone_number_id="12345",
        message_type="text",
        text="Yes, please go ahead and verify it",
    )
    output = SimpleNamespace(
        intent="CONFIRM_DRAFT", reply="", claims=[], queries=[],
        clarification_question=None, reference=None
    )

    async def immediate_in_threadpool(function, *args, **kwargs):
        return function(*args, **kwargs)

    with (
        patch("app.modules.conversations.service._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service._complete_inbound_event"),
        patch("app.modules.conversations.service.ModelGateway") as gateway,
        patch("app.modules.channels.whatsapp.send_text_message") as send,
        patch(
            "app.modules.conversations.service.run_in_threadpool",
            side_effect=immediate_in_threadpool,
        ),
        patch("app.modules.conversations.service.InvestigationService") as investigations,
    ):
        gateway.return_value.interpret_whatsapp_turn = AsyncMock(
            return_value=SimpleNamespace(output=output)
        )
        assert asyncio.run(
            ConversationService(session, _settings()).handle_turn(
                ConversationTurn(
                    message_id=turn.message_id,
                    sender=turn.sender,
                    message_type=turn.message_type,
                    text=turn.text,
                ),
                send,
            )
        )

    investigations.return_value.create.assert_not_called()
    assert "SUBMIT 89ABCDEF" in send.call_args.args[1]
    assert "No investigation has started" in send.call_args.args[1]


def test_previous_preview_code_cannot_approve_replacement_preview() -> None:
    from app.modules.conversations.service import _confirm_conversation_draft

    session = MagicMock()
    conversation = _conversation_fixture(
        state="AWAITING_CONFIRMATION",
        proposed_claims=[{"text": "A changed claim.", "claim_type": "CHECKABLE_EVENT"}],
        confirmation_token="89ABCDEF",
        preview_version=2,
        draft_expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    event = ConversationTurn(
        message_id="wamid.old-code",
        sender="254700000000",
        message_type="text",
        text="SUBMIT 12345678",
    )

    reply, created = asyncio.run(
        _confirm_conversation_draft(
            session,
            conversation=conversation,
            event=event,
            settings=_settings(),
            user_text=event.text or "",
            confirmation_code="12345678",
        )
    )

    assert created is False
    assert "SUBMIT 89ABCDEF" in reply
    session.scalar.assert_not_called()


def test_webhook_kill_switch_hides_conversation_endpoint() -> None:
    payload = json.dumps({"object": "whatsapp_business_account"}).encode()
    settings = _settings()
    settings.whatsapp_conversation_enabled = False
    with patch("app.modules.channels.whatsapp.get_settings", return_value=settings):
        with pytest.raises(HTTPException) as error:
            asyncio.run(receive_webhook(_request_with_body(payload), MagicMock(), None))
    assert error.value.status_code == 404

def test_inbound_text_uses_luna_to_create_preview_without_creating_case() -> None:
    session = MagicMock()
    conversation = _conversation_fixture()
    session.scalar.return_value = conversation
    session.get.return_value = SimpleNamespace(id=UUID(int=1))
    event = IncomingWhatsAppMessage(
        message_id="wamid.abc",
        sender="254700000000",
        phone_number_id="12345",
        message_type="text",
        text="Please investigate this claim",
    )

    async def immediate_in_threadpool(function, *args, **kwargs):
        return function(*args, **kwargs)

    output = SimpleNamespace(
        intent="INVESTIGATION_REQUEST",
        reply="Here is the proposed claim.",
        claims=[
            SimpleNamespace(
                text="Company X received the contract before the tender was announced.",
                claim_type="CHECKABLE_EVENT",
            )
        ],
        queries=[],
        clarification_question=None,
        reference=None,
    )
    with (
        patch("app.modules.conversations.service._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service._complete_inbound_event"),
        patch("app.modules.conversations.service.InvestigationService") as service,
        patch("app.modules.conversations.service.ModelGateway") as gateway,
        patch("app.modules.channels.whatsapp.send_text_message") as send,
        patch(
            "app.modules.conversations.service.run_in_threadpool",
            side_effect=immediate_in_threadpool,
        ),
    ):
        gateway.return_value.interpret_whatsapp_turn = AsyncMock(
            return_value=SimpleNamespace(output=output)
        )
        assert asyncio.run(_handle_message(session, event, _settings()))

    service.return_value.create.assert_not_called()
    assert conversation.state == "AWAITING_CONFIRMATION"
    assert conversation.proposed_claims[0]["claim_type"] == "CHECKABLE_EVENT"
    preview = send.call_args.args[1]
    assert "SUBMIT " in preview
    assert conversation.confirmation_token in preview
    assert "No investigation has started yet" in send.call_args.args[1]


def test_explicit_submit_creates_one_investigation_from_approved_claims() -> None:
    session = MagicMock()
    conversation = _conversation_fixture(
        state="AWAITING_CONFIRMATION",
        draft_text="Please investigate this claim",
        draft_input_type="TEXT",
        proposed_claims=[
            {
                "text": "Company X received the contract before the tender was announced.",
                "claim_type": "CHECKABLE_EVENT",
            }
        ],
        draft_expires_at=datetime.now(UTC) + timedelta(minutes=20),
        preview_version=1,
        confirmation_token="1234ABCD",
    )
    session.scalar.side_effect = [conversation, None]
    investigation = SimpleNamespace(
        id=UUID(int=200), reference="AZ-261027-ABC123", current_stage="TRIAGE_PENDING"
    )
    event = IncomingWhatsAppMessage(
        message_id="wamid.submit",
        sender="254700000000",
        phone_number_id="12345",
        message_type="text",
        text="Yes, please go ahead and verify it. SUBMIT 1234ABCD",
    )

    async def immediate_in_threadpool(function, *args, **kwargs):
        return function(*args, **kwargs)

    with (
        patch("app.modules.conversations.service._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service._complete_inbound_event"),
        patch("app.modules.conversations.service.InvestigationService") as service,
        patch("app.modules.conversations.service.ModelGateway") as gateway,
        patch("app.modules.channels.whatsapp.send_text_message") as send,
        patch(
            "app.modules.conversations.service.run_in_threadpool",
            side_effect=immediate_in_threadpool,
        ),
    ):
        service.return_value.create.return_value = investigation
        gateway.return_value.interpret_whatsapp_turn = AsyncMock(
            return_value=SimpleNamespace(
                output=SimpleNamespace(
                    intent="CONFIRM_DRAFT",
                    reply="",
                    claims=[],
                    queries=[],
                    clarification_question=None,
                    reference=None,
                )
            )
        )
        assert asyncio.run(_handle_message(session, event, _settings()))

    kwargs = service.return_value.create.call_args.kwargs
    assert kwargs["enqueue"] is False
    assert kwargs["commit"] is False
    assert kwargs["source_metadata"]["approved_preview_version"] == 1
    gateway.return_value.interpret_whatsapp_turn.assert_awaited_once()
    assert conversation.state == "IDLE"
    assert "AZ-261027-ABC123" in send.call_args.args[1]
    queued = [
        item
        for item in session.add_all.call_args.args[0]
        if getattr(item, "status", None) == "QUEUED"
    ]
    assert len(queued) == 1


def test_meta_redelivery_repeats_saved_conversation_reply_without_retriage() -> None:
    session = MagicMock()
    conversation = _conversation_fixture(
        processed_events=[
            {"message_id": "wamid.abc", "reply": "I received that message."}
        ],
        context_json=[{"role": "assistant", "content": "I received that message."}],
    )
    session.scalar.return_value = conversation
    event = IncomingWhatsAppMessage(
        message_id="wamid.abc",
        sender="254700000000",
        phone_number_id="12345",
        message_type="text",
        text="Hello",
    )

    async def immediate_in_threadpool(function, *args, **kwargs):
        return function(*args, **kwargs)

    with (
        patch("app.modules.conversations.service._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service._complete_inbound_event"),
        patch("app.modules.conversations.service.ModelGateway") as gateway,
        patch("app.modules.channels.whatsapp.send_text_message") as send,
        patch(
            "app.modules.conversations.service.run_in_threadpool",
            side_effect=immediate_in_threadpool,
        ),
    ):
        assert asyncio.run(_handle_message(session, event, _settings()))

    gateway.return_value.interpret_whatsapp_turn.assert_not_called()
    send.assert_called_once_with(event.sender, "I received that message.")

def test_result_lookup_is_scoped_to_the_hmac_sender_and_includes_saved_limits() -> None:
    session = MagicMock()
    investigation = SimpleNamespace(id=UUID(int=42), reference="AZ-261026-ABC123")
    brief = SimpleNamespace(limitations=["Only accessible public sources were reviewed."])
    finding = SimpleNamespace(
        status="INSUFFICIENT_EVIDENCE",
        statement="The sources did not establish this claim.",
        evidence_confidence="LOW",
        confidence_rationale="Few direct sources.",
    )
    session.scalar.side_effect = [investigation, brief]
    session.scalars.return_value = [finding]
    sender_ref = "private-hmac-reference"

    response = _result_message(
        session, settings=_settings(), sender_ref=sender_ref, reference="AZ-261026-ABC123"
    )

    query = session.scalar.call_args_list[0].args[0]
    assert sender_ref in str(query.compile().params.values())
    assert "not establish this claim" in response
    assert "Only accessible public sources were reviewed." in response
    assert "AZ-261026-ABC123" in response


def test_parser_rejects_self_messages_from_business_number() -> None:
    from app.modules.channels.whatsapp import _parse_message_events

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {
                                "phone_number_id": "12345",
                                "display_phone_number": "254750288942",
                            },
                            "messages": [
                                {
                                    "id": "wamid.self1",
                                    "from": "12345",
                                    "type": "text",
                                    "text": {"body": "echo message"},
                                },
                                {
                                    "id": "wamid.self2",
                                    "from": "254750288942",
                                    "type": "text",
                                    "text": {"body": "echo message"},
                                },
                                {
                                    "id": "wamid.self3",
                                    "from": "+254750288942",
                                    "type": "text",
                                    "text": {"body": "echo message"},
                                },
                            ],
                        },
                    }
                ]
            }
        ],
    }

    events, summary = _parse_message_events(payload)
    assert events == []
    assert summary["parsed_messages"] == 0
    assert "self_message:3" in summary["rejections"]


def test_parser_rejects_bot_echo_messages() -> None:
    from app.modules.channels.whatsapp import _parse_message_events

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": "12345"},
                            "messages": [
                                {
                                    "id": "wamid.echo1",
                                    "from": "254700000000",
                                    "type": "text",
                                    "text": {
                                        "body": (
                                            "Received. Agent Zero is investigating this request. "
                                            "Send RESULT or RESULT AZ-261026-ABC123"
                                        )
                                    },
                                },
                                {
                                    "id": "wamid.echo2",
                                    "from": "254700000000",
                                    "type": "text",
                                    "text": {
                                        "body": "This check is still underway. No conclusion yet."
                                    },
                                },
                                {
                                    "id": "wamid.echo3",
                                    "from": "254700000000",
                                    "type": "text",
                                    "text": {
                                        "body": "Check started.\n\nReference: AZ-261026-ABC123"
                                    },
                                },
                            ],
                        },
                    }
                ]
            }
        ],
    }

    events, summary = _parse_message_events(payload)
    assert events == []
    assert summary["parsed_messages"] == 0
    assert "bot_echo:3" in summary["rejections"]


def test_greeting_is_conversational_and_does_not_create_an_investigation() -> None:
    session = MagicMock()
    conversation = _conversation_fixture()
    session.scalar.return_value = conversation
    session.get.return_value = SimpleNamespace(id=UUID(int=1))
    event = IncomingWhatsAppMessage(
        message_id="wamid.greeting",
        sender="254700000000",
        phone_number_id="12345",
        message_type="text",
        text="Hi there",
    )
    output = SimpleNamespace(
        intent="CONVERSATION",
        reply="Hi! I can help you investigate factual claims or talk through a story.",
        claims=[],
        queries=[],
        clarification_question=None,
        reference=None,
    )

    async def immediate_in_threadpool(function, *args, **kwargs):
        return function(*args, **kwargs)

    with (
        patch("app.modules.conversations.service._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service._complete_inbound_event"),
        patch("app.modules.conversations.service.InvestigationService") as service,
        patch("app.modules.conversations.service.ModelGateway") as gateway,
        patch("app.modules.channels.whatsapp.send_text_message") as send,
        patch(
            "app.modules.conversations.service.run_in_threadpool",
            side_effect=immediate_in_threadpool,
        ),
    ):
        gateway.return_value.interpret_whatsapp_turn = AsyncMock(
            return_value=SimpleNamespace(output=output)
        )
        assert asyncio.run(_handle_message(session, event, _settings()))

    service.return_value.create.assert_not_called()
    assert conversation.state == "IDLE"
    assert send.call_args.args[1] == (
        "Hi, I’m Agent Zero. I can talk through what you’ve shared or help investigate a "
        "factual claim using public evidence. What are you looking into?"
    )


def test_factual_question_without_question_mark_gets_a_useful_safe_response() -> None:
    reply = _conversation_reply("What is Sinaps Technology")

    assert "can’t provide general company profiles yet" in reply
    assert "specific factual claim" in reply
    assert "No investigation has started" in reply


def test_short_topic_follow_up_is_acknowledged_instead_of_repeating_generic_prompt() -> None:
    context = [
        {"role": "user", "content": "What is Sinaps Technology"},
        {
            "role": "assistant",
            "content": "What would you like me to help investigate?",
        },
    ]

    reply = _conversation_reply("Sinaps Technology", context=context)

    assert "Sinaps Technology" in reply
    assert "specific factual claim" in reply
    assert "No investigation has started" in reply
    assert "Thanks for the context" not in reply


def test_factual_question_with_question_mark_uses_same_scope_and_safety_copy() -> None:
    reply = _conversation_reply("What is Sinaps Technology?")

    assert "can’t provide general company profiles yet" in reply
    assert "No investigation has started" in reply
