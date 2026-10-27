# Provider Sandbox Matrix

| Provider | Sandbox/test mode | Credentials source | Verification notes |
|---|---|---|---|
| M-Pesa | <yes/no + mode> | <env var / secret store> | <safe test behavior> |
| SMS/email/OTP | <yes/no + mode> | <env var / mock> | <safe test behavior> |
| OpenAI Agents SDK + hosted web search | No separate sandbox; use a dedicated development project/key and spend limit. Automated tests should use a provider double. | `OPENAI_API_KEY` environment variable, worker only | No live provider call was made for this implementation. Disable SDK traces for user submissions; never use production credentials for agent-run verification. |
| ClickCast WhatsApp HTTP API builder | Use ClickCast Test & Verify with synthetic message/subscriber values; do not send real user content during agent-run verification. | `CLICKCAST_API_TOKEN`, `CLICKCAST_IDENTITY_KEY`, and optional `CLICKCAST_OWNER_ID` in `backend/.env` | No live API call was performed. Confirm event/message variables and response mappings before live traffic. |
| Meta WhatsApp Cloud API | Unit tests use mocked webhook payloads and mocked Graph API requests. Live webhook/send verification requires a designated test recipient and explicit live-smoke approval. Never paste tokens or app secrets into chat or fixtures. | `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_IDENTITY_KEY`, optional `WHATSAPP_OWNER_ID`, and `WHATSAPP_GRAPH_API_VERSION` | A read-only Graph API GET checked the WABA's subscribed apps using the token stored in Render; the token was not displayed. The owner sent live inbound messages, and the Worker/API returned HTTP 200, but no investigation job was observed. No agent-originated outbound message was sent. See `docs/operations/incidents/2026-10-27-whatsapp-webhook-not-queued.md`. The Cloudflare Worker preserves the raw request body and signature header when proxying to `/api/v1/channels/whatsapp/webhook`. |

Production credentials are prohibited in agent-run VERIFY unless a human authorizes a scoped production smoke test for that session.
