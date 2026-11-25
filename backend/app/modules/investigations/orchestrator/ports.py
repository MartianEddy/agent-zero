"""Outside dependencies used by the pipeline stages.

Stages call ports.<name>(...) so a test can replace a dependency once, here, and every
stage sees the replacement.
"""

from time import monotonic

from app.core.config import get_settings
from app.modules.investigations.investigator import (
    ModelGateway,
)
from app.modules.investigations.media_analysis import inspect_media
from app.modules.investigations.usage import (
    add_limitation,
)
from app.modules.sources.exa_search import search_exa
from app.modules.sources.openai_web_search import search_openai_web
from app.modules.sources.retrieval import (
    read_public_page,
)
from app.modules.sources.settled_fact import lookup_settled_fact
from app.storage.s3 import get_private_object, put_private_object

__all__ = [
    "ModelGateway",
    "add_limitation",
    "get_private_object",
    "get_settings",
    "inspect_media",
    "lookup_settled_fact",
    "monotonic",
    "put_private_object",
    "read_public_page",
    "search_exa",
    "search_openai_web",
]
