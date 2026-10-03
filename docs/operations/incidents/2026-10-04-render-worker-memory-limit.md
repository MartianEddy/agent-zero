# Render worker memory restart

**Date:** 2026-10-04 (Africa/Nairobi)
**Service:** `agent-zero-worker`
**Severity:** Availability degradation; Render automatically restarted the worker.

## Evidence

- Render reported that the background worker exceeded its memory limit and restarted.
- The deployed Blueprint assigns the worker the `starter` plan (512 MB RAM).
- The original worker command used Celery's default prefork pool without an explicit concurrency cap, and embedded Beat in that worker.
- The supplied deploy log is for the API, not the worker. It shows a successful image build, migrations through `0009`, and Uvicorn startup. `/api/v1/ready` returned 503 because a readiness dependency was unavailable; object storage had not yet been configured.
- No worker logs or memory metrics around the restart were supplied, so whether the restart happened during startup or during a task is unknown.

## Assessment and mitigation

The confirmed cause is that the worker exceeded its 512 MB limit. Prefork process overhead and the investigation pipeline's media/native-library workload are plausible contributors, but the supplied evidence cannot identify which caused this particular peak.

The Render worker command now uses Celery's `solo` pool with concurrency 1. This avoids prefork child processes and serializes MVP jobs without increasing the plan. Beat remains enabled to dispatch the transactional outbox.

## Follow-up

After redeploy, check worker logs and the service memory graph around startup and the next controlled task. If memory still reaches the limit with one task in-process, identify the task stage and peak before selecting a larger plan; changing plans affects service cost. Do not treat the API's 503 readiness responses as proof of the worker OOM cause.

## Rollback

Revert the `dockerCommand` change in `render.yaml` to restore the previous Celery command. This restores prefork behavior and may reintroduce the memory pressure.
