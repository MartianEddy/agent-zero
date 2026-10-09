# Public site to investigation journey

**Status: Updated draft for the current public demo.** This document describes the observed web implementation plus the intended claim-and-evidence behavior approved for the MVP. The demo has shared history; it is not a private newsroom workspace.

## Primary journey

1. A journalist lands on the public site, sees a clearly marked illustrative sample, and opens Investigate.
2. The workspace warns that the demo history is shared and asks visitors to use public information only.
3. The user submits a specific factual question or claim, a public URL, an image, or a short video. The user may include useful context such as a date or place.
4. Agent 0 identifies up to three atomic, checkable factual claims. Clear questions are restated as declarative propositions while preserving the user's scope. If a necessary detail is ambiguous, the result asks for that detail and records no truth assessment.
5. Agent 0 searches public web results, labels results as candidates until page content is retrieved, and extracts bounded evidence excerpts from retrieved pages. Uploaded images/videos may produce separate visible-content or file observations; those observations are not proof of event truth.
6. Agent 0 assesses each claim only against eligible, traceable evidence and creates a brief with a plain-language outcome, the claim checked, supporting or challenging evidence, source dates and retrieval state, open questions, limitations, and a practical next step.
7. The journalist follows evidence links, inspects the original sources, and makes the editorial decision. Processing completion is not editorial approval or proof of truth.

## Response contract

For each checkable claim, present:

1. **Claim checked:** a concise declarative proposition that preserves the user's actor, action, place, and time.
2. **What the evidence suggests:** one direct, plain-language answer.
3. **Evidence status:** “Supported by the evidence reviewed,” “The evidence challenges this claim,” “Not enough evidence yet,” or “The sources disagree / leave this unresolved.” Keep the internal API values `SUPPORTED`, `CONTRADICTED`, `UNVERIFIED`, and `INCONCLUSIVE` unchanged.
4. **What was reviewed:** retrieved pages and traceable excerpts, clearly separated from search candidates.
5. **What remains unknown:** missing evidence, source scope, date uncertainty, or disagreement.
6. **Next step:** one action matched to the gap, such as checking an official record, sharing the original post, or clarifying a date or location.

“Not enough evidence yet” means the sources Agent 0 could access did not settle the claim. It does not mean the claim is false. A search failure is a processing limitation, not a claim assessment.

## Supported input and analysis states

| Input | Web MVP support | Visible limitation |
|---|---|---|
| Text claim/question | Supported | Ambiguous questions request a missing detail; no guessed scope |
| Public URL | Supported | Submitted page content is context; independent sources are needed to corroborate it |
| JPEG, PNG, WebP | Supported | Metadata/C2PA/visual checks are limited signals; no reverse-image search |
| MP4, WebM | Supported by API and upload workflow | Bounded frame sampling only; video audio is not transcribed |
| Audio-only, PDF, office document | Not supported in this MVP | Reject clearly; do not imply these formats can be investigated |

## Recovery and re-entry

- While processing, show the persisted stage and retain the investigation reference.
- On provider, storage, or retrieval failure, preserve collected evidence and explain whether the failure stopped the whole investigation or only limited coverage.
- Retrying is available only for failed/review-needed jobs within the existing model-call budget; it preserves prior audit events.
- A user can reopen the case by its reference. In the demo, other visitors can also view shared cases.
- When extraction needs clarification, show the exact missing detail and preserve the submitted request. The current MVP asks the user to start a new investigation with that context; in-place clarification and private case ownership require the later authenticated workspace.

## Editorial boundary

The MVP provides decision support. Users inspect the claim, source and evidence trail, then make editorial decisions outside the system. It does not persist a human reviewed/approved disposition. Add that capability only with authenticated reviewer identity and an audit policy so one public-demo visitor cannot alter another visitor's case.
