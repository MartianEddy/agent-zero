# Agent 0 public frontend

The Agent 0 marketing site and investigation workspace entry placeholder. This is a Next.js App Router application using TypeScript, React Server Components and route-level CSS Modules.

## Run locally

From this directory:

```bash
npm ci
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Routes

- `/` — Home
- `/product` — Product
- `/how-it-works` — How it works
- `/newsrooms` — For Newsrooms
- `/about` — About
- `/demo` — Interactive illustrative investigation preview
- `/methodology` — Evidence principles and FAQ
- `/investigate` — Prototype status page (no live investigation service is connected)

The sample case and all figures shown in the demo are illustrative. No claim submission, pilot intake, account system or evidence-search service is connected. The newsroom page explains the intended pilot considerations; the project still needs a published contact channel before it can collect pilot requests.

## Checks

```bash
npm run lint
npx tsc --noEmit
npm run build
```

Brand references live in the repository-level `brand/` directory. The site uses CSS-drawn evidence motifs and does not load external video or font assets.
