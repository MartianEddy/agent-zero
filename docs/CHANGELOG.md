# Changelog

## Slice 1 — claim triage and verdict contract (2026-10-09)

- Added strict claim types, editable pre-search triage for text and URL submissions, and persisted investigation-depth metadata.
- Added deterministic verdict sufficiency and source independence grouping, plus conservative legacy-value migration and rollback notes.
- Added a bounded Wikipedia/Wikidata reference lookup and an explicit source-tier allowlist.
- Added 42 golden claims, a captured-prediction evaluation runner, and an honest no-live-run results report.
- Added true, false, and contested demo claim chips and a shared-history/non-sensitive demo notice.

Still incomplete in this slice: media submissions do not yet pause at the triage editor; nuance depends on evidence-reasoning instructions rather than a dedicated deterministic sense resolver; no live provider evaluation was run. See `docs/BASELINE.md` for pre-change test failures and `evals/RESULTS.md` for evaluation status.
