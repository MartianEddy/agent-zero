# Pre-Slice 1 baseline

**Date:** 2026-10-09  
**Branch:** `baseline/pre-slice-1` (created after baseline test runs; this record is included in the baseline commit)  
**Scope:** Existing backend and frontend test commands, run against the current worktree before Slice 1 edits. Existing uncommitted project changes were present; this is a baseline of that worktree, not a clean upstream revision.

## Environment

- Disk: 11 GB free of 233 GB (96% used). The user authorized proceeding with available resources; no cleanup was performed.
- Backend: Python 3.12.3, pytest 8.4.2.
- Frontend: npm package script runs Node's built-in test runner.
- No live OpenAI, Exa, Jina, social, or other external provider calls were part of these test commands.

## Results

| Suite | Command | Result |
|---|---|---|
| Backend | `cd backend && poetry run pytest` | **109 passed, 8 failed** (117 collected; 18.58 s) |
| Frontend | `cd frontend && npm test` | **13 passed, 2 failed** (15 total; 40.9 ms) |

### Backend failures

- `test_freshness_intent_is_encoded_in_dispatched_search_query`: historical query helper now adds a historical-context suffix, while the existing expectation requires the unchanged query.
- `test_provider_failure_preserves_claims_sources_and_evidence`: got 3 sources where the test expects 1 (additional provider traces/source candidates in current worktree).
- `test_retry_reuses_completed_search_retrieval_and_evidence`: search-call usage increased from 6 to 8 on retry.
- `test_c2pa_analysis_uses_original_and_retry_reuses_run`: expected `INCONCLUSIVE`, got `UNVERIFIED`.
- Four `test_media_evidence_graph` cases expected `INCONCLUSIVE` for rejected/ineligible evidence; implementation returned `UNVERIFIED`.

### Frontend failures

- `processing and evidence relationships use reader-facing language`: expected “Comparing what the evidence says”, received “Comparing retrieved pages”.
- `unknowns, limitations, next steps, and partial-analysis notice are available`: expected an unknown item containing “No evidence is linked”; none matched.

## Baseline conclusion

Both test suites execute, but the existing worktree has known failures before Slice 1 changes. Keep these failures visible during Slice 1 and do not attribute them to Slice 1 without comparison. No source code was edited before this baseline was recorded.
