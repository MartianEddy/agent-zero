from dataclasses import dataclass


@dataclass(frozen=True)
class ConversationTurn:
    """Channel-neutral projection of one inbound message."""

    message_id: str
    # Where to send replies: a phone number, or a business-scoped user ID (BSUID).
    sender: str
    message_type: str
    text: str | None
    # Stable per-user ID from Meta; used as the identity key when present.
    user_id: str | None = None
