# Sinaps Engineering OS Product Roadmap

## Product direction

SEOS is an AI-native engineering operating system: decisions, requirements, architecture, code, journeys, evidence, incidents, and feedback form one durable memory loop.

## Products

### Golden Journey Registry — first product

Canonical journeys connect requirements to real UI behavior. Each journey stores owner, platforms, seed data, steps, expected states, evidence, and last passing run. The filesystem is the first registry; a dashboard comes later.

### Sinaps Control Plane

Read-only aggregation of `.sinaps/state.md`, open questions, verification evidence, security findings, and next actions across registered repositories. It must never become a second source of truth.

### Feedback Engine

Normalizes feedback, screenshots, incidents, and analytics into a triage record linked to a requirement, risk tier, plan, and golden journey.

### Architecture Intelligence

Compares approved diagrams/contracts and repository/runtime evidence. It reports drift; it does not silently rewrite architecture.

### Release Room

Creates a review bundle containing requirement, diff, test/security evidence, journey evidence, rollback, risks, and ship decision.

### Environment Manager

`sinaps health` is read-only inspection. Future `sinaps doctor` and `sinaps env clean --preview` may propose cleanup, but any mutation requires explicit confirmation and a bounded target.

## Product boundary

The CLI and Markdown/YAML artifacts are the durable core. A web dashboard is a consumer of those artifacts, not a replacement for them.
