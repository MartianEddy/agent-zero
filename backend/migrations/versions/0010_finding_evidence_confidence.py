"""Persist qualitative evidence confidence and its explanation on findings."""

import sqlalchemy as sa
from alembic import op

revision = "0010_finding_evidence_confidence"
down_revision = "0009_media_analysis_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "findings",
        sa.Column(
            "evidence_confidence", sa.String(length=12), nullable=False, server_default="UNASSESSED"
        ),
    )
    op.add_column(
        "findings",
        sa.Column("confidence_rationale", sa.Text(), nullable=False, server_default=""),
    )
    op.create_check_constraint(
        "ck_findings_evidence_confidence_valid",
        "findings",
        "evidence_confidence IN ('UNASSESSED', 'LOW', 'MODERATE', 'HIGH')",
    )
    op.alter_column("findings", "evidence_confidence", server_default=None)
    op.alter_column("findings", "confidence_rationale", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_findings_evidence_confidence_valid", "findings", type_="check")
    op.drop_column("findings", "confidence_rationale")
    op.drop_column("findings", "evidence_confidence")
