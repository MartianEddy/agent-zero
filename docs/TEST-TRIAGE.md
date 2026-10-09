# Slice 1 test triage

Compared the post-Slice 1 failures with the pre-Slice 1 results in
[`BASELINE.md`](BASELINE.md). Category (a) is a Slice 1 contract-fixture update;
category (b) is an existing behavior failure that remains out of scope for this
hygiene step. Assertions were kept and updated to the new contract where a
legacy verdict/type was no longer valid.

## Backend: initial 16 failures

| Test | Class | Disposition |
|---|---|---|
| `test_contradicted_finding_requires_contradicting_evidence` | (a) | Added required confidence fields and updated the legacy type/verdict fixture; sufficiency assertion retained. |
| `test_finding_without_matching_evidence_is_downgraded` | (a) | Added required confidence fields and updated legacy type/verdict values; no-evidence downgrade assertion retained. |
| `test_freshness_intent_is_encoded_in_dispatched_search_query` | (b) | Same query expectation failure recorded in baseline; unchanged. |
| `test_normal_text_flow_completes_with_two_model_operations` | (a) | Added required confidence fields to mocked model output; two-operation expectation retained. |
| `test_provider_failure_preserves_claims_sources_and_evidence` | (b) | Same source-count mismatch recorded in baseline; unchanged. |
| `test_retry_reuses_completed_search_retrieval_and_evidence` | (b) | Same retry search-call mismatch recorded in baseline; unchanged. |
| `test_c2pa_analysis_uses_original_and_retry_reuses_run` | (a) | Added confidence fields and migrated legacy claim/verdict expectations to the Slice 1 contract; provenance assertions retained. |
| `test_evidence_from_another_investigation_is_rejected` | (a) | Added confidence fields and updated stale verdict expectation; rejection assertion retained. |
| `test_media_only_evidence_is_included_and_can_support_finding_when_related` | (a) | Added confidence fields; evidence-link and support-policy assertions retained. |
| `test_metadata_alone_cannot_support_a_factual_finding` | (a) | Added confidence fields; insufficiency assertion retained. |
| `test_source_only_evidence_is_included_and_can_support_finding` | (a) | Added confidence fields; evidence-link and support-policy assertions retained. |
| `test_unknown_evidence_id_is_rejected` | (a) | Added confidence fields and updated stale verdict expectation; rejection assertion retained. |
| `test_unrelated_media_evidence_cannot_magically_support_claim` | (a) | Added confidence fields and updated stale verdict expectation; non-support assertion retained. |
| `test_visual_observation_is_persisted_before_synthesis_and_failure_is_safe` | (a) | Added confidence fields; persistence-before-synthesis assertion retained. |
| `test_registry_membership_alone_cannot_support_a_finding` | (a) | Added confidence fields and updated legacy claim type/verdict values; registry-only insufficiency assertion retained. |
| `test_support_and_contradiction_are_both_preserved_and_no_evidence_downgrades_support` | (a) | Added confidence fields, migrated the legacy proposed verdict, and updated the fixture explanation to the current mixed-verdict language; both evidence relationships remain asserted. |

Category (a): 13 tests. Category (b): 3 tests. The four media evidence graph
tests already seen in the baseline also had old status fixtures; they are
classified as (a) because their current failures were caused by the new schema
rejecting the fixture before its original assertion ran.

## Frontend: initial 2 failures

Both failures are category (b) because they were present in the pre-Slice 1
baseline. The accepted Slice 1 frontend copy update already resolves them:

| Test | Class | Current result |
|---|---|---|
| `processing and evidence relationships use reader-facing language` | (b) | Passes with current progress wording. |
| `unknowns, limitations, next steps, and partial-analysis notice are available` | (b) | Passes with current missing-evidence wording. |

## Hygiene verification

- Backend: **122 passed, 3 failed**. The three failures are exactly the
  pre-existing freshness-query, provider source-count, and retry search-call
  failures recorded in `BASELINE.md`; no Slice 1 contract-fixture regressions
  remain.
- Frontend: **15 passed, 0 failed** (baseline was 13 passed, 2 failed).
- No live providers were called.

## Slice 2 verification

- Backend: **133 passed, 3 failed**. Failures are the same three pre-Slice 1 baseline failures above (historical query expectation, extra source rows, retry search-call count); no Slice 2 test is failing.
- Frontend presentation tests: **15 passed, 0 failed**. `npx tsc --noEmit` passed.
- `npm run build` compiled the app but failed during Next.js TypeScript configuration parsing (`Could not parse output from TypeScript's --showConfig`). Direct TypeScript checking passes; this build-tool failure is documented and not attributed to the Slice 2 UI changes.
- Evidence-ledger unit/integration tests cover grouping, excerpt offsets, citation checks, conservative migration defaults/rollback, and all six claim types using mocked evidence. No live source provider was called.
- `evals/run_eval.py` reports 42 golden claims and no accuracy/citation score because no captured provider results were supplied. `evals/RESULTS.md` reports these measures as not measured.
- Jina Reader effective local setting resolves to `jina_reader`; no `JINA_API_KEY` is configured in the current environment. The default reader path and optional Bearer-header behavior are unit tested. No Reader request was made.
