import hashlib
import json
import uuid
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.domain.investigation import InputType
from app.modules.investigations.image_safety import ImageValidationError, validate_image
from app.modules.investigations.media.provenance import public_provenance_summary
from app.modules.investigations.models import (
    AuditEvent,
    Claim,
    ClaimEvidence,
    Evidence,
    Finding,
    FindingEvidence,
    Investigation,
    InvestigationUsage,
    MediaAnalysisRun,
    MediaAsset,
    OutboxEvent,
    ProcessingJob,
    SearchTrace,
    Source,
    SourceRelationship,
    Submission,
    VerificationBrief,
)
from app.modules.investigations.investigator import ModelGateway, ModelInvocationFailed
from app.modules.investigations.schemas import (
    CreateInvestigationRequest,
    ContinueInvestigationRequest,
    InvestigationHistoryResponse,
    InvestigationResponse,
    TriageRequest,
)
from app.modules.investigations.service import DEV_USER_ID, InvestigationService
from app.modules.sources.registry import classify_source
from app.storage.s3 import delete_private_object, get_private_object, put_private_object

router = APIRouter(prefix="/investigations", tags=["investigations"])
DbSession = Annotated[Session, Depends(get_db)]


def current_owner_id() -> UUID:
    settings = get_settings()
    if settings.app_env not in {"development", "test"} or settings.auth_mode != "disabled":
        raise HTTPException(status_code=503, detail="Authentication adapter is not configured")
    return DEV_USER_ID


def _enqueue_confirmed_draft(session: Session, investigation: Investigation) -> ProcessingJob:
    job = ProcessingJob(
        investigation_id=investigation.id,
        stage="RECEIVED",
        status="QUEUED",
        idempotency_key=f"triage-confirmed:{investigation.id}:{uuid4().hex}",
    )
    session.add(job)
    session.flush()
    session.add(
        OutboxEvent(
            aggregate_id=investigation.id,
            event_type="INVESTIGATION_RECEIVED",
            payload={"investigation_id": str(investigation.id), "job_id": str(job.id)},
        )
    )
    investigation.current_stage = "RECEIVED"
    session.add(
        AuditEvent(
            investigation_id=investigation.id,
            event_type="TRIAGE_CONFIRMED",
            actor="local-development-user",
            event_metadata={"claim_count": session.scalar(
                select(func.count()).select_from(Claim).where(
                    Claim.investigation_id == investigation.id
                )
            )},
        )
    )
    return job


@router.post("/triage")
def triage_submission(body: TriageRequest, session: DbSession) -> dict[str, object]:
    """Run structured claim triage, then pause for human edits before queueing research."""
    owner_id = current_owner_id()
    draft = InvestigationService(session).create(
        owner_id=owner_id,
        content=body.content,
        input_type=body.input_type,
        idempotency_key=f"triage:{uuid4().hex}",
        enqueue=False,
    )
    draft.current_stage = "TRIAGE_PENDING"
    session.commit()
    try:
        result = ModelGateway().extract_claims_and_queries(
            text=body.content,
            images=[],
            session=session,
            investigation_id=draft.id,
        )
    except ModelInvocationFailed as exc:
        session.delete(draft)
        session.commit()
        detail = (
            "Claim triage is unavailable because OpenAI is not configured. No source check was started."
            if exc.category.value == "AUTHENTICATION_FAILED"
            else "Claim triage could not complete with the configured OpenAI provider. No source check was started."
        )
        raise HTTPException(status_code=503, detail=detail) from exc
    from app.modules.investigations.orchestrator import _persist_plan

    _persist_plan(session, draft, result.output)
    if not result.output.claims:
        clarification = result.output.clarification_question or (
            "Please share one specific factual statement, including the subject and relevant time or place."
        )
        session.delete(draft)
        session.commit()
        return {"claims": [], "clarification_question": clarification, "draft_id": None}
    draft.current_stage = "TRIAGE_PENDING"
    session.add(
        AuditEvent(
            investigation_id=draft.id,
            event_type="CLAIM_TRIAGE_COMPLETED",
            actor="openai",
            event_metadata={"claim_count": len(result.output.claims), "model": result.model},
        )
    )
    session.commit()
    claims = list(
        session.scalars(
            select(Claim).where(Claim.investigation_id == draft.id).order_by(Claim.created_at, Claim.id)
        )
    )
    return {
        "draft_id": str(draft.id),
        "claims": [
            {
                "text": claim.text,
                "claim_type": claim.claim_type,
                "needs_deep_investigation": claim.needs_deep_investigation,
            }
            for claim in claims
        ],
        "clarification_question": result.output.clarification_question,
        "triage_provider": result.provider,
        "triage_model": result.model,
    }


@router.post("/{investigation_id}/continue", response_model=InvestigationResponse, status_code=status.HTTP_202_ACCEPTED)
def continue_triaged_investigation(
    investigation_id: UUID,
    body: ContinueInvestigationRequest,
    session: DbSession,
) -> InvestigationResponse:
    owner_id = current_owner_id()
    investigation = session.scalar(
        select(Investigation).where(
            Investigation.id == investigation_id,
            Investigation.owner_id == owner_id,
        ).with_for_update()
    )
    if investigation is None or investigation.current_stage != "TRIAGE_PENDING":
        raise HTTPException(status_code=404, detail="Triage draft not found or already continued")
    prior = list(
        session.scalars(
            select(Claim).where(Claim.investigation_id == investigation.id).order_by(Claim.created_at, Claim.id)
        )
    )
    changed = len(prior) != len(body.claims) or any(
        old.text != new.text
        or old.claim_type != new.claim_type
        or old.needs_deep_investigation != new.needs_deep_investigation
        for old, new in zip(prior, body.claims, strict=False)
    )
    if changed:
        for claim in prior:
            session.delete(claim)
        session.execute(delete(SearchTrace).where(SearchTrace.investigation_id == investigation.id))
        session.flush()
        session.add_all(
            [
                Claim(
                    investigation_id=investigation.id,
                    text=item.text,
                    normalized_text=" ".join(item.text.casefold().split()),
                    claim_type=item.claim_type,
                    needs_deep_investigation=item.needs_deep_investigation,
                )
                for item in body.claims
            ]
        )
    _enqueue_confirmed_draft(session, investigation)
    session.commit()
    session.refresh(investigation)
    return InvestigationResponse.model_validate(investigation)


@router.post("", response_model=InvestigationResponse, status_code=status.HTTP_202_ACCEPTED)
def create_investigation(
    body: CreateInvestigationRequest,
    session: DbSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> InvestigationResponse:
    owner_id = current_owner_id()
    investigation = InvestigationService(session).create(
        owner_id=owner_id,
        content=body.content,
        input_type=body.input_type,
        idempotency_key=(
            f"{owner_id}:{idempotency_key}" if idempotency_key else f"{owner_id}:{uuid4()}"
        ),
    )
    return InvestigationResponse.model_validate(investigation)


@router.get("", response_model=list[InvestigationResponse])
def list_investigations(session: DbSession) -> list[InvestigationResponse]:
    owner_id = current_owner_id()
    return [
        InvestigationResponse.model_validate(item)
        for item in InvestigationService(session).list_recent(owner_id=owner_id)
    ]


@router.get("/history", response_model=list[InvestigationHistoryResponse])
def list_investigation_history(session: DbSession) -> list[InvestigationHistoryResponse]:
    """Return one compact, bounded page for the workspace history view."""
    owner_id = current_owner_id()
    investigations = InvestigationService(session).list_recent(owner_id=owner_id, limit=50)
    if not investigations:
        return []
    ids = [item.id for item in investigations]
    first_claim: dict[UUID, str] = {}
    for claim in session.scalars(
        select(Claim)
        .where(Claim.investigation_id.in_(ids))
        .order_by(Claim.created_at, Claim.id)
    ):
        first_claim.setdefault(claim.investigation_id, claim.text)
    first_finding: dict[UUID, str] = {}
    for finding in session.scalars(
        select(Finding)
        .where(Finding.investigation_id.in_(ids))
        .order_by(Finding.created_at, Finding.id)
    ):
        first_finding.setdefault(finding.investigation_id, finding.status)
    source_counts = dict(
        session.execute(
            select(Source.investigation_id, func.count(Source.id))
            .where(Source.investigation_id.in_(ids))
            .group_by(Source.investigation_id)
        ).all()
    )
    return [
        InvestigationHistoryResponse(
            id=item.id,
            reference=item.reference,
            status=item.status,
            input_type=item.input_type,
            current_stage=item.current_stage,
            created_at=item.created_at,
            title=(first_claim.get(item.id) or {
                InputType.IMAGE: "Image investigation",
                InputType.VIDEO: "Video investigation",
                InputType.AUDIO: "Audio investigation",
                InputType.DOCUMENT: "Document investigation",
                InputType.URL: "Public source investigation",
                InputType.TEXT: "Claim investigation",
            }[item.input_type]),
            finding_status=first_finding.get(item.id),
            sources_count=int(source_counts.get(item.id, 0)),
        )
        for item in investigations
    ]


@router.get("/reference/{reference}", response_model=InvestigationResponse)
def get_investigation_by_reference(reference: str, session: DbSession) -> InvestigationResponse:
    investigation = session.scalar(
        select(Investigation).where(
            Investigation.reference == reference.strip().upper(),
            Investigation.owner_id == current_owner_id(),
        )
    )
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return InvestigationResponse.model_validate(investigation)


@router.get("/{investigation_id}", response_model=InvestigationResponse)
def get_investigation(investigation_id: UUID, session: DbSession) -> InvestigationResponse:
    investigation = InvestigationService(session).get(
        investigation_id=investigation_id,
        owner_id=current_owner_id(),
    )
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return InvestigationResponse.model_validate(investigation)


@router.post(
    "/{investigation_id}/retry",
    response_model=InvestigationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_investigation(investigation_id: UUID, session: DbSession) -> InvestigationResponse:
    owner_id = current_owner_id()
    investigation = session.scalar(
        select(Investigation)
        .where(
            Investigation.id == investigation_id,
            Investigation.owner_id == owner_id,
        )
        .with_for_update()
    )
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    if investigation.status.value not in {"NEEDS_REVIEW", "FAILED"}:
        raise HTTPException(status_code=409, detail="This investigation is not available to retry")
    latest_job = session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.investigation_id == investigation_id)
        .order_by(ProcessingJob.created_at.desc())
        .with_for_update()
    )
    if latest_job is None or latest_job.status in {"QUEUED", "RUNNING"}:
        raise HTTPException(status_code=409, detail="An investigation retry is already in progress")
    usage = session.scalar(
        select(InvestigationUsage).where(InvestigationUsage.investigation_id == investigation_id)
    )
    if usage is not None and usage.model_calls >= get_settings().max_model_calls_per_investigation:
        raise HTTPException(
            status_code=409, detail="The investigation model-call budget is exhausted"
        )
    job = ProcessingJob(
        investigation_id=investigation_id,
        stage="RECEIVED",
        status="QUEUED",
        idempotency_key=f"retry:{investigation_id}:{uuid4().hex}",
    )
    session.add(job)
    session.flush()
    session.add_all(
        [
            OutboxEvent(
                aggregate_id=investigation_id,
                event_type="INVESTIGATION_RETRIED",
                payload={"investigation_id": str(investigation_id), "job_id": str(job.id)},
            ),
            AuditEvent(
                investigation_id=investigation_id,
                event_type="INVESTIGATION_RETRIED",
                actor="local-development-user",
                event_metadata={"previous_job_id": str(latest_job.id)},
            ),
        ]
    )
    session.commit()
    session.refresh(investigation)
    return InvestigationResponse.model_validate(investigation)


@router.post("/media", response_model=InvestigationResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_media_investigation(
    session: DbSession,
    file: Annotated[UploadFile, File()],
    prompt: Annotated[str, Form(max_length=2000)] = "",
    triage_id: Annotated[str | None, Form()] = None,
    claims_json: Annotated[str | None, Form(max_length=12000)] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> InvestigationResponse:
    settings = get_settings()
    owner_id = current_owner_id()
    data = await file.read(settings.max_media_bytes + 1)
    if len(data) > settings.max_media_bytes:
        raise HTTPException(
            status_code=413,
            detail={"code": "UPLOAD_TOO_LARGE", "message": "Media exceeds the upload limit"},
        )
    if not data:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_MEDIA", "message": "Media file is empty"},
        )

    media_type: str
    mime_type: str
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        media_type, mime_type = "IMAGE", "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        media_type, mime_type = "IMAGE", "image/jpeg"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        media_type, mime_type = "IMAGE", "image/webp"
    elif (
        len(data) >= 12
        and data[4:8] == b"ftyp"
        and data[8:12] in {b"isom", b"iso2", b"mp41", b"mp42", b"avc1", b"M4V ", b"qt  "}
    ):
        media_type, mime_type = "VIDEO", "video/mp4"
    elif data.startswith(b"\x1aE\xdf\xa3"):
        media_type, mime_type = "VIDEO", "video/webm"
    else:
        raise HTTPException(
            status_code=415,
            detail={
                "code": "UNSUPPORTED_MEDIA_TYPE",
                "message": "Only PNG, JPEG, WebP, MP4 and WebM are accepted",
            },
        )

    if media_type == "IMAGE":
        try:
            decoded = validate_image(data, file.content_type, settings.max_image_pixels)
        except ImageValidationError as exc:
            status_code = (
                413
                if exc.code == "IMAGE_PIXEL_LIMIT_EXCEEDED"
                else 415
                if exc.code == "UNSUPPORTED_MEDIA_TYPE"
                else 422
            )
            raise HTTPException(
                status_code=status_code, detail={"code": exc.code, "message": str(exc)}
            ) from exc
        mime_type = str(decoded["mime_type"])

    asset_id = uuid.uuid4()
    key = f"private/{owner_id}/{asset_id.hex}"
    try:
        try:
            put_private_object(key=key, data=data, content_type=mime_type)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "STORAGE_FAILED", "message": "Media storage is unavailable"},
            ) from exc
        media_asset = {
                "id": asset_id,
                "storage_key": key,
                "media_type": media_type,
                "mime_type": mime_type,
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "metadata_json": {},
            }
        if triage_id:
            try:
                draft_uuid = UUID(triage_id)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="Triage reference is invalid") from exc
            investigation = session.scalar(
                select(Investigation).where(
                    Investigation.id == draft_uuid,
                    Investigation.owner_id == owner_id,
                    Investigation.current_stage == "TRIAGE_PENDING",
                ).with_for_update()
            )
            if investigation is None:
                raise HTTPException(status_code=404, detail="Triage draft not found")
            if claims_json:
                try:
                    edited = ContinueInvestigationRequest.model_validate({"claims": json.loads(claims_json)})
                except (ValueError, TypeError) as exc:
                    raise HTTPException(status_code=422, detail="Edited triage claims are invalid") from exc
                prior_claims = list(session.scalars(select(Claim).where(Claim.investigation_id == investigation.id)))
                for claim in prior_claims:
                    session.delete(claim)
                session.execute(delete(SearchTrace).where(SearchTrace.investigation_id == investigation.id))
                session.flush()
                session.add_all([
                    Claim(
                        investigation_id=investigation.id,
                        text=item.text,
                        normalized_text=" ".join(item.text.casefold().split()),
                        claim_type=item.claim_type,
                        needs_deep_investigation=item.needs_deep_investigation,
                    )
                    for item in edited.claims
                ])
                session.flush()
            investigation.input_type = InputType(media_type)
            submission = session.scalar(
                select(Submission)
                .where(Submission.investigation_id == investigation.id)
                .order_by(Submission.received_at)
            )
            if submission is not None:
                submission.input_type = InputType(media_type)
                if prompt.strip():
                    submission.original_text = prompt.strip()
            session.add(MediaAsset(investigation_id=investigation.id, **media_asset))
            session.flush()
            _enqueue_confirmed_draft(session, investigation)
            session.commit()
            session.refresh(investigation)
        else:
            investigation = InvestigationService(session).create(
                owner_id=owner_id,
                content=prompt.strip()
                or "Please inspect the submitted media and identify verifiable claims.",
                input_type=InputType(media_type),
                idempotency_key=(
                    f"{owner_id}:{idempotency_key}"
                    if idempotency_key
                    else f"{owner_id}:{uuid4()}"
                ),
                media_asset=media_asset,
            )
        if session.get(MediaAsset, asset_id) is None:
            delete_private_object(key=key)
    except Exception:
        try:
            delete_private_object(key=key)
        except Exception:
            pass
        raise
    return InvestigationResponse.model_validate(investigation)


@router.get("/{investigation_id}/media-preview")
def get_investigation_media_preview(investigation_id: UUID, session: DbSession) -> Response:
    """Serve only the normalized, metadata-stripped image derivative for display."""
    investigation = InvestigationService(session).get(
        investigation_id=investigation_id,
        owner_id=current_owner_id(),
    )
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    original = session.scalar(
        select(MediaAsset).where(
            MediaAsset.investigation_id == investigation_id,
            MediaAsset.asset_role == "ORIGINAL",
            MediaAsset.media_type == "IMAGE",
        )
    )
    if original is None:
        raise HTTPException(status_code=404, detail="Image preview not found")
    derivative = session.scalar(
        select(MediaAsset).where(
            MediaAsset.investigation_id == investigation_id,
            MediaAsset.parent_asset_id == original.id,
            MediaAsset.artifact_type == "NORMALIZED_IMAGE",
        )
    )
    if derivative is None:
        raise HTTPException(status_code=404, detail="Image preview is not ready")
    try:
        content = get_private_object(key=derivative.storage_key)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Image preview is unavailable") from exc
    return Response(
        content=content,
        media_type=derivative.mime_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{investigation_id}/results")
def get_investigation_results(investigation_id: UUID, session: DbSession) -> dict[str, object]:
    investigation = InvestigationService(session).get(
        investigation_id=investigation_id,
        owner_id=current_owner_id(),
    )
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    claims = list(session.scalars(select(Claim).where(Claim.investigation_id == investigation_id)))
    sources = list(
        session.scalars(select(Source).where(Source.investigation_id == investigation_id))
    )
    media_assets = list(
        session.scalars(select(MediaAsset).where(MediaAsset.investigation_id == investigation_id))
    )
    source_relationships = list(
        session.scalars(
            select(SourceRelationship).where(
                SourceRelationship.investigation_id == investigation_id
            )
        )
    )
    evidence = list(
        session.scalars(select(Evidence).where(Evidence.investigation_id == investigation_id))
    )
    media_analysis_runs = list(
        session.scalars(
            select(MediaAnalysisRun).where(
                MediaAnalysisRun.investigation_id == investigation_id,
                MediaAnalysisRun.analyzer_id == "C2PA",
            )
        )
    )
    findings = list(
        session.scalars(select(Finding).where(Finding.investigation_id == investigation_id))
    )
    finding_ids = [item.id for item in findings]
    finding_evidence: dict[UUID, list[UUID]] = {}
    if finding_ids:
        for link in session.scalars(
            select(FindingEvidence)
            .where(FindingEvidence.finding_id.in_(finding_ids))
            .order_by(FindingEvidence.id)
        ):
            finding_evidence.setdefault(link.finding_id, []).append(link.evidence_id)
    claim_evidence = list(
        session.scalars(
            select(ClaimEvidence)
            .join(Claim, ClaimEvidence.claim_id == Claim.id)
            .where(Claim.investigation_id == investigation_id)
        )
    )
    search_traces = list(
        session.scalars(select(SearchTrace).where(SearchTrace.investigation_id == investigation_id))
    )
    brief = session.scalar(
        select(VerificationBrief).where(VerificationBrief.investigation_id == investigation_id)
    )
    model_event = session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.investigation_id == investigation_id,
            AuditEvent.event_type.in_(["INVESTIGATION_COMPLETED", "INVESTIGATION_NEEDS_REVIEW"]),
        )
        .order_by(AuditEvent.created_at.desc())
    )
    usage = session.scalar(
        select(InvestigationUsage).where(InvestigationUsage.investigation_id == investigation_id)
    )
    latest_job = session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.investigation_id == investigation_id)
        .order_by(ProcessingJob.created_at.desc())
    )
    evidence_source = {item.id: item.source_id for item in evidence}
    source_by_id = {item.id: item for item in sources}
    evidence_media_asset = {item.id: item.media_asset_id for item in evidence}
    media_asset_by_id = {item.id: item for item in media_assets}
    c2pa_run_by_id = {item.id: item for item in media_analysis_runs}
    registry_by_id = {item.id: classify_source(item.domain or "") for item in sources}
    claim_ids_with_evidence = {link.claim_id for link in claim_evidence}
    findings_with_evidence = 0
    finding_payload = []
    for item in findings:
        linked_ids = finding_evidence.get(item.id, [])
        findings_with_evidence += bool(linked_ids)
        finding_payload.append(
            {
                "id": str(item.id),
                "claim_id": str(item.claim_id),
                "status": item.status,
                "statement": item.statement,
                "evidence_confidence": item.evidence_confidence,
                "confidence_rationale": item.confidence_rationale,
                "explanation": item.explanation_json or [],
                "unsupported_statements_removed": item.unsupported_statements_removed,
                "limitations": item.limitations,
                "evidence_ids": [str(evidence_id) for evidence_id in linked_ids],
            }
        )
    return {
        "investigation_id": str(investigation_id),
        "status": investigation.status.value,
        "current_stage": investigation.current_stage,
        "model_run": (
            model_event.event_metadata.get("model_run")
            if model_event and isinstance(model_event.event_metadata.get("model_run"), dict)
            else model_event.event_metadata
            if model_event
            else None
        ),
        "usage_summary": (
            {
                "model_calls": usage.model_calls,
                "search_calls": usage.search_calls,
                "sources_discovered": usage.sources_discovered,
                "sources_retrieved": usage.sources_retrieved,
                "input_tokens": usage.input_tokens,
                "cached_input_tokens": usage.cached_input_tokens,
                "output_tokens": usage.output_tokens,
                "limitations": usage.limitations,
            }
            if usage
            else None
        ),
        "retry_allowed": bool(
            investigation.status.value in {"NEEDS_REVIEW", "FAILED"}
            and latest_job is not None
            and latest_job.status not in {"QUEUED", "RUNNING"}
            and (
                usage is None
                or usage.model_calls < get_settings().max_model_calls_per_investigation
            )
        ),
        "media_assets": [
            {
                "id": str(item.id),
                "media_type": item.media_type,
                "mime_type": item.mime_type,
                "size_bytes": item.size_bytes,
                "role": item.asset_role,
                "artifact_type": item.artifact_type,
                "parent_asset_id": str(item.parent_asset_id) if item.parent_asset_id else None,
            }
            for item in media_assets
        ],
        "claims": [
            {
                "id": str(item.id),
                "text": item.text,
                "type": item.claim_type,
                "needs_deep_investigation": item.needs_deep_investigation,
            }
            for item in claims
        ],
        "sources": [
            {
                "id": str(item.id),
                "url": item.url,
                "title": item.title,
                "publisher": item.publisher,
                "domain": item.domain,
                "source_type": item.source_type,
                "source_role": item.source_role,
                "registry_jurisdiction": registry_by_id[item.id].jurisdiction,
                "authoritative_for": list(registry_by_id[item.id].authoritative_for),
                "canonical_url": item.canonical_url,
                "author": item.author,
                "published_at": item.published_at,
                "modified_at": item.modified_at,
                "retrieval_status": item.retrieval_status,
                "retrieval_failure_reason": item.retrieval_failure_reason,
                "retrieval_provider": item.retrieval_provider,
                "retrieved_at": item.retrieved_at,
                "discovery_method": item.discovery_method,
                "discovery_trace_id": (
                    str(item.discovery_trace_id) if item.discovery_trace_id else None
                ),
                "content_sha256": item.content_sha256,
            }
            for item in sources
        ],
        "source_relationships": [
            {
                "source_id": str(item.source_id),
                "relationship": item.relationship_type,
                "related_source_id": str(item.related_source_id),
                "basis": item.basis,
            }
            for item in source_relationships
        ],
        "search_traces": [
            {
                "id": str(item.id),
                "provider": item.provider,
                "action": item.action,
                "call_reference": item.call_reference,
                "query": item.query,
                "route": item.route_metadata,
                "url": item.url,
                "sources": item.sources,
                "citations": item.citations,
                "created_at": item.created_at,
            }
            for item in search_traces
        ],
        "claim_evidence": [
            {
                "claim_id": str(item.claim_id),
                "evidence_id": str(item.evidence_id),
                "relationship": item.relationship,
            }
            for item in claim_evidence
        ],
        "evidence": [
            {
                "id": str(item.id),
                "content": item.content,
                "method": item.method,
                "limitations": item.limitations,
                "source_tier": item.source_tier,
                "stance": item.stance,
                "excerpt_location": (
                    {"start": item.excerpt_start, "end": item.excerpt_end}
                    if item.excerpt_start is not None and item.excerpt_end is not None else None
                ),
                "independence_group_id": item.independence_group_id,
                "published_date": item.published_date,
                "is_stale": item.is_stale,
                "retrieval_timestamp": item.retrieval_timestamp,
                "run_id": str(item.run_id) if item.run_id else None,
                "excerpt_validated": item.excerpt_validated,
                "origin": {
                    "source_id": str(item.source_id) if item.source_id else None,
                    "media_asset_id": str(item.media_asset_id) if item.media_asset_id else None,
                },
                "claim_links": [
                    {"claim_id": str(link.claim_id), "relationship": link.relationship}
                    for link in claim_evidence
                    if link.evidence_id == item.id
                ],
                "source": (
                    {
                        "id": str(source_by_id[evidence_source[item.id]].id),
                        "url": source_by_id[evidence_source[item.id]].url,
                        "retrieval_status": source_by_id[evidence_source[item.id]].retrieval_status,
                    }
                    if evidence_source[item.id] is not None
                    and evidence_source[item.id] in source_by_id
                    else None
                ),
                "media_asset": (
                    {
                        "id": str(media_asset_by_id[evidence_media_asset[item.id]].id),
                        "media_type": media_asset_by_id[evidence_media_asset[item.id]].media_type,
                        "mime_type": media_asset_by_id[evidence_media_asset[item.id]].mime_type,
                        "size_bytes": media_asset_by_id[evidence_media_asset[item.id]].size_bytes,
                        "role": media_asset_by_id[evidence_media_asset[item.id]].asset_role,
                        "artifact_type": media_asset_by_id[
                            evidence_media_asset[item.id]
                        ].artifact_type,
                        "parent_asset_id": (
                            str(media_asset_by_id[evidence_media_asset[item.id]].parent_asset_id)
                            if media_asset_by_id[evidence_media_asset[item.id]].parent_asset_id
                            else None
                        ),
                    }
                    if evidence_media_asset[item.id] is not None
                    and evidence_media_asset[item.id] in media_asset_by_id
                    else None
                ),
                "provenance": (
                    {
                        **public_provenance_summary(
                            c2pa_run_by_id[item.media_analysis_run_id].observations_json
                        ),
                        "analysis_run_id": str(item.media_analysis_run_id),
                    }
                    if item.method == "MEDIA_PROVENANCE"
                    and item.media_analysis_run_id in c2pa_run_by_id
                    and isinstance(
                        c2pa_run_by_id[item.media_analysis_run_id].observations_json, dict
                    )
                    else None
                ),
            }
            for item in evidence
        ],
        "findings": finding_payload,
        "evidence_coverage": {
            "claims_total": len(claims),
            "claims_with_linked_evidence": len(claim_ids_with_evidence),
            "claims_without_linked_evidence": len(claims) - len(claim_ids_with_evidence),
            "findings_total": len(findings),
            "findings_with_evidence": findings_with_evidence,
            "sources_total": len(sources),
            "sources_retrieved": sum(item.retrieval_status == "RETRIEVED" for item in sources),
        },
        "brief": (
            {"summary": brief.summary, "limitations": brief.limitations, "version": brief.version}
            if brief
            else None
        ),
    }
