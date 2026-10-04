import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.domain.investigation import InvestigationStatus
from app.modules.investigations.models import AuditEvent, Investigation, OutboxEvent, ProcessingJob
from app.modules.investigations.orchestrator import process_investigation as run_pipeline
from app.worker import celery_app

logger = logging.getLogger(__name__)


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
    cutoff = datetime.now(UTC) - timedelta(minutes=10)
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
                    Investigation.updated_at < cutoff,
                    ProcessingJob.status.in_(["QUEUED", "RUNNING"]),
                )
                .order_by(Investigation.updated_at)
                .limit(50)
                .with_for_update(skip_locked=True)
            ).all()
        )
        for investigation, job in rows:
            # Recheck under lock; a worker may have advanced the stage while
            # the sweep query was being assembled.
            if investigation.updated_at >= cutoff or job.status not in {"QUEUED", "RUNNING"}:
                continue
            investigation.status = InvestigationStatus.FAILED
            investigation.current_stage = InvestigationStatus.FAILED.value
            investigation.failure_reason = (
                "This investigation stopped progressing before its evidence review was complete. "
                "You can retry it; any evidence already collected remains available."
            )
            job.status = "BLOCKED"
            job.error_code = "WORKER_STALLED"
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
    logger.info("Starting investigation job job_id=%s", job_id)
    try:
        with SessionLocal() as session:
            result = run_pipeline(session, job_id=UUID(job_id))
    except Exception:
        logger.exception("Investigation job failed job_id=%s", job_id)
        raise
    logger.info("Finished investigation job job_id=%s result=%s", job_id, result)
    return result
