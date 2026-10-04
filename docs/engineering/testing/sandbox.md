# Provider Sandbox Matrix

| Provider | Sandbox/test mode | Credentials source | Verification notes |
|---|---|---|---|
| M-Pesa | <yes/no + mode> | <env var / secret store> | <safe test behavior> |
| SMS/email/OTP | <yes/no + mode> | <env var / mock> | <safe test behavior> |
| OpenAI Agents SDK + hosted web search | No separate sandbox; use a dedicated development project/key and spend limit. Automated tests should use a provider double. | `OPENAI_API_KEY` environment variable, worker only | No live provider call was made for this implementation. Disable SDK traces for user submissions; never use production credentials for agent-run verification. |
| ClickCast WhatsApp HTTP API builder | Use ClickCast Test & Verify with synthetic message/subscriber values; do not send real user content during agent-run verification. | `CLICKCAST_API_TOKEN`, `CLICKCAST_IDENTITY_KEY`, and optional `CLICKCAST_OWNER_ID` in `backend/.env` | No live API call was performed. Confirm event/message variables and response mappings before live traffic. |

Production credentials are prohibited in agent-run VERIFY unless a human authorizes a scoped production smoke test for that session.
