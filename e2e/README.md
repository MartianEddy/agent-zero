# End-to-end checks

| Script | What is real | What is faked |
|---|---|---|
| `whatsapp_e2e.py` | API process, HTTP, Meta signature checks, conversation service, PostgreSQL (throwaway `agent_zero_e2e` database, created and dropped), outbound request | Meta's Graph API (local server that records each request) |
| `web_e2e.mjs` | Chrome, production build of the web app, local API and its database | Only the claim-review AI step, in one scenario, because it needs a working model key |

```bash
# WhatsApp (needs the local Postgres container on 127.0.0.1:5433)
backend/.venv/bin/python e2e/whatsapp_e2e.py

# Web (needs the API on 127.0.0.1:18000 and `npm run build` in frontend/)
cd e2e && npm install && npm run web
```

Real phones: see `docs/engineering/testing/whatsapp-live-test.md`.

What these found on first run (2026-11-25):
- A repeated Meta delivery of an already-answered message was answered twice. Fixed with a `DELIVERED` receipt state.
- The site's redirects never worked: `next.config.ts` had been written to `frontend/src/`. Moved to `frontend/`.
