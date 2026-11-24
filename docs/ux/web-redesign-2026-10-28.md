# Web redesign and WhatsApp copy pass (2026-10-28)

**Status:** Implemented; verified by type check, lint, production build, backend and frontend unit tests, and headless screenshots against a stub API. Not yet verified against the live backend or on real devices.

## Rules for all user-facing text

- Plain language, short sentences, no jargon (never "model", "pipeline", "intent", "tier").
- No emojis anywhere (web or WhatsApp). Meaning is carried by words; web verdicts also use an icon, never colour alone.
- Web and WhatsApp share one verdict wording. Source of truth: `frontend/src/app/investigate/presentation.mjs` (`statusPresentation`). `backend/app/modules/conversations/messages.py` (`VERDICT_HEADLINES`) must match it.
- Say what happens next and what has not happened ("Nothing has started yet").

## Stack (chosen after research)

| Concern | Choice | Why |
|---|---|---|
| Styling | Tailwind CSS v4, tokens in `src/app/globals.css` `@theme` | One token set replaces seven ad-hoc CSS modules that mixed dark and light palettes |
| Components | shadcn-style copy-in components in `src/components/ui`, built on `radix-ui` | Accessible primitives (accordion, tabs), no component runtime to fight |
| Variants | `class-variance-authority`, `clsx`, `tailwind-merge` | Typed variants for Button and Badge |
| Icons | `lucide-react`, named imports only | Consistent 24px stroke set, tree-shaken. Avoid the `dynamic` entry (one chunk per icon) |
| Notices | `sonner` toasts for transient confirmations; inline `Alert` for errors | Errors stay visible and announced |
| Fonts | `geist` package (local files) | No network call at build time |

## Sitemap

Public site (`SitePage` = header + footer): `/`, `/how-it-works`, `/methodology`, `/whatsapp`, `/newsrooms` (labelled "For teams"), `/about`, `/faq`, `/privacy`. `/product` redirects to `/how-it-works`.

Workspace (`WorkspaceShell` = sidebar on desktop, bottom tab bar on mobile): `/dashboard` (overview), `/investigate` (new check, claim review), `/investigations` (cases), `/investigations/[id]` (case permalink with Summary, Evidence, Media, Brief tabs). `/investigate?investigation=<id>` redirects to the permalink; `/investigate?q=` prefills the form.

## Code layout

- `components/ui`: primitives. `components/site`: public page pieces. `components/workspace`: shell, rows, badges. `components/case`: case view (`model.ts` derives data from the results payload; one component per tab).
- `lib/verdict.ts` maps statuses to label, tone and icon. `lib/use-case.ts` polls an active case every 5 seconds. `lib/api.ts` holds shared helpers.
- `presentation.mjs` and its test are kept as the tested logic layer.

## Known gaps

- Nothing here has been run against the real API; screenshots used a stub.
- No automated accessibility audit or cross-browser pass. Keyboard and screen-reader behaviour relies on Radix and semantic markup.
- The `icon` glyph fields in `presentation.mjs` are unused by the new UI and can be deleted with their test assertions.
- Privacy page is a plain-language summary pending legal review.
- Auth is still disabled; the shell labels the workspace as a shared demo.
