"""Record whether a discovered source has been retrieved and hashed."""

import sqlalchemy as sa
from alembic import op

revision = "0003_source_retrieval"
down_revision = "0002_evidence_graph"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("retrieval_status", sa.String(20), server_default="CANDIDATE", nullable=False),
    )
    op.add_column("sources", sa.Column("retrieval_provider", sa.String(40), nullable=True))
    op.add_column("sources", sa.Column("content_sha256", sa.String(64), nullable=True))
    # Existing records came from hosted search proposals; they were never page-fetched.
    op.execute("UPDATE sources SET retrieved_at = NULL")
    op.alter_column(
        "sources", "retrieved_at", existing_type=sa.DateTime(timezone=True), nullable=True
    )


def downgrade() -> None:
    op.execute("UPDATE sources SET retrieved_at = CURRENT_TIMESTAMP WHERE retrieved_at IS NULL")
    op.alter_column(
        "sources", "retrieved_at", existing_type=sa.DateTime(timezone=True), nullable=False
    )
    op.drop_column("sources", "content_sha256")
    op.drop_column("sources", "retrieval_provider")
    op.drop_column("sources", "retrieval_status")
