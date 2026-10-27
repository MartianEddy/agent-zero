"""Persist bounded WhatsApp conversation context and investigation drafts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016_whatsapp_conversation"
down_revision = "0015_processing_job_lease"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("sender_ref", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("context_json", postgresql.JSONB(), nullable=False),
        sa.Column("processed_events", postgresql.JSONB(), nullable=False),
        sa.Column("draft_text", sa.Text(), nullable=True),
        sa.Column("draft_input_type", sa.String(length=20), nullable=True),
        sa.Column("proposed_claims", postgresql.JSONB(), nullable=False),
        sa.Column("proposed_queries", postgresql.JSONB(), nullable=False),
        sa.Column("clarification_question", sa.Text(), nullable=True),
        sa.Column("preview_version", sa.Integer(), nullable=False),
        sa.Column("draft_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_calls", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "sender_ref", name="uq_whatsapp_conversation_sender"),
    )
    op.create_index("ix_whatsapp_conversations_owner_id", "whatsapp_conversations", ["owner_id"])
    op.create_index(
        "ix_whatsapp_conversations_sender_ref", "whatsapp_conversations", ["sender_ref"]
    )
    op.create_index(
        "ix_whatsapp_conversations_expires_at", "whatsapp_conversations", ["expires_at"]
    )

    op.add_column(
        "model_usage_records",
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
    )
    op.alter_column("model_usage_records", "investigation_id", nullable=True)
    op.create_index(
        "ix_model_usage_records_conversation_id",
        "model_usage_records",
        ["conversation_id"],
    )
    op.create_foreign_key(
        "fk_model_usage_records_conversation_id_whatsapp_conversations",
        "model_usage_records",
        "whatsapp_conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "model_usage_owner_valid",
        "model_usage_records",
        "(investigation_id IS NOT NULL AND conversation_id IS NULL) OR "
        "(investigation_id IS NULL AND conversation_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("model_usage_owner_valid", "model_usage_records", type_="check")
    op.drop_constraint(
        "fk_model_usage_records_conversation_id_whatsapp_conversations",
        "model_usage_records",
        type_="foreignkey",
    )
    op.drop_index("ix_model_usage_records_conversation_id", table_name="model_usage_records")
    op.drop_column("model_usage_records", "conversation_id")
    op.alter_column("model_usage_records", "investigation_id", nullable=False)
    op.drop_index("ix_whatsapp_conversations_expires_at", table_name="whatsapp_conversations")
    op.drop_index("ix_whatsapp_conversations_sender_ref", table_name="whatsapp_conversations")
    op.drop_index("ix_whatsapp_conversations_owner_id", table_name="whatsapp_conversations")
    op.drop_table("whatsapp_conversations")
