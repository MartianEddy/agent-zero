# Agent 0 backend

Backend for the channel-neutral investigation API and worker. The application owns a bounded investigation workflow; a thin OpenAI `ModelGateway` performs structured claim/query planning and, only after evidence is persisted, structured evidence reasoning. OpenAI is the only model provider (`OPENAI_MODEL`). Exa searches are executed by application code. Claims, query plans, search traces, source candidates, retrieved pages and accepted excerpts are committed before final reasoning, so a later provider failure preserves completed work. Findings must link to accepted claim evidence and supported/contradicted statuses require a matching evidence relationship. The verification brief is formatted by application code without another model call.

Conservative defaults bound model calls (4 per investigation), claims (3), queries (5), search results (5 per query), candidate sources (8), retrieved sources (5), page text (6,000 characters per source), evidence text (24,000 characters total), images (4), and model output (700 planning / 900 reasoning tokens). One transient retry is allowed only when suitable; quota errors, authentication errors, invalid output and oversized Retry-After values are not retried. Usage is recorded per investigation and per model call. Source retrieval remains opt-in: with `SOURCE_READER_PROVIDER=disabled`, search results remain candidates and claim findings stay inconclusive unless another accepted evidence path exists.

## Requirements

- Python 3.12
- Poetry 2.x
- Docker Compose v2 for PostgreSQL, Redis and local S3-compatible storage
- FFmpeg/ffprobe for local video metadata and keyframe extraction (included in the backend image)
- OpenAI API key for the configured primary model
- Exa API key for shared web search

## Local setup

```sh
cd backend
cp .env.example .env
poetry lock
poetry install
cd ..
docker compose up --build
```

The API binds to `127.0.0.1:18000`; interactive API docs are at `/docs`. PostgreSQL is exposed at host port `5433`, Redis at `16379`, and the local S3-compatible SeaweedFS endpoint at `8333` (admin/master endpoint `9333`). Local credentials in Compose are disposable development values only.

Set `OPENAI_API_KEY` and `EXA_API_KEY` in `backend/.env`. `OPENAI_MODEL` defaults to [`gpt-6-luna`](https://developers.openai.com/api/docs/models/gpt-6-luna), accessed through the Agents SDK Responses API adapter; `OPENAI_REASONING_EFFORT` defaults to `low`. Luna supports structured output and documents reasoning effort on the Responses API. There is no provider fallback cascade: after the one configured bounded retry, failure pauses the investigation while preserving completed stages. Configure budgets in `.env.example` only when needed. Agent SDK traces are disabled for submitted content. Upload image/video using `POST /api/v1/investigations/media` as multipart fields `file` and optional `prompt`; inspect persisted results at `GET /api/v1/investigations/{id}/results`. Uploads are capped at 25 MB. Video keyframes are sampled from clips up to 90 seconds; audio transcription, C2PA, reverse-image search and advanced forensic detection are not included in this slice.

To independently retrieve public source pages, explicitly set `SOURCE_READER_PROVIDER=jina_reader` in `backend/.env`. This sends candidate source URLs to Jina Reader; private destinations and common credential-bearing URLs are rejected. The default is `disabled`, in which case search results remain candidates and findings stay inconclusive without another validated evidence path. Search providers do not directly access social platforms or browser cookies.

For URL investigations with retrieval enabled, Agent 0 retrieves and stores the submitted page before extracting claims. It records the page as a `SUBMITTED` source: its text helps identify what the article claims, but it is excluded from verification evidence. Exa-discovered pages are retrieved separately before evidence excerpts are accepted. A small source registry adds source type and claim-topic authority context without assigning credibility scores. Explicit links and matching content/canonical URLs can produce `CITES` or `DUPLICATES` source relationships; uncertain lineage stays unknown. Results include retrieved page title, publisher/domain, author/date, canonical URL metadata and honest retrieval status.

```sh
cd backend
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
poetry run celery -A app.worker.celery_app worker --beat --loglevel=INFO
poetry run pytest
poetry run ruff check app migrations tests
```

## API foundation

- `GET /api/v1/health` checks process liveness only.
- `GET /api/v1/ready` checks PostgreSQL, Redis and the configured object-storage bucket.
- `POST /api/v1/investigations` creates a private local development investigation. Supply `Idempotency-Key` to make retries idempotent.
- `GET /api/v1/investigations` lists the local development user's investigations.
- `GET /api/v1/investigations/{id}` retrieves only that user's investigation.
- `POST /api/v1/investigations/media` accepts signature-validated image or video uploads into private object storage.
- `POST /api/v1/investigations/{id}/retry` queues a paused/failed investigation when its model-call budget allows; completed searches and retrieved evidence are reused.
- `GET /api/v1/investigations/{id}/results` returns claims, source references, provider search traces, claim/evidence relationships, evidence coverage, findings, brief and engineering usage counters.

The disabled-auth identity is available only in `development` and `test`. Staging/production reject disabled authentication. An OIDC adapter and retention/deletion workflow are not implemented, so this backend is not ready for production or sensitive real submissions. Enabling Jina sends source URLs to that external page-reader service; do not enable it for private or credential-bearing URLs. Agent Reach's own CLI is not installed or invoked by the worker: it is a local environment installer/router, while the backend calls a narrow reader adapter and never gives the model shell access. Social-platform integrations requiring cookies or browser sessions are not part of this server workflow.

## Configuration

See `.env.example`. Never commit `.env`. Migrations are explicit; do not use ORM `create_all` in deployed environments. PostgreSQL owns durable state and audit history; Redis is a broker/transient dependency, not a source of truth.

Exa search follows the native `POST /search` request shape with `query`, `type: "auto"`, and `contents.highlights: true`; no category, domain filter, explicit result count or recency filter is added. Exa highlights remain search leads. Claim evidence still requires a quote match in independently retrieved page text. See the [Exa search skill](../.agents/skills/build-with-exa/SKILL.md) and [official Search API docs](https://exa.ai/docs/reference/search).
