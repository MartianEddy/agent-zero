import asyncio
import hashlib
import hmac
import json
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from app.core.config import Settings
from app.modules.channels.whatsapp import (
    IncomingWhatsAppMessage,
    _handle_message,
    _result_message,
    parse_message_events,
    receive_webhook,
    verify_webhook,
    verify_webhook_signature,
)


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
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": "12345"},
            "statuses": [{"recipient_id": private_sender, "status": "delivered"}],
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
    assert private_text not in caplog.text
    assert private_sender not in caplog.text


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


def test_inbound_text_uses_investigation_service_and_hmac_sender_identity() -> None:
    session = MagicMock()
    session.scalar.return_value = None
    investigation = SimpleNamespace(reference="AZ-261026-ABC123")
    event = IncomingWhatsAppMessage(
        message_id="wamid.abc",
        sender="254700000000",
        phone_number_id="12345",
        message_type="text",
        text="Check this claim",
    )
    async def immediate_in_threadpool(function, *args):
        return function(*args)

    with (
        patch("app.modules.channels.whatsapp.InvestigationService") as service,
        patch("app.modules.channels.whatsapp.send_text_message") as send,
        patch(
            "app.modules.channels.whatsapp.run_in_threadpool",
            side_effect=immediate_in_threadpool,
        ),
    ):
        service.return_value.create.return_value = investigation

        assert asyncio.run(_handle_message(session, event, _settings()))

    kwargs = service.return_value.create.call_args.kwargs
    assert kwargs["content"] == "Check this claim"
    assert kwargs["channel"].value == "WHATSAPP"
    assert kwargs["idempotency_key"].startswith("meta-wa:12345:")
    assert kwargs["source_metadata"]["platform"] == "meta_cloud_api"
    assert kwargs["source_metadata"]["sender_ref"] != event.sender
    assert send.called


def test_meta_redelivery_reuses_job_without_creating_another_investigation() -> None:
    session = MagicMock()
    session.scalar.return_value = SimpleNamespace(investigation_id=UUID(int=42))
    session.get.return_value = SimpleNamespace(reference="AZ-261026-ABC123")
    event = IncomingWhatsAppMessage(
        message_id="wamid.abc",
        sender="254700000000",
        phone_number_id="12345",
        message_type="text",
        text="Check this claim",
    )
    async def immediate_in_threadpool(function, *args):
        return function(*args)

    with (
        patch("app.modules.channels.whatsapp.InvestigationService") as service,
        patch("app.modules.channels.whatsapp.send_text_message") as send,
        patch(
            "app.modules.channels.whatsapp.run_in_threadpool",
            side_effect=immediate_in_threadpool,
        ),
    ):
        assert asyncio.run(_handle_message(session, event, _settings()))

    service.return_value.create.assert_not_called()
    send.assert_called_once()


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
