"""Strict claim-triage vocabulary shared by the model and HTTP contracts."""

from typing import Literal

ClaimType = Literal[
    "SETTLED_FACT",
    "CHECKABLE_EVENT",
    "STATISTICAL",
    "MEDIA_CLAIM",
    "CONTESTED",
    "OPINION_OR_PREDICTION",
]


def normalize_claim_text(value: str) -> str:
    """Return the canonical comparison form; never trust an LLM-supplied form."""
    return " ".join(value.casefold().split())
