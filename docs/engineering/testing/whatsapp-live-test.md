# WhatsApp live test (real phones)

Automated checks cover everything except Meta itself: `e2e/whatsapp_e2e.py` runs the real API,
signature checks, database and outbound request against a local fake of the Graph API. This
runbook covers the part only a real phone can prove. It takes about 10 minutes.

## Before you start

- API and worker deployed from the latest commit; `GET /api/v1/ready` returns `ready`.
- Cloudflare worker on version `ba92bc75` or later (`npx wrangler deployments list` in `cloudflare/sinaps-wa-webhook`).
- A working `OPENAI_API_KEY` on the API and worker (claim review needs it).
- Three phones: **A** a WhatsApp Business app account, **B** a personal account with a username
  that has never messaged the bot, **C** a personal account that used the bot before.
- Open the API logs (Render dashboard, or `render logs`).

## Steps

| # | Phone | Send | Expect |
|---|---|---|---|
| 1 | B | `hi` | A reply within a few seconds. Logs: `status_states=sent:1`, then `delivered`. No `131026`. |
| 2 | B | `help` | The help message with RESULT, HISTORY, STATUS, STOP. |
| 3 | B | `Nairobi is the capital of Kenya.` | A preview with Submit, Edit and Cancel buttons. "Nothing has started yet." |
| 4 | B | `yes` | "Got it. I am checking this now." and a reference. |
| 5 | B | wait 2 to 5 minutes, then `RESULT` | Verdict first, then claim, why, evidence strength and sources. |
| 6 | C | `HISTORY` | Earlier cases are still listed. |
| 7 | A | `Did Kenya ban plastic bags in 2017?` | A quick answer with sources and "Reply CHECK". |
| 8 | A | `check` | A claim preview for that question (not "nothing to submit"). |
| 9 | A | `the governor thing`, then answer the follow-up vaguely twice | After two rounds, a *Check as written* button instead of the same question again. |
| 10 | any | Send the same message twice quickly | One reply, not two. |

## If a step fails

- **No reply on step 1, log shows `131026`:** check the recipient: WhatsApp updated, current terms
  accepted, business not blocked. If the webhook for that user had no phone number, confirm the
  API is on commit `730688f` or later (BSUID replies use `recipient`).
- **No webhook in the logs at all:** check the Meta app's webhook subscription (`messages` field)
  and the Cloudflare worker's `AGENT_ZERO_WEBHOOK_URL`.
- **"I'm having trouble right now":** the AI service rejected the request; check `OPENAI_API_KEY`.

Record the date, commit and pass or fail for each step in `docs/verification/evidence/`.
