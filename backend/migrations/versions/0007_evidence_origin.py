"""Require evidence to reference at least one origin."""

from alembic import op

revision = "0007_evidence_origin"
down_revision = "0006_source_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_evidence_has_origin",
        "evidence",
        "source_id IS NOT NULL OR media_asset_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_evidence_has_origin", "evidence", type_="check")
