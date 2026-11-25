"""Queue the WhatsApp result message when a case finishes."""

from uuid import uuid5

from sqlalchemy.orm import Session

from app.domain.investigation import Channel
from app.modules.investigations.models import (
    Investigation,
    OutboxEvent,
    ProcessingJob,
)
from app.modules.investigations.orchestrator import common


def _queue_whatsapp_result_notification(
    session: Session, investigation: Investigation, job: ProcessingJob
) -> None:
    if investigation.channel != Channel.WHATSAPP:
        return
    event_id = uuid5(common._WHATSAPP_NOTIFICATION_NAMESPACE, str(job.id))
    if session.get(OutboxEvent, event_id) is None:
        session.add(
            OutboxEvent(
                id=event_id,
                aggregate_id=investigation.id,
                event_type="WHATSAPP_RESULT_READY",
                payload={"job_id": str(job.id), "delivery_state": "PENDING"},
            )
        )
