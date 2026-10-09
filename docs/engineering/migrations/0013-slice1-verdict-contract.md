# Migration 0013: Slice 1 verdict contract

Revision `0013_slice1_verdict_contract` follows `0012_claim_triage`.

The migration maps legacy claim types conservatively: image, video, and provenance become `MEDIA_CLAIM`; known factual/statistical values retain or map to factual categories; unknown types become `CHECKABLE_EVENT`. Legacy findings outside the new contract become `INSUFFICIENT_EVIDENCE`; `MODERATE` confidence becomes `MEDIUM`, and missing/unknown confidence becomes `LOW` with an explicit legacy rationale. It adds database check constraints for claim types, verdicts, and confidence values.

Rollback removes the constraints and maps `PARTLY_TRUE` to legacy `INCONCLUSIVE`, and `NOT_VERIFIABLE`/`INSUFFICIENT_EVIDENCE` to `UNVERIFIED`. Claim types collapse into legacy `FACTUAL`, `GENERAL`, and `PROVENANCE`. This rollback is lossy: preserve a database backup before downgrade if the new distinctions must be retained.
