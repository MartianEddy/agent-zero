# Agent 0 brand and frontend audit

## Starting state

The repository contained a README, license, six brand reference PNGs and a separate neon emblem, with no existing frontend or build tooling. The new Next.js App Router project is scaffolded in `frontend/`, leaving the source brand material at the repository root.

## Brand interpretation

The brand board sets charcoal `#0B0D0E`, paper `#F7F7F4`, signal green `#A3FF47` and slate `#6B7280`. References use editorial two-line headings, generous but disciplined spacing, fine borders, a clean sans for UI and mono for technical labels. Dark and paper sections create rhythm. Green marks primary actions, source nodes and selected highlights; verification statuses keep distinct semantic colors and always include text.

The segmented 0 ring represents multiple sources converging on a claim. Use it as a quiet evidence motif, not a repeated logo stamp. The supplied neon emblem is intentionally glowy and too dominant for small UI use. There is no supplied video or font file, so the page uses a static ring graphic and system font stacks without external downloads.

## Design contract

- Primary job: help a newsroom visitor understand Agent 0 and begin an investigation.
- Hierarchy: claim-focused headline, brief explanation, primary action, and a realistic investigation preview.
- Palette: charcoal/paper foundation, restrained signal green, separate semantic statuses.
- Geometry: 4px spacing rhythm, thin borders, modest 4–8px radii.
- Actions: lime filled primary, outlined secondary and obvious keyboard focus.
- Icons: small inline line icons, no icon package needed for this first page.
- Vocabulary: investigate, source, evidence, corroborate and brief; state uncertainty directly.

## Technical choices

The app uses the standard `create-next-app` TypeScript/App Router scaffold, React Server Components for the marketing page, CSS Modules for page and component styles, and global CSS only for resets, tokens and shared controls. A client component is limited to the collapsible mobile menu. `frontend/src/app/home.module.css` owns homepage styling; workspace placeholder styles have their own route module. No animation, UI framework or chart dependency is justified. `create-next-app` generated dependencies are declared, but npm dependency installation did not complete in the restricted environment.

## Implemented routes

1. Scaffold in `frontend/` and preserve brand assets in the repository root.
2. Define tokens and shared wordmark, header, footer and arrow primitives.
3. Complete the homepage and its responsive styles in a route-specific CSS Module.
4. Add Product, How it works, Newsrooms and About routes, each with its own CSS Module.
5. Resolve the primary CTA to a transparent `/investigate` placeholder.
6. Run typecheck, lint and production build. A browser visual pass remains limited because Argent is not installed in this environment.
