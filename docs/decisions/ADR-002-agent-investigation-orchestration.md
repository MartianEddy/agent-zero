# ADR-002: Agent-assisted investigation orchestration

**Status:** Accepted for local v1 implementation by product owner on 2026-10-03
**Scope:** Text, URL, image and video investigations; no production sensitive-data use.

## Decision

Use one OpenAI Agents SDK Lead Investigator behind an application-owned orchestration interface. The Celery worker invokes the orchestrator. FastAPI routes remain intake/read adapters. The orchestrator owns durable lifecycle transitions and calls bounded application tools for claim extraction, media inspection, source discovery and evidence recording.

PostgreSQL remains the source of truth; the SDK is not permitted to write directly to the database or determine lifecycle status. Material findings must reference persisted evidence from the same investigation. Media signals are observations with methods and limitations, not truth scores. Image/video inputs use the same Investigation domain as text/URL.

## Consequences

- The SDK dependency and model credentials are required only by workers that execute AI stages; provider failures become explicit retryable failure or `NEEDS_REVIEW` outcomes.
- The first version uses one investigator; specialist agents are deferred until evaluated evidence supports splitting responsibilities.
- Provider prompts, model identifier and safe run metadata should be auditable. Submitted media/content must not be written to application logs.
- Local development and test use only. Production auth, retention/deletion, and provider data-handling decisions remain open.

## Rollback

Disable the investigator via configuration and route queued work to `NEEDS_REVIEW`; preserve intake and stored evidence records. Revert the new migration only when no records use the added tables, or retain the additive schema while reverting application code.
