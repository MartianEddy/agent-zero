# agent-zero
A super AI agent 


## Local development

```bash
docker compose up -d postgres redis object-storage    # data services
cd backend && DATABASE_URL=postgresql+psycopg://agent_zero:agent_zero_local@localhost:5433/agent_zero .venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 18000   # API (needs backend/.env)
.venv/bin/celery -A app.worker.celery_app worker --pool=solo --beat --loglevel=INFO   # worker
cd ../frontend && npm run dev                           # web on http://localhost:3000
```

The web app proxies `/api/investigations/*` to `AGENT_ZERO_API_URL` (default `http://127.0.0.1:18000`).
Rebuild the API image (`docker compose build api`) after backend changes, or run it from the venv as above.
A stale image serves an old API, which shows up in the browser as "Method Not Allowed" or "Cases could not be loaded".
Evaluations: see `evals/README.md`.
