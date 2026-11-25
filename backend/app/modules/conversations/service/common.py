"""Shared limits, markers and the configured owner."""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from uuid import UUID

from app.modules.conversations import messages as copy
from app.modules.investigations.service import (
    DEV_USER_ID,
)

logger = logging.getLogger(__name__)


MAX_MESSAGE_CHARS = 20_000


INBOUND_EVENT_PROVIDER = "meta_whatsapp_cloud"


INBOUND_EVENT_LEASE = timedelta(minutes=3)


_UNRESOLVED_CLAIM_PATTERN = re.compile(
    r"(?:\[[^\]\n]{1,100}\]|\b(?:tbd|todo|placeholder|lorem ipsum)\b|"
    r"\b(?:particular|specific|certain|unknown|unspecified|some)\s+"
    r"(?:date|year|time|person|place|number|amount|event)\b)",
    re.IGNORECASE,
)


_FAILURE_COPY = copy.FAILURE_REASONS


_EDIT_PROMPT = "Send the corrected claim or missing detail."


_CLARIFICATION_MARKER = "\nClarification: "


# After this many unanswered clarification rounds, stop asking and offer to check the
# user's own words, so the chat never loops on the same question.
MAX_CLARIFICATION_ROUNDS = 2


_CHECK_AS_IS = frozenset({"check as is", "check as written", "check it as is", "check my words"})


_RUN_FULL_CHECK = frozenset(
    {
        "check",
        "check it",
        "check this",
        "full check",
        "investigate",
        "investigate it",
        "yes",
        "yes please",
        "yes check",
        "go ahead",
        "ndiyo",
        "ndio",
        "chunguza",
    }
)


_QUICK_ANSWER_MARKER = "(not a full investigation)"


class ConversationTurnInProgress(RuntimeError):
    """A prior delivery of this inbound event is still being processed."""


def _owner_id(settings) -> UUID:
    return settings.whatsapp_owner_id or DEV_USER_ID


# Typed phrases that unambiguously approve the preview currently on screen. Deliberately
# excludes "ok" and "sawa", which people also use to acknowledge a message. Anything that
# adds a condition ("yes but change the date") is not a confirmation.
_STRICT_CONFIRMATIONS = frozenset(
    {
        "yes",
        "yes please",
        "yes submit",
        "yes submit it",
        "yes go ahead",
        "go ahead",
        "go ahead and investigate",
        "submit",
        "submit claim",
        "confirm",
        "start",
        "proceed",
        "ndiyo",
        "ndio",
        "endelea",
        "tuma",
        "anza",
    }
)


# Time budget for one WhatsApp turn. Turns run after Meta is acknowledged, so they are not
# limited by the 18-second proxy; the user sees "typing..." meanwhile.
TURN_BUDGET_SECONDS = 50.0
CLASSIFY_BUDGET_SECONDS = 25.0
ANSWER_BUDGET_SECONDS = 25.0
# A sourced quick answer is only started if at least this much time is left.
MIN_ANSWER_SECONDS = 6.0
