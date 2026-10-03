"""Persist provider search traces separately from model-proposed sources."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_search_provenance"
down_revision = "0003_source_retrieval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "search_traces",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "investigation_id",
            uuid,
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("call_reference", sa.String(120), nullable=True),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("sources", jsonb, nullable=False),
        sa.Column("citations", jsonb, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_search_traces_investigation_id", "search_traces", ["investigation_id"]
    )
    op.add_column(
        "sources", sa.Column("discovery_method", sa.String(40), server_default="MODEL_PROPOSED", nullable=False)
    )
    op.add_column(
        "sources",
        sa.Column(
            "discovery_trace_id",
            uuid,
            sa.ForeignKey("search_traces.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("sources", "discovery_trace_id")
    op.drop_column("sources", "discovery_method")
    op.drop_index("ix_search_traces_investigation_id", table_name="search_traces")
    op.drop_table("search_traces")
