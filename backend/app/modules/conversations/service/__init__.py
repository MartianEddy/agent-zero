"""WhatsApp conversation service, split by responsibility.

handler.py handles one inbound message. identity.py derives the per-user key; inbound.py
holds conversation state and delivery receipts; drafts.py builds and confirms claim
previews; case_replies.py formats saved results, status and history. Outside dependencies
are reached through ports.py so tests patch each one in a single place.
"""

from app.modules.conversations.service.case_replies import (  # noqa: F401
    _case_list_message,
    _factual_answer_message,
    _latest_case,
    _model_unavailable_reply,
    _result_message,
    _retrieved_sources,
    _retry_available,
    _retry_message,
    _source_bullets,
    _source_pairs,
    _status_message,
    _with_reference,
)
from app.modules.conversations.service.common import (  # noqa: F401
    _CHECK_AS_IS,
    _CLARIFICATION_MARKER,
    _EDIT_PROMPT,
    _FAILURE_COPY,
    _QUICK_ANSWER_MARKER,
    _RUN_FULL_CHECK,
    _STRICT_CONFIRMATIONS,
    _UNRESOLVED_CLAIM_PATTERN,
    INBOUND_EVENT_LEASE,
    INBOUND_EVENT_PROVIDER,
    MAX_CLARIFICATION_ROUNDS,
    MAX_MESSAGE_CHARS,
    ConversationTurnInProgress,
    _owner_id,
    logger,
)
from app.modules.conversations.service.drafts import (  # noqa: F401
    _clarification_rounds,
    _confirm_conversation_draft,
    _draft_words,
    _last_exchange,
    _looks_like_confirmation,
    _offer_check_as_written,
    _prepare_preview,
    _preview_button_code,
    _preview_code_in,
    _typed_confirmation_code,
)
from app.modules.conversations.service.handler import (  # noqa: F401
    ConversationService,
    _handle_turn,
)
from app.modules.conversations.service.identity import (  # noqa: F401
    _adopt_legacy_identity,
    _decrypt_recipient,
    _encrypt_recipient,
    _identity_refs,
    _notification_preference,
    _notification_preference_for,
    _recipient_cipher,
    _sender_reference,
)
from app.modules.conversations.service.inbound import (  # noqa: F401
    _append_turn,
    _claim_inbound_event,
    _clear_conversation_draft,
    _complete_inbound_event,
    _conversation_for_sender,
    _send_saved_reply,
)
