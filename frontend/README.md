# Agent 0 public frontend

The Agent 0 marketing site and investigation workspace. This is a Next.js App Router application using TypeScript, React Server Components and route-level CSS Modules.

## Run locally

From this directory:

```bash
npm ci
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

The `/investigate` workspace proxies requests to the FastAPI service at `http://127.0.0.1:18000` by default. Set `AGENT_ZERO_API_URL` in the frontend environment to override that backend origin. Start the backend and its worker separately; the owner should set `OPENAI_API_KEY` in `backend/.env` before starting investigations.

## Routes

- `/` — Home
- `/product` — Product
- `/how-it-works` — How it works
- `/newsrooms` — For Newsrooms
- `/about` — About
- `/investigate` — Submit claims, public URLs, or images and review progress, provenance, evidence links, and findings

## Checks

```bash
npm run lint
npx tsc --noEmit
npm run build
```

Brand references live in the repository-level `brand/` directory. The site uses CSS-drawn evidence motifs and does not load external video or font assets.
