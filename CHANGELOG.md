# Changelog

## 2026-10-09 — Slice 2 evidence ledger and citation validation

- Added migration `0014_evidence_ledger` with conservative legacy values and a rollback note. Evidence now stores source tier, stance, excerpt offsets/validation, independence group, publication date/staleness, retrieval timestamp, and case run ID.
- Added deterministic independence grouping for publisher/domain, AP/Associated Press/Reuters/AFP markers, and near-identical excerpts. Verdict sufficiency now uses only cited, retrieved, validated evidence.
- Added sentence-level `{sentence, evidence_ids}` output, one structured-output retry, invalid-citation removal, verdict/confidence re-evaluation, and an unsupported-statement notice in the UI.
- Added evidence ledger details and citation links to the verdict view, shared case deadlines across retrieval/search/model steps, stored-result citation scoring, and claim-type test fixtures.
- Enabled Jina Reader by default for selected public candidate URLs, added optional `JINA_API_KEY` Bearer authentication, and documented opt-out and failure states. Reader failures remain incomplete checks.
- No new package dependency. See `docs/DESIGN.md` and `docs/TEST-TRIAGE.md` for assumptions and measured verification.

### Still not implemented or verified

- No live provider evaluation; the golden-set runner has no captured real predictions, so scores remain unmeasured.
- The Next.js production build still exits in its TypeScript config parsing step after compilation; standalone `tsc --noEmit` passes.
- Human decision panel, append-only reviewer override, and JSON export remain for Slice 3.

## 2026-10-09 — Audit and claim triage foundation

- Added `docs/AUDIT.md` with the repository map, current claim flow, service/data boundaries, coverage, constraints, and prioritized gaps against the requested product brief.
- Added `docs/DESIGN.md` with the intended claim-first flow, evidence contract, verdict rules, data additions, and MVP assumptions.
- Started Phase 1 with a strict structured claim type schema and required `needs_deep_investigation` field; persisted that flag, exposed it in result JSON, and displayed the detected triage type in the workspace.
- Prevented query planning for claims typed as opinions or predictions. Existing legacy claim types passed through the internal retry reconstruction map to `CHECKABLE_EVENT`.
- Added migration `0012_claim_triage` and a schema validation test.

### Still not implemented or verified

- Triage is not yet a pre-search editable/splittable card; no user correction endpoint or clarification-resume lifecycle exists.
- Settled facts do not yet have a dedicated fast reference path. The deep-investigation flag is metadata, not proof of a faster route.
- The requested verdict taxonomy, confidence taxonomy, independence rule, sentence-level citation validation, complete ledger/provenance/contradictions/gaps, human decision, exports, golden claims/eval runner, per-type end-to-end tests, and demo script remain outstanding.
- The migration, lockfile/dependency state, tests, browser journey, and provider integrations were not executed or verified because the repository health record reports the disk-space gate blocked. No live provider calls were made.
