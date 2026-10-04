# SEOS Technology & Tooling Architecture

## Principle

SEOS uses AI for reasoning and deterministic tools for enforcement. Agents interpret evidence; scanners, test runners, telemetry, and CI produce it.

## Stage map

| Stage | Agent responsibility | Preferred evidence/tools | Policy |
|---|---|---|---|
| DISCOVER | Challenge the problem and alternatives | research notes, feedback intake | Human decides problem worth solving |
| DEFINE | Convert evidence into requirements | Spec Kit `specify`, `clarify`, checklists | Spec Kit is an adapter, not SEOS |
| UX | Define journeys and states | Mermaid, Storybook where useful | User-facing flows must be reusable journeys |
| ARCHITECT | Model boundaries, APIs, data, security, failure | Mermaid, ADRs, OpenAPI, Semgrep design review | Architecture changes require explicit approval |
| PLAN | Produce dependency-ordered work | Spec Kit `plan`, `tasks`, `analyze` | Analyze must be clean before BUILD |
| BUILD | Implement one bounded slice | project test/lint/build commands | Respect BUILD gate |
| VERIFY | Prove behavior and safety | Playwright, Playwright MCP/CLI, Argent, Maestro, Semgrep, Trivy | Real journey required for MEDIUM+ UI work |
| REVIEW | Seek reasons not to ship | fresh agent/persona, CI evidence, diff review | Independent pass required for MAJOR+ |
| SHIP | Make release decision | Release Room, GitHub Actions, rollback record | No unresolved blocking questions |
| OPERATE | Learn from runtime behavior | OpenTelemetry, Sentry, incidents, feedback | Findings feed DISCOVER |

## Tool registry policy

Core tools are enabled only when a project has the relevant stack and configuration. The default core set is: GitHub Actions, Mermaid, the project test runner, `sinaps health`, and `sinaps-user-workflow`. Optional adapters are opt-in: Spec Kit, Playwright, Argent/Maestro, Semgrep, Trivy, OpenTelemetry, Sentry, Renovate, and Storybook.

Do not install an MCP zoo. Expose only the tools needed for the current stage and project. Every adapter must have a safe mode, a command/config location, and an evidence artifact.

## Adapter decisions

- **Spec Kit:** use inside DEFINE/PLAN for specification, plan, task, and cross-artifact analysis. Keep SEOS product, UX, architecture, operations, and approval state outside `.specify/`.
- **Playwright:** primary browser journey engine. Test Agents may plan, generate, and heal tests, but a healed test is not accepted until the full journey and expected evidence pass.
- **Argent/Maestro:** mobile journey adapters. Follow the installed platform skill and sandbox rules.
- **Semgrep/Trivy:** deterministic source, dependency, container, and infrastructure checks. Findings block SHIP according to tier and severity policy.
- **OpenTelemetry/Sentry:** runtime evidence adapters. They support OPERATE and diagnosis; they do not replace local reproduction or acceptance journeys.
- **GitHub Actions/Renovate:** automation and dependency hygiene. They enforce policy; they do not approve releases.

## Evidence contract

Every VERIFY result records command/tool, timestamp, environment, input data, result, artifact path, and failure/repair history in `docs/verification/evidence/`. Golden journeys live in `docs/verification/golden-journeys/` and are referenced by requirements.

## Rollout

1. Install the SEOS package and run `sinaps init`.
2. Adopt the core contract and one browser/mobile journey.
3. Add deterministic security and supply-chain checks when the stack supports them.
4. Add telemetry adapters before relying on production diagnosis.
5. Only then build the Control Plane over the persisted project artifacts.
