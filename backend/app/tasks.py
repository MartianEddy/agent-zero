from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.investigations.models import OutboxEvent
from app.modules.investigations.orchestrator import process_investigation as run_pipeline
from app.worker import celery_app


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
    return dispatched


@celery_app.task(
    name="agent_zero.process_investigation",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_investigation(_task, job_id: str) -> str:
    """Run the channel-neutral investigation workflow in the worker process."""
    with SessionLocal() as session:
        return run_pipeline(session, job_id=UUID(job_id))
