# Hyperframes Composition Brief: Agent 0

## Objective
Create a polished 23.4-second launch video for Agent 0, an evidence-first investigation workspace.

## Output
- Composition directory: `brag-output-2026-10-04-082012/composition/`
- Rendered video: `brag-output-2026-10-04-082012/brag.mp4`
- Format: landscape — 1920×1080
- Duration: 23.4 seconds

## Source Material
- Project root: this repository
- Primary files read: `README.md`; `docs/product/problem.md`; `docs/product/requirements.md`; `docs/ux/public-site-journey.md`; `docs/architecture/architecture.md`; `frontend/docs/brand-and-frontend-audit.md`; `frontend/src/app/page.tsx`; `frontend/src/app/home.module.css`; `frontend/src/app/globals.css`; `frontend/src/app/product/page.tsx`; `frontend/src/app/how-it-works/page.tsx`; `frontend/src/app/investigate/page.tsx`; `.sinaps/state.md`; `docs/OPEN-QUESTIONS.md`; brand board, workspace, workflow, and landing page reference images.
- Product name: Agent 0
- Tagline / strongest claim: “Assume nothing. Follow the evidence.” Supporting principle: “AI investigates. Humans decide.”
- Key UI or visual moment to recreate: the homepage’s sample investigation card, source findings, and not-verified result.
- Copy that must appear verbatim:
  - “Know what holds up before you publish.”
  - “Schools in Nyeri County will remain closed tomorrow.”
  - “ILLUSTRATIVE EXAMPLE · NOT A LIVE CHECK”
  - “There isn’t enough reliable evidence to confirm this announcement.”
  - “Assume nothing. Follow the evidence.”
  - “AI investigates. Humans decide.”

## Creative Direction
- Tone preset: polished
- Creative direction: investigative newsroom ident; editorial title sequence, evidence before certainty
- Interpretation: deliberate kinetic type and trace lines; use the evidence card as the actual product moment; keep copy readable and the verdict restrained.
- Angle: make a claim’s path visible, including the point where available evidence runs out. Use the product’s existing illustrative Nyeri schools example and keep its demo label visible.
- Hook: “Know what holds up before you publish.”
- Outro: “Assume nothing. Follow the evidence.” / “AI investigates. Humans decide.”
- Avoid generic SaaS language, unsupported feature claims, fake source counts, and an unrelated redesign.

## Visual Identity
- Background: `#0B0D0E`; paper card: `#F7F7F4`
- Text: paper on charcoal and charcoal on paper
- Accent: signal green `#A3FF47`; amber `#F59E0B` for the not-verified status only
- Display font: system sans fallback; no font files are shipped
- Body font: system sans; metadata in system monospace
- Visual references: brand board palette; web homepage’s sample card; segmented 0 ring; restrained hairline borders and source labels.

## Storyboard
Use `../brag-plan.md` as the creative contract:
1. Before publish — 3.0s — outcome-first hook and source-ring motif.
2. The claim — 4.2s — exact sample claim plus persistent illustrative / not-live label.
3. Follow the evidence — 6.3s — three site-authored source findings connected to that claim.
4. Keep uncertainty visible — 4.8s — not-verified state and its explanation.
5. People decide — 5.1s — wordmark, tagline, human-decision principle, and closing prompt.

## Audio
- Audio role: restrained electronic interface soundscape.
- Audio arc: low-gain entry, quiet under findings and status, fade beneath the final mark.
- Music: none. Use the user-supplied `assets/music/Futuristic interface - HUD sound effects.mp3` as the only sound-design track; its source title identifies it as effects, not music.
- Music treatment: 0.20 gain, short fade-in and fade-out; avoid letting transient effects mask the on-screen copy.
- Music cue guidance: no bundled preset; this effects-led track has no authored beat grid. Use natural editorial timing, no beat-sync claims.
- Audio-reactive treatment: subtle modulation on the existing segmented source ring using the extracted RMS data in `audio-data.js`.
- Audio-coupled moments: card/evidence entrances may follow soft natural transients, if present.
- SFX selection guidance: no additional SFX; user-provided track already contains interface effects.
- Audio files: source `composition/assets/music/Futuristic interface - HUD sound effects.mp3`; playback mix `composition/assets/music/agent-0-hud-soundscape.wav` (23.4s, 20% source gain, fades); `composition/assets/brand/agent-0-logo.png`; extracted data in `composition/audio-data.js`.

## Hyperframes Instructions
Build the supplied five-scene storyboard in this HyperFrames project. Preserve its exact sample copy, labels, palette, and uncertainty. Use the source ring as a restrained evidence motif, never generic HUD clutter. The complete visual presentation is owned by `composition/index.html`; keep asset URLs relative and local. Use a finite, seek-safe timeline. Let natural timing preserve readability; the supplied soundscape has no beat grid. Include a subtle, deterministic RMS response on the ring. Run `hyperframes check` before rendering.
