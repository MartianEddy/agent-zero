"""Entry point: run one investigation job through every stage."""

import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.investigation import InputType, InvestigationStatus, validate_transition
from app.modules.investigations.bounding import clip_text
from app.modules.investigations.image_safety import ImageValidationError
from app.modules.investigations.investigator import (
    ImageQuestionAnswer,
    ModelInvocationFailed,
)
from app.modules.investigations.job_lease import JobLeaseLost
from app.modules.investigations.models import (
    Claim,
    Evidence,
    Finding,
    Investigation,
    ProcessingJob,
    SearchTrace,
    Submission,
    utcnow,
)
from app.modules.investigations.orchestrator import (
    common,
    evidence_review,
    findings_stage,
    media_review,
    notifications,
    planning,
    ports,
    search_stage,
    settled_facts,
    sourcing,
)
from app.modules.investigations.provider_errors import FailureCategory
from app.modules.investigations.usage import (
    ModelCallBudgetExceeded,
)


# Seconds of the case budget kept for the evidence review after searching and reading.
REASONING_RESERVE_SECONDS = 40.0


def _run_widening_lane(
    session: Session,
    investigation: Investigation,
    *,
    lane: str,
    claim_indices: set[int],
    retrieved: dict,
    case_deadline: float,
) -> None:
    """Plan, search, read and persist one widening lane for the claims that still need it."""
    planning._plan_widened_queries(
        session, investigation, source_lane=lane, claim_indices=claim_indices
    )
    search_stage._execute_searches(
        session,
        investigation,
        source_lanes={lane},
        claim_indices=claim_indices,
        case_deadline=case_deadline,
    )
    retrieved.update(
        search_stage._retrieve_candidates(
            session, investigation, source_lanes={lane}, case_deadline=case_deadline
        )
    )
    evidence_review._persist_evidence(session, investigation, retrieved)
    evidence_review._detect_source_relationships(session, investigation, retrieved)


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
    case_deadline = ports.monotonic() + getattr(
        ports.get_settings(), "investigation_deadline_seconds", 120.0
    )
    # Searching and reading stop early enough to leave the evidence review its time:
    # without it a case ends "not enough evidence" even when supporting passages were read.
    research_deadline = case_deadline - REASONING_RESERVE_SECONDS
    try:
        if investigation.status == InvestigationStatus.RECEIVED:
            common._stage(session, investigation, InvestigationStatus.PROCESSING)
        elif investigation.status in {InvestigationStatus.NEEDS_REVIEW, InvestigationStatus.FAILED}:
            common._stage(session, investigation, InvestigationStatus.PROCESSING)
        common._stage(session, investigation, InvestigationStatus.ANALYZING)
        submission = session.scalar(
            select(Submission)
            .where(Submission.investigation_id == investigation.id)
            .order_by(Submission.received_at)
        )
        text = submission.original_text if submission and submission.original_text else ""
        submitted_url = text if investigation.input_type == InputType.URL else None
        assets = common._original_media_assets(session, investigation.id)
        images = media_review._load_or_inspect_media(session, investigation, assets)
        url_source = sourcing._ensure_submitted_url_source(session, investigation, submitted_url)
        url_text = (
            sourcing._save_retrieved_source(
                session,
                investigation,
                url_source,
                timeout_seconds=max(0.1, case_deadline - ports.monotonic()),
            )
            if url_source
            else None
        )
        model_input = text
        if url_text:
            bounded_url_text = clip_text(
                url_text, ports.get_settings().max_model_input_chars - 1_500
            )
            model_input = sourcing._submitted_source_prompt(
                url_source, bounded_url_text, submitted_url
            )
        received_at = investigation.created_at
        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=utcnow().tzinfo)
        model_input = (
            f"INVESTIGATION RECEIVED AT: {received_at.isoformat()} (UTC; submitter timezone unknown).\n"
            + common._relative_date_context(model_input, received_at)
            + "\n"
            + model_input
        )

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
        summary_override = None
        if submitted_url and not url_text and not claims_exist:
            ports.add_limitation(
                session,
                investigation.id,
                "Agent 0 could not independently retrieve the submitted page; "
                "no article claims were inferred.",
            )
            planning._persist_plan(
                session,
                investigation,
                planning._url_only_fallback_plan(submitted_url),
                allow_unassociated_queries=True,
            )
            summary_override = (
                "I couldn’t open the submitted page, so I couldn’t identify the claim it makes. "
                "Share an accessible link or paste the passage you want checked. I haven’t assessed "
                "it as true or false."
            )
        elif not claims_exist or not planned_exist:
            model_run = ports.ModelGateway().extract_claims_and_queries(
                text=model_input,
                images=images,
                session=session,
                investigation_id=investigation.id,
            )
            planning._persist_plan(session, investigation, model_run.output)
            if not model_run.output.claims:
                clarification = (model_run.output.clarification_question or "").strip()
                if clarification:
                    summary_override = (
                        "I need one more detail before I can check this fairly: "
                        f"{clarification} I haven’t assessed it as true or false."
                    )
                elif submitted_url and not url_text:
                    summary_override = (
                        "I couldn’t open the submitted page, so I couldn’t identify the claim "
                        "it makes. Share an accessible link or paste the passage you want checked. "
                        "I haven’t assessed it as true or false."
                    )
                elif images and investigation.input_type == InputType.IMAGE:
                    summary_override = (
                        "I reviewed the image’s available visual and file checks, but they do not "
                        "establish where or when the depicted event happened. Share the original "
                        "post or a source page to investigate its context."
                    )
                elif images and investigation.input_type == InputType.VIDEO:
                    summary_override = (
                        "I sampled visual frames from the video, but couldn’t identify a specific "
                        "claim that those frames could check. Audio was not transcribed. Share the "
                        "spoken claim, a transcript, or the original source to continue."
                    )
                else:
                    summary_override = (
                        "I couldn’t identify a specific, checkable factual claim in this request. "
                        "Share the exact statement, who or what it concerns, and any relevant date "
                        "or place. I haven’t assessed it as true or false."
                    )
        else:
            planning._persist_plan(
                session, investigation, planning._load_plan(session, investigation.id)
            )

        media_review._link_unclaimed_media_evidence(session, investigation)
        if images and investigation.input_type != InputType.URL:
            media_review._persist_visual_observations(
                session, investigation, images, ports.ModelGateway()
            )

        fast_path_deadline = min(case_deadline, ports.monotonic() + 5.0)
        fast_path_indices = settled_facts._run_fast_path_claims(
            session,
            investigation,
            case_deadline=min(case_deadline, ports.monotonic() + 45.0),
            lookup_deadline=min(fast_path_deadline, research_deadline),
        )
        searchable_indices = {
            index
            for index, claim in enumerate(
                session.scalars(
                    select(Claim)
                    .where(Claim.investigation_id == investigation.id)
                    .order_by(Claim.created_at, Claim.id)
                )
            )
            if index not in fast_path_indices and claim.claim_type != "OPINION_OR_PREDICTION"
        }
        common._stage(session, investigation, InvestigationStatus.RESEARCHING)
        search_stage._execute_searches(
            session,
            investigation,
            source_lanes={"PRIMARY"},
            claim_indices=searchable_indices,
            case_deadline=research_deadline,
        )
        common._stage(session, investigation, InvestigationStatus.CORROBORATING)
        settings = ports.get_settings()
        primary_retrieval_cap = max(1, settings.max_retrieved_sources - 2)
        retrieved = search_stage._retrieve_candidates(
            session,
            investigation,
            source_lanes={"PRIMARY"},
            retrieval_cap=primary_retrieval_cap,
            case_deadline=research_deadline,
        )
        evidence_review._persist_evidence(session, investigation, retrieved)
        evidence_review._detect_source_relationships(session, investigation, retrieved)

        for lane in ("REFERENCE_REPORTING", "FACT_CHECK"):
            needing = (
                planning._claims_needing_independent_sources(session, investigation)
                - fast_path_indices
            )
            if needing:
                _run_widening_lane(
                    session,
                    investigation,
                    lane=lane,
                    claim_indices=needing,
                    retrieved=retrieved,
                    case_deadline=research_deadline,
                )
            else:
                planning._mark_routes_not_needed(session, investigation, source_lanes={lane})

        search_stage._execute_searches(
            session,
            investigation,
            source_lanes={"SOCIAL"},
            claim_indices=searchable_indices,
            case_deadline=research_deadline,
        )
        retrieved.update(
            search_stage._retrieve_candidates(session, investigation, case_deadline=research_deadline)
        )
        evidence_review._detect_source_relationships(session, investigation, retrieved)
        claims = list(
            session.scalars(select(Claim).where(Claim.investigation_id == investigation.id))
        )
        evidence_exists = evidence_review._has_claim_linked_evidence(session, investigation)
        if claims:
            has_missing_findings = any(
                session.scalar(select(Finding.id).where(Finding.claim_id == claim.id).limit(1))
                is None
                for claim in claims
            )
            if has_missing_findings:
                common._stage(session, investigation, InvestigationStatus.GENERATING_BRIEF)
                remaining_seconds = case_deadline - ports.monotonic()
                if remaining_seconds <= 0:
                    ports.add_limitation(
                        session,
                        investigation.id,
                        "Case deadline reached; evidence reasoning was cut.",
                    )
                    findings_stage._create_unverified_findings(session, investigation)
                else:
                    result = ports.ModelGateway().reason_about_evidence(
                        evidence_packet=evidence_review._evidence_packet(session, investigation),
                        session=session,
                        investigation_id=investigation.id,
                        timeout_seconds=remaining_seconds,
                    )
                    findings_stage._persist_findings(session, investigation, result.output)
        else:
            findings_stage._create_unverified_findings(session, investigation)
            ai_origin_question = re.search(
                r"\b(ai[- ]?generated|synthetic|deepfake|made by ai|created with ai|ai[- ]?made)\b",
                text,
                re.I,
            )
            if images and investigation.input_type == InputType.IMAGE and ai_origin_question:
                media_rows = list(
                    session.scalars(
                        select(Evidence)
                        .where(
                            Evidence.investigation_id == investigation.id,
                            Evidence.method.in_(common.MEDIA_PACKET_METHODS),
                        )
                        .order_by(Evidence.created_at)
                    )
                )
                signals = (
                    "\n".join(
                        f"{item.method}: {media_review._media_packet_excerpt(item)}"
                        for item in media_rows
                    )
                    or "No image checks were recorded."
                )
                try:
                    response = ports.ModelGateway().answer_image_origin_question(
                        question=text,
                        signals=signals,
                        session=session,
                        investigation_id=investigation.id,
                    )
                    if isinstance(response.output, ImageQuestionAnswer):
                        summary_override = response.output.answer.strip()[:700]
                except (ModelInvocationFailed, ModelCallBudgetExceeded):
                    ports.add_limitation(
                        session,
                        investigation.id,
                        "A direct image-origin response could not be generated; the recorded checks remain available.",
                    )
        if claims and not evidence_exists:
            ports.add_limitation(
                session,
                investigation.id,
                "No retrieved evidence was available; findings remain unverified.",
            )
        if investigation.status != InvestigationStatus.GENERATING_BRIEF:
            common._stage(session, investigation, InvestigationStatus.GENERATING_BRIEF)
        findings_stage._build_brief(session, investigation, summary_override=summary_override)
        common._stage(session, investigation, InvestigationStatus.COMPLETE)
        job.status = "COMPLETE"
        job.stage = "COMPLETE"
        job.error_code = None
        common._audit(session, investigation.id, "INVESTIGATION_COMPLETED", {})
        notifications._queue_whatsapp_result_notification(session, investigation, job)
        session.commit()
        return "complete"
    except Exception as exc:
        if isinstance(exc, JobLeaseLost):
            session.rollback()
            common.logger.warning(
                "Stopped stale investigation worker investigation_id=%s job_id=%s",
                investigation.id,
                job_id,
            )
            return "lease_lost"
        category = (
            exc.category
            if isinstance(exc, ModelInvocationFailed)
            else FailureCategory.BUDGET_EXCEEDED
            if isinstance(exc, ModelCallBudgetExceeded)
            else FailureCategory.STORAGE_FAILED
            if isinstance(exc, common.MediaStorageError)
            else FailureCategory.DERIVATION_FAILED
            if isinstance(exc, ImageValidationError) and exc.code == "DERIVATION_FAILED"
            else FailureCategory.PIPELINE_ERROR
        )
        common.logger.error(
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
            investigation.failure_reason = common.USER_FAILURE_MESSAGE
            job.status = "BLOCKED"
            job.error_code = category.value
            job.attempts += 1
            common._audit(
                session,
                investigation.id,
                "INVESTIGATION_NEEDS_REVIEW",
                {"reason": category.value},
            )
            notifications._queue_whatsapp_result_notification(session, investigation, job)
            session.commit()
        return "needs_review"
