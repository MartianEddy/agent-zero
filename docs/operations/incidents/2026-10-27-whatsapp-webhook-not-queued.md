# WhatsApp intake parsing and outbound delivery failure

**Date:** 2026-10-27 (UTC)
**Services:** Cloudflare Worker `sinaps-wa-webhook`, Render API and Celery worker
**Severity:** Inbound investigation works; outbound acknowledgement is undeliverable

## Evidence

- Two user-initiated Worker `POST /webhook` invocations returned HTTP 200 with no Worker exceptions.
- The corresponding Render API `POST /api/v1/channels/whatsapp/webhook` access logs returned HTTP 200.
- After deploying diagnostic commit `55ec0e2`, a fresh callback at 11:11:37 UTC was classified as `field=messages`, `raw_messages=1`, `statuses=0`, `message_types=text`, `parsed_messages=0`. No investigation job was queued.
- The Celery worker continued to run `agent_zero.dispatch_outbox` and `agent_zero.recover_stalled_investigations` successfully, but no `agent_zero.process_investigation` task or outbox dispatch was observed in the callback windows.
- A read-only Meta Graph API lookup found one app subscription on the WhatsApp Business Account, named `Sinaps Technology`, with no callback override. The app dashboard showed the `messages` webhook field subscribed.
- Direct database inspection was blocked by the database IP allowlist; service SSH was unavailable because no Render SSH public key is registered. No database rows or message content were retrieved.
- After accepting supported sender identity fields and deploying parser commit `c6edf1b`, a live callback at 11:47:22 UTC was parsed (`parsed=1`), queued, and completed by Celery. The sender still reported no acknowledgement.
- Diagnostic commit `b376add` classified the next live callback at 11:55:38 UTC as one parsed text message. The Celery task completed with `needs_review`. At 11:55:40 UTC, Meta's status webhook classified the outbound acknowledgement as `failed` with numeric error code `131026`. No recipient, WAMID, message content, or provider error text was logged.
- At 12:08:21 to 12:12:07 UTC, an inbound test message triggered an automated feedback loop producing 41 investigations in rapid succession. ClickCast's keyword flow listening on the same WhatsApp Business number matched the word "RESULT" in Agent Zero's acknowledgement and called `POST /channels/clickcast/result` (422 Unprocessable Entity), sending an automated message to the chat. Agent Zero lacked a bot-echo and self-sender filter, treating that message as a new claim and repeating the cycle every 5 seconds.

## Assessment

The Cloudflare-to-Render transport, signature verification, sender parsing, queueing, and investigation execution are functioning. The runaway loop was caused by co-existence with ClickCast and the absence of bot-echo/self-sender guards and rate limiting in `whatsapp.py`. The remaining worker-side issue is an HTTP 401 Unauthorized from OpenAI (`gpt-6-luna`), which requires updating the `OPENAI_API_KEY` on Render.

## Mitigation in progress

Added defense-in-depth loop protection in `whatsapp.py`:
1. Self-message rejection: drops messages where `from` matches `phone_number_id` or `display_phone_number` (`rejection="self_message"`).
2. Bot-echo rejection: drops messages matching Agent Zero or ClickCast bot message signatures (`rejection="bot_echo"`).
3. 5-minute duplicate submission suppression: prevents re-creating investigations for identical text from the same sender.
4. 10-second rapid-fire throttle: suppresses consecutive submissions from the same sender within 10 seconds.
Focused tests pass (32); Ruff and `git diff --check` pass. Render services remain online. Recommend disconnecting or disabling ClickCast's WhatsApp workflow so it does not conflict with the direct Cloud API adapter.

Deployed privacy-safe callback-shape and rejection diagnostics, then fixed supported sender identity handling. Deployed `b376add` to both Render API and worker; it logs only allow-listed status values and numeric error codes. Focused WhatsApp tests pass (28); Ruff and `git diff --check` pass. API readiness confirms database, Redis, and object storage are healthy.

## Next steps

1. Ask the owner to check/update WhatsApp and confirm the business number is not blocked.
2. After that, request one fresh plain-text claim and inspect the sanitized status categories.
3. If status is delivered but the user sees no reply, inspect the recipient conversation and the outbound message path; if it fails again, use Meta support diagnostics because `131026` does not disclose the specific cause.
4. Verify `RESULT` separately after acknowledgement delivery succeeds.

No operator manually sent a WhatsApp message through the Cloud API; the tested messages were owner-initiated, and Agent Zero's automatic acknowledgement failed delivery. Render services remain online at the owner's request.

## Rollback

If the status diagnostics need to be removed, revert only commit `b376add` and redeploy the preceding revision; retain the sender-identity parser fix in `c6edf1b`. No schema or data migration is involved.
