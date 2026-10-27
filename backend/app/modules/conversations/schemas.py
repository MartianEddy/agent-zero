from dataclasses import dataclass


@dataclass(frozen=True)
class ConversationTurn:
    """Channel-neutral projection of one inbound message."""

    message_id: str
    sender: str
    message_type: str
    text: str | None
