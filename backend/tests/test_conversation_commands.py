"""The command module handles typed commands on its own, with no AI model involved."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.modules.conversations.schemas import ConversationTurn
from app.modules.conversations.service import commands


def _turn(text: str, **conversation) -> commands.Turn:
    state = {"state": "IDLE", "context_json": [], "processed_events": [], **conversation}
    return commands.Turn(
        session=MagicMock(),
        conversation=SimpleNamespace(**state),
        event=ConversationTurn(message_id="m1", sender="254700000000", message_type="text", text=text),
        settings=SimpleNamespace(whatsapp_owner_id=None, whatsapp_support_url=None),
        send_message=MagicMock(),
        sender_ref="ref",
        now=datetime.now(UTC),
        pending=False,
        command=text,
        folded=text.casefold(),
    )


def test_help_is_answered_without_the_model() -> None:
    turn = _turn("help")
    with (
        patch("app.modules.conversations.service.inbound._complete_inbound_event"),
        patch("app.modules.conversations.service.ports.ModelGateway") as gateway,
        patch(
            "app.modules.conversations.service.ports.run_in_threadpool",
            side_effect=lambda fn, *a, **k: asyncio.sleep(0, fn(*a, **k)),
        ),
    ):
        assert asyncio.run(commands.handle_command(turn)) is True
    gateway.assert_not_called()
    assert "RESULT" in turn.send_message.call_args.args[1]


def test_free_text_is_left_for_the_ai_flow() -> None:
    turn = _turn("Is it true that the budget doubled?")
    assert asyncio.run(commands.handle_command(turn)) is False
    turn.send_message.assert_not_called()


def _run_command(text: str, target: str):
    turn = _turn(text, id="conversation-1")
    with (
        patch("app.modules.conversations.service.inbound._complete_inbound_event"),
        patch(
            "app.modules.conversations.service.ports.run_in_threadpool",
            side_effect=lambda fn, *a, **k: asyncio.sleep(0, fn(*a, **k)),
        ),
        patch(f"app.modules.conversations.service.case_replies.{target}", return_value="ok") as reply,
    ):
        assert asyncio.run(commands.handle_command(turn)) is True
    return reply


def test_short_references_are_accepted_however_they_are_typed() -> None:
    for text in ("result AZ-7KQ2F", "result az 7kq2f", "RESULT 7KQ2F", "result AZ-7KQ2F."):
        reply = _run_command(text.rstrip("."), "_result_message")
        assert reply.call_args.kwargs["reference"] == "AZ-7KQ2F"
    assert _run_command("status 7kq2f", "_status_message").call_args.kwargs["reference"] == (
        "AZ-7KQ2F"
    )
    assert _run_command("retry az-7kq2f", "_retry_message").call_args.kwargs["reference"] == (
        "AZ-7KQ2F"
    )


def test_older_references_still_work_in_commands() -> None:
    reply = _run_command("result AZ-261028-ED24C0", "_result_message")
    assert reply.call_args.kwargs["reference"] == "AZ-261028-ED24C0"


def test_kiswahili_command_with_a_short_reference() -> None:
    from app.modules.conversations.messages import normalize_command_alias

    assert normalize_command_alias("matokeo AZ-7KQ2F") == "result AZ-7KQ2F"
    assert normalize_command_alias("matokeo az 7kq2f") == "result az 7kq2f"
