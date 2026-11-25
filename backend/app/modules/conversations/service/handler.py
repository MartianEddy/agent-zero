"""Handle one inbound WhatsApp message: commands first, then the AI-guided flow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.domain.investigation import InputType
from app.modules.conversations import messages as copy
from app.modules.conversations.schemas import ConversationTurn
from app.modules.conversations.service import (
    case_replies,
    commands,
    common,
    drafts,
    identity,
    inbound,
    ports,
)
from app.modules.investigations.investigator import ModelInvocationFailed
from app.modules.investigations.usage import ModelCallBudgetExceeded


async def _handle_turn(session: Session, event: ConversationTurn, settings, send_message) -> bool:
    """Handle conversation turns separately from investigation records."""
    identity_key = settings.whatsapp_identity_key.get_secret_value()
    sender_ref, legacy_ref = identity._identity_refs(event, identity_key)
    now = datetime.now(UTC)
    if legacy_ref is not None:
        identity._adopt_legacy_identity(
            session,
            owner_id=common._owner_id(settings),
            sender_ref=sender_ref,
            legacy_ref=legacy_ref,
        )
    conversation = inbound._conversation_for_sender(
        session, owner_id=common._owner_id(settings), sender_ref=sender_ref, now=now
    )
    saved_reply = inbound._claim_inbound_event(
        session,
        conversation=conversation,
        event=event,
        sender_ref=sender_ref,
        now=now,
    )
    if saved_reply is not None:
        if saved_reply:
            await inbound._deliver(
                session, event=event, send_message=send_message, reply=saved_reply
            )
        return True

    conversation.recipient_encrypted = identity._encrypt_recipient(event.sender, settings)
    conversation.last_inbound_at = now

    if event.message_type not in {"text", "interactive"} or event.text is None:
        await inbound._send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            user_text="[unsupported message type]",
            reply=(
                "I can only read text and links in this chat for now. "
                "Paste the claim or a link and I’ll take a look."
            ),
            send_message=send_message,
        )
        return True

    command = event.text.strip()
    if len(command) > common.MAX_MESSAGE_CHARS:
        await inbound._send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            user_text=command,
            reply=(
                f"That message is too long for me. Please send the key part, under "
                f"{common.MAX_MESSAGE_CHARS:,} characters."
            ),
            send_message=send_message,
        )
        return True

    previous_reply = next(
        (
            item.get("reply", "")
            for item in reversed(conversation.processed_events or [])
            if item.get("message_id") == event.message_id
        ),
        None,
    )
    if previous_reply is not None:
        inbound._complete_inbound_event(session, event=event, reply=previous_reply)
        session.commit()
        await inbound._deliver(
            session, event=event, send_message=send_message, reply=previous_reply
        )
        return True

    normalized_command = " ".join(command.casefold().split())
    if any(
        normalized_command == " ".join(item.get("reply", "").casefold().split())
        for item in (conversation.processed_events or [])
    ):
        # Some inbox automation replays the agent's own outbound text as inbound.
        inbound._complete_inbound_event(session, event=event, reply="", state="IGNORED")
        session.commit()
        return True

    pending = conversation.state in {"NEEDS_CLARIFICATION", "AWAITING_CONFIRMATION"}
    draft_expiry = conversation.draft_expires_at
    if draft_expiry is not None and draft_expiry.tzinfo is None:
        draft_expiry = draft_expiry.replace(tzinfo=UTC)
    if pending and (draft_expiry is None or draft_expiry <= now):
        inbound._clear_conversation_draft(conversation)
        if drafts._looks_like_confirmation(command):
            await inbound._send_saved_reply(
                session,
                conversation=conversation,
                event=event,
                send_message=send_message,
                user_text=command,
                reply=(
                    "That preview expired, so I didn't start an investigation. "
                    "Please send the claim again and I'll prepare a fresh preview."
                ),
            )
            return True
        pending = False

    command = copy.normalize_command_alias(command)
    folded = command.casefold()
    if await commands.handle_command(
        commands.Turn(
            session=session,
            conversation=conversation,
            event=event,
            settings=settings,
            send_message=send_message,
            sender_ref=sender_ref,
            now=now,
            pending=pending,
            command=command,
            folded=folded,
        )
    ):
        return True

    if not pending and folded.strip(" .!") in common._RUN_FULL_CHECK:
        previous_user, previous_reply = drafts._last_exchange(conversation)
        if common._QUICK_ANSWER_MARKER in previous_reply and previous_user:
            # Turn the question that got a quick answer into a full check, so "yes" or
            # "check" after a quick answer moves forward instead of starting over.
            command = f"Please check this claim: {previous_user}"
            folded = command.casefold()

    draft_text = conversation.draft_text if pending else None
    if pending and conversation.clarification_question == common._EDIT_PROMPT:
        # A correction after tapping Edit replaces the old claim instead of adding to it.
        draft_text = None
    if pending and folded.startswith("edit "):
        command = command[5:].strip()
        draft_text = command
        inbound._clear_conversation_draft(conversation)
        pending = False

    context = list(conversation.context_json or [])
    if draft_text:
        context.append(
            {
                "role": "assistant",
                "content": f"Active investigation draft: {draft_text[:1200]}",
            }
        )
    gateway = ports.ModelGateway()
    try:
        model_run = await gateway.interpret_whatsapp_turn(
            text=command,
            context=context,
            active_draft=draft_text,
            draft_state=conversation.state if pending else None,
            confirmation_token=conversation.confirmation_token if pending else None,
            session=session,
            conversation_id=conversation.id,
        )
        factual_run = None
        if model_run.output.intent == "FACTUAL_ANSWER_REQUEST":
            factual_run = await gateway.answer_whatsapp_factual_question(
                text=command,
                context=context,
                session=session,
                conversation_id=conversation.id,
            )
    except (ModelInvocationFailed, ModelCallBudgetExceeded) as exc:
        common.logger.warning(
            "WhatsApp conversational model unavailable category=%s", type(exc).__name__
        )
        reply = case_replies._model_unavailable_reply(exc)
        await inbound._send_saved_reply(
            session,
            conversation=conversation,
            event=event,
            send_message=send_message,
            user_text=event.text,
            reply=reply,
        )
        return True

    output = model_run.output
    common.logger.info(
        "WhatsApp conversation classified intent=%s draft_pending=%s",
        output.intent,
        pending,
    )
    reply_buttons: list[tuple[str, str]] | None = None
    if output.intent == "CONFIRM_DRAFT":
        code = drafts._preview_code_in(command) or drafts._typed_confirmation_code(
            conversation, event, command
        )
        if not pending or conversation.state != "AWAITING_CONFIRMATION":
            reply = "There’s nothing to submit yet. Send me the claim you want checked first."
        elif code is None:
            reply = "Tap *Submit claim* below to start, or reply *YES*. Nothing has started yet."
            reply_buttons = [
                (f"SUBMIT {conversation.confirmation_token}", "Submit claim"),
                (f"EDIT {conversation.confirmation_token}", "Edit claim"),
                (f"CANCEL {conversation.confirmation_token}", "Cancel"),
            ]
        else:
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
                return True
            await inbound._send_saved_reply(
                session,
                conversation=conversation,
                event=event,
                send_message=send_message,
                user_text=command,
                reply=reply,
            )
            return True
    elif output.intent == "CONVERSATION":
        # Luna owns the wording for ordinary conversation. Application policy
        # still owns intents, authorization, case creation, and all side effects.
        reply = output.reply.strip() or "I’m here. What would you like to talk about?"
    elif output.intent == "FACTUAL_ANSWER_REQUEST":
        answer = factual_run.output.answer if factual_run else ""
        citations = factual_run.citations if factual_run else ()
        reply = case_replies._factual_answer_message(answer, citations)
        if pending and conversation.state == "AWAITING_CONFIRMATION":
            reply += (
                "\n\nYour claim preview is still waiting. Reply *YES* to start it, or *CANCEL*."
            )
    elif output.intent == "CASE_LIST_REQUEST":
        reply = case_replies._case_list_message(session, settings=settings, sender_ref=sender_ref)
    elif output.intent == "STATUS_REQUEST":
        reply = case_replies._status_message(
            session,
            settings=settings,
            sender_ref=sender_ref,
            reference=output.reference,
        )
    elif output.intent == "RESULT_REQUEST":
        reply = case_replies._result_message(
            session,
            settings=settings,
            sender_ref=sender_ref,
            reference=output.reference,
        )
    elif output.intent == "CANCEL_DRAFT":
        if pending:
            inbound._clear_conversation_draft(conversation)
            reply = "Cancelled. Nothing was started. Send another claim whenever you’re ready."
        else:
            reply = "There’s nothing waiting to cancel, and your existing checks are untouched."
    elif output.intent == "INVESTIGATION_REQUEST" and any(
        common._UNRESOLVED_CLAIM_PATTERN.search(claim.text) for claim in output.claims
    ):
        conversation.draft_text = (
            f"{draft_text}\nClarification: {command}"
            if pending and draft_text
            else (draft_text or command)
        )
        conversation.proposed_claims = []
        conversation.proposed_queries = []
        conversation.confirmation_token = None
        conversation.preview_version += 1
        conversation.draft_expires_at = now + timedelta(minutes=30)
        question = (
            "To check this I need one more detail: who or what exactly is it about, and when? "
            "A name, a place or a link is enough."
        )
        conversation.clarification_question = question
        if drafts._clarification_rounds(conversation.draft_text) >= common.MAX_CLARIFICATION_ROUNDS:
            reply, reply_buttons = drafts._offer_check_as_written(
                conversation, "I still can’t pin down one exact claim from this."
            )
        else:
            conversation.state = "NEEDS_CLARIFICATION"
            reply = f"{question} Nothing has started yet."
    elif output.intent == "INVESTIGATION_REQUEST":
        conversation.draft_text = (
            f"{draft_text}\nClarification: {command}"
            if pending and draft_text
            else (draft_text or command)
        )
        parsed = urlsplit(conversation.draft_text.strip())
        if parsed.scheme in {"http", "https"} and (
            not parsed.hostname or parsed.username or parsed.password
        ):
            inbound._clear_conversation_draft(conversation)
            reply = (
                "That link doesn’t look valid. Send a public http or https URL or "
                "describe the claim in your own words."
            )
        else:
            conversation.draft_input_type = (
                InputType.URL.value if parsed.scheme in {"http", "https"} else InputType.TEXT.value
            )
            conversation.preview_version += 1
            conversation.draft_expires_at = now + timedelta(minutes=30)
            conversation.clarification_question = output.clarification_question
            if not output.claims:
                conversation.proposed_claims = []
                conversation.confirmation_token = None
                conversation.state = (
                    "NEEDS_CLARIFICATION" if output.clarification_question else "IDLE"
                )
                if output.clarification_question and (
                    drafts._clarification_rounds(conversation.draft_text)
                    >= common.MAX_CLARIFICATION_ROUNDS
                ):
                    reply, reply_buttons = drafts._offer_check_as_written(
                        conversation, output.clarification_question
                    )
                elif output.clarification_question:
                    reply = (
                        f"{output.clarification_question}\n\n"
                        "Nothing has started yet. Reply with the detail, or *CANCEL*."
                    )
                else:
                    inbound._clear_conversation_draft(conversation)
                    reply = (
                        "I couldn’t find a fact I can check in that. Opinions and predictions "
                        "can’t be fact-checked. If there’s a specific fact in it, like a number, "
                        "a date, or who said or did what, send just that part, or paste the "
                        "exact message you received."
                    )
            else:
                reply, reply_buttons = drafts._prepare_preview(
                    session,
                    conversation=conversation,
                    settings=settings,
                    sender_ref=sender_ref,
                    claims=[
                        {"text": claim.text, "claim_type": claim.claim_type}
                        for claim in output.claims
                    ],
                    queries=[
                        {
                            "text": query.text,
                            "claim_index": query.claim_index,
                            "freshness": query.freshness,
                            "topic": query.topic,
                            "jurisdiction": query.jurisdiction,
                            "source_lane": query.source_lane,
                            "widening_reason": query.widening_reason,
                        }
                        for query in output.queries
                    ],
                )
    await inbound._send_saved_reply(
        session,
        conversation=conversation,
        event=event,
        send_message=send_message,
        user_text=event.text,
        reply=reply,
        buttons=reply_buttons,
    )
    return True


class ConversationService:
    """Application boundary for channel-neutral conversation state transitions."""

    def __init__(self, session: Session, settings) -> None:
        self.session = session
        self.settings = settings

    async def handle_turn(self, turn: ConversationTurn, send_message) -> bool:
        return await _handle_turn(self.session, turn, self.settings, send_message)
