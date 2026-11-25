"""Run planned searches and read the most relevant candidate pages."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.investigations.models import (
    Claim,
    Investigation,
    SearchTrace,
    Source,
    utcnow,
)
from app.modules.investigations.orchestrator import common, ports, sourcing
from app.modules.sources.exa_search import ExaSearchError
from app.modules.sources.openai_web_search import OpenAIWebSearchError
from app.modules.sources.source_prioritization import prioritize_sources
from app.modules.sources.urls import normalize_source_url


def _relevance_terms(value: str) -> set[str]:
    import re

    stop = {"this", "that", "with", "from", "image", "claim", "media", "the", "and", "for"}
    terms = {word for word in re.findall(r"[a-z0-9]{4,}", value.casefold()) if word not in stop}
    if re.search(r"\bai\b", value.casefold()):
        terms.add("ai")
    return terms


def _execute_searches(
    session: Session,
    investigation: Investigation,
    *,
    source_lanes: set[str] | None = None,
    claim_indices: set[int] | None = None,
    case_deadline: float | None = None,
) -> None:
    settings = ports.get_settings()
    key = settings.exa_api_key.get_secret_value().strip() if settings.exa_api_key else ""
    traces = list(
        session.scalars(
            select(SearchTrace)
            .where(
                SearchTrace.investigation_id == investigation.id,
                SearchTrace.action.in_(["planned", "unavailable"]),
            )
            .order_by(SearchTrace.created_at, SearchTrace.id)
        )
    )
    lane_order = {"PRIMARY": 0, "REFERENCE_REPORTING": 1, "FACT_CHECK": 2, "SOCIAL": 3}
    if source_lanes is not None:
        traces = [
            trace
            for trace in traces
            if str((trace.route_metadata or {}).get("source_lane", "PRIMARY")) in source_lanes
            and (
                claim_indices is None
                or int((trace.route_metadata or {}).get("claim_index", 0)) in claim_indices
            )
        ]
    traces.sort(
        key=lambda trace: lane_order.get(
            str((trace.route_metadata or {}).get("source_lane", "PRIMARY")), 0
        )
    )
    max_calls = settings.max_search_queries * 2
    for trace in traces[:max_calls]:
        remaining_seconds = case_deadline - ports.monotonic() if case_deadline is not None else 30.0
        if remaining_seconds <= 0:
            trace.action = "deadline_exceeded"
            session.commit()
            ports.add_limitation(
                session, investigation.id, "Case deadline reached; remaining search steps were cut."
            )
            continue
        provider = trace.provider or "EXA"
        lane = str((trace.route_metadata or {}).get("source_lane", "PRIMARY"))
        if lane == "SOCIAL":
            trace.action = "unavailable"
            session.commit()
            ports.add_limitation(
                session,
                investigation.id,
                "Direct social-platform search is not configured for this investigation.",
            )
            continue
        openai_key = (
            getattr(settings, "openai_api_key", None).get_secret_value().strip()
            if getattr(settings, "openai_api_key", None)
            else ""
        )
        if (provider == "EXA" and not key) or (provider == "OPENAI_WEB_SEARCH" and not openai_key):
            trace.action = "unavailable"
            trace.created_at = utcnow()
            session.commit()
            ports.add_limitation(
                session,
                investigation.id,
                f"{provider.replace('_', ' ').title()} search is not configured.",
            )
            continue
        query_context = (
            f"Topic: {(trace.route_metadata or {}).get('topic', 'general')}. "
            f"Jurisdiction: {', '.join((trace.route_metadata or {}).get('jurisdiction', []))}. "
            f"Source lane: {lane}. "
            f"Why this lane: {(trace.route_metadata or {}).get('widening_reason', '')}. "
            f"Query: {trace.query or ''}"
        )
        usage = common._usage(session, investigation.id)
        if usage.search_calls >= max_calls:
            trace.action = "budget_exceeded"
            session.commit()
            ports.add_limitation(session, investigation.id, "Search-query budget reached.")
            continue
        usage.search_calls += 1
        trace.created_at = utcnow()
        session.commit()
        try:
            current_lane = common.CURRENT_QUERY_MARKER in (trace.query or "").casefold()
            search_now = utcnow()
            date_filters: dict[str, str] = {}
            if current_lane:
                date_filters = {
                    "start_published_date": (search_now - timedelta(days=30)).date().isoformat(),
                    "end_published_date": search_now.date().isoformat(),
                }
            if provider == "EXA":
                response = ports.search_exa(
                    api_key=key,
                    query=query_context,
                    num_results=settings.max_search_results_per_query,
                    timeout_seconds=remaining_seconds,
                    **date_filters,
                )
                provider_results = response.results
                provider_citations = []
                request_id = response.request_id
            elif provider == "OPENAI_WEB_SEARCH":
                response = ports.search_openai_web(
                    api_key=openai_key,
                    model=settings.openai_model,
                    query=query_context,
                    timeout_seconds=remaining_seconds,
                )
                provider_results = response.results
                provider_citations = response.citations
                request_id = response.request_id
            else:
                trace.action = "unavailable"
                session.commit()
                continue
        except (ExaSearchError, OpenAIWebSearchError):
            trace.action = "error"
            trace.created_at = utcnow()
            session.commit()
            ports.add_limitation(
                session,
                investigation.id,
                f"{provider.replace('_', ' ').title()} search could not be completed.",
            )
            continue
        normalized_results: list[dict[str, object]] = []
        for item in provider_results[: settings.max_search_results_per_query]:
            raw_url = item.get("url")
            if not isinstance(raw_url, str):
                continue
            try:
                url = normalize_source_url(raw_url)
            except ValueError:
                continue
            normalized_item = {**item, "url": url}
            if not any(existing["url"] == url for existing in normalized_results):
                normalized_results.append(normalized_item)
        trace.action = "search" if normalized_results else "empty"
        trace.call_reference = request_id
        trace.sources = normalized_results
        trace.citations = provider_citations
        trace.created_at = utcnow()
        for item in normalized_results:
            sourcing._create_source_candidate(
                session,
                investigation,
                url=str(item["url"]),
                title=str(item.get("title") or ""),
                publisher=str(item.get("author") or common._source_domain(str(item["url"])) or ""),
                published_at=common._valid_publication_date(item.get("publishedDate")),
                discovery_method=provider,
                trace_id=trace.id,
            )
        common._audit(
            session,
            investigation.id,
            "SEARCH_COMPLETED",
            {
                "provider": provider,
                "query": trace.query,
                "route": trace.route_metadata,
                "result_count": len(normalized_results),
            },
        )
        session.commit()


def _retrieve_candidates(
    session: Session,
    investigation: Investigation,
    *,
    source_lanes: set[str] | None = None,
    retrieval_cap: int | None = None,
    case_deadline: float | None = None,
) -> dict[UUID, str]:
    settings = ports.get_settings()
    sources = list(
        session.scalars(
            select(Source).where(Source.investigation_id == investigation.id).order_by(Source.id)
        )
    )
    claims = [
        claim.text
        for claim in session.scalars(
            select(Claim).where(Claim.investigation_id == investigation.id)
        )
    ]
    traces = list(
        session.scalars(select(SearchTrace).where(SearchTrace.investigation_id == investigation.id))
    )
    lane_by_trace = {
        trace.id: str((trace.route_metadata or {}).get("source_lane", "PRIMARY"))
        for trace in traces
    }
    context_by_source: dict[UUID, str] = {}
    for source in sources:
        matching_traces = [
            trace
            for trace in traces
            if trace.id == source.discovery_trace_id
            or any(
                isinstance(item, dict) and item.get("url") == source.url for item in trace.sources
            )
        ]
        context_parts: list[str] = []
        for trace in matching_traces:
            if trace.query:
                context_parts.append(trace.query)
            for item in trace.sources:
                if not isinstance(item, dict) or item.get("url") != source.url:
                    continue
                for key in ("title", "highlights", "author"):
                    value = item.get(key)
                    if isinstance(value, str):
                        context_parts.append(value)
                    elif isinstance(value, list):
                        context_parts.extend(str(part) for part in value if part)
        context_by_source[source.id] = " ".join(context_parts)
    sources = prioritize_sources(sources, claims, context_by_source=context_by_source)
    retrieved: dict[UUID, str] = {}
    for source in sources:
        remaining_seconds = case_deadline - ports.monotonic() if case_deadline is not None else 12.0
        if remaining_seconds <= 0:
            source.retrieval_status = "NOT_ATTEMPTED_DEADLINE"
            session.commit()
            ports.add_limitation(
                session,
                investigation.id,
                "Case deadline reached; remaining source retrieval steps were cut.",
            )
            continue
        if source_lanes is not None and source.discovery_trace_id:
            if lane_by_trace.get(source.discovery_trace_id, "PRIMARY") not in source_lanes:
                continue
        if source.retrieval_status == "RETRIEVED" and source.content_storage_key:
            try:
                text = ports.get_private_object(key=source.content_storage_key).decode(
                    "utf-8", errors="replace"
                )
                retrieved[source.id] = text[
                    : getattr(settings, "max_retrieved_document_chars", 60_000)
                ]
            except Exception:
                source.retrieval_status = "FAILED"
                session.commit()
            continue
        if source.retrieval_status not in {"CANDIDATE", "SUBMITTED", "NOT_ENABLED"}:
            continue
        current_count = common._usage(session, investigation.id).sources_retrieved
        effective_retrieval_cap = min(
            settings.max_retrieved_sources,
            retrieval_cap if retrieval_cap is not None else settings.max_retrieved_sources,
        )
        if current_count >= effective_retrieval_cap:
            source.retrieval_status = "NOT_ATTEMPTED_LIMIT"
            session.commit()
            ports.add_limitation(session, investigation.id, "Source retrieval limit reached.")
            continue
        text = (
            sourcing._save_retrieved_source(
                session, investigation, source, timeout_seconds=remaining_seconds
            )
            if case_deadline is not None
            else sourcing._save_retrieved_source(session, investigation, source)
        )
        if text is not None:
            retrieved[source.id] = text[: getattr(settings, "max_retrieved_document_chars", 60_000)]
    return retrieved
