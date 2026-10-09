"""Add auditable evidence ledger and sentence citation storage."""

import sqlalchemy as sa
from alembic import op

revision = "0014_evidence_ledger"
down_revision = "0013_slice1_verdict_contract"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evidence",
        sa.Column("source_tier", sa.String(40), nullable=False, server_default="UNKNOWN"),
    )
    op.add_column(
        "evidence", sa.Column("stance", sa.String(24), nullable=False, server_default="UNKNOWN")
    )
    op.add_column("evidence", sa.Column("excerpt_start", sa.Integer(), nullable=True))
    op.add_column("evidence", sa.Column("excerpt_end", sa.Integer(), nullable=True))
    op.add_column(
        "evidence",
        sa.Column(
            "independence_group_id", sa.String(255), nullable=False, server_default="unknown"
        ),
    )
    op.add_column("evidence", sa.Column("published_date", sa.String(80), nullable=True))
    op.add_column("evidence", sa.Column("is_stale", sa.Boolean(), nullable=True))
    op.add_column(
        "evidence", sa.Column("retrieval_timestamp", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("evidence", sa.Column("run_id", sa.Uuid(), nullable=True))
    op.create_index("ix_evidence_run_id", "evidence", ["run_id"])
    op.add_column(
        "evidence",
        sa.Column("excerpt_validated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "findings", sa.Column("explanation_json", sa.JSON(), nullable=False, server_default="[]")
    )
    op.add_column(
        "findings",
        sa.Column(
            "unsupported_statements_removed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("findings", "unsupported_statements_removed")
    op.drop_column("findings", "explanation_json")
    op.drop_column("evidence", "excerpt_validated")
    op.drop_index("ix_evidence_run_id", table_name="evidence")
    for column in (
        "run_id",
        "retrieval_timestamp",
        "is_stale",
        "published_date",
        "independence_group_id",
        "excerpt_end",
        "excerpt_start",
        "stance",
        "source_tier",
    ):
        op.drop_column("evidence", column)
