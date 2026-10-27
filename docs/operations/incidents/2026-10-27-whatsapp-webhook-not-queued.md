# WhatsApp webhook accepted without an investigation job

**Date:** 2026-10-27 (UTC)
**Services:** Cloudflare Worker `sinaps-wa-webhook`, Render API and Celery worker
**Severity:** WhatsApp intake is unverified; API acknowledges callbacks

## Evidence

- Two user-initiated Worker `POST /webhook` invocations returned HTTP 200 with no Worker exceptions.
- The corresponding Render API `POST /api/v1/channels/whatsapp/webhook` access logs returned HTTP 200.
- The Celery worker continued to run `agent_zero.dispatch_outbox` and `agent_zero.recover_stalled_investigations` successfully, but no `agent_zero.process_investigation` task or outbox dispatch was observed in the callback windows.
- A read-only Meta Graph API lookup found one app subscription on the WhatsApp Business Account, named `Sinaps Technology`, with no callback override. The app dashboard showed the `messages` webhook field subscribed.
- Direct database inspection was blocked by the database IP allowlist; service SSH was unavailable because no Render SSH public key is registered. No database rows or message content were retrieved.

## Assessment

The Cloudflare-to-Render transport and signature/verification path are functioning. The HTTP 200 alone does not prove the POST contained a supported inbound text event: the handler also acknowledges status-only callbacks and currently logs no parsed-event summary. The available evidence does not identify whether Meta delivered a status callback, the parser rejected a message shape, or the sender/phone-number check ignored an event. Do not claim the WhatsApp investigation flow is working yet.

## Mitigation in progress

Added privacy-safe API diagnostics locally. They record only callback field categories, raw message/status counts, parsed message count, and allow-listed message types. They never record message text, sender, message ID, phone-number ID, signature, or token. Added tests covering status-only callbacks, parsed text events, and privacy. Focused tests pass: `13 passed`; Ruff passes. The change has not yet been deployed.

## Next steps

1. Deploy the diagnostic-only API change.
2. Ask the owner to send one plain-text claim from the designated WhatsApp number.
3. Correlate Worker/API status with the new safe callback summary and Celery task logs.
4. If `parsed_messages=0`, use the callback field/status/raw counts and message types to inspect Meta delivery and parser assumptions. If a text message is parsed but not queued, trace the handler/outbox transaction and worker dispatch.

No agent-originated WhatsApp message was sent. Render services remain online at the owner's request.

## Rollback

Revert the diagnostic-only change in `backend/app/modules/channels/whatsapp.py` and its tests, then redeploy the prior API revision. No schema or data migration is involved.
