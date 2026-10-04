import unittest
from uuid import UUID

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.investigation import InputType, InvestigationStatus
from app.modules.investigations.models import AuditEvent, Investigation, OutboxEvent, ProcessingJob, Submission
from app.modules.investigations.service import InvestigationService


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
    )
    Base.metadata.create_all(engine)
    return Session(engine)


class InvestigationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = make_session()

    def tearDown(self) -> None:
        self.session.close()

    def test_create_persists_investigation_submission_job_outbox_and_audit(self) -> None:
        result = InvestigationService(self.session).create(
            owner_id=UUID("00000000-0000-4000-8000-000000000001"),
            content="Schools will be closed tomorrow.",
            input_type=InputType.TEXT,
            idempotency_key="stable-key",
        )

        self.assertEqual(result.status, InvestigationStatus.RECEIVED)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(Submission)), 1)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(ProcessingJob)), 1)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(OutboxEvent)), 1)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(AuditEvent)), 1)

    def test_same_idempotency_key_returns_existing_investigation(self) -> None:
        service = InvestigationService(self.session)
        owner_id = UUID("00000000-0000-4000-8000-000000000001")
        first = service.create(
            owner_id=owner_id,
            content="A claim.",
            input_type=InputType.TEXT,
            idempotency_key="retry-key",
        )
        second = service.create(
            owner_id=owner_id,
            content="A claim.",
            input_type=InputType.TEXT,
            idempotency_key="retry-key",
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(Investigation)), 1)
from uuid import UUID
