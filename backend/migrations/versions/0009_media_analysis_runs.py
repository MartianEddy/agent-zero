"""Add versioned, idempotent M2 media analyzer runs."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_media_analysis_runs"
down_revision = "0008_media_asset_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    json_value = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "media_analysis_runs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "investigation_id",
            uuid,
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "media_asset_id",
            uuid,
            sa.ForeignKey("media_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("analyzer_id", sa.String(40), nullable=False),
        sa.Column("analyzer_version", sa.String(30), nullable=False),
        sa.Column("config_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_category", sa.String(50), nullable=True),
        sa.Column("limitations", json_value, nullable=False),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("observations_json", json_value, nullable=True),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_media_analysis_runs_media_analysis_run_status_valid",
        ),
        sa.UniqueConstraint("cache_key", name="uq_media_analysis_run_cache_key"),
    )
    op.create_index(
        "ix_media_analysis_runs_investigation_id", "media_analysis_runs", ["investigation_id"]
    )
    op.create_index(
        "ix_media_analysis_runs_media_asset_id", "media_analysis_runs", ["media_asset_id"]
    )
    op.add_column("evidence", sa.Column("media_analysis_run_id", uuid, nullable=True))
    op.create_foreign_key(
        "fk_evidence_media_analysis_run_id_media_analysis_runs",
        "evidence",
        "media_analysis_runs",
        ["media_analysis_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_evidence_media_analysis_run_id", "evidence", ["media_analysis_run_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_evidence_media_analysis_run_id", "evidence", type_="unique")
    op.drop_constraint(
        "fk_evidence_media_analysis_run_id_media_analysis_runs",
        "evidence",
        type_="foreignkey",
    )
    op.drop_column("evidence", "media_analysis_run_id")
    op.drop_index("ix_media_analysis_runs_media_asset_id", table_name="media_analysis_runs")
    op.drop_index("ix_media_analysis_runs_investigation_id", table_name="media_analysis_runs")
    op.drop_table("media_analysis_runs")
