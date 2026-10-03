from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.investigation import Channel, InputType, InvestigationStatus
from app.modules.investigations.models import (
    AuditEvent,
    Investigation,
    InvestigationUsage,
    MediaAsset,
    OutboxEvent,
    ProcessingJob,
    Submission,
    User,
)

DEV_USER_ID = UUID("00000000-0000-4000-8000-000000000001")


class InvestigationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        owner_id: UUID,
        content: str,
        input_type: InputType,
        idempotency_key: str,
        media_asset: dict[str, object] | None = None,
        channel: Channel = Channel.WEB,
        source_metadata: dict[str, object] | None = None,
    ) -> Investigation:
        existing_job = self.session.scalar(
            select(ProcessingJob).where(ProcessingJob.idempotency_key == idempotency_key)
        )
        if existing_job is not None:
            existing = self.session.get(Investigation, existing_job.investigation_id)
            if existing is not None:
                return existing

        user = self.session.get(User, owner_id)
        if user is None:
            self.session.add(User(id=owner_id, external_subject=f"local:{owner_id}"))
            self.session.flush()
        investigation_id = uuid4()
        reference = f"AZ-{datetime.now(UTC):%y%m%d}-{investigation_id.hex[:6].upper()}"
        investigation = Investigation(
            id=investigation_id,
            reference=reference,
            owner_id=owner_id,
            channel=channel,
            input_type=input_type,
            status=InvestigationStatus.RECEIVED,
            current_stage="RECEIVED",
        )
        self.session.add(investigation)
        self.session.flush()
        job = ProcessingJob(
            id=uuid4(),
            investigation_id=investigation_id,
            stage="RECEIVED",
            status="QUEUED",
            idempotency_key=idempotency_key,
        )
        records = [
            Submission(
                investigation_id=investigation_id,
                channel=channel,
                input_type=input_type,
                original_text=content,
                source_metadata=source_metadata or {},
            ),
            job,
            OutboxEvent(
                aggregate_id=investigation_id,
                event_type="INVESTIGATION_RECEIVED",
                payload={"investigation_id": str(investigation_id), "job_id": str(job.id)},
            ),
            AuditEvent(
                investigation_id=investigation_id,
                event_type="INVESTIGATION_CREATED",
                actor=(
                    "clickcast-webhook"
                    if channel == Channel.WHATSAPP
                    else "local-development-user"
                ),
                event_metadata={"channel": channel.value, "input_type": input_type.value},
            ),
            InvestigationUsage(investigation_id=investigation_id),
        ]
        if media_asset is not None:
            records.append(MediaAsset(investigation_id=investigation_id, **media_asset))
        self.session.add_all(records)
        self.session.commit()
        self.session.refresh(investigation)
        return investigation

    def get(self, *, investigation_id: UUID, owner_id: UUID) -> Investigation | None:
        return self.session.scalar(
            select(Investigation).where(
                Investigation.id == investigation_id,
                Investigation.owner_id == owner_id,
            )
        )

    def list_recent(self, *, owner_id: UUID, limit: int = 50) -> list[Investigation]:
        return list(
            self.session.scalars(
                select(Investigation)
                .where(Investigation.owner_id == owner_id)
                .order_by(Investigation.created_at.desc())
                .limit(limit)
            )
        )
