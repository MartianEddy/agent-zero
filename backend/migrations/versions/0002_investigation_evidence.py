"""Add multimodal assets and evidence graph records."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_evidence_graph"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "media_assets",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "investigation_id",
            uuid,
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("media_type", sa.String(20), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("metadata_json", jsonb, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("storage_key", name="uq_media_assets_storage_key"),
    )
    op.create_index("ix_media_assets_investigation_id", "media_assets", ["investigation_id"])
    op.create_index("ix_media_assets_sha256", "media_assets", ["sha256"])
    op.create_table(
        "claims",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "investigation_id",
            uuid,
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_claims_investigation_id", "claims", ["investigation_id"])
    op.create_table(
        "sources",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "investigation_id",
            uuid,
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("publisher", sa.String(255), nullable=True),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sources_investigation_id", "sources", ["investigation_id"])
    op.create_table(
        "evidence",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "investigation_id",
            uuid,
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id", uuid, sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column(
            "media_asset_id",
            uuid,
            sa.ForeignKey("media_assets.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("method", sa.String(40), nullable=False),
        sa.Column("limitations", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evidence_investigation_id", "evidence", ["investigation_id"])
    op.create_table(
        "claim_evidence",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("claim_id", uuid, sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "evidence_id", uuid, sa.ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("relationship", sa.String(30), nullable=False),
        sa.UniqueConstraint("claim_id", "evidence_id", name="uq_claim_evidence_pair"),
    )
    op.create_index("ix_claim_evidence_claim_id", "claim_evidence", ["claim_id"])
    op.create_index("ix_claim_evidence_evidence_id", "claim_evidence", ["evidence_id"])
    op.create_table(
        "findings",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "investigation_id",
            uuid,
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("claim_id", uuid, sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("limitations", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_findings_investigation_id", "findings", ["investigation_id"])
    op.create_index("ix_findings_claim_id", "findings", ["claim_id"])
    op.create_table(
        "finding_evidence",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "finding_id", uuid, sa.ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "evidence_id", uuid, sa.ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False
        ),
        sa.UniqueConstraint("finding_id", "evidence_id", name="uq_finding_evidence_pair"),
    )
    op.create_index("ix_finding_evidence_finding_id", "finding_evidence", ["finding_id"])
    op.create_index("ix_finding_evidence_evidence_id", "finding_evidence", ["evidence_id"])
    op.create_table(
        "verification_briefs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "investigation_id",
            uuid,
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("limitations", jsonb, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("investigation_id", name="uq_verification_briefs_investigation_id"),
    )


def downgrade() -> None:
    for table in (
        "verification_briefs",
        "finding_evidence",
        "findings",
        "claim_evidence",
        "evidence",
        "sources",
        "claims",
        "media_assets",
    ):
        op.drop_table(table)
