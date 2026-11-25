import asyncio
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.error import HTTPError
from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from app.core.config import Settings
from app.modules.channels.whatsapp import (
    IncomingWhatsAppMessage,
    WhatsAppSendError,
    _handle_message,
    _send_cloud_message,
    _status_diagnostics,
    parse_message_events,
    receive_webhook,
    verify_webhook,
    verify_webhook_signature,
)
from app.modules.conversations.schemas import ConversationTurn
from app.modules.conversations.service import (
    _factual_answer_message,
    _model_unavailable_reply,
    _result_message,
    _retry_message,
    _sender_reference,
)
from app.modules.investigations.investigator import _web_citations
from app.modules.investigations.service import is_retryable_failure_code
from app.modules.investigations.usage import ModelCallBudgetExceeded


def test_meta_signature_is_verified_against_raw_request_body() -> None:
    body = b'{"object":"whatsapp_business_account"}'
    secret = "app-secret"
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verify_webhook_signature(body, f"sha256={digest}", secret)
    assert not verify_webhook_signature(body + b" ", f"sha256={digest}", secret)
    assert not verify_webhook_signature(body, f"sha1={digest}", secret)
    assert not verify_webhook_signature(body, None, secret)


def test_outbound_rejection_log_keeps_meta_error_code_without_response_body() -> None:
    response = BytesIO(
        b'{"error":{"message":"recipient not allowed","code":131030,'
        b'"fbtrace_id":"private-trace-value"}}'
    )
    settings = SimpleNamespace(
        whatsapp_access_token=SimpleNamespace(get_secret_value=lambda: "token"),
        whatsapp_phone_number_id="12345",
        whatsapp_graph_api_version="v25.0",
    )
    opener = SimpleNamespace(
        open=MagicMock(
            side_effect=HTTPError(
                "https://graph.facebook.com/", 400, "Bad Request", {}, response
            )
        )
    )

    with (
        patch("app.modules.channels.whatsapp._configured_settings", return_value=settings),
        patch("app.modules.channels.whatsapp.build_opener", return_value=opener),
        pytest.raises(WhatsAppSendError, match="HTTP 400, provider code 131030") as error,
    ):
        _send_cloud_message("254700000000", {"to": "254700000000"})

    assert "private-trace-value" not in str(error.value)
    assert "recipient not allowed" not in str(error.value)


def test_outbound_status_diagnostics_correlate_sender_without_logging_number() -> None:
    identity_key = "private-test-identity-key"
    recipient = "254700000000"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "statuses": [
                                {
                                    "id": "wamid.private-provider-id",
                                    "recipient_id": recipient,
                                    "status": "failed",
                                    "errors": [{"code": 131026}],
                                }
                            ]
                        },
                    }
                ]
            }
        ],
    }

    diagnostics = _status_diagnostics(payload, identity_key=identity_key)

    assert diagnostics == [
        {
            "sender_ref": _sender_reference(recipient, identity_key),
            "state": "failed",
            "error_codes": [131026],
        }
    ]
    assert recipient not in str(diagnostics)
    assert "wamid.private-provider-id" not in str(diagnostics)


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


def test_parser_uses_meta_reply_button_id_as_the_inbound_action() -> None:
    from app.modules.channels.whatsapp import _message_event

    event, rejection = _message_event(
        {
            "id": "wamid.button-reply",
            "from": "254700000000",
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": "SUBMIT 1234ABCD", "title": "Submit claim"},
            },
        },
        "12345",
    )

    assert rejection is None
    assert event is not None
    assert event.text == "SUBMIT 1234ABCD"


def test_parser_rejects_interactive_reply_without_a_stable_action_id() -> None:
    from app.modules.channels.whatsapp import _message_event

    event, rejection = _message_event(
        {
            "id": "wamid.button-without-id",
            "from": "254700000000",
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {"title": "Submit claim"},
            },
        },
        "12345",
    )

    assert event is None
    assert rejection == "invalid_interactive_reply"


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


def test_cloud_api_send_reply_buttons_with_stable_action_ids() -> None:
    from app.modules.channels.whatsapp import send_reply_buttons

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

        send_reply_buttons(
            "254700000000",
            "Review this preview.",
            [("SUBMIT 1234ABCD", "Submit claim"), ("EDIT", "Edit claim"), ("CANCEL", "Cancel")],
        )

        request = build_opener.return_value.open.call_args.args[0]
        assert json.loads(request.data) == {
            "messaging_product": "whatsapp",
            "to": "254700000000",
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": "Review this preview."},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": "SUBMIT 1234ABCD", "title": "Submit claim"},
                        },
                        {
                            "type": "reply",
                            "reply": {"id": "EDIT", "title": "Edit claim"},
                        },
                        {
                            "type": "reply",
                            "reply": {"id": "CANCEL", "title": "Cancel"},
                        },
                    ]
                },
            },
        }


def test_long_interactive_preview_keeps_full_text_and_sends_separate_actions() -> None:
    from app.modules.channels.whatsapp import _send_whatsapp_reply

    buttons = [("SUBMIT 1234ABCD", "Submit claim"), ("EDIT", "Edit claim")]
    with (
        patch("app.modules.channels.whatsapp.send_text_message") as send_text,
        patch("app.modules.channels.whatsapp.send_reply_buttons") as send_buttons,
    ):
        _send_whatsapp_reply("254700000000", "x" * 1025, buttons)

    send_text.assert_called_once_with("254700000000", "x" * 1025)
    send_buttons.assert_called_once_with(
        "254700000000", "Choose an action for the preview above.", buttons
    )


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
        body = json.loads(request.data)
        # Meta requires BSUIDs in "recipient"; a BSUID in "to" is undeliverable (131026).
        assert body["recipient"] == "KE.opaqueABC123"
        assert "to" not in body


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
        body = json.loads(request.data)
        assert body["recipient"] == "KE.ENT.opaqueABC123"
        assert "to" not in body


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
        whatsapp_support_url="https://support.example.test/contact",
        whatsapp_conversation_enabled=True,
        max_search_queries=5,
        max_model_calls_per_investigation=4,
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
        patch("app.modules.conversations.service.inbound._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service.inbound._complete_inbound_event"),
            patch("app.modules.conversations.service.identity._notification_preference", return_value=None),
        patch("app.modules.conversations.service.ports.ModelGateway") as gateway,
        patch("app.modules.channels.whatsapp.send_text_message") as send,
        patch(
            "app.modules.conversations.service.ports.run_in_threadpool",
            side_effect=immediate_in_threadpool,
        ),
        patch("app.modules.conversations.service.ports.InvestigationService") as investigations,
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
    assert "reply *YES*" in send.call_args.args[1]
    assert "Nothing has started" in send.call_args.args[1]
    assert send.call_args.args[2] == [
        ("SUBMIT 89ABCDEF", "Submit claim"),
        ("EDIT 89ABCDEF", "Edit claim"),
        ("CANCEL 89ABCDEF", "Cancel"),
    ]


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
    assert "reply *YES*" in reply
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
        patch("app.modules.conversations.service.inbound._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service.inbound._complete_inbound_event"),
        patch("app.modules.conversations.service.identity._notification_preference", return_value=None),
        patch("app.modules.conversations.service.ports.InvestigationService") as service,
        patch("app.modules.conversations.service.ports.ModelGateway") as gateway,
        patch("app.modules.channels.whatsapp.send_reply_buttons") as send,
        patch(
            "app.modules.conversations.service.ports.run_in_threadpool",
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
    assert "Nothing has started" in preview
    assert "reply *YES* to start" in preview
    assert send.call_args.args[2] == [
        (f"SUBMIT {conversation.confirmation_token}", "Submit claim"),
        (f"EDIT {conversation.confirmation_token}", "Edit claim"),
        (f"CANCEL {conversation.confirmation_token}", "Cancel"),
    ]


def test_placeholder_claim_from_luna_is_rejected_before_preview() -> None:
    session = MagicMock()
    conversation = _conversation_fixture()
    session.scalar.return_value = conversation
    session.get.return_value = SimpleNamespace(id=UUID(int=1))
    event = IncomingWhatsAppMessage(
        message_id="wamid.placeholder-claim",
        sender="254700000000",
        phone_number_id="12345",
        message_type="text",
        text="When was it founded?",
    )
    output = SimpleNamespace(
        intent="INVESTIGATION_REQUEST",
        reply="",
        claims=[
            SimpleNamespace(
                text="Sinaps Technology was founded on a particular date.",
                claim_type="CHECKABLE_EVENT",
            )
        ],
        queries=[],
        clarification_question=None,
        reference=None,
    )

    async def immediate_in_threadpool(function, *args, **kwargs):
        return function(*args, **kwargs)

    with (
        patch("app.modules.conversations.service.inbound._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service.inbound._complete_inbound_event"),
        patch("app.modules.conversations.service.ports.InvestigationService") as investigations,
        patch("app.modules.conversations.service.ports.ModelGateway") as gateway,
        patch("app.modules.channels.whatsapp.send_text_message") as send,
        patch(
            "app.modules.conversations.service.ports.run_in_threadpool",
            side_effect=immediate_in_threadpool,
        ),
    ):
        gateway.return_value.interpret_whatsapp_turn = AsyncMock(
            return_value=SimpleNamespace(output=output)
        )
        assert asyncio.run(_handle_message(session, event, _settings()))

    investigations.return_value.create.assert_not_called()
    assert conversation.state == "NEEDS_CLARIFICATION"
    assert conversation.proposed_claims == []
    assert conversation.confirmation_token is None
    assert "particular date" not in send.call_args.args[1]
    assert "Nothing has started" in send.call_args.args[1]


def test_edit_button_reopens_draft_without_preserving_old_preview() -> None:
    from app.modules.conversations.service import ConversationService

    session = MagicMock()
    conversation = _conversation_fixture(
        state="AWAITING_CONFIRMATION",
        draft_text="Check the founding date of Sinaps Technology",
        proposed_claims=[{"text": "Old claim text", "claim_type": "CHECKABLE_EVENT"}],
        proposed_queries=[{"text": "old query"}],
        confirmation_token="1234ABCD",
        preview_version=1,
        draft_expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    session.scalar.return_value = conversation
    turn = ConversationTurn(
        message_id="wamid.edit-button",
        sender="254700000000",
        message_type="interactive",
        text="EDIT 1234ABCD",
    )
    send = MagicMock()

    async def immediate_in_threadpool(function, *args, **kwargs):
        return function(*args, **kwargs)

    with (
        patch("app.modules.conversations.service.inbound._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service.inbound._complete_inbound_event"),
        patch(
            "app.modules.conversations.service.ports.run_in_threadpool",
            side_effect=immediate_in_threadpool,
        ),
    ):
        assert asyncio.run(ConversationService(session, _settings()).handle_turn(turn, send))

    assert conversation.state == "NEEDS_CLARIFICATION"
    assert conversation.proposed_claims == []
    assert conversation.proposed_queries == []
    assert conversation.confirmation_token is None
    assert conversation.preview_version == 2
    assert "Send the corrected claim" in send.call_args.args[1]


def test_stale_edit_button_cannot_change_a_newer_preview() -> None:
    from app.modules.conversations.service import ConversationService

    session = MagicMock()
    conversation = _conversation_fixture(
        state="AWAITING_CONFIRMATION",
        draft_text="Check the founding date",
        proposed_claims=[{"text": "Current claim", "claim_type": "CHECKABLE_EVENT"}],
        confirmation_token="1234ABCD",
        preview_version=2,
        draft_expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    session.scalar.return_value = conversation
    turn = ConversationTurn(
        message_id="wamid.stale-edit-button",
        sender="254700000000",
        message_type="interactive",
        text="EDIT DEADBEEF",
    )
    send = MagicMock()

    async def immediate_in_threadpool(function, *args, **kwargs):
        return function(*args, **kwargs)

    with (
        patch("app.modules.conversations.service.inbound._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service.inbound._complete_inbound_event"),
        patch("app.modules.conversations.service.ports.ModelGateway") as gateway,
        patch(
            "app.modules.conversations.service.ports.run_in_threadpool",
            side_effect=immediate_in_threadpool,
        ),
    ):
        assert asyncio.run(ConversationService(session, _settings()).handle_turn(turn, send))

    gateway.return_value.interpret_whatsapp_turn.assert_not_called()
    assert conversation.state == "AWAITING_CONFIRMATION"
    assert conversation.confirmation_token == "1234ABCD"
    assert conversation.proposed_claims[0]["text"] == "Current claim"
    assert "older preview" in send.call_args.args[1]


def test_stale_cancel_button_cannot_discard_a_newer_preview() -> None:
    from app.modules.conversations.service import ConversationService

    session = MagicMock()
    conversation = _conversation_fixture(
        state="AWAITING_CONFIRMATION",
        draft_text="Check the founding date",
        proposed_claims=[{"text": "Current claim", "claim_type": "CHECKABLE_EVENT"}],
        confirmation_token="1234ABCD",
        preview_version=2,
        draft_expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    session.scalar.return_value = conversation
    turn = ConversationTurn(
        message_id="wamid.stale-cancel-button",
        sender="254700000000",
        message_type="interactive",
        text="CANCEL DEADBEEF",
    )
    send = MagicMock()

    async def immediate_in_threadpool(function, *args, **kwargs):
        return function(*args, **kwargs)

    with (
        patch("app.modules.conversations.service.inbound._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service.inbound._complete_inbound_event"),
        patch(
            "app.modules.conversations.service.ports.run_in_threadpool",
            side_effect=immediate_in_threadpool,
        ),
    ):
        assert asyncio.run(ConversationService(session, _settings()).handle_turn(turn, send))

    assert conversation.state == "AWAITING_CONFIRMATION"
    assert conversation.confirmation_token == "1234ABCD"
    assert conversation.proposed_claims[0]["text"] == "Current claim"
    assert "older preview" in send.call_args.args[1]


def test_explicit_submit_creates_one_investigation_from_approved_claims() -> None:
    from app.modules.investigations.models import OutboxEvent, ProcessingJob

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
    # conversation, idempotency lookup, notification preference, delivery receipt
    session.scalar.side_effect = [conversation, None, None, None]
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
        patch("app.modules.conversations.service.inbound._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service.inbound._complete_inbound_event"),
        patch("app.modules.conversations.service.ports.InvestigationService") as service,
        patch("app.modules.conversations.service.ports.ModelGateway") as gateway,
        patch("app.modules.channels.whatsapp.send_text_message") as send,
        patch(
            "app.modules.conversations.service.ports.run_in_threadpool",
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
    assert "message you here when it’s ready" in send.call_args.args[1]
    assert "*RESULT*" in send.call_args.args[1]
    assert conversation.recipient_encrypted != event.sender
    added = [item for call in session.add_all.call_args_list for item in call.args[0]]
    queued = [item for item in added if isinstance(item, ProcessingJob)]
    assert len(queued) == 1
    outbox = next(item for item in added if isinstance(item, OutboxEvent))
    assert queued[0].id is not None
    assert outbox.payload["job_id"] == str(queued[0].id)


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
        patch("app.modules.conversations.service.inbound._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service.inbound._complete_inbound_event"),
        patch("app.modules.conversations.service.ports.ModelGateway") as gateway,
        patch("app.modules.channels.whatsapp.send_text_message") as send,
        patch(
            "app.modules.conversations.service.ports.run_in_threadpool",
            side_effect=immediate_in_threadpool,
        ),
    ):
        assert asyncio.run(_handle_message(session, event, _settings()))

    gateway.return_value.interpret_whatsapp_turn.assert_not_called()
    send.assert_called_once_with(event.sender, "I received that message.")

def test_result_lookup_is_scoped_to_the_hmac_sender_and_includes_saved_limits() -> None:
    from app.domain.investigation import InvestigationStatus

    session = MagicMock()
    investigation = SimpleNamespace(
        id=UUID(int=42),
        reference="AZ-261026-ABC123",
        status=InvestigationStatus.COMPLETE,
    )
    brief = SimpleNamespace(limitations=["Only accessible public sources were reviewed."])
    finding = SimpleNamespace(
        status="INSUFFICIENT_EVIDENCE",
        statement="The sources did not establish this claim.",
        evidence_confidence="LOW",
        confidence_rationale="Few direct sources.",
        claim_id=UUID(int=7),
    )
    session.scalar.side_effect = [investigation, brief]
    session.scalars.side_effect = [[finding], [], [], [], []]
    sender_ref = "private-hmac-reference"

    response = _result_message(
        session, settings=_settings(), sender_ref=sender_ref, reference="AZ-261026-ABC123"
    )

    query = session.scalar.call_args_list[0].args[0]
    assert sender_ref in str(query.compile().params.values())
    assert "not establish this claim" in response
    assert "Only accessible public sources were reviewed." in response
    assert "AZ-261026-ABC123" in response


def test_processing_result_shows_actual_stage_and_discourages_resubmitting_claim() -> None:
    from app.domain.investigation import InvestigationStatus

    session = MagicMock()
    investigation = SimpleNamespace(
        id=UUID(int=43),
        reference="AZ-261027-55065A",
        status=InvestigationStatus.RESEARCHING,
        current_stage="RESEARCHING",
    )
    session.scalar.side_effect = [investigation, None, None]

    response = _result_message(
        session,
        settings=_settings(),
        sender_ref="private-hmac-reference",
        reference="AZ-261027-55065A",
    )

    assert "Searching for sources" in response
    assert "reply *RESULT*" in response
    assert "AZ-261027-55065A" in response


def test_result_without_reference_selects_latest_case_for_sender() -> None:
    from app.domain.investigation import InvestigationStatus

    session = MagicMock()
    investigation = SimpleNamespace(
        id=UUID(int=47),
        reference="AZ-261028-ED24C0",
        status=InvestigationStatus.RESEARCHING,
        current_stage="RESEARCHING",
    )
    session.scalar.side_effect = [investigation, None, None]

    response = _result_message(
        session,
        settings=_settings(),
        sender_ref="private-hmac-reference",
        reference=None,
    )

    query = session.scalar.call_args_list[0].args[0]
    sql = str(query.compile())
    assert "investigations.reference IS NULL" not in sql
    assert "ORDER BY investigations.created_at DESC" in sql
    assert "AZ-261028-ED24C0" in response


def test_result_lookup_falls_back_to_approved_conversation_mapping() -> None:
    from app.domain.investigation import InvestigationStatus

    conversation_id = UUID(int=48)
    investigation = SimpleNamespace(
        id=UUID(int=49),
        reference="AZ-261028-ED24C0",
        status=InvestigationStatus.RESEARCHING,
        current_stage="RESEARCHING",
    )
    session = MagicMock()
    session.scalar.side_effect = [None, investigation, None, None]

    response = _result_message(
        session,
        settings=_settings(),
        sender_ref="current-sender-hmac",
        reference="AZ-261028-ED24C0",
        conversation_id=conversation_id,
    )

    fallback_query = session.scalar.call_args_list[1].args[0]
    assert str(conversation_id) in str(fallback_query.compile().params.values())
    assert "Ref: AZ-261028-ED24C0" in response


def test_plural_results_command_uses_deterministic_result_lookup() -> None:
    session = MagicMock()
    event = IncomingWhatsAppMessage(
        message_id="wamid.results",
        sender="254700000000",
        phone_number_id="12345",
        message_type="text",
        text="Results",
    )
    conversation = _conversation_fixture()
    session.scalar.return_value = conversation

    with (
        patch("app.modules.conversations.service.inbound._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service.inbound._complete_inbound_event"),
        patch(
            "app.modules.conversations.service.case_replies._result_message", return_value="latest result"
        ) as result,
        patch("app.modules.channels.whatsapp.send_text_message") as send,
        patch(
            "app.modules.conversations.service.ports.run_in_threadpool",
            side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs),
        ),
    ):
        assert asyncio.run(_handle_message(session, event, _settings()))

    result.assert_called_once()
    assert result.call_args.kwargs["reference"] is None
    send.assert_called_once_with(event.sender, "latest result")


def test_failed_result_makes_clear_that_no_assessment_was_produced() -> None:
    from app.domain.investigation import InvestigationStatus

    session = MagicMock()
    investigation = SimpleNamespace(
        id=UUID(int=44),
        reference="AZ-261027-55065A",
        status=InvestigationStatus.FAILED,
        current_stage="FAILED",
    )
    session.scalar.side_effect = [
        investigation,
        None,
        SimpleNamespace(error_code="AUTHENTICATION_FAILED", status="BLOCKED"),
        SimpleNamespace(error_code="AUTHENTICATION_FAILED", status="BLOCKED"),
        SimpleNamespace(model_calls=0),
    ]
    session.scalars.side_effect = [
        [SimpleNamespace(text="Who owns Sinaps Technology in Kenya?")],
        [
            SimpleNamespace(
                title="Company register",
                publisher="Business Registry",
                domain="registry.example",
                canonical_url="https://registry.example/company/123?tracking=private",
                url="https://registry.example/company/123",
            )
        ],
    ]

    response = _result_message(
        session,
        settings=_settings(),
        sender_ref="private-hmac-reference",
        reference="AZ-261027-55065A",
    )

    assert "stopped before it finished" in response
    assert "No conclusion is available" in response
    assert "Who owns Sinaps Technology in Kenya?" in response
    assert "technical problem on our side" in response
    assert "not confirmed as evidence yet" in response
    assert "https://registry.example/company/123" in response
    assert "tracking=private" not in response
    assert "RETRY AZ-261027-55065A" not in response


def test_completed_result_includes_only_sources_linked_to_saved_findings() -> None:
    from app.domain.investigation import InvestigationStatus

    session = MagicMock()
    investigation = SimpleNamespace(
        id=UUID(int=45),
        reference="AZ-261027-ABC123",
        status=InvestigationStatus.COMPLETE,
        current_stage="COMPLETE",
    )
    brief = SimpleNamespace(limitations=[])
    finding = SimpleNamespace(
        status="SUPPORTED",
        statement="The record supports the claim.",
        evidence_confidence="MEDIUM",
        confidence_rationale="A direct public record was retrieved.",
        claim_id=UUID(int=8),
    )
    linked_source = SimpleNamespace(
        title="Official company record",
        publisher="Companies Registry",
        domain="registry.example",
        canonical_url="https://registry.example/company/123",
        url="https://registry.example/company/123",
    )
    session.scalar.side_effect = [investigation, brief]
    session.scalars.side_effect = [
        [finding],
        [SimpleNamespace(id=UUID(int=8), text="The company is owned by its shareholders.")],
        [UUID(int=901)],
        [UUID(int=902)],
        [linked_source],
    ]

    response = _result_message(
        session,
        settings=_settings(),
        sender_ref="private-hmac-reference",
        reference="az-261027-abc123",
    )

    assert "*Claim:* The company is owned by its shareholders." in response
    assert "Evidence supports this claim" in response
    assert "Evidence strength:* Medium" in response
    assert "Official company record" in response
    assert "https://registry.example/company/123" in response
    assert "AZ-261027-ABC123" in response


def test_retry_command_queues_same_sender_case_and_reuses_its_reference() -> None:
    from app.domain.investigation import InvestigationStatus

    session = MagicMock()
    investigation = SimpleNamespace(
        id=UUID(int=46),
        reference="AZ-261027-ABC123",
        status=InvestigationStatus.NEEDS_REVIEW,
    )
    session.scalar.side_effect = [
        investigation,
        SimpleNamespace(error_code="PROVIDER_UNAVAILABLE", status="BLOCKED"),
    ]

    with patch(
        "app.modules.conversations.service.ports.queue_investigation_retry"
    ) as retry:
        response = _retry_message(
            session,
            settings=_settings(),
            sender_ref="private-hmac-reference",
            reference="az-261027-abc123",
        )

    retry.assert_called_once()
    assert retry.call_args.kwargs["investigation"] is investigation
    assert "trying again with your saved claim" in response
    assert "AZ-261027-ABC123" in response


def test_retry_command_does_not_queue_authentication_failure() -> None:
    from app.domain.investigation import InvestigationStatus

    session = MagicMock()
    investigation = SimpleNamespace(
        id=UUID(int=47),
        reference="AZ-261027-ABC123",
        status=InvestigationStatus.NEEDS_REVIEW,
    )
    session.scalar.side_effect = [
        investigation,
        SimpleNamespace(error_code="AUTHENTICATION_FAILED", status="BLOCKED"),
    ]

    with patch(
        "app.modules.conversations.service.ports.queue_investigation_retry"
    ) as retry:
        response = _retry_message(
            session,
            settings=_settings(),
            sender_ref="private-hmac-reference",
            reference="AZ-261027-ABC123",
        )

    retry.assert_not_called()
    assert "can’t be fixed by trying again" in response
    assert "AZ-261027-ABC123" in response


def test_retry_policy_only_offers_retries_for_transient_failure_categories() -> None:
    assert is_retryable_failure_code("RATE_LIMITED")
    assert is_retryable_failure_code("PROVIDER_UNAVAILABLE")
    assert is_retryable_failure_code("TIMEOUT")
    assert not is_retryable_failure_code("AUTHENTICATION_FAILED")
    assert not is_retryable_failure_code("QUOTA_EXHAUSTED")
    assert not is_retryable_failure_code("BUDGET_EXCEEDED")
    assert not is_retryable_failure_code("PIPELINE_ERROR")


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


def test_luna_conversation_reply_is_used_without_creating_an_investigation() -> None:
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
        patch("app.modules.conversations.service.inbound._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service.inbound._complete_inbound_event"),
        patch("app.modules.conversations.service.ports.InvestigationService") as service,
        patch("app.modules.conversations.service.ports.ModelGateway") as gateway,
        patch("app.modules.channels.whatsapp.send_text_message") as send,
        patch(
            "app.modules.conversations.service.ports.run_in_threadpool",
            side_effect=immediate_in_threadpool,
        ),
    ):
        gateway.return_value.interpret_whatsapp_turn = AsyncMock(
            return_value=SimpleNamespace(output=output)
        )
        assert asyncio.run(_handle_message(session, event, _settings()))

    service.return_value.create.assert_not_called()
    assert conversation.state == "IDLE"
    assert send.call_args.args[1] == output.reply


def test_cited_quick_answer_uses_search_and_does_not_create_case() -> None:
    session = MagicMock()
    conversation = _conversation_fixture()
    session.scalar.return_value = conversation
    session.get.return_value = SimpleNamespace(id=UUID(int=1))
    event = IncomingWhatsAppMessage(
        message_id="wamid.factual-conversation",
        sender="254700000000",
        phone_number_id="12345",
        message_type="text",
        text="I’d like you to check what is Sinaps Technology?",
    )
    output = SimpleNamespace(
        intent="FACTUAL_ANSWER_REQUEST",
        reply="I will search for a cited answer.",
        claims=[],
        queries=[],
        clarification_question=None,
        reference=None,
    )

    async def immediate_in_threadpool(function, *args, **kwargs):
        return function(*args, **kwargs)

    with (
        patch("app.modules.conversations.service.inbound._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service.inbound._complete_inbound_event"),
        patch("app.modules.conversations.service.ports.InvestigationService") as service,
        patch("app.modules.conversations.service.ports.ModelGateway") as gateway,
        patch("app.modules.channels.whatsapp.send_text_message") as send,
        patch(
            "app.modules.conversations.service.ports.run_in_threadpool",
            side_effect=immediate_in_threadpool,
        ),
    ):
        gateway.return_value.interpret_whatsapp_turn = AsyncMock(
            return_value=SimpleNamespace(output=output)
        )
        gateway.return_value.answer_whatsapp_factual_question = AsyncMock(
            return_value=SimpleNamespace(
                output=SimpleNamespace(answer="Sinaps Technology provides technology services."),
                citations=({"title": "Company site", "url": "https://sinaps.example/about"},),
            )
        )
        assert asyncio.run(_handle_message(session, event, _settings()))

    service.return_value.create.assert_not_called()
    assert conversation.state == "IDLE"
    gateway.return_value.answer_whatsapp_factual_question.assert_awaited_once()
    assert "Quick answer from a fresh web search" in send.call_args.args[1]
    assert "https://sinaps.example/about" in send.call_args.args[1]
    assert "not a full investigation" in send.call_args.args[1]


def test_quick_answer_without_citations_fails_closed() -> None:
    message = _factual_answer_message("The answer is 42.", ())
    assert "won’t guess" in message
    assert "won’t guess" in message
    assert "Reply *CHECK*" in message


def test_quick_answer_keeps_long_source_lists_within_whatsapp_limit() -> None:
    long_url = "https://example.org/" + ("source/" * 290)
    message = _factual_answer_message(
        "A concise sourced answer.",
        tuple({"title": f"Source {index}", "url": long_url + str(index)} for index in range(3)),
    )
    assert len(message) <= 3900
    assert "Quick answer from a fresh web search" in message


def test_web_citation_extraction_rejects_unsafe_urls() -> None:
    raw = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="message",
                content=[
                    SimpleNamespace(
                        annotations=[
                            SimpleNamespace(
                                type="url_citation",
                                url_citation=SimpleNamespace(
                                    url="javascript:alert(1)", title="unsafe"
                                ),
                            ),
                            SimpleNamespace(
                                type="url_citation",
                                url_citation=SimpleNamespace(
                                    url="https://example.org/fact", title="Source"
                                ),
                            ),
                        ]
                    )
                ],
            )
        ]
    )
    assert _web_citations([raw]) == ({"url": "https://example.org/fact", "title": "Source"},)


def test_start_without_preview_explains_next_step_without_calling_luna() -> None:
    from app.modules.conversations.service import ConversationService

    session = MagicMock()
    conversation = _conversation_fixture()
    session.scalar.return_value = conversation
    event = IncomingWhatsAppMessage(
        message_id="wamid.start-without-preview",
        sender="254700000000",
        phone_number_id="12345",
        message_type="text",
        text="Start",
    )
    send = MagicMock()

    async def immediate_in_threadpool(function, *args, **kwargs):
        return function(*args, **kwargs)

    with (
        patch("app.modules.conversations.service.inbound._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service.inbound._complete_inbound_event"),
        patch("app.modules.conversations.service.ports.ModelGateway") as gateway,
        patch(
            "app.modules.conversations.service.ports.run_in_threadpool",
            side_effect=immediate_in_threadpool,
        ),
    ):
        assert asyncio.run(
            ConversationService(session, _settings()).handle_turn(
                ConversationTurn(
                    message_id=event.message_id,
                    sender=event.sender,
                    message_type=event.message_type,
                    text=event.text,
                ),
                send,
            )
        )

    gateway.return_value.interpret_whatsapp_turn.assert_not_called()
    assert "nothing to submit yet" in send.call_args.args[1]
    assert "Nothing has started" in send.call_args.args[1]


def test_chat_budget_error_gives_reset_time_instead_of_saying_retry_shortly() -> None:
    error = ModelCallBudgetExceeded(
        "WhatsApp conversation model-call budget reached.",
        reset_at=datetime(2026, 10, 28, 12, 0, tzinfo=UTC),
    )

    reply = _model_unavailable_reply(error)

    assert "3:00 PM EAT on Wed, Oct 28" in reply
    assert "nothing was started" in reply
    assert "try again shortly" not in reply


def _run_pending_preview_turn(text: str, *, message_type: str = "text", intent: str = "CONFIRM_DRAFT"):
    from app.modules.conversations.schemas import ConversationTurn
    from app.modules.conversations.service import ConversationService

    session = MagicMock()
    conversation = _conversation_fixture(
        state="AWAITING_CONFIRMATION",
        draft_text="Please investigate this claim",
        draft_input_type="TEXT",
        proposed_claims=[{"text": "Company X received the contract early.", "claim_type": "CHECKABLE_EVENT"}],
        draft_expires_at=datetime.now(UTC) + timedelta(minutes=20),
        preview_version=1,
        confirmation_token="1234ABCD",
    )
    session.scalar.side_effect = [conversation, None, None]
    investigation = SimpleNamespace(id=UUID(int=201), reference="AZ-261028-ABC123", current_stage="X")
    event = IncomingWhatsAppMessage(
        message_id=f"wamid.{abs(hash(text))}", sender="254700000000",
        phone_number_id="12345", message_type=message_type, text=text,
    )

    async def immediate_in_threadpool(function, *args, **kwargs):
        return function(*args, **kwargs)

    with (
        patch("app.modules.conversations.service.inbound._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service.inbound._complete_inbound_event"),
        patch("app.modules.conversations.service.identity._notification_preference", return_value=None),
        patch("app.modules.conversations.service.ports.InvestigationService") as service,
        patch("app.modules.conversations.service.ports.ModelGateway") as gateway,
        patch("app.modules.channels.whatsapp.send_text_message") as send,
        patch("app.modules.conversations.service.ports.run_in_threadpool", side_effect=immediate_in_threadpool),
    ):
        service.return_value.create.return_value = investigation
        gateway.return_value.interpret_whatsapp_turn = AsyncMock(
            return_value=SimpleNamespace(output=SimpleNamespace(
                intent=intent, reply="", claims=[], queries=[],
                clarification_question=None, reference=None,
            ))
        )
        assert asyncio.run(
            ConversationService(session, _settings()).handle_turn(
                ConversationTurn(
                    message_id=event.message_id,
                    sender=event.sender,
                    message_type=event.message_type,
                    text=event.text,
                ),
                send,
            )
        )
    return service, send


def test_typed_yes_approves_the_preview_on_screen() -> None:
    for phrase in ("yes", "Yes!", "go ahead", "Ndiyo", "submit"):
        service, send = _run_pending_preview_turn(phrase)
        service.return_value.create.assert_called_once()
        assert "checking this now" in send.call_args.args[1]


def test_conditional_or_ambiguous_replies_do_not_start_a_check() -> None:
    for phrase in ("yes but change the date", "ok", "maybe", "sawa"):
        service, _send = _run_pending_preview_turn(phrase)
        service.return_value.create.assert_not_called()


def test_button_tap_from_an_older_preview_still_cannot_start_a_check() -> None:
    service, send = _run_pending_preview_turn("SUBMIT 00000000", message_type="interactive")
    service.return_value.create.assert_not_called()
    assert "Nothing has started" in send.call_args.args[1]


def _send_settings():
    return SimpleNamespace(
        whatsapp_access_token=SimpleNamespace(get_secret_value=lambda: "access-token"),
        whatsapp_app_secret=SimpleNamespace(get_secret_value=lambda: "app-secret"),
        whatsapp_verify_token=SimpleNamespace(get_secret_value=lambda: "verify-token"),
        whatsapp_identity_key=SimpleNamespace(get_secret_value=lambda: "i" * 32),
        whatsapp_phone_number_id="12345",
        whatsapp_graph_api_version="v25.0",
    )


def _sent_body(send) -> dict:
    response = type("Response", (), {"status": 200, "read": lambda self, _size: b"{}"})()
    with (
        patch("app.modules.channels.whatsapp.get_settings", return_value=_send_settings()),
        patch("app.modules.channels.whatsapp.build_opener") as build_opener,
    ):
        build_opener.return_value.open.return_value.__enter__.return_value = response
        send()
        return json.loads(build_opener.return_value.open.call_args.args[0].data)


def test_phone_numbers_are_addressed_with_to_and_buttons_with_recipient_for_bsuid() -> None:
    from app.modules.channels.whatsapp import send_reply_buttons, send_text_message

    phone = _sent_body(lambda: send_text_message("+254700000000", "Hi"))
    assert phone["to"] == "254700000000" and "recipient" not in phone
    buttons = _sent_body(
        lambda: send_reply_buttons("KE.abc123", "Pick one", [("SUBMIT 1", "Submit claim")])
    )
    assert buttons["recipient"] == "KE.abc123" and "to" not in buttons


def test_username_user_without_phone_is_parsed_with_bsuid_identity_and_reply_address() -> None:
    from app.modules.channels.whatsapp import parse_message_events

    payload = {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "12345", "display_phone_number": "254711000000"},
        "contacts": [{"profile": {"name": "A", "username": "ann.k"}, "user_id": "KE.111AAA"}],
        "messages": [{"id": "wamid.1", "from_user_id": "KE.111AAA", "type": "text",
                      "text": {"body": "Is this true?"}}],
    }}]}]}
    [event] = parse_message_events(payload)
    assert event.sender == "KE.111AAA"
    assert event.user_id == "KE.111AAA"


def test_phone_is_the_reply_address_and_bsuid_the_identity_when_both_are_present() -> None:
    from app.modules.channels.whatsapp import parse_message_events

    payload = {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "12345"},
        "contacts": [{"wa_id": "254700000000", "user_id": "KE.222BBB"}],
        "messages": [{"id": "wamid.2", "from": "254700000000", "from_user_id": "KE.222BBB",
                      "type": "text", "text": {"body": "hello"}}],
    }}]}]}
    [event] = parse_message_events(payload)
    assert event.sender == "254700000000"
    assert event.user_id == "KE.222BBB"


def test_identity_ref_is_stable_when_the_phone_number_disappears() -> None:
    from app.modules.conversations.service import _identity_refs

    key = "k" * 32
    with_phone = ConversationTurn(
        message_id="1", sender="254700000000", message_type="text", text="x", user_id="KE.333"
    )
    hidden = ConversationTurn(
        message_id="2", sender="KE.333", message_type="text", text="x", user_id="KE.333"
    )
    ref_a, legacy_a = _identity_refs(with_phone, key)
    ref_b, legacy_b = _identity_refs(hidden, key)
    assert ref_a == ref_b
    assert legacy_a is not None and legacy_b is None
    phone_only = ConversationTurn(message_id="3", sender="254700000000", message_type="text", text="x")
    assert _identity_refs(phone_only, key) == (legacy_a, None)


def test_failed_status_for_bsuid_send_is_still_diagnosed() -> None:
    from app.modules.channels.whatsapp import _status_diagnostics

    payload = {"entry": [{"changes": [{"field": "messages", "value": {"statuses": [
        {"status": "failed", "recipient_user_id": "KE.444", "errors": [{"code": 131026}]}
    ]}}]}]}
    [diagnostic] = _status_diagnostics(payload, identity_key="k" * 32)
    assert diagnostic["state"] == "failed" and diagnostic["error_codes"] == [131026]


def _flow_turn(conversation, text, output, *, factual=None, message_type="text"):
    """Run one turn through the real handler with the model mocked; return (send, gateway)."""
    from app.modules.conversations.schemas import ConversationTurn
    from app.modules.conversations.service import ConversationService

    session = MagicMock()
    session.scalar.return_value = conversation
    session.get.return_value = SimpleNamespace(id=UUID(int=1))

    async def immediate_in_threadpool(function, *args, **kwargs):
        return function(*args, **kwargs)

    with (
        patch("app.modules.conversations.service.inbound._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service.inbound._complete_inbound_event"),
        patch("app.modules.conversations.service.identity._notification_preference", return_value=None),
        patch("app.modules.conversations.service.ports.InvestigationService") as service,
        patch("app.modules.conversations.service.ports.ModelGateway") as gateway,
        patch("app.modules.conversations.service.ports.run_in_threadpool", side_effect=immediate_in_threadpool),
    ):
        send = MagicMock()
        gateway.return_value.interpret_whatsapp_turn = AsyncMock(return_value=SimpleNamespace(output=output))
        gateway.return_value.answer_whatsapp_factual_question = AsyncMock(return_value=factual)
        assert asyncio.run(ConversationService(session, _settings()).handle_turn(
            ConversationTurn(message_id=f"wamid.{abs(hash(text))}", sender="254700000000",
                             message_type=message_type, text=text),
            send,
        ))
    return send, gateway, service


def _output(intent, claims=(), question=None):
    return SimpleNamespace(
        intent=intent, reply="ok", queries=[], reference=None, clarification_question=question,
        claims=[SimpleNamespace(text=text, claim_type="CHECKABLE_EVENT") for text in claims],
    )


def test_repeated_clarification_offers_check_as_written_instead_of_looping() -> None:
    conversation = _conversation_fixture(
        state="NEEDS_CLARIFICATION",
        draft_text="the governor thing\nClarification: the one in the news\nClarification: you know",
        draft_expires_at=datetime.now(UTC) + timedelta(minutes=20),
    )
    send, _gateway, _service = _flow_turn(
        conversation, "it was last week", _output("INVESTIGATION_REQUEST", question="Which governor?")
    )
    message, buttons = send.call_args.args[1], send.call_args.args[2]
    assert "Check as written" in message
    assert buttons == [("CHECK AS IS", "Check as written")]


def test_check_as_written_builds_a_preview_from_the_users_own_words() -> None:
    conversation = _conversation_fixture(
        state="NEEDS_CLARIFICATION",
        draft_text="Governor Sakaja closed Gikomba market\nClarification: in March 2025",
        draft_expires_at=datetime.now(UTC) + timedelta(minutes=20),
    )
    send, gateway, _service = _flow_turn(
        conversation, "CHECK AS IS", _output("CONVERSATION"), message_type="interactive"
    )
    gateway.return_value.interpret_whatsapp_turn.assert_not_called()
    assert conversation.state == "AWAITING_CONFIRMATION"
    assert conversation.proposed_claims == [{
        "text": "Governor Sakaja closed Gikomba market in March 2025",
        "claim_type": "CHECKABLE_EVENT",
    }]
    assert "Nothing has started yet" in send.call_args.args[1]


def test_yes_after_a_quick_answer_moves_to_a_claim_preview() -> None:
    conversation = _conversation_fixture(context_json=[
        {"role": "user", "content": "Did Kenya ban plastic bags in 2017?"},
        {"role": "assistant", "content": "Quick answer from a fresh web search (not a full investigation): Yes."},
    ])
    send, gateway, _service = _flow_turn(
        conversation, "yes", _output("INVESTIGATION_REQUEST", claims=["Kenya banned plastic bags in 2017."])
    )
    sent_text = gateway.return_value.interpret_whatsapp_turn.call_args.kwargs["text"]
    assert "Did Kenya ban plastic bags in 2017?" in sent_text
    assert conversation.state == "AWAITING_CONFIRMATION"
    assert "Kenya banned plastic bags in 2017." in send.call_args.args[1]


def test_question_while_preview_waits_is_answered_and_preview_kept() -> None:
    conversation = _conversation_fixture(
        state="AWAITING_CONFIRMATION",
        proposed_claims=[{"text": "A claim.", "claim_type": "CHECKABLE_EVENT"}],
        confirmation_token="ABCD1234",
        draft_expires_at=datetime.now(UTC) + timedelta(minutes=20),
    )
    factual = SimpleNamespace(
        output=SimpleNamespace(answer="Nairobi is the capital."),
        citations=({"url": "https://example.org/a", "title": "Source"},),
    )
    send, _gateway, _service = _flow_turn(
        conversation, "What is the capital of Kenya?", _output("FACTUAL_ANSWER_REQUEST"), factual=factual
    )
    message = send.call_args.args[1]
    assert "Nairobi is the capital." in message
    assert "preview is still waiting" in message
    assert conversation.state == "AWAITING_CONFIRMATION"


def test_correction_after_edit_replaces_the_old_claim() -> None:
    conversation = _conversation_fixture(
        state="NEEDS_CLARIFICATION",
        draft_text="Old wrong claim",
        clarification_question="Send the corrected claim or missing detail.",
        draft_expires_at=datetime.now(UTC) + timedelta(minutes=20),
    )
    _flow_turn(conversation, "The new correct claim about the budget", _output(
        "INVESTIGATION_REQUEST", claims=["The new correct claim about the budget."]
    ))
    assert "Old wrong claim" not in (conversation.draft_text or "")


def test_opinion_gets_a_clear_explanation_and_a_way_forward() -> None:
    conversation = _conversation_fixture()
    send, _gateway, _service = _flow_turn(conversation, "This budget is bad", _output("INVESTIGATION_REQUEST"))
    message = send.call_args.args[1]
    assert "Opinions and predictions" in message and "send just that part" in message


def test_graph_base_url_only_allows_local_http_in_development() -> None:
    import pytest

    from app.core.config import Settings

    assert Settings(whatsapp_graph_base_url="http://127.0.0.1:18999").whatsapp_graph_base_url
    for bad in ("http://example.com", "ftp://127.0.0.1", "https://user:pw@graph.example", "https://graph.facebook.com/v1"):
        with pytest.raises(ValueError):
            Settings(whatsapp_graph_base_url=bad)


def test_retry_of_a_delivered_message_is_acknowledged_without_a_second_reply() -> None:
    from app.modules.conversations.service.inbound import _claim_inbound_event

    now = datetime.now(UTC)
    receipt = SimpleNamespace(
        conversation_id=UUID(int=100), sender_ref="hmac-sender", state="DELIVERED",
        reply_text="Hello", expires_at=now + timedelta(hours=1), lease_expires_at=now,
    )
    session = MagicMock()
    session.scalar.return_value = receipt
    turn = ConversationTurn(message_id="m", sender="254700000000", message_type="text", text="hi")
    reply = _claim_inbound_event(
        session, conversation=_conversation_fixture(), event=turn, sender_ref="hmac-sender", now=now
    )
    assert reply == ""


def test_saved_but_unsent_reply_is_resent_on_retry() -> None:
    from app.modules.conversations.service.inbound import _claim_inbound_event

    now = datetime.now(UTC)
    receipt = SimpleNamespace(
        conversation_id=UUID(int=100), sender_ref="hmac-sender", state="COMPLETED",
        reply_text="Hello", expires_at=now + timedelta(hours=1), lease_expires_at=now,
    )
    session = MagicMock()
    session.scalar.return_value = receipt
    turn = ConversationTurn(message_id="m", sender="254700000000", message_type="text", text="hi")
    assert _claim_inbound_event(
        session, conversation=_conversation_fixture(), event=turn, sender_ref="hmac-sender", now=now
    ) == "Hello"


def _timeout_turn(conversation, text):
    from app.modules.conversations.schemas import ConversationTurn
    from app.modules.conversations.service import ConversationService
    from app.modules.investigations.investigator import ModelInvocationFailed
    from app.modules.investigations.provider_errors import FailureCategory

    session = MagicMock()
    session.scalar.return_value = conversation
    session.get.return_value = SimpleNamespace(id=UUID(int=1))

    async def immediate(function, *args, **kwargs):
        return function(*args, **kwargs)

    failure = ModelInvocationFailed(provider="openai", model="m", category=FailureCategory.TIMEOUT)
    with (
        patch("app.modules.conversations.service.inbound._claim_inbound_event", return_value=None),
        patch("app.modules.conversations.service.inbound._complete_inbound_event"),
        patch("app.modules.conversations.service.identity._notification_preference", return_value=None),
        patch("app.modules.conversations.service.ports.ModelGateway") as gateway,
        patch("app.modules.conversations.service.ports.run_in_threadpool", side_effect=immediate),
    ):
        gateway.return_value.interpret_whatsapp_turn = AsyncMock(side_effect=failure)
        send = MagicMock()
        assert asyncio.run(ConversationService(session, _settings()).handle_turn(
            ConversationTurn(message_id=f"w.{abs(hash(text))}", sender="254700000000",
                             message_type="text", text=text), send,
        ))
    return send


def test_ai_timeout_on_a_claim_still_gives_a_claim_preview_not_an_error() -> None:
    conversation = _conversation_fixture()
    send = _timeout_turn(conversation, "Schools in Nairobi will close on Friday")
    message = send.call_args.args[1]
    assert "Schools in Nairobi will close on Friday" in message
    assert "trouble" not in message.casefold() and "took" not in message.casefold()
    assert conversation.state == "AWAITING_CONFIRMATION"
    assert send.call_args.args[2][0][1] == "Submit claim"


def test_ai_timeout_on_a_greeting_gets_a_greeting() -> None:
    for greeting in ("hi", "Habari yako", "good morning!"):
        send = _timeout_turn(_conversation_fixture(), greeting)
        assert send.call_args.args[1].startswith("Hi! I check claims")


def test_ai_timeout_with_a_waiting_preview_offers_it_again() -> None:
    conversation = _conversation_fixture(
        state="AWAITING_CONFIRMATION",
        proposed_claims=[{"text": "A waiting claim.", "claim_type": "CHECKABLE_EVENT"}],
        confirmation_token="ABCD1234",
        draft_expires_at=datetime.now(UTC) + timedelta(minutes=20),
    )
    send = _timeout_turn(conversation, "what do you think about it")
    assert "A waiting claim." in send.call_args.args[1]
    assert send.call_args.args[2][0] == ("SUBMIT ABCD1234", "Submit claim")


def test_webhook_acknowledges_meta_and_handles_messages_in_the_background() -> None:
    from fastapi import BackgroundTasks

    payload = {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "12345"},
        "messages": [{"id": "wamid.bg", "from": "254700000000", "type": "text", "text": {"body": "hi"}}],
    }}]}]}
    raw_body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"app-secret", raw_body, hashlib.sha256).hexdigest()
    tasks = BackgroundTasks()
    with (
        patch("app.modules.channels.whatsapp.get_settings", return_value=_settings()),
        patch("app.modules.channels.whatsapp._handle_message") as handle,
    ):
        result = asyncio.run(receive_webhook(_request_with_body(raw_body), MagicMock(), signature, tasks))
    assert result == {"status": "ok"}
    handle.assert_not_called()
    assert len(tasks.tasks) == 1


def test_background_worker_shows_typing_and_retries_a_failed_send() -> None:
    from app.modules.channels import whatsapp

    event = IncomingWhatsAppMessage(
        message_id="wamid.bg2", sender="254700000000", phone_number_id="12345",
        message_type="text", text="hi",
    )
    attempts = []

    async def fake_handle(session, incoming, settings, send_message=None):
        send_message(incoming.sender, "Hello")
        return True

    def flaky_send(recipient, body, buttons=None):
        attempts.append(body)
        if len(attempts) == 1:
            raise whatsapp.WhatsAppSendError("temporary")

    with (
        patch.object(whatsapp, "send_typing_indicator") as typing,
        patch.object(whatsapp, "_handle_message", side_effect=fake_handle),
        patch.object(whatsapp, "_send_whatsapp_reply", side_effect=flaky_send),
        patch.object(whatsapp, "SessionLocal", MagicMock()),
        patch.object(whatsapp.time, "sleep"),
    ):
        whatsapp._process_events_in_background([event], _settings())
    typing.assert_called_once_with("wamid.bg2")
    assert attempts == ["Hello", "Hello"]
