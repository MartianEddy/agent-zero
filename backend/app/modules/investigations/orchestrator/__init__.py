"""Investigation pipeline, split into stages.

process_investigation (pipeline.py) runs the stages in order: plan claims, search, read
sources, record evidence, assess, and write the brief. Outside dependencies (settings,
storage, search, page reader, model gateway, clock) are reached through ports.py so tests
patch each one in a single place. Stages call each other as module.function so each
internal function also has one patch target: the module that defines it.
"""

from app.modules.investigations.orchestrator.common import (  # noqa: F401
    _WHATSAPP_NOTIFICATION_NAMESPACE,
    ALLOWED_FINDING_STATUSES,
    ALLOWED_RELATIONSHIPS,
    CURRENT_QUERY_MARKER,
    HISTORICAL_QUERY_MARKER,
    MAX_MEDIA_EVIDENCE_CHARS,
    MEDIA_PACKET_METHODS,
    USER_FAILURE_MESSAGE,
    MediaStorageError,
    _audit,
    _get_media_object,
    _original_media_assets,
    _relative_date_context,
    _source_domain,
    _stage,
    _usage,
    _valid_publication_date,
    logger,
)
from app.modules.investigations.orchestrator.evidence_review import (  # noqa: F401
    _detect_source_relationships,
    _evidence_packet,
    _has_claim_linked_evidence,
    _persist_evidence,
)
from app.modules.investigations.orchestrator.findings_stage import (  # noqa: F401
    _build_brief,
    _create_unverified_findings,
    _persist_findings,
    _record_deterministic_finding,
)
from app.modules.investigations.orchestrator.media_review import (  # noqa: F401
    _link_unclaimed_media_evidence,
    _load_or_inspect_media,
    _media_packet_excerpt,
    _persist_visual_observations,
)
from app.modules.investigations.orchestrator.notifications import (  # noqa: F401
    _queue_whatsapp_result_notification,
)
from app.modules.investigations.orchestrator.pipeline import (  # noqa: F401
    _run_widening_lane,
    process_investigation,
)
from app.modules.investigations.orchestrator.planning import (  # noqa: F401
    _claims_needing_independent_sources,
    _load_plan,
    _mark_routes_not_needed,
    _persist_plan,
    _plan_widened_queries,
    _query_for_freshness,
    _url_only_fallback_plan,
)
from app.modules.investigations.orchestrator.search_stage import (  # noqa: F401
    _execute_searches,
    _relevance_terms,
    _retrieve_candidates,
)
from app.modules.investigations.orchestrator.settled_facts import (  # noqa: F401
    _assess_settled_claims,
    _persist_settled_reference_evidence,
    _run_fast_path_claims,
    _settled_claim_packet,
    _settled_claims_packet,
)
from app.modules.investigations.orchestrator.sourcing import (  # noqa: F401
    _create_source_candidate,
    _ensure_submitted_url_source,
    _normalized_existing_sources,
    _save_retrieved_source,
    _submitted_source_prompt,
)
