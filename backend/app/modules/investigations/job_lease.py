"""PostgreSQL-backed ownership and fencing for Celery investigation jobs."""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import event, func, select, update
from sqlalchemy.orm import Session

from app.modules.investigations.models import ProcessingJob

logger = logging.getLogger(__name__)
LEASE_SECONDS = 180
HEARTBEAT_SECONDS = 30


class JobLeaseLost(RuntimeError):
    """Raised when a worker no longer owns the durable job lease."""


@dataclass(frozen=True)
class JobLease:
    job_id: UUID
    token: UUID
    generation: int


def _uses_postgres_clock(session: Session) -> bool:
    return session.bind is not None and session.bind.dialect.name == "postgresql"


def _clock_expression(session: Session):
    return func.clock_timestamp() if _uses_postgres_clock(session) else datetime.now(UTC)


def _database_now(session: Session) -> datetime:
    if _uses_postgres_clock(session):
        now = session.scalar(select(func.clock_timestamp()))
        if now is None:
            raise JobLeaseLost("Could not read database clock")
    else:
        now = datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now


def _expiration(session: Session):
    return _database_now(session) + timedelta(seconds=LEASE_SECONDS)


def claim_processing_job(session: Session, job_id: UUID) -> JobLease | None:
    """Atomically claim only queued work; stale work requires explicit recovery/retry."""
    token = uuid4()
    expires_at = _expiration(session)
    result = session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.id == job_id, ProcessingJob.status == "QUEUED")
        .values(
            status="RUNNING",
            lease_token=token,
            lease_generation=ProcessingJob.lease_generation + 1,
            lease_expires_at=expires_at,
        )
        .returning(ProcessingJob.lease_generation)
    )
    generation = result.scalar_one_or_none()
    session.commit()
    if generation is None:
        return None
    return JobLease(job_id=job_id, token=token, generation=generation)


def _assert_owned(session: Session, lease: JobLease) -> None:
    row = session.execute(
        select(
            ProcessingJob.lease_token,
            ProcessingJob.lease_generation,
            ProcessingJob.lease_expires_at,
        )
        .where(ProcessingJob.id == lease.job_id)
        .with_for_update()
    ).one_or_none()
    if row is None:
        raise JobLeaseLost("Processing job no longer exists")
    token, generation, expires_at = row
    if token != lease.token or generation != lease.generation or expires_at is None:
        raise JobLeaseLost("Processing job lease ownership changed")
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    now = _database_now(session)
    if expires_at <= now:
        raise JobLeaseLost("Processing job lease expired")


@event.listens_for(Session, "before_commit")
def _fence_commits(session: Session) -> None:
    lease = session.info.get("processing_job_lease")
    if isinstance(lease, JobLease):
        _assert_owned(session, lease)


def _heartbeat_once(session_factory, lease: JobLease) -> bool:
    try:
        with session_factory() as session:
            clock = _clock_expression(session)
            expires_at = _expiration(session)
            result = session.execute(
                update(ProcessingJob)
                .where(
                    ProcessingJob.id == lease.job_id,
                    ProcessingJob.status == "RUNNING",
                    ProcessingJob.lease_token == lease.token,
                    ProcessingJob.lease_generation == lease.generation,
                    ProcessingJob.lease_expires_at > clock,
                )
                .values(lease_expires_at=expires_at)
            )
            if result.rowcount == 1:
                session.commit()
                return True
            session.rollback()
            current = session.execute(
                select(
                    ProcessingJob.status,
                    ProcessingJob.lease_token,
                    ProcessingJob.lease_generation,
                ).where(
                    ProcessingJob.id == lease.job_id
                )
            ).one_or_none()
            # A terminal result may stop lease renewal while still owned.
            return (
                current is not None
                and current[0] in {"COMPLETE", "BLOCKED"}
                and current[1:] == (lease.token, lease.generation)
            )
    except Exception:
        logger.exception("Job lease heartbeat failed job_id=%s", lease.job_id)
        return True  # Fail closed at the next fenced commit if the lease expires.


@contextmanager
def protect_job_lease(
    session: Session,
    lease: JobLease,
    session_factory,
) -> Iterator[threading.Event]:
    """Fence every commit in the pipeline and renew ownership while it is running."""
    stopped = threading.Event()
    lost = threading.Event()
    session.info["processing_job_lease"] = lease

    def heartbeat() -> None:
        while not stopped.wait(HEARTBEAT_SECONDS):
            if not _heartbeat_once(session_factory, lease):
                lost.set()
                logger.warning(
                    "Job lease was lost job_id=%s generation=%s",
                    lease.job_id,
                    lease.generation,
                )
                return

    thread = threading.Thread(
        target=heartbeat,
        name=f"job-lease-{lease.job_id.hex[:8]}",
        daemon=True,
    )
    thread.start()
    try:
        yield lost
    finally:
        stopped.set()
        thread.join(timeout=HEARTBEAT_SECONDS + 1)
        session.info.pop("processing_job_lease", None)


def release_processing_job_lease(session: Session, lease: JobLease) -> bool:
    result = session.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == lease.job_id,
            ProcessingJob.lease_token == lease.token,
            ProcessingJob.lease_generation == lease.generation,
        )
        .values(lease_token=None, lease_expires_at=None)
    )
    session.commit()
    return result.rowcount == 1
