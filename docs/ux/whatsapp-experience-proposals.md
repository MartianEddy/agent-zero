# WhatsApp experience: findings and proposals (2026-11-25)

Status: proposal for review. Nothing below is built except where marked "done".

## What a check looks like today

| Step | Who | Message | Meta category |
|---|---|---|---|
| 1 | User | Sends a claim | free |
| 2 | Agent Zero | Typing indicator, then claim preview with buttons (Submit / Edit / Cancel) | service |
| 3 | User | Taps Submit or types YES | free |
| 4 | Agent Zero | "Got it. I'm checking this now ... Ref: AZ-7KQ2F" | service |
| 5 | Agent Zero | Result, sent automatically when the case finishes (1 to 3 minutes) | service |

So the agent already answers on its own after research (step 5). Each check costs three
business messages.

## Rules and costs that shape the design

Sources: Meta WhatsApp Business Platform pricing and Cloud API docs, read 2026-11-25.

- **Free-form replies only inside the 24-hour window.** A non-template message can only
  be sent within 24 hours of the user's last message. Outside it, only an approved
  template can be sent.
- **Service messages are no longer free.** Since 1 October 2026 Meta charges per
  delivered service message after the first 1,000 per month per business number.
  Kenya is billed at the "Rest of Africa" rate on Meta's rate card.
  At three messages per check, the free tier covers about 330 checks a month. Every extra
  message per check (a progress update, for example) cuts that to 250 and adds cost
  after it.
- **Typing indicator** lasts at most 25 seconds or until we reply, and can only follow a
  user message. It cannot cover a 2-minute investigation. Meta: "only display a typing
  indicator if you are going to respond."
- **Reply buttons:** up to 3 per message, label up to 20 characters, body up to 1,024,
  footer up to 60. List messages allow up to 10 rows.
- **Quality rating:** users blocking or reporting the number lowers its rating and
  messaging limits. Fewer, more useful messages protect it.

## Problems found

1. **The result's "Why" line is internal jargon.** Users see the finding's internal
   statement, for example: "Retrieved evidence meets the support threshold through 2
   independent source group(s). Review the linked passages and context before
   publication." It doesn't say what was found, and "before publication" is newsroom
   language.
2. **The result can't easily be forwarded.** Fact-checks spread when people forward them
   to family and community groups. The current result is long and ends with commands
   ("reply HELP"), so a forwarded copy is confusing.
3. **Fast checks still cost three messages.** Settled facts are often decided in about
   20 seconds, but the user still gets "I'm checking this now" first.
4. **Results that arrive after 24 hours would fail to send.** There is no approved
   template for "your result is ready". This is rare today, but retries and long
   queues make it possible.
5. **No next step on the result.** The user has to type commands. Buttons are cheaper to
   use and harder to get wrong.
6. **Done: long references.** Now short (`AZ-7KQ2F`), accepted in any case, with or
   without "AZ-", and old references keep working.

## Proposals, in recommended order

### P1. Plain-language result (no extra cost)

Lead with the verdict and what the sources say, named. Keep it short enough to read
on a lock screen.

```
*Not true*
Kenya did not win the 2022 FIFA World Cup. FIFA's records show Argentina won
the final against France.

*Sources:* FIFA (fifa.com), Wikipedia
*How sure:* Medium. One official record, no conflicting sources.

Ref: AZ-7KQ2F
```

How: build the "Why" sentence from the model's cited explanation (already validated
against the passages), not from the internal statement. Name sources by publisher.
Keep the threshold wording for the web case view, where reviewers want it.

### P2. Buttons on the result (no extra cost)

Three buttons under the result: **Sources**, **Share**, **Check another**.

- *Sources* replies with the full source list and the passage quoted from each.
- *Share* replies with a short card made for forwarding (P3).
- *Check another* clears the conversation and asks for the next claim.

Each tap is a user message, so it also reopens the 24-hour window.

### P3. A forwardable verdict card (no extra cost when requested)

```
Agent Zero checked: "Kenya won the 2022 FIFA World Cup."
Result: Not true. FIFA's records show Argentina won the final.
Sources: fifa.com, wikipedia.org
Check claims yourself: send a message to <number> | agent-zero-web.onrender.com
Ref: AZ-7KQ2F
```

It is self-contained, carries no commands, and doubles as low-cost word of mouth.

### P4. Answer fast checks in one message (saves one message per fast check)

After the user taps Submit, wait up to about 15 seconds before sending "I'm checking
this now". If the result is ready by then, send only the result. The typing indicator
(up to 25 seconds) covers the wait.

### P5. At most one progress update, and only when it helps (costs one message, sometimes)

Progress messages cost money and add noise, so don't stream them. Send a single
update only if a case is still running after about 2 minutes, and make it useful:

```
Still checking AZ-7KQ2F. I've read 6 sources so far, including the Kenya Law
Reports. I'll send the result here when it's ready.
```

The user can still reply *STATUS* at any time. Cap it at one update per check, and
skip it once the monthly free tier is used up (the delivery webhook reports when
messages become billable).

### P6. A "result ready" utility template (needed for correctness)

Register one utility template with Meta, for example: "Your Agent Zero check {{1}} is
ready. Reply RESULT to see it." Use it only when the 24-hour window has closed.
Utility templates are billed per message, so they are the fallback, not the default.

### P7. Smaller improvements

- Reply in the user's language for the whole flow (Kiswahili already works for
  commands). Mirror the language of the claim in the preview and result.
- On the preview, show claim wording the user can correct in one tap (Edit), and
  show at most 3 claims.
- Mark incoming messages as read immediately (done, along with the typing indicator).
- Voice notes: many users forward audio. Transcribe, then preview the transcript as
  the claim. This adds speech-to-text cost per note.

## Cost summary per check

| Flow | Business messages |
|---|---|
| Today | 3 |
| With P1 to P3 | 3 (Share and Sources only when tapped) |
| With P4, fast check | 2 |
| With P5, slow check | 4 at most |

## What I recommend building first

P1 and P2 together. They fix the most visible problem (jargon) and add one-tap next
steps at no extra message cost. Then P4 (saves money on fast checks) and P6
(correctness). P5 last, behind a setting.
