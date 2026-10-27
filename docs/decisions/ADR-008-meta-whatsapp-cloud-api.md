# ADR-008: Direct Meta WhatsApp Cloud API channel

**Status: Accepted for implementation on 2026-10-26.** Production use remains gated by the existing authentication, retention, and deployment decisions.

## Context

Agent Zero already has a ClickCast adapter that accepts text/URL submissions and sender-scoped result lookups. The product owner has registered a Meta WhatsApp Business phone number and supplied the Cloud API webhook/send-message setup. ClickCast is not required for this direct channel.

## Decision

- Add a separate Meta Cloud API webhook adapter. Keep the ClickCast adapter available and unchanged.
- Expose webhook verification and delivery at `/api/v1/channels/whatsapp/webhook`.
- Verify GET subscription challenges with a dedicated verify token. Verify POST deliveries with `X-Hub-Signature-256` over the exact raw request bytes and the Meta App Secret.
- Accept events only for the configured phone-number ID. Ignore status callbacks and reject malformed or unauthenticated deliveries.
- Support text and public-URL submissions in the first slice. Explain that media messages are not yet supported.
- Accept numeric and plus-prefixed phone IDs, regular BSUIDs (`CC.<id>`), and parent BSUIDs (`CC.ENT.<id>`). `messages[].from` may be absent or non-string in username-era payloads, so fall back to message-level `from_user_id` / `from_parent_user_id`; if those are absent, use `contacts[].user_id`, `parent_user_id`, or `wa_id` only when there is exactly one contact. Never guess a contact in an ambiguous batch. Normalize plus-prefixed phone numbers to digits for Cloud API replies and sender HMACs, while preserving opaque BSUID values exactly.
- Send only user-initiated text replies to the sender ID from the verified webhook event. The user can send `RESULT` or `RESULT AZ-YYMMDD-XXXXXX` to retrieve the latest or a specific result. No recipient identifier is persisted for later outbound messaging.
- Store sender ownership as an HMAC reference, never as the raw phone number or BSUID. Scope result lookup to the configured owner, WhatsApp channel, and sender reference.
- Use the provider message ID, hashed into a bounded idempotency key, so webhook redelivery does not create a second investigation. Outbound acknowledgements are at-least-once; a delivery retry may repeat the acknowledgement.
- Send through `POST https://graph.facebook.com/{version}/{phone-number-id}/messages`, with a bearer token and JSON body. Default Graph API version is `v25.0`, taken from the supplied Meta example; it is configurable. The Meta webhook subscription version is managed separately in Meta's app dashboard.
- Do not connect the WhatsApp Business Tools MCP to the running Agent Zero service. It is an operator/admin tool, while this integration uses the Cloud API directly.

## Configuration

Set these in the API and worker environments; never commit actual values:

- `WHATSAPP_ACCESS_TOKEN`: system-user token authorized for WhatsApp messaging.
- `WHATSAPP_APP_SECRET`: Meta app secret used to verify delivery signatures.
- `WHATSAPP_VERIFY_TOKEN`: random callback-verification value; set the same value in Meta.
- `WHATSAPP_PHONE_NUMBER_ID`: registered sender's numeric phone-number ID.
- `WHATSAPP_IDENTITY_KEY`: independent random secret, at least 32 characters, for sender HMACs.
- `WHATSAPP_OWNER_ID`: optional owner/workspace UUID; local development falls back to the existing development owner.
- `WHATSAPP_GRAPH_API_VERSION`: Graph API version, default `v25.0`.

The Meta callback is `https://sinaps-wa-webhook.sinaps-wa-webhooks.workers.dev/webhook`. The previously live Worker validated signatures, then logged sender numbers and message text without forwarding messages. A repository-managed replacement lives in [`cloudflare/sinaps-wa-webhook`](../../cloudflare/sinaps-wa-webhook/). It validates Meta's challenge/signature, bounds the raw request, and forwards GET query parameters or exact POST bytes plus `X-Hub-Signature-256` to Agent Zero. It does not log message content. On 2026-10-27, the Worker was deployed as version `f6a95135-21e2-4727-b3b0-f21a2c3ff06a`, with `AGENT_ZERO_WEBHOOK_URL=https://agent-zero-api.onrender.com/api/v1/channels/whatsapp/webhook`; the host was confirmed from the authenticated Render service record. The existing Cloudflare secrets `WA_VERIFY_TOKEN` and `WA_APP_SECRET` were preserved. Cloudflare query-string redaction and sampled tracing are enabled. Render API, PostgreSQL, Redis, and worker services were resumed for the authorized live test and should remain online until the user asks to suspend them. API-side `WHATSAPP_*` settings are configured in Render and must not be copied into the repository or logs.

## Consequences

- Meta Cloud API and ClickCast are separate transport adapters over the same investigation lifecycle.
- The channel stores the original submitted text in the existing Submission record, as other channels do. It stores only a pseudonymous sender reference for retrieval authorization.
- No database migration is required.
- Text/URL intake, immediate acknowledgement, and user-requested result retrieval are supported for phone-number, regular BSUID, and parent BSUID senders. Media downloads, interactive messages, status-callback persistence, templates, and completion-time outbound pushes are not included.
- The existing application cannot be considered production-ready solely because webhook signatures are verified. Production authentication, retention/deletion, and deployment controls remain open.

## Verification

Automated backend tests cover raw-body signature validation, payload filtering, Graph API request construction, partial configuration rejection, sender HMAC storage, sender-scoped result selection, duplicate message IDs, and privacy-safe delivery-status diagnostics. The focused WhatsApp suite passes 28 tests; Ruff and `git diff --check` pass. Worker tests cover challenge forwarding, byte-identical signed-body forwarding, invalid signature rejection, payload bounds, redirect rejection, and upstream failures. `npm test` passes 9 Worker tests and `npx wrangler deploy --dry-run` builds the bundle. On 2026-10-27, a live inbound message was parsed and queued by API commit `c6edf1b`; the Celery investigation task succeeded, but the sender reported no acknowledgement. The follow-up commit `b376add` is live on both Render API and worker and classifies status callbacks using allow-listed state labels and numeric error codes, without logging recipient, message ID, or error text. API readiness reports database, Redis, and object storage healthy. A fresh user message is still required to determine Meta's delivery outcome; do not describe outbound acknowledgement as verified until the sender confirms receipt.

## Rollback

Unset the `WHATSAPP_*` settings. The webhook returns not found when the integration is disabled. Remove or disable the Meta webhook subscription/Cloudflare forwarding rule to stop delivery. Existing WhatsApp investigations remain in the database under the existing retention policy.
