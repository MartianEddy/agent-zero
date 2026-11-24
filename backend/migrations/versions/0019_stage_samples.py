"""Record prompt version and latency per model call; add opt-in redacted stage samples."""

import sqlalchemy as sa
from alembic import op

revision = "0019_stage_samples"
down_revision = "0018_wa_result_notify"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("model_usage_records", sa.Column("prompt_version", sa.String(16), nullable=True))
    op.add_column("model_usage_records", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.create_table(
        "stage_samples",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("usage_record_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("prompt_version", sa.String(16), nullable=True),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["usage_record_id"], ["model_usage_records.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("usage_record_id"),
    )
    op.create_index("ix_stage_samples_purpose", "stage_samples", ["purpose"])


def downgrade() -> None:
    op.drop_index("ix_stage_samples_purpose", table_name="stage_samples")
    op.drop_table("stage_samples")
    op.drop_column("model_usage_records", "latency_ms")
    op.drop_column("model_usage_records", "prompt_version")
