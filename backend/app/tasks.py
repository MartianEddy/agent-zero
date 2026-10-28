import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.tracing import configure_tracing, tracer
from app.db.session import SessionLocal
from app.domain.investigation import InvestigationStatus
from app.modules.conversations.models import (
    WhatsAppConversation,
    WhatsAppNotificationPreference,
)
from app.modules.investigations.job_lease import (
    claim_processing_job,
    protect_job_lease,
    release_processing_job_lease,
)
from app.modules.investigations.models import (
    AuditEvent,
    Investigation,
    OutboxEvent,
    ProcessingJob,
    Submission,
)
from app.modules.investigations.orchestrator import (
    _queue_whatsapp_result_notification,
)
from app.modules.investigations.orchestrator import (
    process_investigation as run_pipeline,
)
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
            if event.event_type == "WHATSAPP_RESULT_READY":
                celery_app.send_task(
                    "agent_zero.send_whatsapp_result_notification",
                    args=[str(event.id)],
                    task_id=str(event.id),
                )
            else:
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


@celery_app.task(name="agent_zero.send_whatsapp_result_notification", acks_late=True)
def send_whatsapp_result_notification(event_id: str) -> str:
    """Send a saved result once, only inside the user's open 24-hour reply window."""
    from app.domain.investigation import Channel
    from app.modules.channels.whatsapp import (
        WhatsAppConfigurationError,
        _configured_settings,
        send_text_message,
    )
    from app.modules.conversations.service import _decrypt_recipient, _result_message

    now = datetime.now(UTC)
    with SessionLocal() as session:
        event = session.get(OutboxEvent, UUID(event_id))
        if event is None:
            return "missing"
        payload = dict(event.payload or {})
        if payload.get("delivery_state") != "PENDING":
            return str(payload.get("delivery_state", "unknown")).lower()
        event.payload = {**payload, "delivery_state": "SENDING"}
        session.commit()

        investigation = session.get(Investigation, event.aggregate_id)
        if investigation is None or investigation.channel != Channel.WHATSAPP:
            delivery_state = "SKIPPED"
            reason = "not_whatsapp_case"
        else:
            submission = session.scalar(
                select(Submission)
                .where(Submission.investigation_id == investigation.id)
                .order_by(Submission.received_at)
            )
            metadata = submission.source_metadata if submission is not None else {}
            sender_ref = metadata.get("sender_ref") if isinstance(metadata, dict) else None
            conversation = (
                session.scalar(
                    select(WhatsAppConversation).where(
                        WhatsAppConversation.owner_id == investigation.owner_id,
                        WhatsAppConversation.sender_ref == sender_ref,
                    )
                )
                if sender_ref
                else None
            )
            preference = (
                session.scalar(
                    select(WhatsAppNotificationPreference).where(
                        WhatsAppNotificationPreference.owner_id == investigation.owner_id,
                        WhatsAppNotificationPreference.sender_ref == sender_ref,
                    )
                )
                if sender_ref
                else None
            )
            delivery_state, reason = None, None
            latest_job = session.scalar(
                select(ProcessingJob)
                .where(ProcessingJob.investigation_id == investigation.id)
                .order_by(ProcessingJob.created_at.desc())
            )
            if latest_job is None or str(latest_job.id) != str(payload.get("job_id")):
                delivery_state, reason = "SKIPPED", "superseded_run"
            last_inbound_at = conversation.last_inbound_at if conversation else None
            if last_inbound_at is not None and last_inbound_at.tzinfo is None:
                last_inbound_at = last_inbound_at.replace(tzinfo=UTC)
            conversation_expires_at = conversation.expires_at if conversation else None
            if conversation_expires_at is not None and conversation_expires_at.tzinfo is None:
                conversation_expires_at = conversation_expires_at.replace(tzinfo=UTC)
            if delivery_state == "SKIPPED":
                pass
            elif preference is not None and preference.notifications_disabled:
                delivery_state, reason = "SKIPPED", "notifications_disabled"
            elif (
                conversation is None
                or not conversation.recipient_encrypted
                or conversation_expires_at is None
                or conversation_expires_at <= now
                or last_inbound_at is None
                or last_inbound_at + timedelta(hours=24) <= now
            ):
                delivery_state, reason = "SKIPPED", "service_window_closed"
            else:
                settings = get_settings()
                support_url = getattr(settings, "whatsapp_support_url", None)
                if support_url is None:
                    delivery_state, reason = "SKIPPED", "support_escalation_not_configured"
                    settings = None
                else:
                    try:
                        settings = _configured_settings()
                    except WhatsAppConfigurationError:
                        delivery_state, reason = "FAILED", "channel_not_configured"
                        settings = None
                if settings is None:
                    recipient = None
                else:
                    recipient = _decrypt_recipient(conversation.recipient_encrypted, settings)
                if recipient is None:
                    if settings is not None:
                        delivery_state, reason = "SKIPPED", "recipient_route_unavailable"
                else:
                    reference = investigation.reference
                    message = _result_message(
                        session,
                        settings=settings,
                        sender_ref=sender_ref,
                        reference=reference,
                    )
                    if len(message) > 3900:
                        message = (
                            f"Your result is ready. Reference: {reference}. "
                            f"Send RESULT {reference} to view the complete assessment and sources."
                        )
                    message = (
                        f"Your result is ready. Reference: {reference}.\n\n"
                        f"{message}\n\nNeed human help? {support_url}"
                    )
                    try:
                        send_text_message(recipient, message)
                    except WhatsAppConfigurationError:
                        delivery_state, reason = "FAILED", "channel_not_configured"
                    except Exception as exc:  # transport failures leave polling available
                        delivery_state, reason = "FAILED", type(exc).__name__
                    else:
                        delivery_state, reason = "SENT", "accepted_by_whatsapp"
        event.payload = {
            **dict(event.payload or {}),
            "delivery_state": delivery_state,
            "delivery_reason": reason,
        }
        session.commit()
        logger.info(
            "WhatsApp result notification state=%s reason=%s",
            delivery_state,
            reason,
        )
        return delivery_state.lower()


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
            _queue_whatsapp_result_notification(session, investigation, job)
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
