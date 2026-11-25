# Evaluations

Two claim sets, one scorer.

| File | Cases | What it covers |
|---|---:|---|
| `golden_claims.json` | 42 | Original generic set (English). |
| `kenya_claims.json` | 35 | Kenyan public records, statistics, events, health rumours, Kiswahili (9), Sheng/mixed (3), WhatsApp-style forwards, ambiguous requests that should get a clarifying question, and prompt-injection attempts. |

Every expected label in `kenya_claims.json` is a draft (`label_status: draft_needs_review`).
An editor should confirm each one, especially time-sensitive items (KE-015, KE-016, KE-019, KE-026, KE-027), before scores are treated as decisions.

## Run

```bash
# 1. Capture: spends real model and search calls, so it needs --confirm-spend.
#    Start small with --limit. Re-running resumes and skips finished cases.
backend/.venv/bin/python evals/capture.py --set evals/kenya_claims.json \
  --api http://127.0.0.1:18000 --out evals/runs/kenya-YYYYMMDD.json --confirm-spend --limit 5

# 2. Score: offline, no network.
backend/.venv/bin/python evals/score.py --set evals/kenya_claims.json \
  --predictions evals/runs/kenya-YYYYMMDD.json --report evals/RESULTS-kenya.md
```

## What is measured

Each metric is reported with its counts, not as a bare percentage:

- **Claim type correct**: did triage label the claim as expected?
- **Clarification behaviour**: did it ask a question exactly when it should, and only then?
- **Verdict correct**, overall, by group and by language.
- **Left undecided when it should**: abstention on cases that lack decisive evidence.
- **Decided when it should**: coverage on cases with clear official evidence.
- **Unsafe verdicts**: decided in the wrong direction. This is the number to drive to zero.
- **Citations valid**: cited evidence ids that are validated, retrieved, same-run passages.
- **Latency and model calls per case**.

## Status (2026-10-28)

No baseline has been recorded. The local API's OpenAI key is rejected (HTTP 401), so live
capture cannot run. After the key is fixed, capture the Kenya set and commit the report.
