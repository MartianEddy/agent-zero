# ClickCast WhatsApp intake MVP

## Flow

ClickCast connects the WhatsApp Business account and runs its bot/inbox. Use the HTTP API builder to call Agent 0's intake endpoint when the bot receives an incoming message. Agent 0 creates a normal `WHATSAPP` investigation and returns `202 Accepted` with the reference/status; ClickCast maps those fields into its acknowledgement.

When the user later sends `RESULT` or taps a case-specific “Check this result” button, ClickCast calls Agent 0's result endpoint with the sender and, optionally, an investigation reference. With a reference, Agent 0 returns that exact investigation; without one, it returns the sender's latest WhatsApp investigation in the configured workspace. The API verifies sender ownership and returns a bounded status, journalist-readable summary, limitations and up to five findings. A result can be ready while still inconclusive or needing human review; “ready” means there is an assessment to show, not that the claim is proven. A terminal investigation (`COMPLETE`, `NEEDS_REVIEW`, `FAILED`, or `CANCELLED`) is reported as ready, so a finished review is not labelled as pending forever.

Agent 0 does not register a Meta webhook or retain a Meta access token. The connected ClickCast account maps to one configured Agent 0 owner/workspace. Media input is not included in this first slice.

## Configuration

Set these in `backend/.env` (never commit them):

- `CLICKCAST_API_TOKEN`: at least 32 alphanumeric characters; use a cryptographically random value. Configure ClickCast's HTTP API builder to send `Authorization: Bearer <token>`.
- `CLICKCAST_IDENTITY_KEY`: at least 32 secret characters, stable across deployments; used only to pseudonymize sender identity.
- `CLICKCAST_OWNER_ID`: optional workspace owner UUID. Local development defaults to the existing development owner.

Configure these endpoints in ClickCast HTTP API:

- Intake: `POST /api/v1/channels/clickcast/investigations`, JSON body with `sender` and `message`; `event_id` is optional.
- Result lookup: `POST /api/v1/channels/clickcast/result`, JSON body with `sender`; `reference` is optional. Include it to check that exact investigation, or omit it to check the sender's latest one.

## Request and response mapping

Intake example:

```json
{
  "sender": "254700000000",
  "message": "Please check this claim: ..."
}
```

Map the subscriber/WhatsApp identifier and saved incoming text to `sender` and `message`. Use the exact same sender variable and format for intake and result calls (for example, WhatsApp chat ID on both); switching between subscriber ID and phone number will fail sender verification. The ClickCast variable picker currently exposes subscriber IDs and phone numbers, but no incoming message ID. If a stable event ID becomes available, map it to `event_id` for retry idempotency. Without it, an identical submission from the same sender reuses an existing investigation while that exact submission is still active; after a terminal outcome, submitting it again starts a new investigation. This is a best-effort retry guard, not a replacement for a stable event ID. The intake response contains `id`, `reference`, `status`, `current_stage`, and `created_at`; map `reference` and `status` into the immediate bot acknowledgement.

`event_id` may be included when ClickCast supplies a stable incoming-message identifier. Do not use a subscriber ID as the event ID; it is stable across messages and would cause later submissions from that subscriber to collide.

Result lookup for the latest investigation (recommended for a standalone `result` keyword flow):

```json
{
  "sender": "254700000000"
}
```

To check a specific investigation instead, include its reference:

```json
{
  "reference": "AZ-261004-ABC123",
  "sender": "254700000000"
}
```

The response has `reference`, `status`, `current_stage`, `ready`, `summary`, `limitations`, and up to five `findings` (`status` and `statement`). If `ready` is false, the selected investigation is still running; if true, it has a brief or has reached a terminal outcome. Use ClickCast's Test & Verify step to confirm its available variables and response mapping before live traffic.

### Journalist-facing WhatsApp copy and rechecks

Use the following message pattern in the result flow. Keep the line breaks so the outcome and next step are easy to scan:

```text
Your result is ready.

#az_summary#

Reference: #az_reference#
```

For the false branch:

```text
This check is still underway. There is no conclusion yet. You do not need to submit the claim again.

Reference: #az_reference#
Send RESULT again in a few minutes to check this case.
```

Map the result response's `ready` to `az_ready` and compare it with the value ClickCast stores (`1` in the current account), rather than the literal `true`. Map `summary` to `az_summary` and `status` to a separate field such as `az_result_status`; the intake `status` is only the initial `RECEIVED` state. The summary identifies an assessment, explains what the evidence does or does not establish, and gives an editorial next step. Avoid saying a claim is “true” or “false” unless that is the actual finding.

To add a case-specific “Check this result” button, configure its action to start the existing result flow. That request should include both the saved custom field `#az_reference#` and the same sender variable used at intake (for example, `#LEAD_USER_CHAT_ID#`). This retrieves the exact saved investigation; it does not rerun the research. A plain `RESULT` keyword can remain as a shortcut to the latest case. To recheck an older case after a newer claim has overwritten `az_reference`, add a reference-entry step that saves the supplied reference to a separate field such as `az_requested_reference`, then send that field with `sender`. Do not overwrite the intake reference while capturing a lookup request.

Suggested intake acknowledgement:

```text
Check started.

Reference: #az_reference#
Send RESULT to check the latest case, or use Check this result to reopen this case.
```

The ClickCast HTTP API builder UI exposes request headers/body, Test & Verify, and Response Mapping. Use `Authorization` header for the bearer token; do not put it in the URL or request body.

## Privacy and rollback

The API stores the message as the investigation submission and stores only an HMAC sender reference, not the raw sender number. Existing retention decisions still apply. Disable/remove both ClickCast HTTP API actions and unset `CLICKCAST_API_TOKEN` and `CLICKCAST_IDENTITY_KEY` to turn off intake/result lookups. No database migration is required.
