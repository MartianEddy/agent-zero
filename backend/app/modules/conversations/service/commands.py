"""Typed commands and button taps that never need the AI model.

HELP, STOP and ALERTS ON, RETRY, RESULT, STATUS, HISTORY, CANCEL, Edit, SUBMIT or YES on a
preview, and Check as written. handle_command returns True when the message was handled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.modules.conversations import messages as copy
from app.modules.conversations.models import (
    WhatsAppNotificationPreference,
)
from app.modules.conversations.schemas import ConversationTurn
from app.modules.conversations.service import case_replies, common, drafts, identity, inbound


@dataclass
class Turn:
    """Everything a command needs about the current message and conversation."""

    session: Session
    conversation: object
    event: ConversationTurn
    settings: object
    send_message: object
    sender_ref: str
    now: datetime
    pending: bool
    command: str
    folded: str


async def handle_command(turn: Turn) -> bool:
    session = turn.session
    conversation = turn.conversation
    event = turn.event
    settings = turn.settings
    send_message = turn.send_message
    sender_ref = turn.sender_ref
    now = turn.now
    pending = turn.pending
    command = turn.command
    folded = turn.folded

    if (
        not pending
        and folded
        in {
            "start",
            "start investigation",
            "submit",
            "submit claim",
            "confirm",
            "yes",
        }
        and common._QUICK_ANSWER_MARKER not in drafts._last_exchange(conversation)[1]
    ):
        await inbound._send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=(
                "There’s nothing to submit yet. Tell me the claim you want checked and I’ll "
                "show you what I understood first. Nothing has started."
            ),
        )
        return True
    if folded == "help":
        reply = copy.help_message()
        await inbound._send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=reply,
        )
        return True
    if folded in {"stop", "mute", "alerts off", "notifications off"}:
        preference = identity._notification_preference(
            session, settings=settings, sender_ref=sender_ref
        )
        if preference is None:
            session.add(
                WhatsAppNotificationPreference(
                    owner_id=common._owner_id(settings),
                    sender_ref=sender_ref,
                    notifications_disabled=True,
                )
            )
        else:
            preference.notifications_disabled = True
        reply = (
            "*Automatic result messages are off.* Your checks will still run. "
            "Reply *ALERTS ON* to turn them back on, or *HISTORY* to see your checks."
        )
        await inbound._send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=reply,
        )
        return True
    if folded in {"alerts on", "notifications on"}:
        preference = identity._notification_preference(
            session, settings=settings, sender_ref=sender_ref
        )
        if preference is not None:
            session.delete(preference)
        if getattr(settings, "whatsapp_support_url", None):
            reply = (
                "*Automatic result messages are on.* I’ll send each result here when it’s "
                "ready, as long as you’ve messaged me in the last 24 hours. Reply *STOP* any time."
            )
        else:
            reply = (
                "I’ve saved your choice, but automatic result messages aren’t available yet. "
                "Reply *RESULT* any time to see your latest result."
            )
        await inbound._send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=reply,
        )
        return True
    if folded == "retry" or folded == "try again" or folded.startswith("retry "):
        reference = command[5:].strip() if folded.startswith("retry ") else None
        if reference and not re.fullmatch(r"AZ-[0-9]{6}-[A-F0-9]{6}", reference, re.IGNORECASE):
            reply = "To retry, reply *RETRY* or *RETRY* followed by the reference."
        else:
            reply = case_replies._retry_message(
                session, settings=settings, sender_ref=sender_ref, reference=reference
            )
        await inbound._send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=reply,
        )
        return True
    if folded in {"result", "results"} or folded.startswith(("result ", "results ")):
        reference = re.sub(r"^results?\s*", "", command, flags=re.IGNORECASE).strip() or None
        if reference and not re.fullmatch(r"AZ-[0-9]{6}-[A-F0-9]{6}", reference, re.IGNORECASE):
            reply = "To see a result, reply *RESULT* or *RESULT* followed by the reference."
        else:
            reply = case_replies._result_message(
                session,
                settings=settings,
                sender_ref=sender_ref,
                reference=reference,
                conversation_id=conversation.id,
            )
        await inbound._send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=reply,
        )
        return True
    if folded == "status" or folded.startswith("status "):
        reference = command[6:].strip() or None
        if reference and not re.fullmatch(r"AZ-[0-9]{6}-[A-F0-9]{6}", reference, re.IGNORECASE):
            reply = "To check progress, reply *STATUS* or *STATUS* followed by the reference."
        else:
            reply = case_replies._status_message(
                session, settings=settings, sender_ref=sender_ref, reference=reference
            )
        await inbound._send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=reply,
        )
        return True
    if (
        folded
        in {
            "history",
            "case history",
            "cases",
            "my checks",
            "my investigations",
            "my cases",
            "list investigations",
        }
        or folded in {"history more", "cases more"}
        or folded.startswith("history ")
    ):
        if folded in {"history more", "cases more"}:
            page = 2
        elif folded in {
            "history",
            "case history",
            "cases",
            "my checks",
            "my investigations",
            "my cases",
            "list investigations",
        }:
            page = 1
        else:
            page_text = command.split(maxsplit=1)[1]
            if page_text.isdigit() and 1 <= int(page_text) <= 100:
                page = int(page_text)
            else:
                page = 0
        reply = (
            "Reply *HISTORY* for your latest checks, or *HISTORY 2* for older ones."
            if page == 0
            else case_replies._case_list_message(
                session, settings=settings, sender_ref=sender_ref, page=page
            )
        )
        await inbound._send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=reply,
        )
        return True
    interactive_cancel = event.message_type == "interactive" and folded.startswith("cancel")
    if interactive_cancel:
        code = drafts._preview_button_code(command, "CANCEL")
        if (
            not pending
            or conversation.state != "AWAITING_CONFIRMATION"
            or code != conversation.confirmation_token
        ):
            await inbound._send_saved_reply(
                session,
                conversation=conversation,
                event=event,
                send_message=send_message,
                user_text=command,
                reply=(
                    "That button is from an older preview, so I ignored it. "
                    "Use the latest preview, or reply *CANCEL* to start over."
                ),
            )
            return True
        inbound._clear_conversation_draft(conversation)
        await inbound._send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply="Cancelled. Nothing was started. Send another claim whenever you’re ready.",
        )
        return True
    if folded == "cancel":
        if pending:
            inbound._clear_conversation_draft(conversation)
            reply = "Cancelled. Nothing was started. Send another claim whenever you’re ready."
        else:
            reply = "There’s nothing waiting to cancel, and your existing checks are untouched."
        await inbound._send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=reply,
        )
        return True
    interactive_edit = event.message_type == "interactive" and folded.startswith("edit")
    if interactive_edit and (
        not pending
        or conversation.state != "AWAITING_CONFIRMATION"
        or drafts._preview_button_code(command, "EDIT") != conversation.confirmation_token
    ):
        await inbound._send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=(
                "That button is from an older preview, so I ignored it. "
                "Use the latest preview, or reply *EDIT* followed by your correction."
            ),
        )
        return True
    if (
        pending
        and conversation.state == "AWAITING_CONFIRMATION"
        and (folded in {"edit", "edit claim"} or interactive_edit)
    ):
        conversation.state = "NEEDS_CLARIFICATION"
        conversation.proposed_claims = []
        conversation.proposed_queries = []
        conversation.confirmation_token = None
        conversation.preview_version += 1
        conversation.clarification_question = common._EDIT_PROMPT
        conversation.draft_expires_at = now + timedelta(minutes=30)
        await inbound._send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=command,
            reply=(
                "Send the corrected claim in your next message and I’ll show you a new "
                "preview before anything starts. Reply *CANCEL* to stop."
            ),
        )
        return True
    if pending and conversation.state == "AWAITING_CONFIRMATION":
        folded_prefix = folded.split(maxsplit=1)[0] if folded else ""
        typed_code = drafts._typed_confirmation_code(conversation, event, command)
        if folded_prefix in {"submit", "confirm"} or typed_code is not None:
            code = drafts._preview_code_in(command) or typed_code
            if code is None:
                reply = (
                    "Tap *Submit claim* below to start, or reply *YES*. Nothing has started yet."
                )
                await inbound._send_saved_reply(
                    session,
                    conversation=conversation,
                    event=event,
                    send_message=send_message,
                    user_text=command,
                    reply=reply,
                    buttons=[
                        (f"SUBMIT {conversation.confirmation_token}", "Submit claim"),
                        (f"EDIT {conversation.confirmation_token}", "Edit claim"),
                        (f"CANCEL {conversation.confirmation_token}", "Cancel"),
                    ],
                )
                return True
            reply, saved = await drafts._confirm_conversation_draft(
                session,
                conversation=conversation,
                event=event,
                settings=settings,
                user_text=command,
                confirmation_code=code,
            )
            if saved:
                await inbound._deliver(session, event=event, send_message=send_message, reply=reply)
            else:
                await inbound._send_saved_reply(
                    session,
                    conversation=conversation,
                    event=event,
                    send_message=send_message,
                    user_text=command,
                    reply=reply,
                )
            return True

    if (
        pending
        and conversation.state == "NEEDS_CLARIFICATION"
        and (folded.strip(" .!") in common._CHECK_AS_IS)
    ):
        words = drafts._draft_words(conversation.draft_text or "")
        if len(words) >= 5:
            reply, buttons = drafts._prepare_preview(
                session,
                conversation=conversation,
                settings=settings,
                sender_ref=sender_ref,
                claims=[{"text": words, "claim_type": "CHECKABLE_EVENT"}],
                queries=[],
            )
            conversation.preview_version += 1
            conversation.draft_expires_at = now + timedelta(minutes=30)
            await inbound._send_saved_reply(
                session,
                conversation=conversation,
                event=event,
                send_message=send_message,
                user_text=command,
                reply=reply,
                buttons=buttons,
            )
            return True

    return False
