from app.modules.channels.clickcast import ClickCastSubmitRequest


def test_clickcast_submission_accepts_request_without_event_id() -> None:
    request = ClickCastSubmitRequest(
        sender="254750288942",
        message="A factual claim to check",
    )

    assert request.event_id is None


def test_clickcast_submission_preserves_optional_event_id() -> None:
    request = ClickCastSubmitRequest(
        event_id="message-event-123",
        sender="+254750288942",
        message="A factual claim to check",
    )

    assert request.event_id == "message-event-123"
    assert request.sender == "254750288942"
