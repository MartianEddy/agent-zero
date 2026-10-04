# ADR-001: Modular investigation platform foundation

- Status: Accepted for phased implementation
- Date: 2026-10-03
- Decision owner: Product owner

## Context

Agent 0 receives requests through web, WhatsApp and future channels, and must produce evidence-traceable findings. Channel-specific verification logic would duplicate rules and weaken auditability. The approved architecture diagram specifies FastAPI, PostgreSQL, Celery/Redis and object storage.

## Decision

- Treat `Investigation` as the channel-neutral aggregate and route all channel adapters through the same application interface.
- Begin with a modular monolith: one FastAPI application and one Celery worker codebase, organized by domain modules.
- Use PostgreSQL as system of record, Redis for Celery/transient state, and private S3-compatible object storage for originals and derived media.
- Represent evidence/source/claim relationships relationally with explicit typed links. Do not add a graph database or `pgvector` until a demonstrated use case requires them.
- Persist lifecycle transitions and audit events. Technical job outcomes and claim assessment outcomes are separate.
- Findings must cite stored evidence; provenance and forensic outputs are signals, not automatic truth judgments.
- Build in phases, beginning with foundation only. No AI/search behavior is simulated as real.

## Consequences

This keeps deployment and domain ownership simple while preserving replaceable seams for channels, storage, search and model providers. Celery/Redis and object storage add operational dependencies, so local Compose and readiness checks are part of the foundation. Production identity, retention, provider and deployment policies require explicit follow-up before sensitive real submissions.

## Rollback

Remove the new backend application and Compose services without changing the existing Next.js frontend. For schema rollback, use Alembic downgrade only while data is disposable; production migrations require a reviewed recovery plan before deployment.
