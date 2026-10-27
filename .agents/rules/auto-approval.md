# Auto-Approval & Autonomous Execution Policy

## Guidelines
- **Autonomous Execution**: Automatically proceed with implementing code changes, creating/updating documentation, running test suites, executing linter checks, and performing non-destructive deployments without stopping between steps to ask for permission.
- **Non-Interactive Commands**: Always pass non-interactive and auto-confirmation flags (e.g. `--confirm`, `--yes`, `-y`, `--no-interaction`) to terminal and CLI tools (e.g. Render CLI, package managers, git commands) to prevent interactive prompts from stalling execution.
- **Clear Reporting**: Perform end-to-end task execution and deliver concise, complete reports of findings, errors, and next actions.
- **Safety Boundary**: Stop for explicit user confirmation only if an action is destructive, irreversible, or high-risk (such as deleting databases, purging unrecoverable production state, or force-pushing over active branches).
