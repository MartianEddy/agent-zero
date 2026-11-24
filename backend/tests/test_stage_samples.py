from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from pydantic import BaseModel

from app.modules.investigations.privacy import redact_pii
from app.modules.investigations.usage import maybe_capture_sample


class _Output(BaseModel):
    answer: str


def _record():
    return SimpleNamespace(id=uuid4(), purpose="EVIDENCE_REASONING", prompt_version="abc123")


def test_capture_is_off_by_default_and_stores_nothing():
    session = MagicMock()
    stored = maybe_capture_sample(
        session, _record(), prompt="claim", output=_Output(answer="x"), enabled=False
    )
    assert stored is False
    session.add.assert_not_called()


def test_capture_stores_a_redacted_prompt_and_json_output_when_enabled():
    session = MagicMock()
    stored = maybe_capture_sample(
        session,
        _record(),
        prompt="Call me on +254 712 345 678 or mail jane@example.com about the budget",
        output=_Output(answer="ok"),
        enabled=True,
    )
    assert stored is True
    sample = session.add.call_args.args[0]
    assert "[phone]" in sample.input_text and "[email]" in sample.input_text
    assert "712" not in sample.input_text and "jane@" not in sample.input_text
    assert sample.output_json == {"answer": "ok"}
    assert sample.prompt_version == "abc123"


def test_redaction_keeps_claim_numbers_that_are_not_identifiers():
    text = "Kenya's population is 47.6 million and inflation was 6.8 percent in 2024."
    assert redact_pii(text) == text


def test_redaction_handles_local_numbers_and_long_ids():
    assert "[phone]" in redact_pii("Reach 0712 345678 today")
    assert "[number]" in redact_pii("National ID 12345678901 was shown")
