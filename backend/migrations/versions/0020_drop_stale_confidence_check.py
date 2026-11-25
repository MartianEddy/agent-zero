"""Drop the stale evidence-confidence check left behind by 0010.

0010 created its check through the naming convention, so it was stored as
ck_findings_ck_findings_evidence_confidence_valid (UNASSESSED, LOW, MODERATE, HIGH).
0013 added ck_findings_finding_confidence_slice1_valid (HIGH, MEDIUM, LOW) but did not
drop the old one. With both in force only LOW and HIGH could be saved, so every finding
with MEDIUM evidence strength failed to save and its investigation stopped.
"""

from alembic import op

revision = "0020_drop_stale_confidence_check"
down_revision = "0019_stage_samples"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE findings DROP CONSTRAINT IF EXISTS "
        "ck_findings_ck_findings_evidence_confidence_valid"
    )
    op.execute(
        "ALTER TABLE findings DROP CONSTRAINT IF EXISTS ck_findings_evidence_confidence_valid"
    )


def downgrade() -> None:
    # Re-creating the stale check would block MEDIUM findings again; leave it dropped.
    pass
