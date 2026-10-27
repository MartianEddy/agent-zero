# WhatsApp webhook accepted without an investigation job

**Date:** 2026-10-27 (UTC)
**Services:** Cloudflare Worker `sinaps-wa-webhook`, Render API and Celery worker
**Severity:** WhatsApp intake is unverified; API acknowledges callbacks

## Evidence

- Two user-initiated Worker `POST /webhook` invocations returned HTTP 200 with no Worker exceptions.
- The corresponding Render API `POST /api/v1/channels/whatsapp/webhook` access logs returned HTTP 200.
- After deploying diagnostic commit `55ec0e2`, a fresh callback at 11:11:37 UTC was classified as `field=messages`, `raw_messages=1`, `statuses=0`, `message_types=text`, `parsed_messages=0`. No investigation job was queued.
- The Celery worker continued to run `agent_zero.dispatch_outbox` and `agent_zero.recover_stalled_investigations` successfully, but no `agent_zero.process_investigation` task or outbox dispatch was observed in the callback windows.
- A read-only Meta Graph API lookup found one app subscription on the WhatsApp Business Account, named `Sinaps Technology`, with no callback override. The app dashboard showed the `messages` webhook field subscribed.
- Direct database inspection was blocked by the database IP allowlist; service SSH was unavailable because no Render SSH public key is registered. No database rows or message content were retrieved.

## Assessment

The Cloudflare-to-Render transport and signature/verification path are functioning. The latest callback is an inbound `messages` event containing one text item, but Agent Zero parsed zero messages. The failure is inside the application parsing boundary, before the investigation/outbox/worker path. The initial diagnostic did not identify which required input failed validation, so the exact field is still unknown. Do not claim the WhatsApp investigation flow is working yet.

## Mitigation in progress

Deployed `55ec0e2` with privacy-safe callback field/count/type logging. A follow-up local change records only allow-listed parser rejection categories (such as invalid message ID, invalid sender format, invalid text body, or missing phone-number metadata); it never records the rejected value. Added tests covering status-only callbacks, parsed text events, parser rejection, and privacy. Focused tests pass: `14 passed`; Ruff passes. The rejection-category follow-up has not yet been deployed.

## Next steps

1. Deploy the rejection-category diagnostic.
2. Ask the owner to send one plain-text claim from the designated WhatsApp number.
3. Use `rejections=` counts to identify the failing parser condition without viewing the value.
4. Fix that parser condition with a realistic regression fixture, then verify parsing, outbox dispatch, Celery processing, and the user-facing acknowledgement.

No agent-originated WhatsApp message was sent. Render services remain online at the owner's request.

## Rollback

Revert the diagnostic-only change in `backend/app/modules/channels/whatsapp.py` and its tests, then redeploy the prior API revision. No schema or data migration is involved.
