"""Bounded application-owned investigation workflow with durable stage results."""

import hashlib
import json
import logging
import re
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.investigation import InputType, InvestigationStatus, validate_transition
from app.modules.investigations.image_safety import ImageValidationError
from app.modules.investigations.investigator import (
    EvidenceReasoning,
    ModelGateway,
    ModelInvocationFailed,
    ResearchPlan,
    VisualAnalysis,
)
from app.modules.investigations.media.analyzers import analyze_image_assets
from app.modules.investigations.media_analysis import inspect_media
from app.modules.investigations.models import (
    AuditEvent,
    Claim,
    ClaimEvidence,
    Evidence,
    Finding,
    FindingEvidence,
    Investigation,
    InvestigationUsage,
    MediaAsset,
    ProcessingJob,
    SearchTrace,
    Source,
    SourceRelationship,
    Submission,
    VerificationBrief,
    utcnow,
)
from app.modules.investigations.provider_errors import FailureCategory
from app.modules.investigations.summary import finding_result_summary
from app.modules.investigations.usage import (
    ModelCallBudgetExceeded,
    add_limitation,
    get_or_create_usage,
)
from app.modules.sources.evidence_extraction import (
    extract_candidate_excerpts,
    select_claim_relevant_regions,
)
from app.modules.sources.exa_search import ExaSearchError, search_exa
from app.modules.sources.registry import classify_source, role_for_claim
from app.modules.sources.retrieval import (
    SourceRetrievalError,
    excerpt_is_present,
    read_public_page,
)
from app.modules.sources.source_prioritization import prioritize_sources
from app.modules.sources.urls import extract_markdown_link_urls, normalize_source_url
from app.storage.s3 import get_private_object, put_private_object

logger = logging.getLogger(__name__)
ALLOWED_RELATIONSHIPS = {"SUPPORTS", "CONTRADICTS", "CONTEXTUALIZES", "MENTIONS", "UNKNOWN"}
ALLOWED_FINDING_STATUSES = {"SUPPORTED", "CONTRADICTED", "UNVERIFIED", "INCONCLUSIVE"}
MEDIA_PACKET_METHODS = {
    "MEDIA_PROVENANCE",
    "MEDIA_TECHNICAL_METADATA",
    "MEDIA_METADATA",
    "MEDIA_VISUAL_OBSERVATION",
}
MAX_MEDIA_EVIDENCE_CHARS = 6_000
USER_FAILURE_MESSAGE = (
    "Investigation paused. Agent 0 could not complete the analysis. "
    "Evidence collected so far has been preserved. "
    "No unsupported verification finding was produced."
)


class MediaStorageError(RuntimeError):
    """Private object storage failed during media processing."""


def _get_media_object(key: str) -> bytes:
    try:
        return get_private_object(key=key)
    except Exception as exc:
        raise MediaStorageError("Media object could not be read") from exc


def _original_media_assets(session: Session, investigation_id: UUID) -> list[MediaAsset]:
    return list(
        session.scalars(
            select(MediaAsset).where(
                MediaAsset.investigation_id == investigation_id,
                MediaAsset.asset_role == "ORIGINAL",
            )
        )
    )


def _stage(session: Session, investigation: Investigation, stage: InvestigationStatus) -> None:
    if investigation.status != stage:
        validate_transition(investigation.status, stage)
    investigation.status = stage
    investigation.current_stage = stage.value
    job = session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.investigation_id == investigation.id)
        .order_by(ProcessingJob.created_at.desc())
    )
    if job is not None:
        job.stage = stage.value
        job.status = "RUNNING"
    session.add(
        AuditEvent(
            investigation_id=investigation.id,
            event_type=f"STAGE_{stage.value}",
            actor="system",
            event_metadata={},
        )
    )
    session.commit()


def _audit(session: Session, investigation_id: UUID, event_type: str, metadata: dict) -> None:
    session.add(
        AuditEvent(
            investigation_id=investigation_id,
            event_type=event_type,
            actor="system",
            event_metadata=metadata,
        )
    )


def _usage(session: Session, investigation_id: UUID) -> InvestigationUsage:
    return get_or_create_usage(session, investigation_id)


def _source_domain(url: str) -> str | None:
    return (urlsplit(url).hostname or "").casefold() or None


def _valid_publication_date(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value[:80]


def _normalized_existing_sources(session: Session, investigation_id: UUID) -> dict[str, Source]:
    output: dict[str, Source] = {}
    for source in session.scalars(
        select(Source).where(Source.investigation_id == investigation_id).order_by(Source.id)
    ):
        try:
            output.setdefault(normalize_source_url(source.url), source)
        except ValueError:
            continue
    return output


def _create_source_candidate(
    session: Session,
    investigation: Investigation,
    *,
    url: str,
    title: str | None = None,
    publisher: str | None = None,
    published_at: str | None = None,
    discovery_method: str,
    trace_id: UUID | None = None,
) -> Source | None:
    try:
        normalized = normalize_source_url(url)
    except ValueError:
        return None
    existing = _normalized_existing_sources(session, investigation.id)
    if normalized in existing:
        source = existing[normalized]
        if published_at and not source.published_at:
            source.published_at = published_at[:80]
            session.commit()
        return source
    settings = get_settings()
    if len(existing) >= settings.max_sources_per_investigation:
        add_limitation(session, investigation.id, "Source-candidate limit reached.")
        return None
    domain = _source_domain(normalized)
    source = Source(
        investigation_id=investigation.id,
        url=normalized,
        title=(title or "")[:2000] or None,
        publisher=(classify_source(domain or "").name if domain else publisher or "")[:255] or None,
        domain=domain,
        source_type=classify_source(domain or "").source_type,
        published_at=published_at[:80] if published_at else None,
        source_role="SUBMITTED" if discovery_method == "SUBMITTED_URL" else "UNKNOWN",
        discovery_method=discovery_method[:40],
        discovery_trace_id=trace_id,
        retrieval_status="CANDIDATE",
    )
    session.add(source)
    usage = _usage(session, investigation.id)
    usage.sources_discovered += 1
    _audit(session, investigation.id, "SOURCES_DISCOVERED", {"count": 1, "domain": domain})
    session.commit()
    session.refresh(source)
    return source


def _save_retrieved_source(
    session: Session,
    investigation: Investigation,
    source: Source,
) -> str | None:
    settings = get_settings()
    if source.retrieval_status == "RETRIEVED" and source.content_storage_key:
        try:
            return get_private_object(key=source.content_storage_key).decode(
                "utf-8", errors="replace"
            )
        except Exception:
            source.retrieval_status = "FAILED"
            session.commit()
            add_limitation(
                session, investigation.id, "A previously retrieved source could not be loaded."
            )
            return None
    if source.retrieval_status in {"FAILED", "NOT_ATTEMPTED_LIMIT"}:
        return None
    if settings.source_reader_provider == "disabled":
        source.retrieval_status = "NOT_ENABLED"
        source.retrieval_failure_reason = "RETRIEVAL_DISABLED"
        session.commit()
        add_limitation(
            session,
            investigation.id,
            "Agent 0 could not independently retrieve the submitted page."
            if source.discovery_method == "SUBMITTED_URL"
            else "Source retrieval is disabled; search results remain candidates.",
        )
        return None
    if source.retrieval_status == "NOT_ENABLED":
        source.retrieval_status = "CANDIDATE"
    usage = _usage(session, investigation.id)
    if usage.sources_retrieved >= settings.max_retrieved_sources:
        source.retrieval_status = "NOT_ATTEMPTED_LIMIT"
        session.commit()
        add_limitation(session, investigation.id, "Source retrieval limit reached.")
        return None
    try:
        page = read_public_page(source.url)
    except SourceRetrievalError:
        source.retrieval_status = "FAILED"
        source.retrieval_failure_reason = "PUBLIC_PAGE_UNAVAILABLE"
        session.commit()
        message = (
            "Agent 0 could not independently retrieve the submitted page."
            if source.discovery_method == "SUBMITTED_URL"
            else "One or more candidate sources could not be retrieved."
        )
        add_limitation(session, investigation.id, message)
        return None
    text = page.text[: getattr(settings, "max_retrieved_document_chars", 60_000)]
    source.title = (page.title or source.title or "")[:2000] or None
    source.author = (page.author or source.author or "")[:255] or None
    source.published_at = (page.published_at or source.published_at or "")[:80] or None
    source.modified_at = (page.modified_at or source.modified_at or "")[:80] or None
    if page.canonical_url:
        try:
            source.canonical_url = normalize_source_url(page.canonical_url)
        except ValueError:
            source.canonical_url = None
    storage_key = f"private-retrieved/{investigation.id}/{source.id}.txt"
    put_private_object(
        key=storage_key, data=text.encode("utf-8"), content_type="text/plain; charset=utf-8"
    )
    source.content_storage_key = storage_key
    source.content_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    source.retrieval_status = "RETRIEVED"
    source.retrieval_failure_reason = None
    source.retrieval_provider = page.provider
    source.retrieved_at = utcnow()
    usage.sources_retrieved += 1
    _audit(
        session,
        investigation.id,
        "SOURCES_RETRIEVED",
        {"source_id": str(source.id), "domain": source.domain},
    )
    session.commit()
    return text


def _load_or_inspect_media(
    session: Session,
    investigation: Investigation,
    assets: list[MediaAsset],
) -> list[tuple[str, bytes]]:
    settings = get_settings()
    images: list[tuple[str, bytes]] = []
    for asset in assets:
        metadata = dict(asset.metadata_json or {})
        cached = metadata.get("analysis_object_keys")
        derived_asset = None
        if asset.media_type == "IMAGE":
            derived_asset = session.scalar(
                select(MediaAsset).where(
                    MediaAsset.parent_asset_id == asset.id,
                    MediaAsset.artifact_type == "NORMALIZED_IMAGE",
                    MediaAsset.transformation_version == "image-normalization-v1",
                )
            )
        if isinstance(cached, list):
            for key in cached:
                if len(images) >= settings.max_images_to_model:
                    break
                mime = "image/png" if asset.media_type == "IMAGE" else "image/jpeg"
                images.append((mime, _get_media_object(str(key))))
            if derived_asset is not None:
                analyze_image_assets(
                    session,
                    investigation_id=investigation.id,
                    original=asset,
                    normalized=derived_asset,
                    original_loader=lambda key=asset.storage_key: _get_media_object(key),
                    normalized_loader=lambda key=derived_asset.storage_key: _get_media_object(key),
                )
        else:
            data = _get_media_object(asset.storage_key)
            extracted_metadata, extracted_frames, limitations = inspect_media(
                data=data,
                media_type=asset.media_type,
                mime_type=asset.mime_type,
            )
            keys: list[str] = []
            if derived_asset is not None:
                extracted_frames = [
                    (derived_asset.mime_type, _get_media_object(derived_asset.storage_key))
                ]
            for index, (mime, frame) in enumerate(extracted_frames):
                ext = "png" if mime == "image/png" else "jpg"
                key = (
                    derived_asset.storage_key
                    if derived_asset is not None
                    else f"private-derived/{asset.id}/normalized-image-v1.{ext}"
                    if asset.media_type == "IMAGE"
                    else f"private-derived/{investigation.id}/{asset.id}/{index}.{ext}"
                )
                if derived_asset is None:
                    try:
                        put_private_object(key=key, data=frame, content_type=mime)
                    except Exception as exc:
                        raise MediaStorageError("Derived media could not be stored") from exc
                if derived_asset is None and asset.media_type == "IMAGE":
                    child = MediaAsset(
                        investigation_id=asset.investigation_id,
                        parent_asset_id=asset.id,
                        asset_role="DERIVED",
                        artifact_type="NORMALIZED_IMAGE",
                        transformation_version="image-normalization-v1",
                        transformation_metadata=extracted_metadata.get("normalization", {}),
                        storage_key=key,
                        media_type="IMAGE",
                        mime_type=mime,
                        size_bytes=len(frame),
                        sha256=hashlib.sha256(frame).hexdigest(),
                        metadata_json={},
                    )
                    session.add(child)
                    session.flush()
                    derived_asset = child
                keys.append(key)
                if len(images) < settings.max_images_to_model:
                    images.append((mime, frame))
            metadata.update(extracted_metadata)
            metadata["analysis_object_keys"] = keys
            asset.metadata_json = metadata
            if not session.scalar(
                select(Evidence.id).where(
                    Evidence.media_asset_id == asset.id,
                    Evidence.method == "MEDIA_METADATA",
                )
            ):
                session.add(
                    Evidence(
                        investigation_id=investigation.id,
                        media_asset_id=asset.id,
                        content=(
                            f"Uploaded {asset.media_type.lower()} media; SHA-256 {asset.sha256}; "
                            f"metadata: {json.dumps(extracted_metadata, sort_keys=True)}"
                        ),
                        method="MEDIA_METADATA",
                        limitations=(
                            "File metadata does not establish whether the recorded event "
                            "is authentic."
                        ),
                    )
                )
            for limitation in limitations:
                add_limitation(session, investigation.id, limitation)
            session.commit()
            if derived_asset is not None and asset.media_type == "IMAGE":
                normalized_data = (
                    frame if extracted_frames else _get_media_object(derived_asset.storage_key)
                )
                analyze_image_assets(
                    session,
                    investigation_id=investigation.id,
                    original=asset,
                    normalized=derived_asset,
                    original_loader=lambda image_data=data: image_data,
                    normalized_loader=lambda image_data=normalized_data: image_data,
                )
    return images[: settings.max_images_to_model]


def _ensure_submitted_url_source(
    session: Session,
    investigation: Investigation,
    submitted_url: str | None,
) -> Source | None:
    if not submitted_url:
        return None
    existing = _normalized_existing_sources(session, investigation.id)
    try:
        normalized = normalize_source_url(submitted_url)
    except ValueError:
        return None
    if normalized in existing:
        return existing[normalized]
    return _create_source_candidate(
        session,
        investigation,
        url=normalized,
        title="Submitted URL",
        publisher=_source_domain(normalized),
        discovery_method="SUBMITTED_URL",
    )


def _persist_plan(
    session: Session,
    investigation: Investigation,
    plan: ResearchPlan,
) -> None:
    settings = get_settings()
    claims = list(session.scalars(select(Claim).where(Claim.investigation_id == investigation.id)))
    extracted_now = not claims
    if extracted_now:
        for candidate in plan.claims[: settings.max_claims_per_investigation]:
            text = candidate.text.strip()
            if not text:
                continue
            normalized = " ".join((candidate.normalized_text or text).casefold().split())
            claims.append(
                Claim(
                    investigation_id=investigation.id,
                    text=text,
                    normalized_text=normalized,
                    claim_type=candidate.claim_type[:40] or "GENERAL",
                )
            )
        session.add_all(claims)
        session.flush()
        _audit(session, investigation.id, "CLAIMS_EXTRACTED", {"count": len(claims)})
    traces = list(
        session.scalars(select(SearchTrace).where(SearchTrace.investigation_id == investigation.id))
    )
    already_planned = {trace.query for trace in traces}
    queries = []
    for planned_query in plan.queries:
        if isinstance(planned_query, str):
            query_text = planned_query
            freshness = "BALANCED"
        else:
            query_text = planned_query.text
            freshness = planned_query.freshness
        normalized_query = _query_for_freshness(query_text, freshness)[:500]
        if normalized_query and normalized_query not in already_planned:
            queries.append(normalized_query)
            already_planned.add(normalized_query)
    if not queries and not traces:
        queries = [claim.text[:500] for claim in claims]
    for query in queries[: settings.max_search_queries]:
        session.add(
            SearchTrace(
                investigation_id=investigation.id,
                provider="EXA",
                action="planned",
                query=query,
                sources=[],
                citations=[],
            )
        )
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
        if "original records and recent reporting that checks the current context" in query.casefold():
            return query[:500]
        query = query[:400]
        query += " original records and recent reporting that checks the current context"
    return query[:500]


def _link_unclaimed_media_evidence(session: Session, investigation: Investigation) -> None:
    """Link media context only when deterministic terms overlap a claim."""
    claims = list(session.scalars(select(Claim).where(Claim.investigation_id == investigation.id)))
    if not claims:
        return
    media_evidence = list(
        session.scalars(
            select(Evidence).where(
                Evidence.investigation_id == investigation.id,
                Evidence.media_asset_id.is_not(None),
            )
        )
    )
    for evidence in media_evidence:
        existing_claim_ids = set(
            session.scalars(
                select(ClaimEvidence.claim_id).where(ClaimEvidence.evidence_id == evidence.id)
            )
        )
        evidence_terms = _relevance_terms(evidence.content)
        for claim in claims:
            if claim.id not in existing_claim_ids:
                claim_terms = _relevance_terms(claim.text)
                if not (evidence_terms & claim_terms):
                    continue
                session.add(
                    ClaimEvidence(
                        claim_id=claim.id,
                        evidence_id=evidence.id,
                        relationship="UNKNOWN",
                    )
                )
    session.commit()


def _relevance_terms(value: str) -> set[str]:
    import re

    stop = {"this", "that", "with", "from", "image", "claim", "media", "the", "and", "for"}
    terms = {word for word in re.findall(r"[a-z0-9]{4,}", value.casefold()) if word not in stop}
    if re.search(r"\bai\b", value.casefold()):
        terms.add("ai")
    return terms


def _media_packet_excerpt(evidence: Evidence) -> str:
    """Project persisted media Evidence through an allowlisted, privacy-safe summary."""
    if evidence.method == "MEDIA_PROVENANCE":
        states = {
            "A locally validated C2PA manifest is present.": "VALID",
            "No supported C2PA manifest was detected in the original uploaded image.": (
                "NOT_PRESENT"
            ),
            "C2PA data was present, but local validation did not succeed.": "INVALID",
            "The local C2PA SDK does not support this asset or manifest.": "UNSUPPORTED",
            (
                "C2PA provenance was present or suspected, "
                "but local analysis could not fully validate it."
            ): "INDETERMINATE",
            "Local C2PA analysis could not be completed.": "ERROR",
        }
        state = next(
            (value for prefix, value in states.items() if evidence.content.startswith(prefix)),
            "INDETERMINATE",
        )
        text = f"Local C2PA state: {state}. This does not establish depicted event truth."
        if "Content Credentials declare generative AI involvement." in evidence.content:
            text += " Content Credentials declare generative-AI involvement."
        return text + (
            " Local offline validation; remote manifest retrieval and "
            "OCSP/revocation checks were disabled."
        )
    if evidence.method == "MEDIA_VISUAL_OBSERVATION":
        return evidence.content[:1000]
    if evidence.method == "MEDIA_TECHNICAL_METADATA":
        marker = "Safe decoded fields: "
        try:
            payload = evidence.content.split(marker, 1)[1].split(". Analyzed", 1)[0]
            fields = json.loads(payload)
        except (IndexError, json.JSONDecodeError):
            return "Allowlisted image metadata was recorded; private fields are omitted."
        safe = {key: fields[key] for key in ("format", "width", "height") if key in fields}
        return (
            "Allowlisted technical metadata reports "
            + json.dumps(safe, separators=(",", ":"))
            + ". Metadata is editable and does not establish manipulation, origin, or event time."
        )[:700]
    if evidence.method == "MEDIA_METADATA":
        return (
            "A media observation was recorded. Metadata can be edited and does not establish "
            "manipulation, origin, or event time."
        )
    return ""


def _persist_visual_observations(
    session: Session,
    investigation: Investigation,
    images: list[tuple[str, bytes]],
    gateway: ModelGateway,
) -> None:
    if not images or not session.scalar(
        select(Claim.id).where(Claim.investigation_id == investigation.id)
    ):
        return
    if session.scalar(
        select(Evidence.id).where(
            Evidence.investigation_id == investigation.id,
            Evidence.method == "MEDIA_VISUAL_OBSERVATION",
        )
    ):
        return
    original = session.scalar(
        select(MediaAsset)
        .where(
            MediaAsset.investigation_id == investigation.id,
            MediaAsset.asset_role == "ORIGINAL",
            MediaAsset.media_type == "IMAGE",
        )
        .order_by(MediaAsset.created_at)
    )
    if original is None:
        return
    normalized = session.scalar(
        select(MediaAsset).where(
            MediaAsset.parent_asset_id == original.id,
            MediaAsset.artifact_type == "NORMALIZED_IMAGE",
        )
    )
    if normalized is None:
        return
    claim = session.scalar(
        select(Claim).where(Claim.investigation_id == investigation.id).order_by(Claim.created_at)
    )
    if claim is None:
        return
    claim_text = claim.text.casefold()
    visual_cues = (
        "shows",
        "depicts",
        "visible",
        "sign",
        "banner",
        "text",
        "logo",
        "scene",
        "weather",
        "landmark",
        "reads",
        "says",
        "screenshot",
        "what is in",
        "what appears in",
    )
    if not any(cue in claim_text for cue in visual_cues):
        return
    try:
        result = gateway.analyze_visual_content(
            image=(normalized.mime_type, images[0][1]),
            claim_text=claim.text,
            session=session,
            investigation_id=investigation.id,
        )
        if not isinstance(result.output, VisualAnalysis):
            raise ValueError("Invalid visual analysis output")
    except Exception as exc:
        add_limitation(
            session,
            investigation.id,
            "Visual interpretation was unavailable; deterministic media and source evidence "
            "were retained.",
        )
        _audit(
            session,
            investigation.id,
            "MEDIA_VISUAL_ANALYSIS_FAILED",
            {"category": getattr(getattr(exc, "category", None), "value", "ANALYSIS_FAILED")},
        )
        session.commit()
        return
    observations = []
    for item in result.output.observations[:12]:
        text = re.sub(r"(?:https?://|www\.)\S+|[\w.+-]+@[\w.-]+", "[redacted]", item.observation)
        text = re.sub(r"[\x00-\x1f<>]", " ", text).strip()[:300]
        if text:
            observations.append(
                {
                    "observation": text,
                    "uncertainty": item.confidence,
                    "relevance": item.relevance[:200],
                    "limitations": [value[:200] for value in item.limitations[:5]],
                }
            )
    if not observations:
        return
    evidence = Evidence(
        investigation_id=investigation.id,
        media_asset_id=original.id,
        content="Structured visual observations (not forensic findings): "
        + json.dumps(observations, ensure_ascii=False, separators=(",", ":")),
        method="MEDIA_VISUAL_OBSERVATION",
        limitations=(
            "Visual descriptions may be mistaken and do not establish authenticity, "
            "manipulation, event truth, or synthetic generation."
        ),
    )
    session.add(evidence)
    session.flush()
    session.commit()
    _link_unclaimed_media_evidence(session, investigation)


def _execute_searches(session: Session, investigation: Investigation) -> None:
    settings = get_settings()
    key = settings.exa_api_key.get_secret_value().strip() if settings.exa_api_key else ""
    traces = list(
        session.scalars(
            select(SearchTrace)
            .where(
                SearchTrace.investigation_id == investigation.id,
                SearchTrace.action.in_(["planned", "unavailable"]),
            )
            .order_by(SearchTrace.created_at)
        )
    )
    for trace in traces[: settings.max_search_queries]:
        if not key:
            trace.action = "unavailable"
            trace.created_at = utcnow()
            session.commit()
            add_limitation(
                session,
                investigation.id,
                "Web search is not configured; sources could not be discovered.",
            )
            continue
        usage = _usage(session, investigation.id)
        if usage.search_calls >= settings.max_search_queries:
            trace.action = "budget_exceeded"
            session.commit()
            add_limitation(session, investigation.id, "Search-query budget reached.")
            continue
        usage.search_calls += 1
        trace.created_at = utcnow()
        session.commit()
        try:
            response = search_exa(
                api_key=key,
                query=trace.query or "",
                num_results=settings.max_search_results_per_query,
            )
        except ExaSearchError:
            trace.action = "error"
            trace.created_at = utcnow()
            session.commit()
            add_limitation(session, investigation.id, "A web search could not be completed.")
            continue
        normalized_results: list[dict[str, object]] = []
        for item in response.results[: settings.max_search_results_per_query]:
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
        trace.call_reference = response.request_id
        trace.sources = normalized_results
        trace.created_at = utcnow()
        for item in normalized_results:
            _create_source_candidate(
                session,
                investigation,
                url=str(item["url"]),
                title=str(item.get("title") or ""),
                publisher=str(item.get("author") or _source_domain(str(item["url"])) or ""),
                published_at=_valid_publication_date(item.get("publishedDate")),
                discovery_method="EXA",
                trace_id=trace.id,
            )
        _audit(
            session,
            investigation.id,
            "SEARCH_COMPLETED",
            {"query": trace.query, "result_count": len(normalized_results)},
        )
        session.commit()


def _retrieve_candidates(session: Session, investigation: Investigation) -> dict[UUID, str]:
    settings = get_settings()
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
    trace_ids = {source.discovery_trace_id for source in sources if source.discovery_trace_id}
    traces = (
        list(session.scalars(select(SearchTrace).where(SearchTrace.id.in_(trace_ids))))
        if trace_ids
        else []
    )
    context_by_source: dict[UUID, str] = {}
    for source in sources:
        matching_traces = [trace for trace in traces if trace.id == source.discovery_trace_id]
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
        if source.retrieval_status == "RETRIEVED" and source.content_storage_key:
            try:
                text = get_private_object(key=source.content_storage_key).decode(
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
        current_count = _usage(session, investigation.id).sources_retrieved
        if current_count >= settings.max_retrieved_sources:
            source.retrieval_status = "NOT_ATTEMPTED_LIMIT"
            session.commit()
            add_limitation(session, investigation.id, "Source retrieval limit reached.")
            continue
        text = _save_retrieved_source(session, investigation, source)
        if text is not None:
            retrieved[source.id] = text[: getattr(settings, "max_retrieved_document_chars", 60_000)]
    return retrieved


def _persist_evidence(
    session: Session,
    investigation: Investigation,
    retrieved_pages: dict[UUID, str],
) -> None:
    settings = get_settings()
    claims = list(session.scalars(select(Claim).where(Claim.investigation_id == investigation.id)))
    existing_evidence: set[tuple[UUID, UUID, str]] = set()
    evidence_count_by_claim_source: dict[tuple[UUID, UUID], int] = {}
    rows = session.execute(
        select(ClaimEvidence.claim_id, Evidence.source_id, Evidence.content)
        .join(Evidence, ClaimEvidence.evidence_id == Evidence.id)
        .where(ClaimEvidence.claim_id.in_([claim.id for claim in claims] or [UUID(int=0)]))
    )
    for claim_id, source_id, content in rows:
        if not source_id:
            continue
        content_key = " ".join(content.casefold().split())
        existing_evidence.add((claim_id, source_id, content_key))
        pair = (claim_id, source_id)
        evidence_count_by_claim_source[pair] = evidence_count_by_claim_source.get(pair, 0) + 1
    current_chars = sum(
        len(item.content)
        for item in session.scalars(
            select(Evidence).where(Evidence.investigation_id == investigation.id)
        )
    )
    remaining = max(0, settings.max_total_evidence_chars - current_chars)
    claim_pairs = [(str(claim.id), claim.text) for claim in claims]
    max_windows = getattr(settings, "max_evidence_windows_per_source_per_claim", 2)
    added = 0
    for source_id, text in retrieved_pages.items():
        source = session.get(Source, source_id)
        if (
            source is None
            or source.discovery_method == "SUBMITTED_URL"
            or source.source_role == "DERIVATIVE"
        ):
            continue
        candidates = []
        for claim_id, claim_text in claim_pairs:
            pair = (UUID(claim_id), source_id)
            windows_remaining = max_windows - evidence_count_by_claim_source.get(pair, 0)
            if windows_remaining <= 0 or remaining < 24:
                continue
            regions = select_claim_relevant_regions(
                claim_id=claim_id,
                claim_text=claim_text,
                document_text=text[: getattr(settings, "max_retrieved_document_chars", 60_000)],
                max_regions=getattr(settings, "max_matching_regions_per_claim", 4),
                region_chars=settings.max_source_chars_per_source,
            )
            if not regions:
                continue
            candidates.extend(
                extract_candidate_excerpts(
                    claims=[(claim_id, claim_text)],
                    page_text="\n\n".join(region.text for region in regions),
                    max_chars=settings.max_source_chars_per_source,
                    remaining_total_chars=remaining,
                    max_windows=windows_remaining,
                )
            )
        for candidate in candidates:
            if not excerpt_is_present(candidate.excerpt, text):
                continue
            claim_id = UUID(candidate.claim_id)
            pair = (claim_id, source_id)
            content_key = " ".join(candidate.excerpt.casefold().split())
            if (claim_id, source_id, content_key) in existing_evidence:
                continue
            windows_remaining = max_windows - evidence_count_by_claim_source.get(pair, 0)
            if windows_remaining <= 0:
                continue
            evidence = Evidence(
                investigation_id=investigation.id,
                source_id=source_id,
                content=candidate.excerpt,
                method="CLAIM_ANCHOR_MATCH",
                limitations=(
                    "Deterministically selected claim-relevant passage; relevance and meaning "
                    "still require review. Localization does not establish factual support."
                ),
            )
            session.add(evidence)
            session.flush()
            session.add(
                ClaimEvidence(claim_id=claim_id, evidence_id=evidence.id, relationship="UNKNOWN")
            )
            existing_evidence.add((claim_id, source_id, content_key))
            evidence_count_by_claim_source[pair] = evidence_count_by_claim_source.get(pair, 0) + 1
            added += 1
            remaining -= len(candidate.excerpt)
        session.commit()
    if added:
        _audit(session, investigation.id, "EVIDENCE_ACCEPTED", {"count": added})
        session.commit()
    if remaining <= 0:
        add_limitation(session, investigation.id, "Total evidence-text budget reached.")


def _detect_source_relationships(
    session: Session,
    investigation: Investigation,
    retrieved_pages: dict[UUID, str],
) -> None:
    """Persist only deterministic duplicate and explicit-link relationships."""
    sources = list(
        session.scalars(select(Source).where(Source.investigation_id == investigation.id))
    )
    by_url: dict[str, Source] = {}
    by_hash: dict[str, Source] = {}
    by_id = {source.id: source for source in sources}
    for source in sources:
        for candidate_url in (source.url, source.canonical_url):
            if not candidate_url:
                continue
            try:
                normalized = normalize_source_url(candidate_url)
            except ValueError:
                continue
            by_url.setdefault(normalized, source)
    existing = {
        (item.source_id, item.related_source_id, item.relationship_type)
        for item in session.scalars(
            select(SourceRelationship).where(
                SourceRelationship.investigation_id == investigation.id
            )
        )
    }

    def add(source_id: UUID, related_id: UUID, relationship: str, basis: str) -> None:
        key = (source_id, related_id, relationship)
        if source_id == related_id or key in existing:
            return
        session.add(
            SourceRelationship(
                investigation_id=investigation.id,
                source_id=source_id,
                related_source_id=related_id,
                relationship_type=relationship,
                basis=basis,
            )
        )
        existing.add(key)

    for source in sources:
        if not source.canonical_url:
            continue
        try:
            canonical = normalize_source_url(source.canonical_url)
        except ValueError:
            continue
        original = by_url.get(canonical)
        if original and original.id != source.id:
            add(source.id, original.id, "DUPLICATES", "matching normalized canonical URL")
            source.source_role = "DERIVATIVE"

    for source_id, text in retrieved_pages.items():
        source = by_id.get(source_id)
        if source is None:
            continue
        if source.content_sha256:
            duplicate = by_hash.get(source.content_sha256)
            if duplicate is not None:
                add(source.id, duplicate.id, "DUPLICATES", "matching retrieved-content SHA-256")
                source.source_role = "DERIVATIVE"
            else:
                by_hash[source.content_sha256] = source
        for linked_url in extract_markdown_link_urls(text):
            target = by_url.get(linked_url)
            if target and target.id != source.id:
                add(source.id, target.id, "CITES", "explicit retrieved-page hyperlink")
    session.commit()


def _evidence_packet(session: Session, investigation: Investigation) -> str:
    settings = get_settings()
    claims = list(session.scalars(select(Claim).where(Claim.investigation_id == investigation.id)))
    evidence_rows = list(
        session.execute(
            select(Evidence, ClaimEvidence, Source, MediaAsset)
            .join(ClaimEvidence, ClaimEvidence.evidence_id == Evidence.id)
            .outerjoin(Source, Evidence.source_id == Source.id)
            .outerjoin(MediaAsset, Evidence.media_asset_id == MediaAsset.id)
            .where(Evidence.investigation_id == investigation.id)
            .order_by(Evidence.created_at)
        )
    )
    packet = {
        "claims": [{"id": str(claim.id), "text": claim.text[:2000]} for claim in claims],
        "submitted_sources": [
            {
                "source_id": str(source.id),
                "url": source.url[:1000],
                "canonical_url": source.canonical_url,
                "title": source.title,
                "publisher": source.publisher,
                "author": source.author,
                "published_at": source.published_at,
                "source_type": source.source_type,
                "authoritative_for": list(classify_source(source.domain or "").authoritative_for),
                "retrieval_status": source.retrieval_status,
                "role": "SUBMITTED; context for claim extraction, not independent evidence",
            }
            for source in session.scalars(
                select(Source).where(
                    Source.investigation_id == investigation.id,
                    Source.discovery_method == "SUBMITTED_URL",
                )
            )
        ],
        "source_candidates_not_evidence": [
            {
                "source_id": str(source.id),
                "title": (source.title or "")[:250],
                "publisher": (source.publisher or "")[:100],
                "domain": source.domain,
                "source_type": source.source_type,
                "published_at": source.published_at,
                "retrieval_status": source.retrieval_status,
                "role": "Candidate only; page content was not retrieved as evidence.",
            }
            for source in session.scalars(
                select(Source)
                .where(Source.investigation_id == investigation.id)
                .order_by(Source.id)
                .limit(12)
            )
        ],
        "evidence": [],
        "source_relationships": [],
        "limitations": _usage(session, investigation.id).limitations,
    }
    claim_by_id = {claim.id: claim for claim in claims}
    relationships = list(
        session.scalars(
            select(SourceRelationship).where(
                SourceRelationship.investigation_id == investigation.id
            )
        )
    )
    packet["source_relationships"] = [
        {
            "source_id": str(item.source_id),
            "relationship": item.relationship_type,
            "related_source_id": str(item.related_source_id),
            "basis": item.basis,
        }
        for item in relationships
    ]
    remaining = min(settings.max_total_evidence_chars, 24_000)
    media_remaining = MAX_MEDIA_EVIDENCE_CHARS
    media_priority = {
        "MEDIA_PROVENANCE": 0,
        "MEDIA_VISUAL_OBSERVATION": 1,
        "MEDIA_TECHNICAL_METADATA": 2,
        "MEDIA_METADATA": 2,
    }
    evidence_rows.sort(
        key=lambda row: (
            row[0].method in MEDIA_PACKET_METHODS,
            media_priority.get(row[0].method, 0) if row[0].media_asset_id else 0,
            row[0].created_at,
        )
    )
    for evidence, link, source, media_asset in evidence_rows:
        if remaining < 24:
            break
        is_media = evidence.media_asset_id is not None
        if is_media:
            if evidence.method not in MEDIA_PACKET_METHODS or media_remaining < 24:
                continue
            excerpt = _media_packet_excerpt(evidence)[: min(remaining, media_remaining)]
        else:
            excerpt = evidence.content[:remaining]
        item: dict[str, object] = {
            "evidence_id": str(evidence.id),
            "claim_id": str(link.claim_id),
            "origin": {
                "source_id": str(source.id) if source else None,
                "media_asset_id": str(media_asset.id) if media_asset else None,
            },
            "source_id": str(source.id) if source else None,
            "media_asset_id": str(media_asset.id) if media_asset else None,
            "kind": evidence.method,
            "excerpt": excerpt,
            "relationship": link.relationship,
            "limitations": evidence.limitations,
        }
        if source:
            source_registry = classify_source(source.domain or "")
            item.update(
                {
                    "title": (source.title or "")[:250],
                    "publisher": (source.publisher or "")[:100],
                    "domain": source.domain,
                    "url": source.url[:1000],
                    "source_type": source.source_type,
                    "authoritative_for": list(source_registry.authoritative_for),
                    "role": (
                        source.source_role
                        if source.source_role == "DERIVATIVE"
                        else role_for_claim(
                            source_registry,
                            claim_by_id[link.claim_id].text if link.claim_id in claim_by_id else "",
                            submitted=source.discovery_method == "SUBMITTED_URL",
                        )
                    ),
                    "author": source.author,
                    "published_at": source.published_at,
                }
            )
        if media_asset:
            item["media_asset"] = {
                "id": str(media_asset.id),
                "media_type": media_asset.media_type,
                "mime_type": media_asset.mime_type,
                "size_bytes": media_asset.size_bytes,
            }
        packet["evidence"].append(item)
        remaining -= len(excerpt)
        if is_media:
            media_remaining -= len(excerpt)
    return json.dumps(packet, ensure_ascii=False, separators=(",", ":"))


def _has_claim_linked_evidence(session: Session, investigation: Investigation) -> bool:
    return (
        session.scalar(
            select(Evidence.id)
            .join(ClaimEvidence, ClaimEvidence.evidence_id == Evidence.id)
            .join(Claim, Claim.id == ClaimEvidence.claim_id)
            .where(
                Evidence.investigation_id == investigation.id,
                Claim.investigation_id == investigation.id,
                Evidence.method != "MEDIA_FINGERPRINT",
                (Evidence.source_id.is_not(None) | Evidence.media_asset_id.is_not(None)),
            )
            .limit(1)
        )
        is not None
    )


def _persist_findings(
    session: Session,
    investigation: Investigation,
    output: EvidenceReasoning,
) -> None:
    claims = list(session.scalars(select(Claim).where(Claim.investigation_id == investigation.id)))
    existing = {
        item.claim_id
        for item in session.scalars(
            select(Finding).where(Finding.investigation_id == investigation.id)
        )
    }
    proposed = {finding.claim_id: finding for finding in output.findings}
    for claim in claims:
        if claim.id in existing:
            continue
        candidate = proposed.get(str(claim.id))
        accepted: list[tuple[UUID, str]] = []
        accepted_methods: dict[UUID, str] = {}
        support_capable_ids: set[UUID] = set()
        contradiction_capable_ids: set[UUID] = set()
        if candidate is not None:
            for assessment in candidate.evidence:
                if assessment.relationship not in ALLOWED_RELATIONSHIPS:
                    continue
                try:
                    evidence_id = UUID(assessment.evidence_id)
                except ValueError:
                    continue
                link = session.scalar(
                    select(ClaimEvidence).where(
                        ClaimEvidence.claim_id == claim.id,
                        ClaimEvidence.evidence_id == evidence_id,
                    )
                )
                if link is None:
                    continue
                evidence = session.scalar(
                    select(Evidence).where(
                        Evidence.id == evidence_id,
                        Evidence.investigation_id == investigation.id,
                        Evidence.method != "MEDIA_FINGERPRINT",
                        (Evidence.source_id.is_not(None) | Evidence.media_asset_id.is_not(None)),
                    )
                )
                if evidence is None:
                    continue
                link.relationship = assessment.relationship
                accepted.append((evidence_id, assessment.relationship))
                accepted_methods[evidence_id] = evidence.method
                credential_claim = any(
                    term in claim.text.casefold()
                    for term in ("credential", "c2pa", "content credentials")
                ) and not any(
                    term in claim.text.casefold()
                    for term in ("authentic", "real", "fake", "true", "depicts", "shows", "event")
                )
                visual_description_claim = (
                    evidence.method == "MEDIA_VISUAL_OBSERVATION"
                    and any(
                        marker in claim.text.casefold()
                        for marker in (
                            "shows",
                            "visible",
                            "contains",
                            "sign",
                            "banner",
                            "text",
                            "logo",
                        )
                    )
                    and not any(
                        marker in claim.text.casefold()
                        for marker in (
                            "manipulat",
                            "fake",
                            "authentic",
                            "ai-generated",
                            "synthetic",
                        )
                    )
                )
                if evidence.source_id is not None or visual_description_claim:
                    support_capable_ids.add(evidence_id)
                elif (
                    evidence.method == "MEDIA_PROVENANCE" and assessment.relationship == "SUPPORTS"
                ):
                    claim_lower = claim.text.casefold()
                    ai_declaration_claim = (
                        credential_claim
                        and any(term in claim_lower for term in ("declare", "declaration"))
                        and any(term in claim_lower for term in ("ai", "generative"))
                        and "Content Credentials declare generative AI involvement."
                        in evidence.content
                    )
                    state = _media_packet_excerpt(evidence)
                    positive_credentials_claim = (
                        credential_claim
                        and "no " not in claim_lower
                        and "without" not in claim_lower
                        and state.startswith("Local C2PA state: VALID.")
                    )
                    negative_credentials_claim = (
                        credential_claim
                        and any(term in claim_lower for term in ("no ", "without", "absent"))
                        and state.startswith("Local C2PA state: NOT_PRESENT.")
                    )
                    if (
                        ai_declaration_claim
                        or positive_credentials_claim
                        or negative_credentials_claim
                    ):
                        support_capable_ids.add(evidence_id)
                if evidence.source_id is not None:
                    contradiction_capable_ids.add(evidence_id)
        status = candidate.status if candidate is not None else "UNVERIFIED"
        has_eligible_support = any(
            rel == "SUPPORTS" and evidence_id in support_capable_ids
            for evidence_id, rel in accepted
        )
        has_eligible_contradiction = any(
            rel == "CONTRADICTS" and evidence_id in contradiction_capable_ids
            for evidence_id, rel in accepted
        )
        if status == "SUPPORTED" and not has_eligible_support:
            status = "UNVERIFIED"
        elif status == "CONTRADICTED" and not has_eligible_contradiction:
            status = "UNVERIFIED"
        has_material_conflict = has_eligible_support and has_eligible_contradiction
        if has_material_conflict:
            status = "INCONCLUSIVE"
        elif status == "INCONCLUSIVE":
            status = "UNVERIFIED"
        if status not in ALLOWED_FINDING_STATUSES:
            status = "UNVERIFIED"
        if not accepted and status in {"SUPPORTED", "CONTRADICTED", "INCONCLUSIVE"}:
            status = "UNVERIFIED"
        conflicting = has_material_conflict
        if candidate is not None and status == candidate.status and not conflicting:
            statement = candidate.statement.strip()
            limitations = candidate.limitations
            evidence_confidence = candidate.evidence_confidence
            confidence_rationale = candidate.confidence_rationale.strip()
        elif conflicting:
            statement = (
                "Retrieved evidence supports and contradicts this claim; it remains inconclusive."
            )
            limitations = candidate.limitations if candidate else []
            evidence_confidence = "LOW"
            confidence_rationale = (
                "Retrieved evidence conflicts, so the available record cannot resolve the claim."
            )
        elif accepted:
            statement = (
                "The retrieved material did not provide enough claim-specific evidence to "
                "confirm or challenge this claim. Review the linked context and seek a source "
                "that addresses it directly."
            )
            limitations = [
                "Retrieved excerpts were linked, but none had an eligible relationship and source "
                "type to support a factual conclusion."
            ]
            evidence_confidence = "LOW"
            confidence_rationale = (
                "The linked material did not provide eligible, claim-specific support or "
                "contradiction."
            )
        else:
            statement = (
                "Agent 0 could not verify this claim because no retrieved, claim-linked evidence "
                "was available. Review the source candidates or provide an accessible primary "
                "source."
            )
            limitations = [
                "Source candidates and search-result titles are leads, not evidence; no retrieved "
                "excerpt was available to assess this claim."
            ]
            evidence_confidence = "LOW"
            confidence_rationale = (
                "The available evidence is insufficient or not traceably linked to this claim."
            )
        if status in {"INCONCLUSIVE", "UNVERIFIED"} and evidence_confidence == "HIGH":
            evidence_confidence = "LOW"
            confidence_rationale = (
                "The evidence does not resolve the claim, so confidence in this assessment is low."
            )
        if not accepted:
            evidence_confidence = "LOW"
            confidence_rationale = (
                "No retrieved, claim-linked excerpt was available to assess the evidence."
            )
        if status == "SUPPORTED":
            supporting_methods = {
                accepted_methods[evidence_id]
                for evidence_id, relationship in accepted
                if relationship == "SUPPORTS"
            }
            if supporting_methods == {"MEDIA_PROVENANCE"}:
                cited = [
                    session.get(Evidence, evidence_id)
                    for evidence_id, relationship in accepted
                    if relationship == "SUPPORTS"
                ]
                declares_ai = any(
                    item is not None
                    and "Content Credentials declare generative AI involvement." in item.content
                    for item in cited
                )
                statement = (
                    "The uploaded image contains Content Credentials declaring "
                    "generative-AI involvement."
                    if declares_ai
                    else "The uploaded image contains locally validated Content Credentials."
                )
                limitations = [
                    "Content Credentials are provenance assertions and do not establish the "
                    "truth of depicted events. Local remote-manifest and OCSP checks were disabled."
                ]
                evidence_confidence = "MODERATE"
                confidence_rationale = (
                    "Local credentials were validated, but they describe provenance and do not "
                    "verify the depicted event."
                )
            elif supporting_methods == {"MEDIA_VISUAL_OBSERVATION"}:
                statement = (
                    "A visual observation in the uploaded image is consistent with this claim; "
                    "visual interpretation is not forensic verification."
                )
                limitations = [
                    "Visual observations may be mistaken and do not independently establish the "
                    "truth of the depicted event."
                ]
                evidence_confidence = "LOW"
                confidence_rationale = (
                    "This is a fallible visual observation and is not independent verification."
                )
        finding = Finding(
            investigation_id=investigation.id,
            claim_id=claim.id,
            status=status,
            statement=statement,
            evidence_confidence=evidence_confidence,
            confidence_rationale=confidence_rationale[:1000],
            limitations="; ".join(limitations)[:2000] or None,
        )
        session.add(finding)
        session.flush()
        session.add_all(
            [
                FindingEvidence(finding_id=finding.id, evidence_id=evidence_id)
                for evidence_id, _ in accepted
            ]
        )
    session.commit()
    _audit(session, investigation.id, "FINDINGS_CREATED", {"count": len(claims)})


def _create_unverified_findings(session: Session, investigation: Investigation) -> None:
    claims = list(session.scalars(select(Claim).where(Claim.investigation_id == investigation.id)))
    existing = {
        item.claim_id
        for item in session.scalars(
            select(Finding).where(Finding.investigation_id == investigation.id)
        )
    }
    for claim in claims:
        if claim.id not in existing:
            session.add(
                Finding(
                    investigation_id=investigation.id,
                    claim_id=claim.id,
                    status="UNVERIFIED",
                    statement=(
                        "Agent 0 could not verify this claim because no retrieved, claim-linked "
                        "evidence was available. Review the listed source candidates or provide "
                        "an accessible primary source."
                    ),
                    evidence_confidence="LOW",
                    confidence_rationale=(
                        "The available evidence is insufficient or not traceably linked to this claim."
                    ),
                    limitations="No retrieved source excerpt was available for assessment.",
                )
            )
    session.commit()
    _audit(
        session,
        investigation.id,
        "FINDINGS_CREATED",
        {"count": len(claims), "mode": "deterministic_inconclusive"},
    )


def _build_brief(session: Session, investigation: Investigation) -> None:
    if session.scalar(
        select(VerificationBrief.id).where(VerificationBrief.investigation_id == investigation.id)
    ):
        return
    usage = _usage(session, investigation.id)
    findings = list(
        session.scalars(select(Finding).where(Finding.investigation_id == investigation.id))
    )
    claims = list(session.scalars(select(Claim).where(Claim.investigation_id == investigation.id)))
    media_counts = {
        method: session.scalar(
            select(func.count(Evidence.id)).where(
                Evidence.investigation_id == investigation.id,
                Evidence.method == method,
            )
        )
        or 0
        for method in ("MEDIA_PROVENANCE", "MEDIA_TECHNICAL_METADATA", "MEDIA_VISUAL_OBSERVATION")
    }
    media_labels = {
        "MEDIA_PROVENANCE": "image provenance",
        "MEDIA_TECHNICAL_METADATA": "image file details",
        "MEDIA_VISUAL_OBSERVATION": "visible image content",
    }
    present_media = [media_labels[name] for name, count in media_counts.items() if count]
    summary = finding_result_summary(findings)
    if present_media:
        summary += "\n\nMedia reviewed: " + ", ".join(present_media) + "."
    limitations = list(usage.limitations)
    if not findings and claims:
        limitations.append("Findings are unavailable because evidence reasoning did not complete.")
    if any(item.status in {"INCONCLUSIVE", "UNVERIFIED"} for item in findings):
        limitations.append(
            "Recommended next step: review the cited sources and seek confirmation from an "
            "independent, authoritative source before publication. This is a recommendation, "
            "not evidence."
        )
    brief = VerificationBrief(
        investigation_id=investigation.id,
        summary=summary,
        limitations=list(dict.fromkeys(limitations)),
        version=1,
    )
    session.add(brief)
    session.commit()
    _audit(session, investigation.id, "BRIEF_GENERATED", {"finding_count": len(findings)})


def _load_plan(session: Session, investigation_id: UUID) -> ResearchPlan:
    claims = list(session.scalars(select(Claim).where(Claim.investigation_id == investigation_id)))
    planned = list(
        session.scalars(
            select(SearchTrace).where(
                SearchTrace.investigation_id == investigation_id,
                SearchTrace.action.in_(["planned", "unavailable"]),
            )
        )
    )
    from app.modules.investigations.investigator import PlannedClaim, PlannedQuery

    planned_queries = []
    for item in planned:
        query = item.query or ""
        freshness = (
            "CURRENT"
            if "prioritize current information and dated sources" in query.casefold()
            else "BALANCED"
            if "original records and recent reporting that checks the current context"
            in query.casefold()
            else "HISTORICAL"
        )
        planned_queries.append(PlannedQuery(text=query[:500], freshness=freshness))

    return ResearchPlan(
        claims=[
            PlannedClaim(
                text=item.text, normalized_text=item.normalized_text, claim_type=item.claim_type
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


def _submitted_source_prompt(source: Source, retrieved_text: str, original_url: str) -> str:
    """Bounded input for claim extraction, clearly separating source claims from proof."""
    metadata = [
        "SUBMITTED SOURCE (extract its verifiable claims; do not treat it as independent evidence)",
        f"Submitted URL: {original_url}",
        f"Normalized URL: {source.url}",
        f"Canonical URL: {source.canonical_url or 'unknown'}",
        f"Title: {source.title or 'unknown'}",
        f"Publisher/domain: {source.publisher or source.domain or 'unknown'}",
        f"Author: {source.author or 'unknown'}",
        f"Publication date: {source.published_at or 'unknown'}",
        "Retrieved article text:",
        retrieved_text,
    ]
    return "\n".join(metadata)


def process_investigation(session: Session, *, job_id: UUID) -> str:
    job = session.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id).with_for_update())
    if job is None:
        return "missing"
    if job.status == "COMPLETE":
        return "complete"
    investigation = session.get(Investigation, job.investigation_id)
    if investigation is None:
        job.status = "FAILED"
        job.error_code = "INVESTIGATION_NOT_FOUND"
        session.commit()
        return "failed"
    if investigation.status == InvestigationStatus.COMPLETE:
        job.status = "COMPLETE"
        session.commit()
        return "complete"
    try:
        if investigation.status == InvestigationStatus.RECEIVED:
            _stage(session, investigation, InvestigationStatus.PROCESSING)
        elif investigation.status in {InvestigationStatus.NEEDS_REVIEW, InvestigationStatus.FAILED}:
            _stage(session, investigation, InvestigationStatus.PROCESSING)
        _stage(session, investigation, InvestigationStatus.ANALYZING)
        submission = session.scalar(
            select(Submission)
            .where(Submission.investigation_id == investigation.id)
            .order_by(Submission.received_at)
        )
        text = submission.original_text if submission and submission.original_text else ""
        submitted_url = text if investigation.input_type == InputType.URL else None
        assets = _original_media_assets(session, investigation.id)
        images = _load_or_inspect_media(session, investigation, assets)
        url_source = _ensure_submitted_url_source(session, investigation, submitted_url)
        url_text = (
            _save_retrieved_source(session, investigation, url_source) if url_source else None
        )
        model_input = text
        if url_text:
            bounded_url_text = url_text[: get_settings().max_model_input_chars]
            model_input = _submitted_source_prompt(url_source, bounded_url_text, submitted_url)

        claims_exist = (
            session.scalar(
                select(Claim.id).where(Claim.investigation_id == investigation.id).limit(1)
            )
            is not None
        )
        planned_exist = (
            session.scalar(
                select(SearchTrace.id)
                .where(SearchTrace.investigation_id == investigation.id)
                .limit(1)
            )
            is not None
        )
        if submitted_url and not url_text and not claims_exist:
            add_limitation(
                session,
                investigation.id,
                "Agent 0 could not independently retrieve the submitted page; "
                "no article claims were inferred.",
            )
            _persist_plan(session, investigation, _url_only_fallback_plan(submitted_url))
        elif not claims_exist or not planned_exist:
            model_run = ModelGateway().extract_claims_and_queries(
                text=model_input,
                images=images,
                session=session,
                investigation_id=investigation.id,
            )
            _persist_plan(session, investigation, model_run.output)
        else:
            _persist_plan(session, investigation, _load_plan(session, investigation.id))

        _link_unclaimed_media_evidence(session, investigation)
        if images and investigation.input_type != InputType.URL:
            _persist_visual_observations(session, investigation, images, ModelGateway())

        _stage(session, investigation, InvestigationStatus.RESEARCHING)
        _execute_searches(session, investigation)
        _stage(session, investigation, InvestigationStatus.CORROBORATING)
        retrieved = _retrieve_candidates(session, investigation)
        _detect_source_relationships(session, investigation, retrieved)
        _persist_evidence(session, investigation, retrieved)
        claims = list(
            session.scalars(select(Claim).where(Claim.investigation_id == investigation.id))
        )
        evidence_exists = _has_claim_linked_evidence(session, investigation)
        if claims:
            has_missing_findings = any(
                session.scalar(select(Finding.id).where(Finding.claim_id == claim.id).limit(1))
                is None
                for claim in claims
            )
            if has_missing_findings:
                _stage(session, investigation, InvestigationStatus.GENERATING_BRIEF)
                result = ModelGateway().reason_about_evidence(
                    evidence_packet=_evidence_packet(session, investigation),
                    session=session,
                    investigation_id=investigation.id,
                )
                _persist_findings(session, investigation, result.output)
        else:
            _create_unverified_findings(session, investigation)
        if claims and not evidence_exists:
            add_limitation(
                session,
                investigation.id,
                "No retrieved evidence was available; findings remain unverified.",
            )
        if investigation.status != InvestigationStatus.GENERATING_BRIEF:
            _stage(session, investigation, InvestigationStatus.GENERATING_BRIEF)
        _build_brief(session, investigation)
        _stage(session, investigation, InvestigationStatus.COMPLETE)
        job.status = "COMPLETE"
        job.stage = "COMPLETE"
        job.error_code = None
        _audit(session, investigation.id, "INVESTIGATION_COMPLETED", {})
        session.commit()
        return "complete"
    except Exception as exc:
        category = (
            exc.category
            if isinstance(exc, ModelInvocationFailed)
            else FailureCategory.BUDGET_EXCEEDED
            if isinstance(exc, ModelCallBudgetExceeded)
            else FailureCategory.STORAGE_FAILED
            if isinstance(exc, MediaStorageError)
            else FailureCategory.DERIVATION_FAILED
            if isinstance(exc, ImageValidationError) and exc.code == "DERIVATION_FAILED"
            else FailureCategory.PIPELINE_ERROR
        )
        logger.error(
            "Investigation paused investigation_id=%s job_id=%s category=%s exception=%s",
            investigation.id,
            job_id,
            category.value,
            type(exc).__name__,
        )
        session.rollback()
        investigation = session.get(Investigation, job.investigation_id)
        job = session.get(ProcessingJob, job_id)
        if investigation is not None and job is not None:
            if investigation.status not in {
                InvestigationStatus.NEEDS_REVIEW,
                InvestigationStatus.FAILED,
            }:
                validate_transition(investigation.status, InvestigationStatus.NEEDS_REVIEW)
                investigation.status = InvestigationStatus.NEEDS_REVIEW
                investigation.current_stage = InvestigationStatus.NEEDS_REVIEW.value
            investigation.failure_reason = USER_FAILURE_MESSAGE
            job.status = "BLOCKED"
            job.error_code = category.value
            job.attempts += 1
            _audit(
                session,
                investigation.id,
                "INVESTIGATION_NEEDS_REVIEW",
                {"reason": category.value},
            )
            session.commit()
        return "needs_review"
