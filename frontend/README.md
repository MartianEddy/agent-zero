# Agent 0 public frontend

The Agent 0 marketing site and investigation workspace. This is a Next.js App Router application using TypeScript, React Server Components and route-level CSS Modules.

## Run locally

From this directory:

```bash
npm ci
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

The `/investigate` workspace proxies requests to the FastAPI service at `http://127.0.0.1:18000` by default. Set `AGENT_ZERO_API_URL` in the frontend environment to override that backend origin. It accepts either a URL or a host and port (Render Blueprint supplies the API's private host and port). Start the backend and its worker separately; the owner should set `OPENAI_API_KEY` in `backend/.env` before starting investigations.

## Routes

- `/` — Home
- `/product` — Product
- `/how-it-works` — How it works
- `/newsrooms` — For Newsrooms
- `/about` — About
- `/investigate` — Submit claims, public URLs, or images and review progress, provenance, evidence links, and findings
- `/investigations` — Browse recent cases or reopen a case using its `AZ-YYMMDD-XXXXXX` reference

The Render Blueprint includes a free Next.js web service. The API remains the source of truth for ownership checks, and the browser never receives backend or ClickCast credentials. The current deployment uses a shared demo owner because authentication and tenant isolation are not implemented; its UI labels the workspace as public and advises against private or sensitive submissions. Do not use it as a private newsroom workspace until authentication and data-retention controls are in place.

## Checks

```bash
npm run lint
npx tsc --noEmit
npm run build
```

Brand references live in the repository-level `brand/` directory. The site uses CSS-drawn evidence motifs and does not load external video or font assets.
