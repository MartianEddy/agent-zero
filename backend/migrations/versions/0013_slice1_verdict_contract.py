"""Normalize legacy claim and finding values to the Slice 1 contract."""

from alembic import op

revision = "0013_slice1_verdict_contract"
down_revision = "0012_claim_triage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """UPDATE claims SET claim_type = CASE UPPER(claim_type)
            WHEN 'SETTLED_FACT' THEN 'SETTLED_FACT'
            WHEN 'CHECKABLE_EVENT' THEN 'CHECKABLE_EVENT'
            WHEN 'STATISTICAL' THEN 'STATISTICAL'
            WHEN 'MEDIA_CLAIM' THEN 'MEDIA_CLAIM'
            WHEN 'IMAGE' THEN 'MEDIA_CLAIM'
            WHEN 'VIDEO' THEN 'MEDIA_CLAIM'
            WHEN 'PROVENANCE' THEN 'MEDIA_CLAIM'
            WHEN 'CONTESTED' THEN 'CONTESTED'
            WHEN 'OPINION_OR_PREDICTION' THEN 'OPINION_OR_PREDICTION'
            ELSE 'CHECKABLE_EVENT' END"""
    )
    op.execute(
        """UPDATE claims SET needs_deep_investigation =
            CASE WHEN claim_type = 'SETTLED_FACT' THEN FALSE ELSE TRUE END"""
    )
    op.execute(
        """UPDATE findings SET status = CASE UPPER(status)
            WHEN 'SUPPORTED' THEN 'SUPPORTED'
            WHEN 'CONTRADICTED' THEN 'CONTRADICTED'
            WHEN 'PARTLY_TRUE' THEN 'PARTLY_TRUE'
            WHEN 'NOT_VERIFIABLE' THEN 'NOT_VERIFIABLE'
            WHEN 'INSUFFICIENT_EVIDENCE' THEN 'INSUFFICIENT_EVIDENCE'
            ELSE 'INSUFFICIENT_EVIDENCE' END"""
    )
    op.execute(
        """UPDATE findings SET evidence_confidence = CASE UPPER(evidence_confidence)
            WHEN 'HIGH' THEN 'HIGH'
            WHEN 'MEDIUM' THEN 'MEDIUM'
            WHEN 'MODERATE' THEN 'MEDIUM'
            ELSE 'LOW' END"""
    )
    op.execute(
        """UPDATE findings SET confidence_rationale =
            'Legacy confidence was not assessed with the Slice 1 evidence rules.'
            WHERE confidence_rationale IS NULL OR trim(confidence_rationale) = ''"""
    )
    op.create_check_constraint(
        "claim_type_slice1_valid",
        "claims",
        "claim_type IN ('SETTLED_FACT','CHECKABLE_EVENT','STATISTICAL','MEDIA_CLAIM','CONTESTED','OPINION_OR_PREDICTION')",
    )
    op.create_check_constraint(
        "finding_verdict_slice1_valid",
        "findings",
        "status IN ('SUPPORTED','CONTRADICTED','PARTLY_TRUE','INSUFFICIENT_EVIDENCE','NOT_VERIFIABLE')",
    )
    op.create_check_constraint(
        "finding_confidence_slice1_valid",
        "findings",
        "evidence_confidence IN ('HIGH','MEDIUM','LOW')",
    )
    op.alter_column("findings", "evidence_confidence", server_default="LOW")


def downgrade() -> None:
    op.alter_column("findings", "evidence_confidence", server_default=None)
    op.drop_constraint("finding_confidence_slice1_valid", "findings", type_="check")
    op.drop_constraint("finding_verdict_slice1_valid", "findings", type_="check")
    op.drop_constraint("claim_type_slice1_valid", "claims", type_="check")
    op.execute(
        """UPDATE findings SET status = CASE status
            WHEN 'PARTLY_TRUE' THEN 'INCONCLUSIVE'
            WHEN 'NOT_VERIFIABLE' THEN 'UNVERIFIED'
            WHEN 'INSUFFICIENT_EVIDENCE' THEN 'UNVERIFIED'
            ELSE status END"""
    )
    op.execute("UPDATE findings SET evidence_confidence = 'MODERATE' WHERE evidence_confidence = 'MEDIUM'")
    op.execute(
        """UPDATE claims SET claim_type = CASE claim_type
            WHEN 'SETTLED_FACT' THEN 'FACTUAL'
            WHEN 'STATISTICAL' THEN 'FACTUAL'
            WHEN 'MEDIA_CLAIM' THEN 'PROVENANCE'
            WHEN 'CONTESTED' THEN 'FACTUAL'
            WHEN 'OPINION_OR_PREDICTION' THEN 'GENERAL'
            ELSE 'FACTUAL' END"""
    )
