"""Add investigation usage telemetry and reusable retrieved source content."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_cost_controlled_pipeline"
down_revision = "0004_search_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.add_column("sources", sa.Column("domain", sa.String(255), nullable=True))
    op.add_column("sources", sa.Column("content_storage_key", sa.String(500), nullable=True))
    op.create_table(
        "investigation_usage",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "investigation_id",
            uuid,
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("model_calls", sa.Integer(), nullable=False),
        sa.Column("search_calls", sa.Integer(), nullable=False),
        sa.Column("sources_discovered", sa.Integer(), nullable=False),
        sa.Column("sources_retrieved", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("limitations", jsonb, nullable=False),
    )
    op.create_table(
        "model_usage_records",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "investigation_id",
            uuid,
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("failure_category", sa.String(40), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_model_usage_records_investigation_id",
        "model_usage_records",
        ["investigation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_model_usage_records_investigation_id", table_name="model_usage_records")
    op.drop_table("model_usage_records")
    op.drop_table("investigation_usage")
    op.drop_column("sources", "content_storage_key")
    op.drop_column("sources", "domain")
