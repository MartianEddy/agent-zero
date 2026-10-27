"""Add durable ownership tokens and expiring leases to processing jobs."""

import sqlalchemy as sa
from alembic import op

revision = "0015_processing_job_lease"
down_revision = "0014_evidence_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("processing_jobs", sa.Column("lease_token", sa.Uuid(), nullable=True))
    op.add_column(
        "processing_jobs",
        sa.Column("lease_generation", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "processing_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("ix_processing_jobs_lease_expires_at", "processing_jobs", ["lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_lease_expires_at", table_name="processing_jobs")
    op.drop_column("processing_jobs", "lease_expires_at")
    op.drop_column("processing_jobs", "lease_generation")
    op.drop_column("processing_jobs", "lease_token")
