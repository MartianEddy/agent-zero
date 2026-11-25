# Is Agent Zero its own agent, or a GPT wrapper?

**Date:** 2026-11-25 · **Author:** product lead review · **Status:** for decision

## Short answer

Agent Zero is a Sinaps Technology product with its own system. GPT is the reasoning engine it calls at six points. It is not a thin wrapper on the main investigation path: the application plans the work, finds and reads sources, checks every quote, and its own rules decide the result. But two things are true and must change:

1. **The most important judgment is still GPT's.** Whether a passage supports or contradicts a claim (the "stance") is decided by GPT. Our rules then check counts, independence and authority, but they trust GPT's reading of each passage.
2. **Two paths are close to a wrapper.** WhatsApp quick answers are GPT plus OpenAI's own web search, with our code only formatting the reply. WhatsApp routing (what does the user want?) is GPT's choice. That is how the bot told a user it was "built by OpenAI": the question went to a web search, which found ChatGPT.

## What Agent Zero owns and what GPT owns

| Step | Who decides | Where |
|---|---|---|
| Accept the message, verify Meta's signature, deduplicate, identity | Agent Zero | `channels/whatsapp.py`, `conversations/service/inbound.py`, `identity.py` |
| Typed commands, previews, confirmation, history, results | Agent Zero | `conversations/service/commands.py`, `drafts.py`, `case_replies.py` |
| Questions about Agent Zero itself | Agent Zero (fixed profile, added today) | `conversations/messages.py` |
| What the WhatsApp user wants (chat, question, claim, status) | **GPT** | `WHATSAPP_CONVERSATION` |
| Quick factual answers | **GPT + OpenAI web search** | `WHATSAPP_QUICK_ANSWER` |
| Split a request into claims, pick a claim type, plan searches | **GPT** proposes; Agent Zero normalises, caps and routes | `CLAIM_EXTRACTION`, `orchestrator/planning.py` |
| Stage order, budgets, deadlines, which lanes to widen | Agent Zero | `orchestrator/pipeline.py` |
| Search | Agent Zero via Exa, plus OpenAI web search as a second provider | `orchestrator/search_stage.py` |
| Open pages and extract passages | Agent Zero (Jina reader, own extraction) | `sources/retrieval.py`, `evidence_extraction.py` |
| Check that each quote really is on the page | Agent Zero | `evidence_ledger.validate_excerpt` |
| Group copies and same-owner sources | Agent Zero | `evidence_ledger.independence_groups`, `verdict_policy` |
| Source tier and authority for the topic | Agent Zero | `sources/registry.py`, `source_tiers.json` |
| **Does each passage support or contradict the claim** | **GPT** | `EVIDENCE_REASONING` |
| Proposed verdict | GPT proposes; Agent Zero's rules can only make it weaker | `verdict_policy.assess_verdict` |
| Final verdict and evidence strength | Agent Zero | `verdict_policy.py` |
| Headline wording | Agent Zero | `orchestrator/findings_stage.py` |
| Explanation sentences | GPT writes; Agent Zero deletes any sentence not tied to a checked quote | `validate_sentence_citations` |
| Image file details, content credentials, fingerprints | Agent Zero | `investigations/media/` |
| What an image shows | **GPT** (labelled as fallible observation) | `MEDIA_VISUAL_ANALYSIS` |

Of about 18 decision points, Agent Zero alone owns 12. GPT alone owns 4, and the remaining 2 are GPT proposals that Agent Zero checks. The weak spots are the ones in bold.

## Safeguards in place

1. **Untrusted input:** every prompt tells the model that user text and web pages are data, not instructions (`UNTRUSTED_CONTENT_POLICY`).
2. **Strict output shapes:** model output must match a fixed schema with no extra fields, or it is rejected.
3. **Quotes must exist:** a passage only counts if it was retrieved and matched against the page text.
4. **Citations must hold:** explanation sentences that do not cite a checked passage from the same run are removed.
5. **Rules over model:** the verdict can never be stronger than the evidence rules allow.
6. **Independence:** copies, wire stories and same-owner sites count once.
7. **Authority:** social, unknown and fact-check sources cannot settle a result; one official source settles only a basic fact or a fresh statistic on its own topic.
8. **Our words for the verdict:** headlines come from the application, not the model.
9. **Human first:** users approve the exact claim before any research.
10. **Budgets:** caps on model calls, searches, pages and time per case and per chat.
11. **Identity:** "who are you / who built you / are you ChatGPT" is answered from a fixed Sinaps Technology profile, never by search (added today).
12. **Privacy:** sender IDs are keyed hashes, reply routes are encrypted, training samples are redacted and off by default.
13. **Channel security:** Meta signatures checked twice (Cloudflare and API); receipts prevent double replies.

## Gaps

| Gap | Risk | Fix |
|---|---|---|
| Stance is GPT's judgment and unmeasured | Wrong "supports" or "contradicts" passes straight into the verdict | Measure on the eval set, then train our own stance model (see training architecture) |
| Quick answers are GPT + OpenAI search | Off-brand or unsourced answers; no quote checking | Route through Agent Zero's own search, page reading and quote checks |
| WhatsApp routing is GPT | Misrouted messages, as with "who built you" | Own intent classifier; deterministic rules for known patterns (started) |
| One model, one provider | One bad key or outage stops everything | Provider failover; then our own models for the high-volume steps |
| Claim type is GPT's and unlocks the one-source rule | A disputed claim labelled "settled fact" gets a weaker bar | Check claim type against the registry and the evidence; train a claim-type classifier |
| No prompt-injection evaluation | Unknown resistance to hostile pages | Add injection cases with live scoring (cases INJ-001 to INJ-003 exist) |
| Sign-in is off | Shared demo data | Authentication before wider launch |

## Way forward

| Phase | Goal | Result |
|---|---|---|
| Now (done today) | Correct identity | Fixed profile; prompt rules; tracking links removed; Sinaps Technology on the website |
| 1. Measure (2 weeks) | Know how good each step is | Baseline on the Kenya eval set per step, with a working model key |
| 2. Own the answers (2 weeks) | No wrapper path left | Quick answers through our search and quote checks; provider failover |
| 3. Own the judgments (6 to 8 weeks) | Agent Zero's own models for stance and intent | Trained in-house, GPT kept as teacher and fallback |
| 4. Own the language (later) | Claim extraction and explanations in our own model | Only where evals show it beats GPT |

The goal is not to remove GPT. It is that every decision that affects a verdict is either made by Agent Zero's rules or by a model Sinaps Technology trained, measured and can explain, with GPT as a replaceable component.

See [training architecture](../architecture/training-architecture.md).
