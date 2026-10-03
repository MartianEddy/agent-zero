# ADR-007: ClickCast owns WhatsApp transport for the intake MVP

**Status: Accepted for local/sandbox implementation by product owner on 2026-10-04; HTTP API builder path clarified 2026-10-04. Production use remains blocked.**

## Context

The product owner connected the Mediremind WhatsApp Business account in ClickCast and asked to route messages into Agent 0's existing investigation workflow. Agent 0 already has a `WHATSAPP` channel value and channel-neutral async investigation service. The product owner showed ClickCast's HTTP API builder, which provides API details, request headers/body, Test & Verify, and response mapping.

## Decision

- ClickCast remains the WhatsApp connection, bot, and inbox layer. Agent 0 will not register a second Meta webhook or retain Meta access tokens for this MVP.
- ClickCast's HTTP API builder calls an Agent 0 intake endpoint for text and direct URL messages, then maps the `202` response into a bot acknowledgement.
- Deduplicate on the stable message event ID. Route through the integration's configured workspace owner and derive a sender reference using HMAC pseudonymization; never persist the raw sender number in submission metadata.
- Authenticate requests using a bearer token in the builder's Authorization header.
- A later user interaction calls Agent 0's result endpoint with the investigation reference and sender; the endpoint returns a bounded result only after verifying the sender reference. ClickCast maps the fields into its reply.
- Keep the integration disabled unless its API token and HMAC key are configured. Validate request variables and response mappings with Test & Verify before live traffic.

## Consequences

- The transport remains replaceable and the investigation logic stays channel-neutral.
- The first slice supports text/direct URLs and user-initiated result retrieval; media remains unsupported. Production multi-user use additionally requires the unresolved authentication/tenant, retention/deletion, provider-handling and deployment decisions.

## Rollback

Disable the ClickCast HTTP API actions and unset `CLICKCAST_API_TOKEN` and `CLICKCAST_IDENTITY_KEY`. The endpoints then reject requests. Existing investigations remain available under the existing retention policy.
