"""User-facing WhatsApp copy.

Pure functions only: no database, network, or settings access. Keep wording here so
tone, formatting and length are reviewed in one place. WhatsApp renders ``*bold*`` and
``_italic_``; messages must stay well under the 4,096-character limit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.investigations.references import parse_reference

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


# Emoji and pictographs, removed from quoted and user text: replies never show them.
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]")


def _truncate(text: str, limit: int) -> str:
    """Cut to `limit` characters at a line or word boundary, keeping line breaks."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    cut = cut.rsplit("\n", 1)[0] if "\n" in cut[limit // 2 :] else cut.rsplit(" ", 1)[0]
    return cut.rstrip(",;: \n") + "…"


def clip(text: str, limit: int) -> str:
    """Collapse whitespace, drop emoji and cut at a word boundary."""
    text = " ".join(_EMOJI.sub("", text or "").split())
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
        if len(rest) <= 2 and parse_reference(" ".join(rest)) is not None:
            return f"{english} {' '.join(rest)}"
    return command


# Plain reasons, used when the cited explanation has nothing a reader can use.
PLAIN_REASONS = {
    "SUPPORTED": "Reliable sources confirm this claim.",
    "CONTRADICTED": "Reliable sources contradict this claim.",
    "PARTLY_TRUE": "Sources support part of this claim, but not all of it.",
    "INSUFFICIENT_EVIDENCE": (
        "I couldn’t find enough reliable sources that address this directly. "
        "That doesn’t mean it is true or false."
    ),
    "NOT_VERIFIABLE": "This is an opinion or a prediction, so it can’t be checked as a fact.",
}

HOW_SURE = {
    "HIGH": "High. Several independent sources agree, including official records.",
    "MEDIUM": "Medium. Reliable sources agree, but only one or two address this directly.",
    "LOW": "Low. Little reliable evidence addresses this directly.",
}

# Button labels are at most 20 characters (Meta).
RESULT_BUTTON_LABELS = ("Sources", "Share", "Check another")
INTERACTIVE_BODY_LIMIT = 1024


def result_buttons(reference: str, *, has_sources: bool = True) -> list[tuple[str, str]]:
    """Button IDs double as typed commands: SOURCES <ref>, SHARE <ref>, NEW."""
    sources, share, new = RESULT_BUTTON_LABELS
    buttons = [(f"SHARE {reference}", share), ("NEW", new)]
    return ([(f"SOURCES {reference}", sources)] if has_sources else []) + buttons


def _how_sure(confidence: str) -> str | None:
    line = HOW_SURE.get(confidence)
    return f"*How sure:* {line}" if line else None


def result_message(
    findings: list[FindingView],
    *,
    source_names: list[str],
    reference: str,
    stopped_early: bool = False,
    stopped_reason: str | None = None,
    retry_hint: str | None = None,
) -> str:
    """Verdict, what the sources say, who they are, how sure. Short enough for buttons."""
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
        lines.append(f"*{VERDICT_HEADLINES.get(item.status, 'No result yet')}*")
        lines.append(f"“{clip(item.claim, 200)}”\n{clip(item.headline, 360)}")
    else:
        lines.append(f"*{len(findings)} claims checked*")
        for number, item in enumerate(findings, start=1):
            label = VERDICT_HEADLINES.get(item.status, "No result yet")
            lines.append(
                f"{number}. *{label}*\n“{clip(item.claim, 110)}”\n{clip(item.headline, 150)}"
            )

    details = []
    if source_names:
        details.append("*Sources:* " + ", ".join(source_names[:3]))
    if len(findings) == 1:
        sure = _how_sure(findings[0].confidence)
        if sure:
            details.append(sure)
    if details:
        lines.append("\n".join(details))
    if findings:
        lines.append(
            "Tap *Sources* for the links and quotes, or *Share* to forward it."
            if source_names
            else "Tap *Share* to forward it."
        )
    message = fit("\n\n".join(lines), reference)
    if len(message) > INTERACTIVE_BODY_LIMIT and findings:
        # Too long for a message with buttons: keep the verdicts, drop the detail.
        lines = [line for line in lines if not line.startswith(("*Sources:*", "Tap "))]
        footer = f"\n\n_Ref: {reference}_"
        body = _truncate("\n\n".join(lines), INTERACTIVE_BODY_LIMIT - len(footer))
        message = body + footer
    return message


def sources_message(entries: list[tuple[str, str, str]], *, reference: str) -> str:
    """entries: (source name, link, quoted passage)."""
    if not entries:
        return fit("I don’t have source links saved for this check.", reference)
    lines = ["*Sources for this check*"]
    for number, (name, url, passage) in enumerate(entries, start=1):
        quote = " ".join(passage.split())
        block = f"*{number}. {name}*"
        if quote:
            block += f"\n_“{clip(quote, 220)}”_"
        lines.append(f"{block}\n{url}")
    return fit("\n\n".join(lines), reference)


def share_card(
    findings: list[tuple[str, str, str]],
    *,
    source_names: list[str],
    reference: str,
    whatsapp_number: str | None,
    site_url: str | None,
) -> str:
    """A self-contained message made to be forwarded: no commands, no buttons.

    findings: (claim, status, plain reason).
    """
    lines = ["*Agent Zero fact-check*"]
    for claim, status, why in findings[:3]:
        label = VERDICT_HEADLINES.get(status, "No result yet")
        lines.append(f"Claim: “{clip(claim, 160)}”\nResult: *{label}*. {clip(why, 200)}")
    if source_names:
        lines.append("Sources: " + ", ".join(source_names[:3]))
    invite = []
    if whatsapp_number:
        digits = "".join(ch for ch in whatsapp_number if ch.isdigit())
        invite.append(f"Check a claim yourself on WhatsApp: https://wa.me/{digits}")
    if site_url:
        invite.append(f"Learn more: {site_url.rstrip('/')}")
    if invite:
        lines.append("\n".join(invite))
    lines.append(f"Ref: {reference}")
    return _truncate("\n\n".join(lines), MAX_MESSAGE)


def no_result_yet() -> str:
    return (
        "That check doesn’t have a result yet. Reply *STATUS* to see how it’s going, "
        "or *HISTORY* to see your checks."
    )


def new_check_prompt() -> str:
    return "Send me the next claim, link or screenshot you want checked."


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
        "• *SOURCES*: the links and quotes behind it\n"
        "• *SHARE*: a short version to forward to a group\n"
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


# Questions about Agent Zero itself. Answered from this fixed profile, never by a web
# search or the AI model, so the bot cannot describe itself as ChatGPT or another product.
_SELF_QUESTION = re.compile(
    r"\b("
    r"who\s+(are|r)\s+(you|u)|what\s+(are|r)\s+(you|u)\b(?!\s+(doing|saying|checking))"
    r"|who\s+(built|made|created|developed|designed|owns|runs|trained|programmed)\s+(you|u|this|agent\s*(zero|0))"
    r"|who\s+is\s+behind\s+(you|this|agent\s*(zero|0))"
    r"|are\s+(you|u)\s+(chat\s*gpt|gpt|open\s*ai|gemini|claude|an?\s+(ai|bot|robot)|a\s+human|human|real)"
    r"|(what|which)\s+(ai|model|llm|gpt)\b.*\b(you|agent\s*(zero|0))"
    r"|what\s+powers\s+(you|agent\s*(zero|0))|tell\s+me\s+about\s+(yourself|agent\s*(zero|0))"
    r"|wewe\s+ni\s+nani|nani\s+(alikutengeneza|aliyekutengeneza|amekutengeneza)"
    r"|umetengenezwa\s+na\s+nani|wewe\s+ni\s+(chatgpt|gpt|roboti|binadamu)"
    r")",
    re.IGNORECASE,
)


def is_question_about_agent_zero(text: str) -> bool:
    return bool(_SELF_QUESTION.search(" ".join(text.split())))


def about_agent_zero(builder: str = "Sinaps Technology", site_url: str | None = None) -> str:
    lines = [
        f"I’m *Agent Zero*, a fact-checking assistant built by {builder}, a technology "
        "company in Nairobi, Kenya.",
        "I check claims against public sources and tell you plainly what holds up, what "
        "doesn’t, and what I couldn’t confirm.",
        "Inside, I use AI models, including models from OpenAI, to read sources and draft "
        "explanations. I’m not ChatGPT: Agent Zero’s own system plans each check, finds and "
        "reads the sources, and its rules decide the result. Every result links to its sources.",
    ]
    if site_url:
        lines.append(f"More about how I work: {site_url.rstrip('/')}/methodology")
    lines.append("Send me a claim or a link whenever you’re ready.")
    return "\n\n".join(lines)
