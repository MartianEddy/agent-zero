"""Add original and derived media asset lineage."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_media_asset_lineage"
down_revision = "0007_evidence_origin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "media_assets",
        sa.Column("parent_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "media_assets",
        sa.Column("asset_role", sa.String(20), nullable=False, server_default="ORIGINAL"),
    )
    op.add_column("media_assets", sa.Column("artifact_type", sa.String(40), nullable=True))
    op.add_column(
        "media_assets", sa.Column("transformation_version", sa.String(80), nullable=True)
    )
    op.add_column(
        "media_assets",
        sa.Column("transformation_metadata", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
    )
    op.create_foreign_key(
        "fk_media_assets_parent_asset_id", "media_assets", "media_assets",
        ["parent_asset_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_media_assets_parent_asset_id", "media_assets", ["parent_asset_id"])
    op.create_check_constraint(
        "ck_media_assets_asset_role_valid", "media_assets", "asset_role IN ('ORIGINAL', 'DERIVED')"
    )
    op.create_check_constraint(
        "ck_media_assets_asset_parent_not_self", "media_assets",
        "parent_asset_id IS NULL OR parent_asset_id != id"
    )
    op.create_check_constraint(
        "ck_media_assets_asset_parent_matches_role", "media_assets",
        "(asset_role = 'ORIGINAL' AND parent_asset_id IS NULL) OR "
        "(asset_role = 'DERIVED' AND parent_asset_id IS NOT NULL)"
    )
    op.create_unique_constraint(
        "uq_media_derivative_identity", "media_assets",
        ["parent_asset_id", "artifact_type", "transformation_version"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_media_derivative_identity", "media_assets", type_="unique")
    op.drop_constraint("ck_media_assets_asset_parent_matches_role", "media_assets", type_="check")
    op.drop_constraint("ck_media_assets_asset_parent_not_self", "media_assets", type_="check")
    op.drop_constraint("ck_media_assets_asset_role_valid", "media_assets", type_="check")
    op.drop_index("ix_media_assets_parent_asset_id", table_name="media_assets")
    op.drop_constraint("fk_media_assets_parent_asset_id", "media_assets", type_="foreignkey")
    for name in ("transformation_metadata", "transformation_version", "artifact_type", "asset_role", "parent_asset_id"):
        op.drop_column("media_assets", name)
