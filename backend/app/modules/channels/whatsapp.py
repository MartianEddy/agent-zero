"""Meta WhatsApp Cloud API transport for Agent Zero investigations.

Webhook events are authenticated by Meta's app-secret signature. The channel
only adapts incoming messages to the existing investigation service; it does
not implement a second research or assessment pipeline.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi import Request as FastAPIRequest
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.domain.investigation import Channel, InputType, InvestigationStatus
from app.modules.investigations.models import (
    Finding,
    Investigation,
    ProcessingJob,
    Submission,
    VerificationBrief,
)
from app.modules.investigations.service import DEV_USER_ID, InvestigationService
from app.modules.investigations.summary import finding_result_summary

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/channels/whatsapp", tags=["WhatsApp Cloud API"])
MAX_WEBHOOK_BYTES = 1_000_000
MAX_MESSAGE_CHARS = 20_000
MAX_MESSAGES_PER_WEBHOOK = 25
GRAPH_SEND_TIMEOUT_SECONDS = 8


@dataclass(frozen=True)
class IncomingWhatsAppMessage:
    message_id: str
    sender: str
    phone_number_id: str
    message_type: str
    text: str | None


class WhatsAppConfigurationError(RuntimeError):
    """The Cloud API integration is disabled or incompletely configured."""


class WhatsAppSendError(RuntimeError):
    """Meta rejected or could not receive an outbound message."""


def _configured_settings():
    settings = get_settings()
    values = (
        settings.whatsapp_access_token,
        settings.whatsapp_app_secret,
        settings.whatsapp_verify_token,
        settings.whatsapp_phone_number_id,
        settings.whatsapp_identity_key,
    )
    if not all(values):
        raise WhatsAppConfigurationError
    return settings


def verify_webhook_signature(body: bytes, signature: str | None, app_secret: str) -> bool:
    """Verify X-Hub-Signature-256 against the exact raw request bytes."""
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _message_event(
    message: dict, phone_number_id: str
) -> tuple[IncomingWhatsAppMessage | None, str | None]:
    message_id = message.get("id")
    sender = message.get("from")
    message_type = message.get("type")
    if not isinstance(message_id, str) or not message_id or len(message_id) > 200:
        return None, "invalid_message_id"
    if not isinstance(sender, str) or not re.fullmatch(r"[0-9]{5,20}", sender):
        return None, "invalid_sender"
    if not isinstance(message_type, str):
        return None, "invalid_message_type"
    text: str | None = None
    if message_type == "text":
        text_value = message.get("text")
        if isinstance(text_value, dict) and isinstance(text_value.get("body"), str):
            text = text_value["body"].strip()
            if not text:
                return None, "empty_text"
        else:
            return None, "invalid_text_body"
    return (
        IncomingWhatsAppMessage(
            message_id=message_id,
            sender=sender,
            phone_number_id=phone_number_id,
            message_type=message_type,
            text=text,
        ),
        None,
    )


def _parse_message_events(
    payload: object,
) -> tuple[list[IncomingWhatsAppMessage], dict[str, object]]:
    """Parse supported messages and collect privacy-safe rejection diagnostics."""
    events: list[IncomingWhatsAppMessage] = []
    callback_fields: set[str] = set()
    message_types: set[str] = set()
    rejection_counts: dict[str, int] = {}
    summary: dict[str, object] = {
        "fields": "none",
        "raw_messages": 0,
        "statuses": 0,
        "parsed_messages": 0,
        "message_types": "none",
        "rejections": "none",
    }
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        return events, summary

    entries = payload.get("entry")
    if not isinstance(entries, list):
        return events, summary

    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("changes"), list):
            continue
        for change in entry["changes"]:
            if not isinstance(change, dict):
                continue
            field = change.get("field")
            callback_fields.add(
                field
                if isinstance(field, str) and field in {"messages", "statuses"}
                else "other"
            )
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            statuses = value.get("statuses")
            if isinstance(statuses, list):
                summary["statuses"] = int(summary["statuses"]) + len(statuses)
            if field != "messages":
                continue

            messages = value.get("messages")
            if not isinstance(messages, list):
                rejection_counts["missing_message_list"] = (
                    rejection_counts.get("missing_message_list", 0) + 1
                )
                continue
            summary["raw_messages"] = int(summary["raw_messages"]) + len(messages)
            metadata = value.get("metadata")
            phone_number_id = (
                metadata.get("phone_number_id") if isinstance(metadata, dict) else None
            )
            if not isinstance(phone_number_id, str) or not phone_number_id:
                rejection_counts["missing_phone_number_id"] = (
                    rejection_counts.get("missing_phone_number_id", 0) + len(messages)
                )
                continue

            for message in messages:
                if not isinstance(message, dict):
                    rejection_counts["invalid_message_object"] = (
                        rejection_counts.get("invalid_message_object", 0) + 1
                    )
                    continue
                message_type = message.get("type")
                if isinstance(message_type, str):
                    message_types.add(
                        message_type
                        if message_type
                        in {
                            "audio",
                            "button",
                            "contacts",
                            "document",
                            "image",
                            "interactive",
                            "location",
                            "order",
                            "reaction",
                            "sticker",
                            "system",
                            "text",
                            "unknown",
                            "video",
                        }
                        else "other"
                    )
                else:
                    message_types.add("other")
                event, rejection = _message_event(message, phone_number_id)
                if event is not None:
                    events.append(event)
                    if len(events) >= MAX_MESSAGES_PER_WEBHOOK:
                        break
                elif rejection is not None:
                    rejection_counts[rejection] = rejection_counts.get(rejection, 0) + 1
            if len(events) >= MAX_MESSAGES_PER_WEBHOOK:
                break
        if len(events) >= MAX_MESSAGES_PER_WEBHOOK:
            break

    summary.update(
        {
            "fields": ",".join(sorted(callback_fields)) or "none",
            "parsed_messages": len(events),
            "message_types": ",".join(sorted(message_types)) or "none",
            "rejections": ",".join(
                f"{reason}:{count}" for reason, count in sorted(rejection_counts.items())
            )
            or "none",
        }
    )
    return events, summary


def parse_message_events(payload: object) -> list[IncomingWhatsAppMessage]:
    """Read only supported Cloud API message events; ignore status callbacks."""
    events, _summary = _parse_message_events(payload)
    return events


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def send_text_message(recipient: str, body: str) -> None:
    """Send a user-initiated service reply through the configured phone number."""
    settings = _configured_settings()
    if not re.fullmatch(r"[0-9]{5,20}", recipient) or not body.strip() or len(body) > 4096:
        raise WhatsAppSendError("Outbound message is invalid")
    phone_number_id = settings.whatsapp_phone_number_id
    endpoint = (
        f"https://graph.facebook.com/{settings.whatsapp_graph_api_version}/"
        f"{phone_number_id}/messages"
    )
    request = Request(
        endpoint,
        data=json.dumps(
            {
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "text",
                "text": {"body": body.strip()},
            }
        ).encode(),
        headers={
            "Authorization": f"Bearer {settings.whatsapp_access_token.get_secret_value()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with build_opener(_NoRedirect).open(
            request, timeout=GRAPH_SEND_TIMEOUT_SECONDS
        ) as response:
            if not 200 <= response.status < 300:
                raise WhatsAppSendError("Meta rejected the outbound message")
            response.read(64_000)
    except HTTPError as exc:
        raise WhatsAppSendError(f"Meta rejected the outbound message (HTTP {exc.code})") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise WhatsAppSendError("Meta message delivery failed") from exc


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


async def _handle_message(session: Session, event: IncomingWhatsAppMessage, settings) -> bool:
    """Persist a new inquiry or answer a result command. Returns whether it was accepted."""
    if event.phone_number_id != settings.whatsapp_phone_number_id:
        logger.warning("Ignoring WhatsApp event for an unconfigured phone number")
        return False
    identity_key = settings.whatsapp_identity_key.get_secret_value()
    sender_ref = _sender_reference(event.sender, identity_key)
    if event.message_type != "text" or event.text is None:
        await run_in_threadpool(
            send_text_message,
            event.sender,
            "I can currently investigate text claims and public URLs. "
            "Send a text claim or public link to begin.",
        )
        return True

    command = event.text.strip()
    if len(command) > MAX_MESSAGE_CHARS:
        await run_in_threadpool(
            send_text_message,
            event.sender,
            f"That message is too long. Please keep it under {MAX_MESSAGE_CHARS:,} characters.",
        )
        return True
    if command.casefold() == "result" or command.casefold().startswith("result "):
        reference = command[6:].strip() or None
        if reference and not re.fullmatch(r"AZ-[0-9]{6}-[A-F0-9]{6}", reference, re.IGNORECASE):
            await run_in_threadpool(
                send_text_message, event.sender, "Use RESULT or RESULT AZ-YYMMDD-XXXXXX."
            )
            return True
        response = _result_message(
            session, settings=settings, sender_ref=sender_ref, reference=reference
        )
        await run_in_threadpool(send_text_message, event.sender, response)
        return True

    parsed = urlsplit(command)
    if parsed.scheme in {"http", "https"}:
        if not parsed.hostname or parsed.username or parsed.password:
            await run_in_threadpool(
                send_text_message,
                event.sender,
                "That URL is invalid. Send a public http or https link.",
            )
            return True
        input_type = InputType.URL
    else:
        input_type = InputType.TEXT

    message_digest = hashlib.sha256(event.message_id.encode()).hexdigest()
    idempotency_key = f"meta-wa:{event.phone_number_id}:{message_digest}"
    existing_job = session.scalar(
        select(ProcessingJob).where(ProcessingJob.idempotency_key == idempotency_key)
    )
    if existing_job is not None:
        # Meta redeliveries must not enqueue another investigation. Repeating
        # the acknowledgement lets a retry recover if the first Graph send
        # failed after the database commit.
        existing = session.get(Investigation, existing_job.investigation_id)
        if existing is not None:
            await run_in_threadpool(
                send_text_message,
                event.sender,
                "Received. Agent Zero is investigating this request. Send RESULT or "
                f"RESULT {existing.reference} to check progress and read the saved result.",
            )
        return True
    investigation = InvestigationService(session).create(
        owner_id=_owner_id(settings),
        content=command,
        input_type=input_type,
        idempotency_key=idempotency_key,
        channel=Channel.WHATSAPP,
        source_metadata={
            "platform": "meta_cloud_api",
            "provider_message_id": event.message_id,
            "sender_ref": sender_ref,
            "message_type": "TEXT",
        },
    )
    await run_in_threadpool(
        send_text_message,
        event.sender,
        "Received. Agent Zero is investigating this request. Send RESULT or "
        f"RESULT {investigation.reference} to check progress and read the saved result.",
    )
    return True


@router.get("/webhook", response_class=PlainTextResponse)
def verify_webhook(
    mode: str | None = Query(default=None, alias="hub.mode"),
    verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> PlainTextResponse:
    try:
        settings = _configured_settings()
    except WhatsAppConfigurationError as exc:
        raise HTTPException(status_code=404, detail="Webhook not found") from exc
    configured_token = settings.whatsapp_verify_token.get_secret_value()
    if (
        mode != "subscribe"
        or challenge is None
        or verify_token is None
        or not hmac.compare_digest(configured_token, verify_token)
    ):
        raise HTTPException(status_code=403, detail="Webhook verification failed")
    return PlainTextResponse(challenge)


@router.post("/webhook")
async def receive_webhook(
    request: FastAPIRequest,
    session: Session = Depends(get_db),  # noqa: B008
    signature: str | None = Header(default=None, alias="X-Hub-Signature-256"),
) -> dict[str, str]:
    try:
        settings = _configured_settings()
    except WhatsAppConfigurationError as exc:
        raise HTTPException(status_code=404, detail="Webhook not found") from exc
    body_chunks: list[bytes] = []
    body_size = 0
    async for chunk in request.stream():
        body_size += len(chunk)
        if body_size > MAX_WEBHOOK_BYTES:
            raise HTTPException(status_code=413, detail="Webhook payload is too large")
        body_chunks.append(chunk)
    raw_body = b"".join(body_chunks)
    if not verify_webhook_signature(
        raw_body, signature, settings.whatsapp_app_secret.get_secret_value()
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        raise HTTPException(status_code=400, detail="Unexpected webhook object")
    events, summary = _parse_message_events(payload)
    logger.info(
        "WhatsApp webhook payload fields=%s raw_messages=%d statuses=%d "
        "parsed_messages=%d message_types=%s rejections=%s",
        summary["fields"],
        summary["raw_messages"],
        summary["statuses"],
        summary["parsed_messages"],
        summary["message_types"],
        summary["rejections"],
    )
    if len(events) == MAX_MESSAGES_PER_WEBHOOK:
        raise HTTPException(status_code=413, detail="Too many messages in one webhook")
    handled_messages = 0
    for event in events:
        try:
            handled_messages += await _handle_message(session, event, settings)
        except WhatsAppSendError as exc:
            # If Meta retries after this error, the provider message ID keeps
            # the investigation idempotent and the existing job can be used to
            # retry only its acknowledgement.
            logger.warning("WhatsApp outbound reply failed: %s", exc)
            raise HTTPException(status_code=502, detail="WhatsApp reply could not be sent") from exc
        except Exception as exc:
            logger.error("WhatsApp webhook message processing failed")
            raise HTTPException(
                status_code=500, detail="Message processing failed"
            ) from exc
    if events:
        logger.info(
            "WhatsApp webhook messages handled=%d parsed_messages=%d",
            handled_messages,
            len(events),
        )
    return {"status": "ok"}
