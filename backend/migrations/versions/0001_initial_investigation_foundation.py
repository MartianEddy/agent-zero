"""Initial investigation foundation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

channel = postgresql.ENUM("WEB", "WHATSAPP", "API", name="channel", create_type=False)
input_type = postgresql.ENUM(
    "TEXT", "URL", "IMAGE", "VIDEO", "AUDIO", "DOCUMENT", name="input_type", create_type=False
)
investigation_status = postgresql.ENUM(
    "RECEIVED", "PROCESSING", "ANALYZING", "RESEARCHING", "CORROBORATING",
    "GENERATING_BRIEF", "COMPLETE", "NEEDS_REVIEW", "FAILED", "CANCELLED",
    name="investigation_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    channel.create(bind, checkfirst=True)
    input_type.create(bind, checkfirst=True)
    investigation_status.create(bind, checkfirst=True)
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("external_subject", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("external_subject", name="uq_users_external_subject"),
    )
    op.create_table(
        "investigations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(20), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("channel", channel, nullable=False),
        sa.Column("input_type", input_type, nullable=False),
        sa.Column("status", investigation_status, nullable=False),
        sa.Column("current_stage", sa.String(40), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("reference", name="uq_investigations_reference"),
    )
    op.create_index("ix_investigations_owner_id", "investigations", ["owner_id"])
    op.create_table(
        "submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", channel, nullable=False),
        sa.Column("input_type", input_type, nullable=False),
        sa.Column("original_text", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index("ix_submissions_investigation_id", "submissions", ["investigation_id"])
    op.create_index("ix_submissions_channel", "submissions", ["channel"])
    op.create_table(
        "processing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_processing_jobs_idempotency_key"),
    )
    op.create_index("ix_processing_jobs_investigation_id", "processing_jobs", ["investigation_id"])
    op.create_index("ix_processing_jobs_status", "processing_jobs", ["status"])
    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"])
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("actor", sa.String(120), nullable=False),
        sa.Column("event_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_investigation_id", "audit_events", ["investigation_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("outbox_events")
    op.drop_table("processing_jobs")
    op.drop_table("submissions")
    op.drop_table("investigations")
    op.drop_table("users")
    investigation_status.drop(op.get_bind(), checkfirst=True)
    input_type.drop(op.get_bind(), checkfirst=True)
    channel.drop(op.get_bind(), checkfirst=True)
