# ClickCast investigation result journey

## User goal

A journalist submits one claim or public URL, receives a reference, and can return to the same investigation to see progress or read its assessment. The bot must not imply that an available result proves a claim.

## Conversation states

### Intake accepted

Confirm what Agent 0 received and give the reference the user will need to reopen this case.

```text
Check started.

Reference: #az_reference#
Send RESULT to check the latest case, or use Check this result to reopen this case.
```

### Investigation still running

Be clear that there is no conclusion yet, and prevent duplicate submissions.

```text
This check is still underway. There is no conclusion yet. You do not need to submit the claim again.

Reference: #az_reference#
Send RESULT again in a few minutes to check this case.
```

### Assessment available

Lead with the outcome, explain its limits, and give an editorial next step. Insert the API `summary` as a single variable so the backend can tailor the wording to the finding statuses.

```text
Your result is ready.

#az_summary#

Reference: #az_reference#
```

### Reference not found

Use this when the exact reference does not belong to this sender or cannot be found. Do not fall through to the latest case silently.

```text
I couldn't find that check for this WhatsApp account. Check the reference and send it again.
```

### Result service unavailable

Use this for an HTTP/API error. Do not show a previous `az_summary` as if it were the response to this request.

```text
I couldn't retrieve the result just now. Your investigation was not resubmitted. Please try again shortly.
```

Example for one inconclusive finding:

```text
Assessment: Inconclusive.

The evidence reviewed so far does not confirm or refute the claim. One finding needs human review.

Before publication, verify the claim with an independent, authoritative source.
```

“Ready” means an assessment is available. It does not mean the claim is confirmed. Outcomes may be supported, challenged, not verified, inconclusive, or mixed.

## Reopen behavior

- `RESULT` is a shortcut to the sender's latest investigation.
- A **Check this result** button starts the result flow with the saved `az_reference`; the API also receives the sender identifier used at intake. This retrieves that exact investigation and does not rerun research.
- For an older case after a new submission has replaced `az_reference`, prompt for the reference and save it to a separate `az_requested_reference` field. Call the result endpoint with that reference and the same sender identifier. Keep the submitted-case field unchanged.
- A new **Investigate again** action creates a new investigation; it is different from reopening a result.

## ClickCast mapping

- Intake response `reference` → `az_reference`.
- Result response `ready` → `az_ready`; in the current ClickCast account it is stored as `1`, so the condition must compare with `1`.
- Result response `summary` → `az_summary`.
- Result response `status` → `az_result_status`, separate from the intake status (`RECEIVED`).
- Both HTTP API requests send the same sender variable in the same format.

Before each result API call, clear or reset `az_ready` and `az_summary` if ClickCast supports it. An HTTP/API error must not reuse a previous `az_ready` value or display an old summary as a new result. Verify error behavior in ClickCast Test & Verify. Automatic completion messages are not part of this journey until ClickCast confirms recipient routing and callback authentication.
