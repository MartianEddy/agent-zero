# Provider Sandbox Matrix

| Provider | Sandbox/test mode | Credentials source | Verification notes |
|---|---|---|---|
| M-Pesa | Not used by Agent Zero | Not configured | No M-Pesa flow is in scope. |
| SMS/email/OTP | Not used by Agent Zero | Not configured | No SMS, email, or OTP flow is in scope. |
| OpenAI Agents SDK + hosted web search | No separate sandbox; use a dedicated development project/key and spend limit. Automated tests should use a provider double. | `OPENAI_API_KEY` environment variable, worker only | No live provider call was made for this implementation. Disable SDK traces for user submissions; never use production credentials for agent-run verification. |
| ClickCast WhatsApp HTTP API builder | Use ClickCast Test & Verify with synthetic message/subscriber values; do not send real user content during agent-run verification. | `CLICKCAST_API_TOKEN`, `CLICKCAST_IDENTITY_KEY`, and optional `CLICKCAST_OWNER_ID` in `backend/.env` | No live API call was performed. Confirm event/message variables and response mappings before live traffic. |
| Meta WhatsApp Cloud API | Automated tests use mocked webhook payloads and mocked Graph API requests. A live smoke test uses only the owner-designated recipient and requires explicit scoped approval. Never paste tokens or app secrets into chat or fixtures. | `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_IDENTITY_KEY`, optional `WHATSAPP_OWNER_ID`, and `WHATSAPP_GRAPH_API_VERSION` | Past owner-run Phase 1 messages reached the API; one personal-account reply failed delivery with Meta code `131026` (see the 2026-10-28 history/result incident). Do not use that as evidence of Phase 2. The Cloudflare Worker preserves the raw request body and signature header when proxying to `/api/v1/channels/whatsapp/webhook`. |

Production credentials are prohibited in agent-run VERIFY unless a human authorizes a scoped production smoke test for that session.
