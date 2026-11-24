"""User-facing WhatsApp copy.

Pure functions only: no database, network, or settings access. Keep wording here so
tone, formatting and length are reviewed in one place. WhatsApp renders ``*bold*`` and
``_italic_``; messages must stay well under the 4,096-character limit.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_MESSAGE = 3900

# Labels match frontend/src/app/investigate/presentation.mjs statusPresentation so the
# web and WhatsApp use identical wording. Keep both in sync.
VERDICT_HEADLINES = {
    "SUPPORTED": "Evidence supports this claim",
    "CONTRADICTED": "Evidence challenges this claim",
    "PARTLY_TRUE": "Some parts or meanings are supported",
    "INSUFFICIENT_EVIDENCE": "Not enough evidence yet",
    "NOT_VERIFIABLE": "Not verifiable as a factual claim",
}

CONFIDENCE_WORDS = {"HIGH": "High", "MEDIUM": "Medium", "LOW": "Low"}

FAILURE_REASONS = {
    "RATE_LIMITED": "Our research tools were too busy for a moment.",
    "QUOTA_EXHAUSTED": "Our research tools were unavailable.",
    "AUTHENTICATION_FAILED": "A technical problem on our side stopped the check.",
    "PROVIDER_UNAVAILABLE": "Our research tools were briefly unavailable.",
    "TIMEOUT": "The check took too long to finish.",
    "INVALID_MODEL_OUTPUT": "One step of the check gave an unusable answer.",
    "BUDGET_EXCEEDED": "The check reached its usage limit.",
    "PIPELINE_ERROR": "Something went wrong while checking.",
    "DERIVATION_FAILED": "I couldn’t read the file you sent.",
    "STORAGE_FAILED": "I couldn’t safely save the research material.",
}
DEFAULT_FAILURE_REASON = "Something went wrong while checking."

PROGRESS_LABELS = {
    "RECEIVED": "Waiting in line",
    "PROCESSING": "Getting started",
    "ANALYZING": "Reading your claim",
    "RESEARCHING": "Searching for sources",
    "CORROBORATING": "Comparing what the sources say",
    "GENERATING_BRIEF": "Writing up the result",
}

# Short Swahili command aliases. Applied only when the whole message is the alias
# (optionally followed by a case reference) so ordinary sentences are never rewritten.
COMMAND_ALIASES = {
    "msaada": "help",
    "menu": "help",
    "hali": "status",
    "matokeo": "result",
    "jibu": "result",
    "historia": "history",
    "ghairi": "cancel",
    "jaribu tena": "retry",
}


@dataclass(frozen=True)
class FindingView:
    status: str
    claim: str
    headline: str
    confidence: str
    confidence_reason: str


def clip(text: str, limit: int) -> str:
    """Collapse whitespace and cut at a word boundary."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;: ")
    return (cut or text[: limit - 1]) + "…"


def fit(message: str, reference: str | None = None) -> str:
    footer = f"\n\n_Ref: {reference}_" if reference else ""
    body = message.rstrip()
    if len(body) + len(footer) > MAX_MESSAGE:
        body = body[: MAX_MESSAGE - len(footer) - 1].rstrip() + "…"
    return body + footer


def normalize_command_alias(command: str) -> str:
    """Map a bare Swahili command (plus optional reference) to its English command."""
    parts = command.strip().split()
    for alias_words in (2, 1):
        if len(parts) < alias_words:
            continue
        alias = " ".join(parts[:alias_words]).casefold()
        english = COMMAND_ALIASES.get(alias)
        if english is None:
            continue
        rest = parts[alias_words:]
        if not rest:
            return english
        if len(rest) == 1 and rest[0].upper().startswith("AZ-"):
            return f"{english} {rest[0]}"
    return command


def result_message(
    findings: list[FindingView],
    *,
    sources: list[tuple[str, str]],
    limitations: list[str],
    reference: str,
    stopped_early: bool = False,
    stopped_reason: str | None = None,
    retry_hint: str | None = None,
) -> str:
    """Verdict first, then why, then how sure, then where to look."""
    lines: list[str] = []
    if stopped_early:
        note = "*This check stopped early, so treat the result below as preliminary.*"
        if stopped_reason:
            note += f"\n{stopped_reason}"
        if retry_hint:
            note += f"\n{retry_hint}"
        lines.append(note)

    if not findings:
        lines.append(
            "I couldn’t reach a result for this claim. That doesn’t mean it is true or false."
        )
    elif len(findings) == 1:
        item = findings[0]
        label = VERDICT_HEADLINES.get(item.status, "No result yet")
        lines.append(f"*{label}*")
        lines.append(f"*Claim:* {clip(item.claim, 240)}")
        lines.append(f"*Why:* {clip(item.headline, 420)}")
        lines.append(_confidence_line(item))
    else:
        lines.append(f"*{len(findings)} claims checked*")
        for number, item in enumerate(findings, start=1):
            label = VERDICT_HEADLINES.get(item.status, "No result yet")
            lines.append(
                f"{number}. *{label}*\n"
                f"   {clip(item.claim, 140)}\n"
                f"   {clip(item.headline, 200)}"
            )
        lines.append(
            "_Evidence strength shows how much solid evidence was found, "
            "not the chance a claim is true._"
        )

    if sources:
        listed = "\n".join(f"• {title}: {url}" for title, url in sources)
        lines.append("*Read the sources*\n" + listed)
    else:
        lines.append("_No source links to show in this summary._")

    if limitations:
        noted = "\n".join(f"• {clip(item, 160)}" for item in limitations[:2])
        lines.append("*Keep in mind*\n" + noted)

    lines.append("Send me another claim any time, or reply *HELP* to see what I can do.")
    return fit("\n\n".join(lines), reference)


def _confidence_line(item: FindingView) -> str:
    if item.confidence == "UNASSESSED":
        return "*Evidence strength:* not recorded for this earlier result."
    word = CONFIDENCE_WORDS.get(item.confidence, item.confidence.title())
    reason = clip(item.confidence_reason, 200)
    line = f"*Evidence strength:* {word}"
    if reason:
        line += f". {reason}"
    return (
        line
        + "\n_This shows how much solid evidence was found, not the chance the claim is true._"
    )


def preview_message(claims: list[str], *, notification_notice: str) -> str:
    plural = len(claims) > 1
    claim_lines = "\n".join(f"• {clip(text, 300)}" for text in claims)
    heading = "Here are the claims I’ll check:" if plural else "Here’s the claim I’ll check:"
    return (
        f"{heading}\n\n{claim_lines}\n\n"
        "I’ll search public sources and tell you plainly what I find, including what I "
        "couldn’t confirm.\n"
        f"{notification_notice}\n\n"
        "*Nothing has started yet.* Tap a button below, or reply *YES* to start, "
        "*EDIT* to change it, or *CANCEL*."
    )


def registered_message(reference: str, update_expectation: str) -> str:
    return (
        "*Got it. I’m checking this now.*\n\n"
        "It usually takes a few minutes.\n"
        f"{update_expectation}\n\n"
        f"_Ref: {reference}_"
    )


def status_message(
    stage: str | None,
    status_value: str,
    reference: str,
    *,
    queued_retry: bool,
    retry_hint: str | None = None,
) -> str:
    if queued_retry:
        return fit(
            "*Your retry is waiting in line.* No need to send the claim again.", reference
        )
    if status_value == "COMPLETE":
        body = "*Done.* Reply *RESULT* to see what I found."
    elif status_value == "CANCELLED":
        body = "*This check was cancelled.*"
    elif status_value == "FAILED":
        body = (
            "*This check couldn’t be completed.* No conclusion is available.\n"
            "Reply *RESULT* to see anything gathered before it stopped."
        )
    elif status_value == "NEEDS_REVIEW":
        body = (
            "*This check stopped before it finished.* No final conclusion yet.\n"
            "Reply *RESULT* to see anything gathered before it stopped."
        )
    else:
        label = PROGRESS_LABELS.get(stage or status_value, "Still working")
        body = (
            f"*{label}...*\n"
            "I’ll message you when the result is ready, or reply *RESULT* to check."
        )
    if retry_hint:
        body += f"\n{retry_hint}"
    return fit(body, reference)


def history_message(rows: list[tuple[str, str, str]], *, page: int) -> str:
    """rows: (reference, plain status label, claim snippet)."""
    lines = [f"*Your checks* (page {page}, newest first)"]
    for reference, label, claim in rows:
        suffix = f"\n   {clip(claim, 90)}" if claim else ""
        lines.append(f"• {reference} · {label}{suffix}")
    lines.append(
        f"Reply *RESULT <reference>* to open one, or *HISTORY {page + 1}* for older checks."
    )
    return "\n".join(lines)


def case_status_label(status_value: str) -> str:
    return {
        "RECEIVED": "waiting",
        "PROCESSING": "in progress",
        "ANALYZING": "in progress",
        "RESEARCHING": "in progress",
        "CORROBORATING": "in progress",
        "GENERATING_BRIEF": "almost done",
        "COMPLETE": "done",
        "NEEDS_REVIEW": "stopped early",
        "FAILED": "couldn’t finish",
        "CANCELLED": "cancelled",
    }.get(status_value, "in progress")


def help_message() -> str:
    return (
        "*I’m Agent Zero.* I check claims against public sources.\n\n"
        "*Try this:*\n"
        "• Paste a claim, a link, or a photo you want checked\n"
        "• Or just ask a question\n\n"
        "I’ll show you what I understood *before* I start, so you stay in control.\n\n"
        "*Shortcuts*\n"
        "• *RESULT*: your latest result\n"
        "• *HISTORY*: your recent checks\n"
        "• *STATUS*: how a check is going\n"
        "• *STOP*: turn off automatic result messages\n\n"
        "_Kiswahili: MSAADA, MATOKEO, HALI, HISTORIA, GHAIRI_"
    )


def no_check_found() -> str:
    return (
        "I couldn’t find a check for this number yet.\n"
        "Send me a claim or a link and I’ll look into it."
    )


def failed_without_summary(
    *, claims: list[str], reason: str, sources: str, retry_line: str
) -> str:
    parts = ["*This check stopped before it finished.* No conclusion is available."]
    if claims:
        parts.append("*Claim:*\n" + "\n".join(f"• {clip(text, 240)}" for text in claims))
    parts.append(reason)
    if sources:
        parts.append(
            "*Pages I found before it stopped* (not confirmed as evidence yet):\n" + sources
        )
    parts.append(retry_line)
    return "\n\n".join(parts)


def failure_reason(code: str | None) -> str:
    return FAILURE_REASONS.get(code or "", DEFAULT_FAILURE_REASON)
