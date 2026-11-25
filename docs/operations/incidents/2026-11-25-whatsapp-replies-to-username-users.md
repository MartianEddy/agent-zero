# WhatsApp replies not delivered to some personal accounts

**Date:** 2026-11-25
**Status:** Deployed 2026-11-25 (API, worker and web on `53f926e`; migration 0019 applied; Cloudflare worker `ba92bc75`). Awaiting a live-phone retest (`docs/engineering/testing/whatsapp-live-test.md`).

Production logs for the 30 days before the fix show one outbound delivery, on 2026-11-20, which failed with `131026`. No AI authentication failures in the 14 days before deployment. Render auto-deploy did not trigger for pushes after 2026-10-28; the deploys were started manually.

## Symptom

Some accounts, reported as business accounts, got replies. Some personal accounts sent messages that reached Agent Zero and were handled, but no reply arrived. The 2026-10-28 incident recorded the matching outbound status as `failed` with Meta code `131026` (message undeliverable).

## Cause

Meta began sending business-scoped user IDs (BSUIDs) in April 2026 as part of WhatsApp usernames ([Meta: Business-scoped user IDs](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-scoped-user-ids)):

- Every incoming message includes the user's BSUID in `from_user_id`, for example `KE.13491208655302741918`.
- If the user has a username and the business has not messaged or heard from their phone number in the last 30 days, Meta **omits** the phone number (`from`, `wa_id`).
- To reply to a BSUID, the send request must use `"recipient": "<BSUID>"`. The `to` field is for phone numbers only.

Agent Zero already parsed the BSUID as the sender when `from` was missing, but `_send_cloud_message` always wrote it into `"to"`. Meta treated the BSUID as a phone number and the reply could not be delivered. Usernames are rolling out on the consumer app, which matches "personal accounts fail". Two existing tests asserted the wrong behaviour (`to == BSUID`).

A second, related defect: the conversation and case history were keyed on the phone number when present, otherwise on the BSUID. When Meta stops including a user's number, their key changes, so the chat lost its context and `HISTORY`/`RESULT` could not find earlier cases.

## Fix

- Replies to a BSUID use `recipient`; replies to a phone number use `to` (`app/modules/channels/whatsapp.py`).
- The BSUID is now the identity key (`_identity_refs`). The phone number, when present, is still the reply address.
- When a message carries both a BSUID and a phone number, any conversation, notification preference and WhatsApp cases saved under the old phone-based key are moved to the BSUID key once (`_adopt_legacy_identity`).
- Failed status callbacks for BSUID sends are now diagnosed (`recipient_user_id`).

Limitation: a user whose history was saved under a phone number, and whose next message arrives with only a BSUID, starts a fresh conversation. Their earlier cases stay reachable by reference on the web.

## Verify on production

1. Deploy API and worker.
2. From a personal account that previously got no reply, send `hi`. A reply should arrive.
3. In API logs, the outbound status for that `sender_ref` should be `sent`, then `delivered`, with no `131026`.
4. Send `HISTORY` from an account that used the bot before, to confirm history is still found.

If `131026` persists for a user whose webhook includes a phone number, the remaining documented causes are recipient-side: the number is not on WhatsApp, the user has not accepted current WhatsApp terms, an outdated app, or the user blocked the business.
