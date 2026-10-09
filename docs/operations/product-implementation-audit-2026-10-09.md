# Agent 0 product and implementation audit

**Date:** 2026-10-09  
**Review type:** Static, end-to-end product and code-path audit  
**Scope:** Product intent, public entry, web intake/results/history, API and worker orchestration, evidence model, safety gates, and operational readiness.  
**Evidence limit:** This review inspected repository documentation and source. It did not run the app, execute tests, call live providers, or measure user accuracy. Findings below are implementation mismatches and risks, not an accuracy evaluation.

## Product model

Agent 0 is intended to help journalists and editors investigate a claim by extracting a bounded question, discovering candidate sources, retrieving source text, preserving traceable evidence, comparing it, and presenting an uncertain, reviewable finding. The product promise is “AI investigates. Humans decide.” Its central value is an auditable evidence trail, not an autonomous truth score.

The current product is a local/public-demo investigation workspace with a shared text, URL, image, and video backend path; public-web search and page retrieval; a single OpenAI model gateway; an evidence/results view; and a ClickCast intake/result adapter. It is not yet a private multi-user newsroom workspace. Production authentication, retention/deletion, provider handling, and deployment remain open gates in `.sinaps/state.md` and `docs/OPEN-QUESTIONS.md`.

## Findings by priority

### P0 — Do not use the current shared workspace for private or sensitive cases

The web UI labels the workspace public and shared, and the backend deliberately disables identity only in development/test. This is acceptable for a clearly bounded public demo, but it conflicts with the intended private-by-default investigation workspace if users interpret “your workspace” or “reopen” as private. The production gate is correctly recorded, but the active UI still allows submissions and exposes shared history.

**Fix:** Before any public or sensitive deployment, implement authenticated owner identity and authorization on every read/write route, including history, reference lookup, results, preview, retry, and media. Add retention/deletion behavior and a provider data-flow decision, including whether submitted URLs can go to Jina. Until then, keep the service explicitly demo-only and avoid real private material.

**Acceptance:** Two authenticated users cannot enumerate, reopen, retry, or preview each other’s cases by ID or reference; deletion removes relational records, original and derived blobs, and provider-held content according to a documented policy; production startup fails closed without auth and storage policy.

### P1 — Text questions can complete without answering the user’s question

The intake prompt invites “What do you want to check?” and suggests open questions such as “Did the government announce this?” The worker extracts up to three claims and, when it extracts none, creates unverified findings. A direct answer path exists only for a narrow set of image-origin keywords. As a result, ordinary questions, requests for attribution, or ambiguous prompts can finish as a generic unverified result even when they are valid investigative requests.

**Fix:** Add an explicit request-intent/claim contract before search: distinguish a factual proposition, an answerable research question, an image-origin request, and insufficient/ambiguous input. For questions, resolve to one or more reviewable propositions or provide a clear clarification prompt; never label the question itself as a claim without preserving its wording and scope. Add fixtures for question-only, attribution, compound, time-bounded, and non-factual prompts.

**Acceptance:** Every completed text investigation either presents a scoped answer with evidence links and limitations, or states the exact missing information and a useful next action. It must not claim to have verified an unparsed question.

### P1 — Public input affordances and supported media scope disagree

The requirements describe text, URL, image, and video in the current slice and mention audio/documents as supported-channel submissions. The API accepts MP4/WebM and the worker can extract bounded keyframes, but the web UI only accepts JPEG/PNG/WebP and the result view is image-specific. Audio and document types exist in the domain enum but are rejected by the submission schema and have no end-to-end workflow. This makes “supported” ambiguous and hides video capability from web users.

**Fix:** Decide and publish the actual supported matrix. Either expose video upload with duration, keyframe, and “audio not transcribed” states in intake/results, or reject/feature-gate it until the UI can explain its limits. Mark audio and document as planned/unsupported everywhere until there is a complete pipeline. Align the requirements, architecture, help copy, file picker, result rendering, and tests.

**Acceptance:** For each advertised type, a user can submit, see processing progress, inspect the appropriate extracted evidence and limitations, and understand what was not analyzed. Unsupported types fail before upload with a precise message.

### P1 — Evidence and finding states need a clearer human review loop

The system persists findings and qualitative confidence, but the inspected web flow presents them as a finished brief. There is no visible editor action to mark a finding reviewed, correct a relation, add a source, or record a decision. The product principle says humans decide, while the current interface mostly asks them to consume the model’s result. Existing source-link and limitation presentation is a solid foundation, but not an editorial workflow.

**Fix:** Define a human review state and minimum editorial actions before adding collaborative features: accept/reject/needs-more-work on a finding, annotate or correct evidence relations, add a source/evidence note, and record reviewer plus timestamp. Keep model assessment and human disposition separate in the data model and UI. Do not turn review into a public fact-check publication action.

**Acceptance:** A journalist can see what the model asserted, inspect each cited evidence item, record a distinct human disposition with attribution, and reopen the case without overwriting model output.

### P2 — History loading is request-heavy and labels are image-centric

The history page fetches the list and then issues a results request for each of the first 20 cases. This multiplies backend work and latency; the results endpoint also assembles relationships through per-finding queries. The history title/type fallback calls any media case “Image investigation,” which is wrong for video. There is no server-side pagination or search in the inspected route.

**Fix:** Add a compact history-list response containing safe title, input type, lifecycle state, finding status, and timestamp. Paginate and filter on the server. Keep full results loading for the selected investigation only. Use input-type-aware labels and avoid N+1 reads when returning finding evidence relationships.

**Acceptance:** History initial load uses a bounded page request, shows correct type/status for text, URL, image, and video, and continues to work as case count grows without fetching every result payload.

### P2 — Requirements and UX journey artifacts are stale relative to the shipped workspace

`docs/ux/public-site-journey.md` still describes `/investigate` as an unconnected placeholder with no submit, progress, error, or completion state. The live implementation now provides those behaviors. Architecture/requirements also mix implemented, authorized, later, and not-supported media capabilities. This makes the approved product contract unreliable for future implementation and review.

**Fix:** Refresh the UX journey and state tables from the current interface, label each requirement as implemented, partial, planned, or blocked, and link each to a golden journey and an implementation location. Record the open production gates in the relevant workflow so “public demo” cannot be mistaken for a production-ready workspace.

**Acceptance:** A new engineer can identify the supported intake types, every lifecycle state, recovery behavior, and the exact difference between demo and production from the approved artifacts without relying on the session log.

### P2 — “Current” research still needs an explicit freshness and coverage contract

The pipeline has current/historical query lanes and carries publication dates, but the experience can only report what providers returned and what pages were retrieved. A recent query or a recent article date does not prove that the latest authoritative status was found. The current/historical grouping is useful, but should not read as exhaustive coverage.

**Fix:** Show the investigation’s retrieval time, the latest publication date among reviewed sources, the number of candidates versus retrieved pages, and whether an authoritative source was actually retrieved for the claim. Phrase freshness as “coverage retrieved as of …”; add regression cases where current search returns only old/undated material or no official source.

**Acceptance:** Users can distinguish “no recent evidence was located” from “the claim is false,” and see when date metadata is missing or a source was only a candidate.

## Recommended sequence

1. Keep current demo boundaries visible and resolve the auth, retention/deletion, provider, and deployment questions before production use.
2. Correct the core investigation contract for question intent and claim extraction; add adversarial input cases.
3. Publish an accurate support matrix and close the web video-to-result experience or remove video from the active scope.
4. Add the human review disposition loop while preserving the model’s original result.
5. Refresh UX/requirements artifacts and the golden journeys to match implementation.
6. Reduce history API fan-out and add scalable pagination.
7. Improve freshness coverage indicators, then evaluate accuracy with a labelled claim set before introducing numeric confidence or stronger verification language.

## Verification needed before implementation can be called end-to-end

- A complete browser journey for text question, direct URL, image claim, and video upload (if retained in scope), including retry and failure recovery.
- A source-trace audit confirming every displayed support/contradiction finding links to retrieved, eligible evidence and that candidate-only sources cannot establish a finding.
- A privacy/authorization test with at least two separate users before any authenticated multi-user deployment.
- A labelled evaluation set measuring claim extraction errors, evidence entailment/contradiction errors, source independence, and stale/missing-date behavior.

The current session record says automated and real-browser verification remain pending resource repair. This audit therefore does not mark VERIFY or production readiness complete.

## Remediation update — 2026-10-09

The following local MVP fixes are now in the working tree:

- Claim extraction now rewrites clear factual questions into declarative checkable claims, requests missing context instead of guessing, and receives the extracted image/video frames. This repairs the prior multimodal extraction path that discarded its `images` argument.
- No-claim and inaccessible-URL results now give a plain-language explanation and next action. The user-facing `UNVERIFIED` label is “Not enough evidence yet” and explicitly says that missing evidence does not mean false.
- The web intake now accepts the API-supported MP4/WebM video types; sampled frames reach both claim extraction and the bounded visual-observation call, and the results view states the no-audio-transcription limitation. Audio-only and documents are explicitly outside current web MVP scope.
- Investigation history now uses one compact, bounded summary request instead of one full result request per case; finding-to-evidence serialization no longer issues a query per finding.
- The public journey artifact now describes the working investigation flow and evidence response contract.

Still open: shared demo cases remain visible to all demo visitors, and the product has no persisted human review disposition. Do not use the demo for private material. Closing those gaps requires the documented auth, ownership, retention/deletion, and reviewer-audit decisions. The web journey, API behavior, and worker pipeline have not been run or browser-verified in this session because `sinaps health` reported only 4% free disk and returned BLOCKED; no cleanup was authorized or performed.
