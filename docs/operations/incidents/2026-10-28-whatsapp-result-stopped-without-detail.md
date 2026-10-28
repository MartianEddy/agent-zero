# WhatsApp result returned a generic stopped-state message

**Date:** 2026-10-28  
**Case:** `AZ-261028-F4AEA3`  
**Status:** Root cause identified; result/recovery improvements and WhatsApp retry suppression are deployed. The worker credential requires owner-side correction/confirmation.

## Follow-up anomaly: latest case not found by RESULT

**Case:** `AZ-261028-ED24C0`
**Observed:** After submitting the approved claim, both `Results` and `Result` replied that no check existed for the WhatsApp number.

The direct `RESULT` path always added `Investigation.reference == reference`, even when the user omitted a reference. With `reference=None`, SQLAlchemy emitted `investigations.reference IS NULL`; valid cases always have a reference, so the lookup could never match. The plural spelling `Results` was also not a deterministic command and fell through to model interpretation.

The fix makes an unqualified `RESULT` select the newest case scoped to the sender's HMAC identity, retains exact reference lookup when supplied, and recognizes both `RESULT` and `RESULTS` with or without a reference. Regression tests cover the null-reference query and plural command routing. Commit `9d2c2ca` is deployed as `dep-dbgukd0u01pc73b46e7g`; API readiness is healthy. The owner should query `RESULT AZ-261028-ED24C0` to confirm the saved case's processing outcome.

## Observed

The owner completed the WhatsApp claim-preview flow for “Who owns Sinaps Technology in Kenya?”, approved the preview, received a case reference, and requested `Result` about two minutes later. The bot replied that the check needed human review, without showing the claim, any retrieved sources, a failure reason, or a retry action.

## Diagnosis from implementation

The result handler returns the same `NEEDS_REVIEW` fallback whenever a case has no saved `VerificationBrief`. The worker moves cases to `NEEDS_REVIEW` after a broad exception path and persists an error category on its latest `ProcessingJob`; WhatsApp did not use that category or show safe partial research. This explains the generic reply, but does not establish the exception that stopped this case.

The case record is `NEEDS_REVIEW` with no saved finding or brief. Its persisted audit category is `AUTHENTICATION_FAILED`. The result projection shows one investigation model call, eight searches, eight discovered source candidates, three retrieved pages, and zero findings. Render worker logs identify the failed call as `EVIDENCE_REASONING` to `gpt-6-luna`, HTTP 401, at 2026-10-28 08:49:40 UTC (provider request ID `req_4ae3fac97bee4d56bcef71fb855ec420`). API-side claim triage returned HTTP 200, so the evidence points to a worker-side credential/model authorization difference; the exact misconfigured secret cannot be read or verified here. Readiness reports the model provider as configured, which confirms configuration presence but not credential validity.

## Product and implementation response

- Completed results now include the saved claim, persisted finding summary, limitations, and retrieved URLs linked to saved findings.
- Stopped results say no assessment was saved, translate the stored failure category into plain language, and list retrieved pages only as unassessed. Retry is limited to transient failures; this case's authentication failure does not offer `RETRY` in WhatsApp.
- Transient retries use the existing worker and outbox path, check sender ownership, block duplicate active runs, and do not ask the user to resubmit. The existing web retry endpoint remains available to an operator after correcting the underlying service issue.
- Broad identity requests now receive concrete follow-up choices and avoid repeating the same capability disclaimer.

## Remaining verification

Resource health is BLOCKED (5% disk free, RAM 91%, swap full). Result/recovery commit `1ac2556` is deployed as `dep-dbgrsd61egvs73e1nup0`; auth retry guard `a69cd56` is deployed as `dep-dbgs0d6c6qcc73cgdpng`; API readiness is healthy. Local suites pass (53 WhatsApp tests; 17 cost-controlled pipeline tests), as do static Ruff F/I, compileall, and `git diff --check`. Correct/confirm the worker OpenAI credential without exposing its value, then complete a fresh owner-run WhatsApp journey. Phase 1 remains in VERIFY.
