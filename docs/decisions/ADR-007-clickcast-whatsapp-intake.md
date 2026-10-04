# ADR-007: ClickCast owns WhatsApp transport for the intake MVP

**Status: Accepted for local/sandbox implementation by product owner on 2026-10-04; HTTP API builder path clarified 2026-10-04. Automatic completion delivery is proposed; production use remains blocked.**

## Context

The product owner connected the Mediremind WhatsApp Business account in ClickCast and asked to route messages into Agent 0's existing investigation workflow. Agent 0 already has a `WHATSAPP` channel value and channel-neutral async investigation service. The product owner showed ClickCast's HTTP API builder, which provides API details, request headers/body, Test & Verify, and response mapping.

## Decision

- ClickCast remains the WhatsApp connection, bot, and inbox layer. Agent 0 will not register a second Meta webhook or retain Meta access tokens for this MVP.
- ClickCast's HTTP API builder calls an Agent 0 intake endpoint for text and direct URL messages, then maps the `202` response into a bot acknowledgement.
- Use a stable message event ID for deduplication when ClickCast supplies one. The current ClickCast variable picker has only subscriber IDs and phone numbers, so `event_id` is optional; when absent, Agent 0 generates a unique idempotency key to prevent separate messages from colliding. Retries without an event ID can create duplicate investigations. Route through the integration's configured workspace owner and derive a sender reference using HMAC pseudonymization; never persist the raw sender number in submission metadata.
- Authenticate requests using a bearer token in the builder's Authorization header.
- A later user interaction calls Agent 0's result endpoint with the sender and optionally the investigation reference; if omitted, Agent 0 selects the sender's latest WhatsApp investigation in the configured workspace. The endpoint returns a bounded result only after matching the sender reference. Terminal outcomes are returned as ready, including review, failure, and cancellation, so the bot does not report them as pending indefinitely. ClickCast maps the fields into a reply.
- For automatic completion delivery, use ClickCast WhatsApp Webhook Workflow if its callback can address the originating subscriber. Agent 0 would invoke the generated callback when the investigation reaches a terminal state, supplying the approved-template variables. The documented setup requires an approved message template and sample-data mapping, but does not explain recipient selection or callback authentication.
- Keep an immediate `RECEIVED` / `IN_PROGRESS` acknowledgement in the bot. Do not show numeric completion percentages: investigation stages are not equal units of work.
- Keep the integration disabled unless its API token and HMAC key are configured. Validate request variables and response mappings with Test & Verify before live traffic.

## Consequences

- The transport remains replaceable and the investigation logic stays channel-neutral.
- The implemented slice supports text/direct URLs and user-initiated result retrieval; media remains unsupported. Automatic final-result messages require confirmation that ClickCast can target a subscriber from callback data and confirmation of callback security/retry semantics. If recipient routing needs a phone number, its storage, encryption, and retention must be designed before implementation. Production multi-user use additionally requires the unresolved authentication/tenant, retention/deletion, provider-handling and deployment decisions.

## Rollback

Disable the ClickCast HTTP API actions and unset `CLICKCAST_API_TOKEN` and `CLICKCAST_IDENTITY_KEY`. The endpoints then reject requests. Existing investigations remain available under the existing retention policy.
