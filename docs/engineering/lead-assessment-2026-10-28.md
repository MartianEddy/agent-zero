# Agent Zero lead assessment: vision, defects, and path forward (2026-10-28)

**Status:** Proposal for product-owner decision. No code or config was changed.
**Method:** Read `.sinaps/state.md`, open questions, product/architecture docs, the evidence policy, `orchestrator.py`, `investigator.py`, `verdict_policy.py`, `registry.py`, `source_tiers.json`, `render.yaml`, `evals/`. Ran `assess_verdict` and `build_independence_groups` on constructed inputs (read-only, no DB, no provider calls). Did not run the test suite (disk 99% used, 3.8 GB free; memory 228 MB free) or probe any live service.

## 1. Verdict on the vision

The vision is sound and well-scoped: "AI investigates, humans decide", claims traced to retrieved excerpts, uncertainty preserved, application code (not the model) owns the verdict. The core design choice, a bounded application-controlled pipeline instead of a free-roaming agent, is correct for this domain and should stay.

The implementation has outrun its evidence. About 60 commits of policy, prompt and WhatsApp work exist, and **no quality number exists**: `evals/RESULTS.md` reports 0 of 42 predictions measured. The system cannot currently say whether any change made it better.

## 2. What to keep

- Model output is a proposal; `verdict_policy.py` decides status and confidence.
- Exact-excerpt validation and sentence-level citation checking before anything is shown.
- Untrusted-content framing in every prompt, strict Pydantic output schemas (`extra="forbid"`).
- Outbox + job lease + audit events; idempotency keys on intake.
- Cost and time budgets (`max_model_calls`, `investigation_deadline_seconds`).
- Honest copy: "insufficient evidence is not false", qualitative confidence.

## 3. Defects, ranked

### P0: exposure and release hygiene

1. **Public deploy runs with auth off.** `render.yaml` sets `APP_ENV=development`, `AUTH_MODE=disabled` for the API and worker. `config.py` deliberately raises for staging/production, so the deployment is labelled "development" to get past the guard. Every route resolves to one shared `DEV_USER_ID` (`routes.py:68`). If the API service is publicly reachable, history, results, export and media preview are readable and writable by anyone. *Not verified live; confirm the API's public reachability first.*
2. **Uncommitted, unrun work.** 10 modified files (policy, registry, orchestrator, investigator, conversation service and tests) with backend tests "not run". The most recent policy changes are unverified.
3. **Disk 99%, swap exhausted.** Blocks tests, migrations, deploys. Migration 0015 is unapplied on the persistent local DB.

### P1: verdict logic (reproduced with `assess_verdict`)

| Input | Result | Problem |
|---|---|---|
| 1 matching PRIMARY source, `STATISTICAL` claim, proposes CONTRADICTED | `INSUFFICIENT_EVIDENCE/LOW` | The one-primary-source rule is gated on `SETTLED_FACT` only. An official KNBS figure cannot refute a statistic alone, though statistics are where one official source is decisive. The golden set has 6 statistical claims. |
| 4 reputable groups support, 1 reputable group contradicts | `INSUFFICIENT_EVIDENCE/MEDIUM` | Any single contradiction neutralizes any amount of support. No weighting by tier, directness, or date. |
| 1 matching PRIMARY, `SETTLED_FACT` | `SUPPORTED/LOW` | The canonical clean case is labelled low confidence. |
| 2 PRIMARY groups | `SUPPORTED/HIGH` | HIGH needs two primary groups. For most facts only one agency exists, so HIGH is unreachable in practice. |
| Conflict, nothing resolved | `INSUFFICIENT_EVIDENCE/MEDIUM` | An unresolved verdict reports MEDIUM confidence, which reads as "fairly sure". |
| `en.wikipedia.org` + `www.wikidata.org` | two independent groups | Same foundation, same underlying data. `nation.africa` and `nationmedia.com` also split. Independence is by registrable domain unless a CITES/DUPLICATES link was detected, so syndicated wire copy counts as corroboration. |

Related:
- **Registry is 24 domains**: 9 PRIMARY (7 Kenyan, plus un.org, who.int, worldbank.org), 4 reference, 3 Kenyan outlets, 1 fact-checker, 7 social. Unknown domains are ineligible for any verdict (`verdict_policy.py`). Reuters, AP, BBC, AFP, PesaCheck, and every non-listed ministry or court can never contribute. Most real claims will land on `INSUFFICIENT_EVIDENCE`.
- **`africacheck.org` is `SECONDARY_AGGREGATOR`**, the lowest non-social tier, and `orchestrator.py` (~line 1870) skips aggregators whose `source_type` is UNKNOWN. Fact-checkers are the product's closest peers and best leads.
- **`authority_fits_claim`** is English keyword overlap between claim words and registry topic words. Swahili, Sheng, and mixed-language claims (common in Kenyan WhatsApp) will mostly fail the match.
- **Freshness** is described in the policy doc but `verdict_policy.py` takes no date input.
- **Vocabulary conflict** between approved docs (`UNVERIFIED/INCONCLUSIVE/MODERATE`) and code (`INSUFFICIENT_EVIDENCE/PARTLY_TRUE/NOT_VERIFIABLE/MEDIUM`) is still open.
- **SETTLED_FACT is a model-assigned label** that unlocks the single-source path. A misclassified contested claim gets the weakest evidence bar. Settled facts also spend one model call each.

### P1: architecture

1. **`orchestrator.py` is 2,913 lines.** `process_investigation` is one ~370-line function with three near-identical search/retrieve/persist blocks (PRIMARY, REFERENCE_REPORTING, FACT_CHECK). Failure anywhere becomes one coarse `NEEDS_REVIEW`; the audit calls this "stage-level", not resumable. `conversations/service.py` (1,839 lines) and `_handle_turn` (~700 lines) have the same shape.
2. **Model budget collides with design.** `max_model_calls_per_investigation=4`. Extraction (1) + one call per settled-fact claim + final reasoning (1) + visual analysis (1) can exceed 4 for a three-claim or image case, and exceeding it aborts the whole investigation. Output caps (700 plan, 900 findings for up to 3 claims × 12 sentences × 20 evidence links) risk truncated JSON. *Truncation handling not traced.*
3. **Single provider, no failover.** ADR-005 is superseded. The 2026-10-28 HTTP 401 stopped the whole pipeline. All claim extraction, stance judgement, intent and answers depend on one model and one key.
4. **Policy lives twice.** Verdict thresholds are written into the reasoning prompt and into `verdict_policy.py`. Prompts are 40-line string literals, with no version recorded against results (not found in code), so a behaviour change cannot be tied to a prompt change.
5. **Evidence packet is cut by character slice** (`prompt[: max_total_evidence_chars + 8000]`), which can drop the tail claim's evidence silently.
6. **No prior fact-check reuse.** No ClaimReview / Google Fact Check Tools lookup exists in code (only in docs). Checking whether Africa Check, PesaCheck or others already assessed a claim is the cheapest high-value step in the field.
7. **No CI.** No `.github/workflows`; tests, lint and evals run only by hand, which is how 10 files reached "unverified".
8. **Worker sized at 512 MB, concurrency 1**, running an investigation with up to ~540 s time limit. One slow case blocks everyone, including the outbox dispatcher on the same process (`--beat` is co-located).

### P1: evaluation

- 42-claim golden set: 8 settled-true, 8 settled-false, etc. Examples are generic ("Mango is a fruit", "Pluto is a planet"). None are Kenyan, Swahili, WhatsApp-forward style, image, or video.
- Only end-to-end verdict/triage/citation metrics. No retrieval recall, stance accuracy, independence accuracy, abstention rate, or latency/cost.
- Scores are computed from captured outputs by hand; no run has ever been captured.

## 4. Target architecture

Keep: modular monolith, PostgreSQL, Celery, bounded pipeline. Change:

1. **Split the pipeline into explicit stages with typed input/output and checkpoints**: `intake → claim_extraction → plan → retrieve[lane] → stance → assess → brief`. One generic `run_lane(lane)` replaces the three copied blocks. Each stage persists a result row, so retry resumes at the failed stage. Lanes for different claims run concurrently inside the deadline.
2. **Separate stance from verdict.** One focused call per (claim, excerpt batch) returns SUPPORTS/CONTRADICTS/CONTEXT with a quote span. A second step synthesizes. Smaller prompts are cheaper to evaluate, fine-tune, and swap. This matches stage-wise results in the literature (retrieval and stance quality drive end accuracy).
3. **Evidence-weighted assessment** replacing count-only rules. Inputs: source tier, directness, recency vs claim type, independence group, ownership group. Output: status + a reasoned confidence that is never MEDIUM on an unresolved verdict. Allow one decisive primary source for `STATISTICAL` and `CHECKABLE_EVENT` when registry remit matches. Keep the thresholds in code, versioned, and out of the prompt.
4. **Source registry as data with ownership and remit**, reviewed by humans: `owner_group` (Wikimedia, Nation Media Group, wire services), `remit` topics, language, jurisdiction. Reclassify fact-checkers as a `FACT_CHECK` tier that is a lead and can corroborate, never settles alone. Seed with: Kenya courts/Judiciary, IEBC, Treasury/Controller of Budget, Auditor-General, CBK, KNBS, Ministry of Health, plus Reuters, AP, AFP, BBC, PesaCheck, Africa Check, Kenya Gazette.
5. **ClaimReview lookup stage** before web search: query existing fact-checks, follow them to their cited records, mark as `FACT_CHECK` context.
6. **Model gateway with provider abstraction**, per-task model config (cheap for intent/stance, stronger for assessment), fallback on 401/429/5xx with an explicit audit entry. Record `prompt_version` and `model` on each finding.
7. **Real auth** (the OIDC adapter the config already anticipates) or, as an interim, a shared-secret gate on the API origin and Render private networking so only the web service and worker can reach it. Add per-user ownership before human review exists.
8. **Language layer**: detect language, translate claim to English for retrieval while preserving the original; support Swahili/Sheng in extraction and in the registry's remit matching (replace keyword overlap with embedding or model-assisted topic match, still validated against the registry).
9. **CI**: ruff + pytest + eval smoke on every push.

## 5. Agent modelling and training: recommended approach

**Do not fine-tune yet.** You have no labelled data and no baseline. Order of work:

1. **Measure (weeks 1-2).** Build the eval set that represents users: 150-300 claims from real WhatsApp submissions (consent and privacy first), Kenyan fact-checks from Africa Check/PesaCheck with their verdicts as gold, Swahili and mixed-language items, image/forward-style items, and a deliberate abstention slice (claims with no findable evidence) plus prompt-injection fixtures. Score per stage: claim extraction, retrieval recall@k of the gold fact-check's cited sources, stance accuracy, verdict accuracy, **abstention precision** (don't answer when you shouldn't), citation validity, p50/p95 latency, cost per case. Report calibration, not just accuracy. AVeriTeC (4,568 real-world claims from 50 fact-checking organisations, evidence as question-answer pairs) is the standard public benchmark to borrow metrics from, including its evidence-aware score. Keep your own set as the decision set; public benchmarks are English and Western-weighted.
2. **Fix the cheap defects (weeks 1-3).** Items in section 3 that need no model: independence/ownership, registry, tier fixes, primary-for-statistics, confidence semantics, CI, auth. Re-run evals after each; keep a changelog of score deltas.
3. **Improve prompting and structure (weeks 3-6).** Stance/verdict split, claim decomposition limited to genuinely multi-part claims, retrieval-refine step to cut irrelevant evidence, selective abstention. Use LLM-as-judge only for semantic checks (faithfulness of the explanation to cited text) and calibrate the judge against human labels; grade the trajectory (queries, sources chosen, what was dropped), not only the final answer. Outcome-only grading hides right-answer-wrong-process failures.
4. **Collect training signal from human review (ongoing).** The "humans decide" step is your data engine. Persist every reviewer action (accept/override stance, verdict, source quality, edited explanation) with reviewer identity. This requires solving the reviewer-identity open question first.
5. **Then train, narrowly (month 3+).** Candidate targets in order of payoff: (a) a small stance/NLI classifier for English+Swahili fine-tuned on reviewer-labelled (claim, excerpt) pairs, (b) a claim-worthiness/extraction model for WhatsApp-style text, (c) a reranker for retrieval. Distil the expensive model's labels only after human spot-check. Keep verdicting in application code. Pay for fine-tuning only when an eval stage shows a measurable gap that prompting cannot close.
6. **Privacy rule for training data**: current docs say submissions are private and not used for training by default. Training on user data needs explicit consent, redaction of phone numbers, and a retention decision before any dataset is built.

## 6. Roadmap

| Phase | Outcome | Gate |
|---|---|---|
| 0 (now) | Free disk, run backend tests on current diff, commit or stash the 10 modified files, confirm API exposure, gate the API | Tests green, API not anonymously reachable |
| 1 | Eval harness v2 + CI; first real baseline | `RESULTS.md` has real numbers |
| 2 | Verdict/independence/registry fixes; confidence semantics; vocabulary decision | Score deltas ≥ 0 on abstention and citation validity |
| 3 | Staged pipeline with checkpoints, gateway with failover, ClaimReview stage, prompt versioning | p95 latency and cost per case recorded and within budget |
| 4 | Language layer, human review with identity, feedback capture | Reviewer decisions persisted |
| 5 | Narrow fine-tunes where evals justify | Beats prompted baseline on the decision set |

## 7. Decisions needed from the product owner

1. Is the Render API currently public, and are you willing to put an auth gate on it before any further WhatsApp rollout?
2. Canonical status vocabulary (docs vs code), including whether unresolved conflict should be `INCONCLUSIVE`.
3. May we use consented real submissions and public Kenyan fact-checks to build the eval set?
4. Who is the first human reviewer, and how are they identified?
5. Provider policy: add a second model provider for failover, and is any data-handling constraint on which one?

## Sources

- AVeriTeC dataset: Schlichtkrull et al., https://arxiv.org/abs/2305.13117
- AVeriTeC shared tasks: https://arxiv.org/abs/2410.23850 and https://aclanthology.org/2025.fever-1.15.pdf (the second task changed constraints toward open-weights and efficiency, so its scores are not comparable to the first)
- Stage-wise fact-checking benchmark (claim extraction, retrieval, verification): https://arxiv.org/html/2601.02669v1
- Calibrated selective fact-checking: https://arxiv.org/pdf/2607.18240v1
- Outcome-only agent grading limits: https://arxiv.org/html/2609.00038
- Search snippets were used for orientation; I read abstracts only and did not review the papers in full.
