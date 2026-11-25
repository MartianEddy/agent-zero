"""Widen sources.retrieval_status so NOT_ATTEMPTED_DEADLINE (22 characters) fits.

The column was VARCHAR(20). When a case reached its research deadline the pipeline
marked the remaining sources NOT_ATTEMPTED_DEADLINE, the update failed, and the whole
investigation was marked FAILED instead of being decided on the sources already read.
"""

import sqlalchemy as sa
from alembic import op

revision = "0021_widen_retrieval_status"
down_revision = "0020_drop_stale_confidence_check"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "sources",
        "retrieval_status",
        existing_type=sa.String(20),
        type_=sa.String(40),
        existing_nullable=False,
        existing_server_default="CANDIDATE",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE sources SET retrieval_status = 'NOT_ATTEMPTED_LIMIT' "
        "WHERE length(retrieval_status) > 20"
    )
    op.alter_column(
        "sources",
        "retrieval_status",
        existing_type=sa.String(40),
        type_=sa.String(20),
        existing_nullable=False,
        existing_server_default="CANDIDATE",
    )
