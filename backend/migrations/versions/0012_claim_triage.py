"""Persist typed claim triage metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0012_claim_triage"
down_revision = "0011_search_route_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "claims",
        sa.Column("needs_deep_investigation", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("claims", "needs_deep_investigation", server_default=None)


def downgrade() -> None:
    op.drop_column("claims", "needs_deep_investigation")
