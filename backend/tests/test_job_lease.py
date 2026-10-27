from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.domain.investigation import InputType, InvestigationStatus
from app.modules.investigations.job_lease import (
    JobLeaseLost,
    claim_processing_job,
    protect_job_lease,
)
from app.modules.investigations.models import AuditEvent, Investigation, ProcessingJob
from app.modules.investigations.service import InvestigationService


@pytest.fixture
def sessions():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        investigation = InvestigationService(session).create(
            owner_id=UUID("00000000-0000-4000-8000-000000000001"),
            content="A factual claim for job lease tests.",
            input_type=InputType.TEXT,
            idempotency_key=f"lease-test-{uuid4()}",
        )
        job_id = session.scalar(
            select(ProcessingJob.id).where(ProcessingJob.investigation_id == investigation.id)
        )
    yield factory, job_id
    engine.dispose()


def test_only_one_delivery_can_claim_a_queued_job(sessions) -> None:
    factory, job_id = sessions
    with factory() as first, factory() as second:
        first_lease = claim_processing_job(first, job_id)
        duplicate_lease = claim_processing_job(second, job_id)

    assert first_lease is not None
    assert first_lease.generation == 1
    assert duplicate_lease is None


def test_concurrent_deliveries_cannot_both_claim_one_job(tmp_path) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'lease-race.sqlite'}",
        connect_args={"timeout": 10},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        investigation = InvestigationService(session).create(
            owner_id=UUID("00000000-0000-4000-8000-000000000001"),
            content="Concurrent claim fixture.",
            input_type=InputType.TEXT,
            idempotency_key=f"lease-race-{uuid4()}",
        )
        job_id = session.scalar(
            select(ProcessingJob.id).where(ProcessingJob.investigation_id == investigation.id)
        )

    barrier = Barrier(2)

    def claim():
        with factory() as session:
            barrier.wait()
            return claim_processing_job(session, job_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(pool.map(lambda _: claim(), range(2)))

    assert sum(lease is not None for lease in leases) == 1
    engine.dispose()


def test_stale_worker_cannot_commit_after_ownership_token_changes(sessions) -> None:
    factory, job_id = sessions
    stale_session: Session = factory()
    lease = claim_processing_job(stale_session, job_id)
    assert lease is not None

    with protect_job_lease(stale_session, lease, factory):
        with factory.begin() as current_session:
            current_session.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == job_id)
                .values(
                    lease_token=uuid4(),
                    lease_generation=lease.generation + 1,
                    lease_expires_at=datetime.now(UTC) + timedelta(minutes=3),
                )
            )
        stale_session.add(
            AuditEvent(
                investigation_id=stale_session.get(ProcessingJob, job_id).investigation_id,
                event_type="STALE_WORKER_WRITE",
                actor="test",
                event_metadata={},
            )
        )
        with pytest.raises(JobLeaseLost):
            stale_session.commit()
        stale_session.rollback()

    stale_session.close()


def test_expired_worker_lease_fences_late_commits(sessions) -> None:
    factory, job_id = sessions
    stale_session: Session = factory()
    lease = claim_processing_job(stale_session, job_id)
    assert lease is not None

    with factory.begin() as current_session:
        current_session.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == job_id)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    stale_session.add(
        AuditEvent(
            investigation_id=stale_session.get(ProcessingJob, job_id).investigation_id,
            event_type="EXPIRED_WORKER_WRITE",
            actor="test",
            event_metadata={},
        )
    )
    with protect_job_lease(stale_session, lease, factory):
        with pytest.raises(JobLeaseLost):
            stale_session.commit()
        stale_session.rollback()
    stale_session.close()


def test_stalled_recovery_clears_lease_and_marks_investigation_retryable(sessions) -> None:
    factory, job_id = sessions
    with factory.begin() as session:
        job = session.get(ProcessingJob, job_id)
        investigation = session.get(Investigation, job.investigation_id)
        job.status = "RUNNING"
        job.lease_token = uuid4()
        job.lease_generation = 1
        job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        investigation.status = InvestigationStatus.PROCESSING

    with patch("app.tasks.SessionLocal", factory):
        from app.tasks import recover_stalled_investigations

        assert recover_stalled_investigations.run() == 1

    with factory() as session:
        job = session.get(ProcessingJob, job_id)
        investigation = session.get(Investigation, investigation.id)
        assert job.status == "BLOCKED"
        assert job.lease_token is None
        assert job.lease_expires_at is None
        assert investigation.status == InvestigationStatus.FAILED


def test_celery_duplicate_delivery_does_not_reenter_pipeline(sessions) -> None:
    factory, job_id = sessions
    from app.tasks import process_investigation

    with (
        patch("app.tasks.SessionLocal", factory),
        patch("app.tasks.run_pipeline", return_value="complete") as run_pipeline,
    ):
        first = process_investigation.run(str(job_id))
        duplicate = process_investigation.run(str(job_id))

    assert first == "complete"
    assert duplicate == "already_claimed"
    run_pipeline.assert_called_once()
