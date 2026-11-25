"""Research plan: claims, search queries, freshness and lane widening."""

from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.investigations.investigator import (
    ResearchPlan,
)
from app.modules.investigations.models import (
    Claim,
    ClaimEvidence,
    Evidence,
    Investigation,
    SearchTrace,
    Source,
)
from app.modules.investigations.orchestrator import common, ports
from app.modules.investigations.triage import normalize_claim_text
from app.modules.sources.urls import normalize_source_url


def _persist_plan(
    session: Session,
    investigation: Investigation,
    plan: ResearchPlan,
    *,
    allow_unassociated_queries: bool = False,
) -> None:
    settings = ports.get_settings()
    claims = list(session.scalars(select(Claim).where(Claim.investigation_id == investigation.id)))
    extracted_now = not claims
    if extracted_now:
        for candidate in plan.claims[: settings.max_claims_per_investigation]:
            text = " ".join(candidate.text.split())
            if not text:
                continue
            normalized = normalize_claim_text(text)
            claims.append(
                Claim(
                    investigation_id=investigation.id,
                    text=text,
                    normalized_text=normalized,
                    claim_type=candidate.claim_type,
                    needs_deep_investigation=candidate.claim_type != "SETTLED_FACT",
                )
            )
        session.add_all(claims)
        session.flush()
        common._audit(session, investigation.id, "CLAIMS_EXTRACTED", {"count": len(claims)})
    traces = list(
        session.scalars(select(SearchTrace).where(SearchTrace.investigation_id == investigation.id))
    )
    already_planned = {(trace.query, trace.provider) for trace in traces}
    queries: list[tuple[str, dict[str, object]]] = []
    seen_query_texts: set[str] = set()
    for planned_query in plan.queries:
        if isinstance(planned_query, str):
            query_text = planned_query
            freshness = "BALANCED"
            route_metadata: dict[str, object] = {
                "topic": "general",
                "jurisdiction": [],
                "source_lane": "PRIMARY",
                "widening_reason": "",
                "claim_index": 0,
                "freshness": freshness,
            }
        else:
            query_text = planned_query.text
            freshness = planned_query.freshness
            route_metadata = {
                "topic": planned_query.topic,
                "jurisdiction": planned_query.jurisdiction,
                "source_lane": planned_query.source_lane,
                "widening_reason": planned_query.widening_reason,
                "claim_index": planned_query.claim_index,
                "freshness": planned_query.freshness,
            }
        claim_index = int(route_metadata.get("claim_index", 0))
        if not 0 <= claim_index < len(claims) and not (allow_unassociated_queries and not claims):
            continue
        if claims and claims[claim_index].claim_type == "OPINION_OR_PREDICTION":
            continue
        normalized_query = _query_for_freshness(query_text, freshness)[:500]
        if normalized_query and normalized_query not in seen_query_texts:
            queries.append((normalized_query, route_metadata))
            seen_query_texts.add(normalized_query)
    # Every checkable claim gets a primary-source pass, even if the planner only
    # proposed secondary/reporting queries. Secondary lanes remain additional.
    primary_claim_indices = {
        int(route.get("claim_index", 0))
        for _, route in queries
        if route.get("source_lane") == "PRIMARY"
    }
    for claim_index, claim in enumerate(claims[: settings.max_claims_per_investigation]):
        if claim.claim_type == "OPINION_OR_PREDICTION":
            continue
        if claim_index in primary_claim_indices:
            continue
        contextual_route = next(
            (route for _, route in queries if int(route.get("claim_index", 0)) == claim_index),
            {},
        )
        freshness = str(contextual_route.get("freshness", "BALANCED"))
        primary_query = _query_for_freshness(
            f"{claim.text[:360]} original official records and primary sources",
            freshness,
        )[:500]
        queries.append(
            (
                primary_query,
                {
                    **contextual_route,
                    "claim_index": claim_index,
                    "freshness": freshness,
                    "source_lane": "PRIMARY",
                    "widening_reason": "Required first pass for this claim before secondary sources.",
                },
            )
        )
    # Reserve budget for historical context beside recent coverage. Search results
    # from the background lane never substitute for date-checked recent reporting.
    current_queries = [
        item for item in queries if common.CURRENT_QUERY_MARKER in item[0].casefold()
    ]
    other_queries = [item for item in queries if item not in current_queries]
    queries = list(current_queries)
    if current_queries and len(queries) < settings.max_search_queries:
        current_query, current_route = current_queries[0]
        base_query = current_query.split(
            " latest official updates and recent independent reporting", 1
        )[0]
        historical_query = (
            base_query[:330]
            + " original historical records and background context; "
            + common.HISTORICAL_QUERY_MARKER
        )[:500]
        historical_route = {**current_route, "source_lane": "PRIMARY"}
        if (historical_query, "EXA") not in already_planned:
            queries.append((historical_query, historical_route))
    queries.extend(other_queries)
    lane_order = {"PRIMARY": 0, "REFERENCE_REPORTING": 1, "FACT_CHECK": 2, "SOCIAL": 3}
    queries.sort(key=lambda item: lane_order.get(str(item[1].get("source_lane")), 0))
    if not queries and not traces:
        queries = [
            (
                claim.text[:500],
                {
                    "topic": "general",
                    "jurisdiction": [],
                    "source_lane": "PRIMARY",
                    "widening_reason": "",
                    "claim_index": index,
                    "freshness": "BALANCED",
                },
            )
            for index, claim in enumerate(claims)
            if claim.claim_type != "OPINION_OR_PREDICTION"
        ]
    for query, route_metadata in queries[: settings.max_search_queries]:
        for provider in ("EXA", "OPENAI_WEB_SEARCH"):
            if (query, provider) in already_planned:
                continue
            session.add(
                SearchTrace(
                    investigation_id=investigation.id,
                    provider=provider,
                    action="planned",
                    query=query,
                    route_metadata=route_metadata,
                    sources=[],
                    citations=[],
                )
            )
            already_planned.add((query, provider))
    session.commit()


def _query_for_freshness(query: str, freshness: str) -> str:
    """Turn Luna's temporal classification into explicit provider search intent."""
    query = " ".join(query.split())
    if freshness == "CURRENT":
        if "prioritize current information and dated sources" in query.casefold():
            return query[:500]
        query = query[:350]
        query += (
            " latest official updates and recent independent reporting; prioritize current "
            "information and dated sources"
        )
    elif freshness == "BALANCED":
        if (
            "original records and recent reporting that checks the current context"
            in query.casefold()
        ):
            return query[:500]
        query = query[:400]
        query += " original records and recent reporting that checks the current context"
    elif freshness == "HISTORICAL":
        if common.HISTORICAL_QUERY_MARKER in query.casefold():
            return query[:500]
        query = query[:400]
        query += " " + common.HISTORICAL_QUERY_MARKER
    return query[:500]


def _claims_needing_independent_sources(session: Session, investigation: Investigation) -> set[int]:
    """Return zero-based claim indexes with fewer than two independent evidence groups."""
    claims = list(
        session.scalars(
            select(Claim)
            .where(Claim.investigation_id == investigation.id)
            .order_by(Claim.created_at, Claim.id)
        )
    )
    indexes: set[int] = set()
    for index, claim in enumerate(claims):
        groups = set(
            session.scalars(
                select(Evidence.independence_group_id)
                .select_from(ClaimEvidence)
                .join(Evidence, ClaimEvidence.evidence_id == Evidence.id)
                .join(Source, Evidence.source_id == Source.id)
                .where(
                    ClaimEvidence.claim_id == claim.id,
                    Evidence.investigation_id == investigation.id,
                    Evidence.independence_group_id != "unknown",
                    Evidence.excerpt_validated.is_(True),
                    Source.retrieval_status == "RETRIEVED",
                    Source.source_role != "DERIVATIVE",
                )
            )
        )
        if len(groups) < 2:
            indexes.add(index)
    return indexes


def _plan_widened_queries(
    session: Session,
    investigation: Investigation,
    *,
    source_lane: str,
    claim_indices: set[int],
) -> None:
    """Add focused secondary queries only for claims with an evidence coverage gap."""
    if not claim_indices:
        return
    settings = ports.get_settings()
    claims = list(
        session.scalars(
            select(Claim)
            .where(Claim.investigation_id == investigation.id)
            .order_by(Claim.created_at, Claim.id)
        )
    )
    traces = list(
        session.scalars(select(SearchTrace).where(SearchTrace.investigation_id == investigation.id))
    )
    distinct_queries = {trace.query for trace in traces if trace.query}
    lane_queries = {
        (
            str((trace.route_metadata or {}).get("source_lane", "PRIMARY")),
            int((trace.route_metadata or {}).get("claim_index", 0)),
        )
        for trace in traces
        if trace.query
    }
    for claim_index in sorted(claim_indices):
        if claim_index >= len(claims) or (source_lane, claim_index) in lane_queries:
            continue
        if len(distinct_queries) >= settings.max_search_queries:
            ports.add_limitation(
                session,
                investigation.id,
                "The search budget did not allow another source lane for every claim.",
            )
            break
        claim = claims[claim_index]
        primary_trace = next(
            (
                trace
                for trace in traces
                if str((trace.route_metadata or {}).get("source_lane", "PRIMARY")) == "PRIMARY"
                and int((trace.route_metadata or {}).get("claim_index", 0)) == claim_index
            ),
            None,
        )
        primary_route = primary_trace.route_metadata if primary_trace else {}
        freshness = str(primary_route.get("freshness", "BALANCED"))
        query_seed = (
            f"{claim.text[:340]} independent established reporting and references"
            if source_lane == "REFERENCE_REPORTING"
            else f"published fact checks assessing: {claim.text[:350]}"
        )
        query = _query_for_freshness(query_seed, freshness)[:500]
        route_metadata = {
            "claim_index": claim_index,
            "topic": primary_route.get("topic", "general"),
            "jurisdiction": primary_route.get("jurisdiction", []),
            "freshness": freshness,
            "source_lane": source_lane,
            "widening_reason": (
                "Primary-source pass found fewer than two distinct retrieved source domains."
                if source_lane == "REFERENCE_REPORTING"
                else "Independent reporting pass still lacks two retrieved source domains."
            ),
        }
        for provider in ("EXA", "OPENAI_WEB_SEARCH"):
            session.add(
                SearchTrace(
                    investigation_id=investigation.id,
                    provider=provider,
                    action="planned",
                    query=query,
                    route_metadata=route_metadata,
                    sources=[],
                    citations=[],
                )
            )
        distinct_queries.add(query)
        lane_queries.add((source_lane, claim_index))
    session.commit()


def _mark_routes_not_needed(
    session: Session,
    investigation: Investigation,
    *,
    source_lanes: set[str],
    claim_indices: set[int] | None = None,
) -> None:
    traces = list(
        session.scalars(
            select(SearchTrace).where(
                SearchTrace.investigation_id == investigation.id,
                SearchTrace.action == "planned",
            )
        )
    )
    for trace in traces:
        route = trace.route_metadata or {}
        if str(route.get("source_lane", "PRIMARY")) not in source_lanes:
            continue
        if claim_indices is not None and int(route.get("claim_index", 0)) not in claim_indices:
            continue
        trace.action = "not_needed"
    session.commit()


def _load_plan(session: Session, investigation_id: UUID) -> ResearchPlan:
    claims = list(session.scalars(select(Claim).where(Claim.investigation_id == investigation_id)))
    planned = list(
        session.scalars(
            select(SearchTrace).where(
                SearchTrace.investigation_id == investigation_id,
                SearchTrace.action.in_(["planned", "unavailable", "search"]),
            )
        )
    )
    from app.modules.investigations.investigator import PlannedClaim, PlannedQuery

    planned_queries = []
    seen_queries: set[str] = set()
    for item in planned:
        query = item.query or ""
        if query in seen_queries:
            continue
        seen_queries.add(query)
        freshness = (
            "CURRENT"
            if common.CURRENT_QUERY_MARKER in query.casefold()
            else "BALANCED"
            if "original records and recent reporting that checks the current context"
            in query.casefold()
            else "HISTORICAL"
        )
        route = item.route_metadata or {}
        planned_queries.append(
            PlannedQuery(
                text=query[:500],
                freshness=freshness,
                topic=str(route.get("topic") or "general"),
                jurisdiction=[
                    str(value) for value in route.get("jurisdiction", []) if isinstance(value, str)
                ][:5],
                source_lane=route.get("source_lane", "PRIMARY"),
                claim_index=int(route.get("claim_index", 0)),
                widening_reason=str(route.get("widening_reason") or "")[:240],
            )
        )

    return ResearchPlan(
        claims=[
            PlannedClaim(
                text=item.text,
                claim_type=(
                    item.claim_type
                    if item.claim_type
                    in {
                        "SETTLED_FACT",
                        "CHECKABLE_EVENT",
                        "STATISTICAL",
                        "MEDIA_CLAIM",
                        "CONTESTED",
                        "OPINION_OR_PREDICTION",
                    }
                    else "CHECKABLE_EVENT"
                ),
            )
            for item in claims
        ],
        queries=planned_queries,
    )


def _url_only_fallback_plan(submitted_url: str) -> ResearchPlan:
    """Search for a failed-to-retrieve URL without inventing its article claims."""
    try:
        normalized = normalize_source_url(submitted_url)
    except ValueError:
        return ResearchPlan()
    parsed = urlsplit(normalized)
    slug = " ".join(part for part in parsed.path.rsplit("/", 1)[-1].replace("-", " ").split())
    query = " ".join(part for part in (f"site:{parsed.hostname}", slug) if part)[:500]
    return ResearchPlan(queries=[query] if query else [])
