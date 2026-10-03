# Open Questions

Add one row per unresolved question. Leave this table empty when there are no open questions.

| Question | Blocks | Raised | Status |
|---|---|---|---|
| Resolve production authentication, retention/deletion, outbound provider (including whether Jina Reader may receive source URLs), and deployment decisions before accepting sensitive submissions or deploying publicly | Production rollout / sensitive submissions | 2026-10-03 | Open |
| ClickCast exposes no stable incoming-message ID in the current variable picker; requests without `event_id` are not retry-idempotent and can duplicate investigations. Confirm outbound response mappings; resolve production auth/tenant, retention/deletion, provider handling and deployment before live multi-user traffic | Retry-safe live ClickCast traffic and production multi-user use | 2026-10-04 | Open |
