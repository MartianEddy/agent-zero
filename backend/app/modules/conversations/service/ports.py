"""Outside dependencies used by the conversation modules.

Modules call ports.<name>(...) so a test can replace a dependency once, here.
"""

from __future__ import annotations

from fastapi.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.modules.investigations.investigator import ModelGateway
from app.modules.investigations.service import (
    InvestigationService,
    queue_investigation_retry,
)

__all__ = [
    "InvestigationService",
    "ModelGateway",
    "get_settings",
    "queue_investigation_retry",
    "run_in_threadpool",
]
