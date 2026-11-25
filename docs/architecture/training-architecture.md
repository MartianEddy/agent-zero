# Agent Zero training architecture (draft v1)

**Date:** 2026-11-25 · **Status:** draft for product and engineering review · **Owner:** Sinaps Technology

## Goal

Move the decisions that shape a verdict from a general-purpose model to models Sinaps Technology trains, measures and can explain. Keep the deterministic rules (verdict policy, independence, authority, quote checks) as code: they are policy, not something to learn. GPT stays as a teacher for labelling and as a fallback.

## What to train, in order

| # | Model | Replaces | Why first | Input → output | Starting model | Runs on |
|---|---|---|---|---|---|---|
| 1 | **Stance** | GPT's judgment of each passage in `EVIDENCE_REASONING` | It is the decision the verdict depends on most | (claim, passage) → supports / contradicts / context / unrelated | Multilingual NLI cross-encoder (mDeBERTa-v3-base-xnli class, ~280M) | CPU, int8 ONNX, small model service |
| 2 | **Intent router** | GPT in `WHATSAPP_CONVERSATION` (routing only) | High volume, simple labels, fixes misrouting | message + last turns → chat / question / claim / status / result / cancel / confirm / about-us | Small multilingual encoder (AfroXLMR or mMiniLM class, ~100M) | CPU in the API |
| 3 | **Claim type and check-worthiness** | Part of `CLAIM_EXTRACTION` | Claim type unlocks the one-source rule | claim → settled fact / event / statistic / contested / opinion; checkable yes/no | Same encoder family as #2 | CPU |
| 4 | **Retrieval reranker** | Keyword relevance in `search_stage` | Better passages in, better stance out | (claim, passage) → relevance score | Multilingual cross-encoder | CPU |
| 5 | **Claim extraction and explanation writer** | `CLAIM_EXTRACTION` text and explanation sentences | Hardest and costliest; only if evals justify it | request → atomic claims and queries; evidence → cited sentences | 7–8B open-weights model with LoRA | GPU, later |

Kiswahili, Sheng and English mixed text are in scope for every model from the start.

## System view

```text
                    ┌──────────────── live system ────────────────┐
 WhatsApp / web ──▶ │ commands ─▶ intent ─▶ claims ─▶ search ─▶     │
                    │ read pages ─▶ STANCE ─▶ verdict rules ─▶ brief│
                    └──────┬──────────────────────────┬────────────┘
                           │ stage_samples (opt-in,   │ reviewer
                           │ redacted, prompt version)│ decisions
                           ▼                          ▼
                 ┌────────────────────── data ──────────────────────┐
                 │ raw samples ─▶ PII redaction ─▶ dedupe ─▶        │
                 │ labelling (GPT teacher + human review) ─▶        │
                 │ versioned datasets (train / dev / frozen test)    │
                 └───────────────────────┬──────────────────────────┘
                                         ▼
                 ┌──────────────────── training ────────────────────┐
                 │ fine-tune on rented GPU ─▶ model card ─▶          │
                 │ evaluation gates ─▶ model registry               │
                 └───────────────────────┬──────────────────────────┘
                                         ▼
                 ┌──────────────────── release ─────────────────────┐
                 │ shadow (run beside GPT, not shown) ─▶ canary      │
                 │ (small share of traffic) ─▶ promote, GPT fallback │
                 └──────────────────────────────────────────────────┘
```

## 1. Data

| Source | Used for | Notes |
|---|---|---|
| `stage_samples` | All stages | Already built. Redacted prompt and output per model call, with prompt version and latency. Off until consent is decided (`CAPTURE_STAGE_SAMPLES`). |
| Reviewer decisions | Stance, claim type, verdict audits | Needs the reviewer tool and reviewer sign-in (open question). Highest-value labels. |
| Kenyan fact-checks (Africa Check, PesaCheck, AFP Fact Check) | Stance, claim type, eval | Each article gives a claim, a verdict and the cited records. Check each publisher's licence first. |
| Public datasets: AVeriTeC, FEVER, X-Fact (multilingual) | Stance and claim type pre-training | English-heavy; use for pre-training, not for the decision set. |
| Kiswahili and Sheng | All | Translate a sample of the above with human review; collect real WhatsApp phrasing with consent. |
| GPT as teacher | Bulk labels | Label large unlabelled sets, then have humans audit a stratified sample. Never train on unaudited teacher labels alone. |

**Splits:** by case and by claim, never by row, so the same claim never appears in both training and test. The Kenya evaluation set (`evals/kenya_claims.json`) and a reviewer-built test set stay frozen and are never trained on.

**Target sizes for the first stance model:** 2,000 to 5,000 labelled (claim, passage) pairs, at least 25% Kiswahili or mixed, balanced across the four labels.

## 2. Labels

| Stage | Label set | Guideline highlight |
|---|---|---|
| Stance | supports, contradicts, context, unrelated | "Supports" only if the passage addresses the same subject, action, place, time and scope. Background is context. |
| Intent | chat, factual question, claim to check, case list, status, result, cancel, confirm, about Agent Zero | Questions about Agent Zero are always "about Agent Zero". |
| Claim type | settled fact, event, statistic, media claim, contested, opinion or prediction | Disputed or current claims are never "settled fact". |
| Check-worthiness | checkable, needs detail, not checkable | "Needs detail" when subject, place or time is missing. |

Each item gets two independent labels; disagreements go to a third reviewer. Track agreement (Cohen's kappa) per label; below 0.6 means the guideline needs work before more labelling.

## 3. Training

- Encoders (#1 to #4): standard fine-tuning, a few hours on a single rented GPU (L4 or A10 class). Export to ONNX with int8 quantisation for CPU serving.
- Generator (#5): LoRA on an open 7–8B model, only after #1 to #4 are in production.
- Every run records dataset version, code commit, hyperparameters and metrics, and produces a model card: intended use, languages, known weaknesses, evaluation results.

## 4. Evaluation gates

A model is promoted only if, on the frozen test sets:

| Metric | Gate |
|---|---|
| Unsafe verdicts (decided in the wrong direction), measured end to end | Not higher than the GPT baseline |
| Stance macro-F1, and contradicts recall | At least the GPT baseline |
| Kiswahili and mixed slice | No more than 3 points below English |
| Injection cases | No change of verdict caused by text inside a passage |
| Latency and cost per case | Lower than the GPT baseline |

The harness exists (`evals/capture.py`, `evals/score.py`); it needs a per-stage mode added for stance and intent.

## 5. Serving

- **Stage model interface.** Each AI step gets a small interface (for example `StanceModel.classify(claim, passages)`) with two implementations: the current GPT one and Agent Zero's own model. The `ports` modules created in the refactor are where this plugs in.
- **Router.** Per stage, choose the model by configuration: GPT, own, or own-with-GPT-fallback when the own model's confidence is low.
- **Shadow mode.** The new model runs beside GPT on live traffic, its output stored but not used, until the gates pass on real data.
- **Canary, then promote.** A small share of traffic first; roll back with one setting.
- **Hosting.** Encoders as one small CPU service (about 1 to 2 GB RAM) next to the API; the current 512 MB worker is too small to host them.

## 6. Governance

- Training on user messages needs explicit consent and a retention period. Until both are decided, train only on public data and reviewer-labelled public claims.
- Redact phone numbers, emails and identifiers before anything is stored (already implemented for `stage_samples`).
- Keep a dataset register: source, licence, consent basis, size, languages.
- Publish model cards on the methodology page when a model is in production.

## 7. Plan

| Weeks | Work | Exit criterion |
|---|---|---|
| 1–2 | Working model key; baseline on the Kenya set; per-stage eval mode; consent decision | Baseline numbers committed |
| 2–4 | Reviewer tool and sign-in; labelling guideline; first 2,000 stance pairs (public and Kenyan fact-checks) | Agreement at least 0.6 |
| 4–6 | Train stance v1; offline eval; stage model interface and router | Passes offline gates |
| 6–8 | Shadow on live traffic; intent router v1 | Passes gates on live samples |
| 8–10 | Canary and promote stance; train claim type | Stance in production with GPT fallback |
| Later | Reranker; decide on the generator | Evals justify the cost |

## Decisions needed

1. Consent and retention for training on user messages.
2. Who reviews and labels, and how they sign in.
3. Budget for labelling and GPU hours. The encoder training runs are small: a few GPU-hours each.
4. Licences for Kenyan fact-check content.
