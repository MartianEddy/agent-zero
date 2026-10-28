# WhatsApp result returned a generic stopped-state message

**Date:** 2026-10-28  
**Case:** `AZ-261028-F4AEA3`  
**Status:** User-visible recovery improved; underlying hosted worker failure still needs diagnosis.

## Observed

The owner completed the WhatsApp claim-preview flow for “Who owns Sinaps Technology in Kenya?”, approved the preview, received a case reference, and requested `Result` about two minutes later. The bot replied that the check needed human review, without showing the claim, any retrieved sources, a failure reason, or a retry action.

## Diagnosis from implementation

The result handler returns the same `NEEDS_REVIEW` fallback whenever a case has no saved `VerificationBrief`. The worker moves cases to `NEEDS_REVIEW` after a broad exception path and persists an error category on its latest `ProcessingJob`; WhatsApp did not use that category or show safe partial research. This explains the generic reply, but does not establish the exception that stopped this case.

A read-only Render log request for the screenshot time could not resolve `api.render.com` in the current environment. The hosted failure category for this reference remains unverified.

## Product and implementation response

- Completed results now include the saved claim, persisted finding summary, limitations, and retrieved URLs linked to saved findings.
- Stopped results say no assessment was saved, translate the stored failure category into plain language, list retrieved pages only as unassessed, and offer `RETRY <reference>` when the saved case and usage budget allow it.
- Retry uses the existing worker and outbox path, checks sender ownership, blocks duplicate active runs, and does not ask the user to submit a second case.
- Broad identity requests now receive concrete follow-up choices and avoid repeating the same capability disclaimer.

## Remaining verification

Resource health is BLOCKED (5% disk free, RAM above 90%, swap full). Focused local suites passed (51 WhatsApp tests; 17 cost-controlled pipeline tests), as did static Ruff F/I, compileall, and `git diff --check`; full-stack/live verification was not run. The hosted readiness endpoint returned healthy once, but subsequent Render API and case lookups failed DNS resolution. Inspect the hosted job error category for `AZ-261028-F4AEA3` and complete a fresh owner-run WhatsApp journey before marking Phase 1 verified.
