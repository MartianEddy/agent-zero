# Open Questions

Add one row per unresolved question. Leave this table empty when there are no open questions.

| Question | Blocks | Raised | Status |
|---|---|---|---|
| Resolve production authentication, retention/deletion, outbound provider (including whether Jina Reader may receive source URLs), and deployment decisions before accepting sensitive submissions or deploying publicly | Production rollout / sensitive submissions | 2026-10-03 | Open |
| ClickCast's documented WhatsApp Webhook Workflow can trigger an approved template from an external callback, but recipient selection and callback authentication/retry semantics are undocumented. Confirm whether it can address the originating subscriber by ClickCast Subscriber ID; otherwise design encrypted, time-limited recipient storage before implementing completion notifications | Automatic ClickCast completion messages | 2026-10-04 | Open |
| ClickCast exposes no stable incoming-message ID in the current variable picker; requests without `event_id` can create duplicates on retry. Resolve production auth/tenant, retention/deletion, provider handling and deployment before live multi-user traffic | Retry-safe live ClickCast traffic and production multi-user use | 2026-10-04 | Open |
| Define the persisted human review action (reviewed, correction, or editorial disposition), reviewer identity, and audit/retention policy. Do not let shared demo visitors alter one another's findings | Auditable editorial review workflow | 2026-10-09 | Open |
