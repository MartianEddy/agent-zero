# WhatsApp case history and result delivery gaps

**Date:** 2026-10-28  
**Status:** Implementation complete; deployment and owner verification pending

## User-visible evidence

The live journey approved case `AZ-261028-ED24C0`, then the user sent `Results` and `Result`. Both received: “I couldn't find a check for this WhatsApp number. Send a claim or public URL to start one.” This is the no-match fallback in `_result_message`; it does not represent the worker's assessment or prove that every run returns the same result. The screenshots do not reveal the actual worker status or persisted source set.

The result lookup is deliberately restricted to the configured owner, WhatsApp channel, and sender HMAC. If that HMAC metadata is absent or inconsistent on the saved submission, the valid case is invisible to this lookup. The implementation now makes a fallback lookup using the exact conversation ID persisted when the user approved that case, retaining the owner, channel, and optional exact reference filters. It does not broaden access to another sender's cases. Production database access was unavailable here, so the specific metadata mismatch remains unverified; the exact case still needs a live retest.

The screenshots also show that the user was told to ask for an update but was not given a visible history command. `HISTORY` now lists recent case references and statuses; `HISTORY <page>` gets older cases. The approval response and `HELP` explain `HISTORY`, `STATUS`, and `RESULT <reference>`.

In the follow-up result, `RESULT AZ-261028-ED24C0` now returns the saved claim, assessment, linked source, confidence, limitations, and reference. It also exposed an implementation defect: the fast path added “Settled-fact assessment exceeded its five-second worker deadline” after the evidence assessment had completed successfully. That post-success warning is removed, and genuine timeout copy no longer exposes the internal five-second budget.

A second WhatsApp account repeatedly sent the same claim but received no reply. The owner confirms `WHATSAPP_PHONE_NUMBER_ID` is a registered production number, so the test-sender allowlist hypothesis does not apply. The screenshot alone cannot show whether that account's inbound webhook reached Agent Zero. A prior incident recorded an inbound message parsed and handled successfully while Meta later marked the outbound acknowledgement `failed` with numeric provider code `131026`; this shows outbound delivery can fail, but does not prove the current sender has the same cause. Remaining possibilities are: Meta did not deliver the inbound webhook to the configured endpoint; the webhook arrived but the message was rejected during parsing/routing; or Agent Zero sent a reply that Meta rejected or later failed to deliver. The exact current cause cannot be distinguished without correlated webhook and status logs.

Diagnostics now log inbound payload counts/rejection categories, numeric synchronous Meta send-error codes, and per-recipient outbound status (`sent`/`delivered`/`read`/`failed`) with an HMAC sender reference. They omit phone numbers, message IDs, response bodies, and trace IDs. A failed status with no provider code still needs Meta delivery details to identify its reason.

## Result delivery behavior

Terminal WhatsApp investigations now emit a durable outbox event. The notification worker formats the same persisted assessment used by `RESULT`, including the reference, findings, linked sources, and limitations. It sends only when:

- the user submitted the preview consent and has not sent `STOP`;
- the conversation's last inbound message is within Meta's 24-hour customer service window;
- the recipient route remains in the expiring conversation record; and
- `WHATSAPP_SUPPORT_URL` points to the real human support channel.

The recipient address is encrypted at rest with a key derived from the existing WhatsApp identity key; raw digits are not stored in the preference table. `STOP` is persistent and `ALERTS ON` opts in again. If the window closes or the support route is not configured, no free-form result is sent; users retrieve it with `HISTORY` or `RESULT`.

Meta's [WhatsApp Business Messaging Policy](https://whatsappbusiness.com/policy/) permits automated replies during the 24-hour service window and requires a clear human escalation path. Outside that window, only approved message templates may initiate a message. Phase 1 does not implement those templates. This policy was verified against Meta's official policy page on 2026-10-28; the Meta developer reference pages were rate limited in this environment.

## Changes and verification

- Added sender-scoped paginated case history and direct `RESULT(S)` behavior.
- Added exact-conversation fallback for result lookup.
- Added migration `0018_whatsapp_result_notifications` for encrypted recipient routing, inbound timestamps, and persistent opt-out preferences.
- Added durable terminal-result notifications gated by service window, explicit consent, opt-out, and configured support URL.
- Added safe numeric Meta provider-error-code capture to outbound send errors, excluding provider response text, recipient, and trace IDs. Added status-event correlation by HMAC sender reference and numeric error codes only.
- Removed the false timeout limitation after successful settled-fact evidence reasoning.
- Updated product, architecture, decision, and WhatsApp journey docs.
- Follow-up tests: 75 passed across WhatsApp and cost-controlled pipeline suites; scoped lint and `git diff --check` pass.
- Not yet deployed. A real human support URL must be configured before automatic result messages can activate. The latest sender's Meta mode, recipient status, webhook receipt, and delivery code still need checking; Render log access from this environment fails at DNS resolution.
- First Render API deploy attempt reached the pre-deploy migration and failed before rollout because the Alembic revision ID exceeded PostgreSQL's 32-character `alembic_version.version_num` limit. The migration transaction rolled back; the revision ID was shortened before retry.

## Acceptance follow-up

1. Configure `WHATSAPP_SUPPORT_URL` with a staffed, user-accessible support channel in both API and worker environments.
2. Deploy API and worker with migration `0018`.
3. From the test sender, send `HISTORY`; verify the case reference and status are listed.
4. Send `RESULT AZ-261028-ED24C0`; verify the saved assessment/current state and ensure no false internal timeout message appears.
5. After deploying the diagnostic change, send one short `Hi` from the additional personal account. Match the API inbound summary and outbound status using the HMAC sender reference. If no inbound event appears, inspect Cloudflare forwarding and Meta's WABA `messages` subscription; if it appears but is rejected, inspect the rejection category/phone-number ID; if the send fails, record the numeric Meta code and delivery state.
6. Confirm the production phone-number ID, WABA app subscription and `messages` webhook field subscription, and that the access token has `whatsapp_business_messaging` access to that asset. The owner confirmed production-number use; test-recipient allowlisting is not the explanation being pursued.
7. Submit a new approved claim, verify the automatic saved-result message arrives inside the 24-hour window, and verify `STOP` prevents a later push.
8. Verify behavior after 24 hours is user initiated; do not send free-form notification without a user message or approved template.
