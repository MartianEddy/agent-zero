# Sinaps WhatsApp webhook Worker

This Worker validates the Meta webhook challenge and HMAC signature, then forwards the original request to Agent Zero's existing WhatsApp route. The FastAPI route validates the signature again before processing messages. Message bodies, phone numbers, and signature values are never logged by this Worker.

## Required runtime configuration

Keep the existing Worker secrets:

- `WA_VERIFY_TOKEN`
- `WA_APP_SECRET`

Set the non-secret `AGENT_ZERO_WEBHOOK_URL` Worker variable to the deployed API endpoint:

```text
https://<public-agent-zero-api-host>/api/v1/channels/whatsapp/webhook
```

The backend must also have its existing `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, and `WHATSAPP_IDENTITY_KEY` settings configured. The verify token and app secret must match the Worker values. Do not put credentials into the Worker URL.

If the Worker variable is missing or invalid, the Worker returns `503` instead of acknowledging and dropping webhook events.

## Local verification

Run the built-in Node tests:

```sh
npm test
```

Compile and validate the Wrangler bundle without uploading:

```sh
npx wrangler deploy --dry-run
```

## Deployment

The production Worker was deployed on 2026-10-27 as version `f6a95135-21e2-4727-b3b0-f21a2c3ff06a`. Its `AGENT_ZERO_WEBHOOK_URL` targets the Render-confirmed API route below. Render currently reports the API and its database, Redis, and worker dependencies as suspended, so do not treat the channel as live until those services are resumed and API-side WhatsApp settings are confirmed.

For a future deployment after backend readiness is confirmed, run from this directory:

```sh
npx wrangler deploy --var 'AGENT_ZERO_WEBHOOK_URL:https://<public-agent-zero-api-host>/api/v1/channels/whatsapp/webhook' --keep-vars
```

`--keep-vars` preserves existing dashboard variables; Wrangler keeps existing secrets when deploying. Do not set or print the secrets in a command. After backend readiness is confirmed, complete the webhook challenge and send one test message from a designated recipient. The backend should return its acknowledgement, and a `RESULT` message should retrieve a saved result.

Cloudflare Workers Logs and sampled traces are enabled in the Wrangler config. Query strings are redacted because Meta includes `hub.verify_token` in the challenge request. The Worker emits no application logs containing request data.

## Rollback

Use Cloudflare Workers **Deployments** to roll traffic back to the preceding ready version. The previous implementation only verified Meta requests and logged incoming message details; use that version only as a temporary rollback, since it does not deliver messages into Agent Zero and logs personal message data. Disable the Meta webhook subscription if a safe rollback is unavailable.
