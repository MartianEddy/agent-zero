"""Persist typed source-routing metadata on provider search traces."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_search_route_metadata"
down_revision = "0010_finding_evidence_confidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_traces",
        sa.Column(
            "route_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("search_traces", "route_metadata", server_default=None)


def downgrade() -> None:
    op.drop_column("search_traces", "route_metadata")
