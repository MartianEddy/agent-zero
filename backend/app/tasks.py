import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.tracing import configure_tracing, tracer
from app.db.session import SessionLocal
from app.domain.investigation import InvestigationStatus
from app.modules.conversations.models import WhatsAppConversation
from app.modules.investigations.job_lease import (
    claim_processing_job,
    protect_job_lease,
    release_processing_job_lease,
)
from app.modules.investigations.models import AuditEvent, Investigation, OutboxEvent, ProcessingJob
from app.modules.investigations.orchestrator import process_investigation as run_pipeline
from app.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="agent_zero.expire_whatsapp_conversations")
def expire_whatsapp_conversations() -> int:
    """Delete expired conversational context and its associated model usage."""
    now = datetime.now(UTC)
    with SessionLocal() as session:
        result = session.execute(
            delete(WhatsAppConversation).where(WhatsAppConversation.expires_at <= now)
        )
        session.commit()
        return int(result.rowcount or 0)


@celery_app.task(name="agent_zero.dispatch_outbox")
def dispatch_outbox() -> int:
    """Publish committed work records; repeated delivery is safe by job ID."""
    dispatched = 0
    with SessionLocal() as session:
        events = list(
            session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.dispatched_at.is_(None))
                .order_by(OutboxEvent.created_at)
                .limit(50)
                .with_for_update(skip_locked=True)
            )
        )
        for event in events:
            celery_app.send_task(
                "agent_zero.process_investigation",
                args=[event.payload["job_id"]],
                task_id=str(event.id),
            )
            event.dispatched_at = datetime.now(UTC)
            dispatched += 1
        session.commit()
    if dispatched:
        logger.info("Dispatched investigation jobs count=%s", dispatched)
    return dispatched


@celery_app.task(name="agent_zero.recover_stalled_investigations")
def recover_stalled_investigations() -> int:
    """Stop reporting work as active when its worker has disappeared."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=10)
    recovered = 0
    active_statuses = (
        InvestigationStatus.RECEIVED,
        InvestigationStatus.PROCESSING,
        InvestigationStatus.ANALYZING,
        InvestigationStatus.RESEARCHING,
        InvestigationStatus.CORROBORATING,
        InvestigationStatus.GENERATING_BRIEF,
    )
    with SessionLocal() as session:
        rows = list(
            session.execute(
                select(Investigation, ProcessingJob)
                .join(ProcessingJob, ProcessingJob.investigation_id == Investigation.id)
                .where(
                    Investigation.status.in_(active_statuses),
                    ProcessingJob.status.in_(["QUEUED", "RUNNING"]),
                    (
                        (ProcessingJob.status == "RUNNING")
                        & ProcessingJob.lease_expires_at.is_not(None)
                        & (ProcessingJob.lease_expires_at <= now)
                    )
                    | ((ProcessingJob.status == "QUEUED") & (Investigation.updated_at < cutoff))
                    | (
                        (ProcessingJob.status == "RUNNING")
                        & ProcessingJob.lease_expires_at.is_(None)
                        & (Investigation.updated_at < cutoff)
                    ),
                )
                .order_by(Investigation.updated_at)
                .limit(50)
                .with_for_update(skip_locked=True)
            ).all()
        )
        for investigation, job in rows:
            # Recheck under lock; a worker may have advanced the stage while
            # the sweep query was being assembled.
            lease_expires_at = job.lease_expires_at
            if lease_expires_at is not None and lease_expires_at.tzinfo is None:
                lease_expires_at = lease_expires_at.replace(tzinfo=UTC)
            lease_expired = lease_expires_at is not None and lease_expires_at <= now
            stale_legacy_or_queued = (
                job.lease_expires_at is None and investigation.updated_at < cutoff
            )
            if job.status not in {"QUEUED", "RUNNING"} or not (
                lease_expired or stale_legacy_or_queued
            ):
                continue
            investigation.status = InvestigationStatus.FAILED
            investigation.current_stage = InvestigationStatus.FAILED.value
            investigation.failure_reason = (
                "This investigation stopped progressing before its evidence review was complete. "
                "You can retry it; any evidence already collected remains available."
            )
            job.status = "BLOCKED"
            job.error_code = "WORKER_STALLED"
            job.lease_token = None
            job.lease_expires_at = None
            job.attempts += 1
            session.add(
                AuditEvent(
                    investigation_id=investigation.id,
                    event_type="INVESTIGATION_WORKER_STALLED",
                    actor="system",
                    event_metadata={"last_stage": job.stage},
                )
            )
            recovered += 1
        if recovered:
            session.commit()
    if recovered:
        logger.warning("Marked stalled investigations for retry count=%s", recovered)
    return recovered


@celery_app.task(
    name="agent_zero.process_investigation",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_investigation(_task, job_id: str) -> str:
    """Run the channel-neutral investigation workflow in the worker process."""
    configure_tracing(get_settings().otel_exporter_otlp_endpoint)
    logger.info("Starting investigation job job_id=%s", job_id)
    try:
        with tracer(__name__).start_as_current_span(
            "investigation.process", record_exception=False, set_status_on_exception=False
        ) as span:
            span.set_attribute("agent_zero.job_id", job_id)
            with SessionLocal() as session:
                lease = claim_processing_job(session, UUID(job_id))
                if lease is None:
                    logger.info("Skipped duplicate investigation delivery job_id=%s", job_id)
                    span.set_attribute("agent_zero.job.duplicate", True)
                    return "already_claimed"
                result: str | None = None
                try:
                    with protect_job_lease(session, lease, SessionLocal) as lease_lost:
                        result = run_pipeline(session, job_id=UUID(job_id))
                        if lease_lost.is_set():
                            result = "lease_lost"
                finally:
                    session.rollback()
                    if result is not None and result != "lease_lost":
                        release_processing_job_lease(session, lease)
    except Exception:
        logger.exception("Investigation job failed job_id=%s", job_id)
        raise
    if result is None:
        raise RuntimeError("Investigation pipeline returned without a result")
    logger.info("Finished investigation job job_id=%s result=%s", job_id, result)
    return result
