# ClickCast WhatsApp intake MVP

## Flow

ClickCast connects the WhatsApp Business account and runs its bot/inbox. Use the HTTP API builder to call Agent 0's intake endpoint when the bot receives an incoming message. Agent 0 creates a normal `WHATSAPP` investigation and returns `202 Accepted` with the reference/status; ClickCast maps those fields into its acknowledgement.

When the user later sends a “check result” command or taps a status button, ClickCast calls Agent 0's result endpoint with the investigation reference and sender. The API verifies sender ownership and returns a bounded status, summary, limitations and up to five findings. ClickCast maps those values into its WhatsApp reply. This avoids needing Agent 0 to send asynchronous messages through ClickCast or Meta.

Agent 0 does not register a Meta webhook or retain a Meta access token. The connected ClickCast account maps to one configured Agent 0 owner/workspace. Media input is not included in this first slice.

## Configuration

Set these in `backend/.env` (never commit them):

- `CLICKCAST_API_TOKEN`: at least 32 alphanumeric characters; use a cryptographically random value. Configure ClickCast's HTTP API builder to send `Authorization: Bearer <token>`.
- `CLICKCAST_IDENTITY_KEY`: at least 32 secret characters, stable across deployments; used only to pseudonymize sender identity.
- `CLICKCAST_OWNER_ID`: optional workspace owner UUID. Local development defaults to the existing development owner.

Configure these endpoints in ClickCast HTTP API:

- Intake: `POST /api/v1/channels/clickcast/investigations`, JSON body with `event_id`, `sender`, and `message`.
- Result lookup: `POST /api/v1/channels/clickcast/result`, JSON body with `reference` and `sender`.

## Request and response mapping

Intake example:

```json
{
  "event_id": "stable-clickcast-message-id",
  "sender": "254700000000",
  "message": "Please check this claim: ..."
}
```

Map ClickCast's stable message ID, subscriber/WhatsApp identifier and incoming text to those three body fields. The intake response contains `id`, `reference`, `status`, `current_stage`, and `created_at`; map `reference` and `status` into the immediate bot acknowledgement.

Result lookup example:

```json
{
  "reference": "AZ-261004-ABC123",
  "sender": "254700000000"
}
```

The response has `reference`, `status`, `current_stage`, `ready`, `summary`, `limitations`, and up to five `findings` (`status` and `statement`). If `ready` is false, tell the user to check again later. Use ClickCast's Test & Verify step to confirm its available variables and response mapping before live traffic.

The ClickCast HTTP API builder UI exposes request headers/body, Test & Verify, and Response Mapping. Use `Authorization` header for the bearer token; do not put it in the URL or request body.

## Privacy and rollback

The API stores the message as the investigation submission and stores only an HMAC sender reference, not the raw sender number. Existing retention decisions still apply. Disable/remove both ClickCast HTTP API actions and unset `CLICKCAST_API_TOKEN` and `CLICKCAST_IDENTITY_KEY` to turn off intake/result lookups. No database migration is required.
