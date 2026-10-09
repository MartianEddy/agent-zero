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
