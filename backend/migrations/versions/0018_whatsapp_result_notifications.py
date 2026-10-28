"""Add encrypted short-lived WhatsApp reply routing and notification preferences."""

import sqlalchemy as sa
from alembic import op

revision = "0018_whatsapp_result_notifications"
down_revision = "0017_whatsapp_inbound_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_conversations",
        sa.Column("recipient_encrypted", sa.Text(), nullable=True),
    )
    op.add_column(
        "whatsapp_conversations",
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "whatsapp_notification_preferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("sender_ref", sa.String(length=64), nullable=False),
        sa.Column(
            "notifications_disabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id", "sender_ref", name="uq_whatsapp_notification_preference"
        ),
    )
    op.create_index(
        "ix_whatsapp_notification_preferences_owner_id",
        "whatsapp_notification_preferences",
        ["owner_id"],
    )
    op.create_index(
        "ix_whatsapp_notification_preferences_sender_ref",
        "whatsapp_notification_preferences",
        ["sender_ref"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_whatsapp_notification_preferences_sender_ref",
        table_name="whatsapp_notification_preferences",
    )
    op.drop_index(
        "ix_whatsapp_notification_preferences_owner_id",
        table_name="whatsapp_notification_preferences",
    )
    op.drop_table("whatsapp_notification_preferences")
    op.drop_column("whatsapp_conversations", "last_inbound_at")
    op.drop_column("whatsapp_conversations", "recipient_encrypted")
