"""Add durable inbound event receipts and preview-bound confirmation codes."""

import sqlalchemy as sa
from alembic import op

revision = "0017_whatsapp_inbound_receipts"
down_revision = "0016_whatsapp_conversation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_conversations",
        sa.Column("confirmation_token", sa.String(length=24), nullable=True),
    )
    op.create_table(
        "whatsapp_inbound_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("message_id", sa.String(length=200), nullable=False),
        sa.Column("sender_ref", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("reply_text", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["whatsapp_conversations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "message_id", name="uq_whatsapp_inbound_provider_message"
        ),
    )
    op.create_index(
        "ix_whatsapp_inbound_events_conversation_id",
        "whatsapp_inbound_events",
        ["conversation_id"],
    )
    op.create_index(
        "ix_whatsapp_inbound_events_expires_at",
        "whatsapp_inbound_events",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_whatsapp_inbound_events_expires_at", table_name="whatsapp_inbound_events")
    op.drop_index(
        "ix_whatsapp_inbound_events_conversation_id", table_name="whatsapp_inbound_events"
    )
    op.drop_table("whatsapp_inbound_events")
    op.drop_column("whatsapp_conversations", "confirmation_token")
