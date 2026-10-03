"""Add URL source metadata and deterministic source relationships."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_source_intelligence"
down_revision = "0005_cost_controlled_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    for name, column_type in (
        ("source_role", sa.String(40)),
        ("canonical_url", sa.Text()),
        ("author", sa.String(255)),
        ("published_at", sa.String(80)),
        ("modified_at", sa.String(80)),
        ("retrieval_failure_reason", sa.String(120)),
    ):
        op.add_column(
            "sources",
            sa.Column(name, column_type, nullable=False, server_default="UNKNOWN")
            if name == "source_role"
            else sa.Column(name, column_type, nullable=True),
        )
    op.create_table(
        "source_relationships",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "investigation_id",
            uuid,
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id", uuid, sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "related_source_id",
            uuid,
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relationship_type", sa.String(30), nullable=False),
        sa.Column("basis", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_id", "related_source_id", "relationship_type", name="uq_source_relationship"
        ),
    )
    op.create_index(
        "ix_source_relationships_investigation_id",
        "source_relationships",
        ["investigation_id"],
    )
    op.create_index("ix_source_relationships_source_id", "source_relationships", ["source_id"])
    op.create_index(
        "ix_source_relationships_related_source_id",
        "source_relationships",
        ["related_source_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_source_relationships_related_source_id", table_name="source_relationships")
    op.drop_index("ix_source_relationships_source_id", table_name="source_relationships")
    op.drop_index("ix_source_relationships_investigation_id", table_name="source_relationships")
    op.drop_table("source_relationships")
    for name in (
        "retrieval_failure_reason",
        "modified_at",
        "published_at",
        "author",
        "canonical_url",
        "source_role",
    ):
        op.drop_column("sources", name)
