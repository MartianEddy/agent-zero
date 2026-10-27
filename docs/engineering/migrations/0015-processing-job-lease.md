# Migration 0015: Processing job leases

Migration `0015_processing_job_lease` adds a nullable ownership token, a
monotonically increasing lease generation, and a nullable expiry timestamp to
`processing_jobs`, plus an index on the expiry timestamp. Existing jobs retain
their status and receive generation `0`; the recovery path continues to support
jobs created before leases were introduced.

## Apply

The repository migration head is `0015_processing_job_lease`. Run migrations
before starting API or worker code that reads the lease columns:

```sh
docker compose run --rm migrate
```

The Compose API and worker services depend on the migration service completing
successfully. Starting only `postgres` does not apply migrations. For a deployed
environment, run the same Alembic upgrade as a release migration job after a
database backup and before rolling out the new API/worker image. Do not run the
migration directly against production without the deployment's normal backup
and release controls.

Verification on 2026-10-26 applied the full migration chain through `0015` to an
isolated, throwaway PostgreSQL database. The existing local Agent Zero database
was observed at `0009_media_analysis_runs` and was not migrated.

## Rollback

First stop workers and roll back API/worker code to a version that does not read
lease columns. Then run:

```sh
poetry run alembic downgrade 0014_evidence_ledger
```

This removes only the three lease columns and their index. Lease ownership and
expiry metadata are lost; existing investigation, source, and evidence rows
remain. Do not downgrade the schema while the lease-aware application version
is running.
