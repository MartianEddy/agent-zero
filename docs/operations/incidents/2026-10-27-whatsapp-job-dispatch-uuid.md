# WhatsApp investigation job rejected before research

**Date:** 2026-10-27 (UTC)
**Service:** Render API and Agent Zero Celery worker
**Investigation:** `AZ-261027-55065A`
**Severity:** Confirmed investigations failed before research began

## User impact

The user submitted the displayed preview code at approximately 16:14 UTC and received an investigation reference. `RESULT` repeatedly reported that the check was processing. At 16:26 UTC, it reported failure. No evidence assessment was produced.

## Evidence and root cause

- At 16:14:19.867 UTC, the worker's outbox dispatcher logged `Dispatched investigation jobs count=1`.
- At 16:14:19.876 UTC, Celery received `agent_zero.process_investigation`; immediately after, the worker logged `Starting investigation job job_id=None`.
- At 16:14:19.881 UTC, `process_investigation` failed at `app/tasks.py:160`, while converting the job ID to a UUID: `ValueError: badly formed hexadecimal UUID string`.
- The failure occurred before job-lease acquisition and before the research pipeline. This was not Luna latency, search-provider latency, or a model authentication issue.
- The WhatsApp confirmation path created `ProcessingJob` and `OutboxEvent` together, then serialized `job.id` into the event payload before SQLAlchemy flushed the pending job. The Python-side UUID default is assigned during flush, so `job.id` was still `None` when the outbox payload was built.
- Since no processing task could claim the queued job, `RESULT` showed its old active state. At 16:24:38.933 UTC, stalled-job recovery marked one case failed after the ten-minute queued-job threshold. This explains the wait and final failure.

## Remediation

- Assign the job UUID explicitly when constructing the `ProcessingJob`, before constructing the outbox event. The final commit remains atomic across the case, job, outbox, and audit record.
- Add a regression assertion that the outbox `job_id` equals the `ProcessingJob.id` assigned at construction.
- Make active `RESULT` replies name the current work stage, say that the claim need not be submitted again, and provide the exact reference command. Make terminal failure copy explicit that no assessment or conclusion exists and tell the user how to start a replacement check.

## Verification and next action

- The regression test failed before the fix because `ProcessingJob.id` was `None` and passed after the job UUID was assigned before building the outbox payload.
- Focused WhatsApp suite: 49 passed. Scoped Ruff, compilation, and `git diff --check` pass.
- The code fix still needs commit, push, and Render API deployment. The worker code itself does not need a change; it correctly rejected the malformed task argument.
- The failed case remains terminal and has no assessment. Do not imply it can be revived; after deployment the user can resubmit the original claim and approve a new preview to create a fresh case.
- Repeat a controlled WhatsApp claim, confirm it once, then verify that worker logs show a non-empty UUID and `process_investigation` reaches the pipeline. Check `RESULT <reference>` while active and after completion.

## Rollback

Revert the API commit. No schema change or migration is involved.
