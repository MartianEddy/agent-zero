from app.modules.conversations import messages as m


def _finding(status="SUPPORTED", claim="Nairobi is the capital of Kenya.", confidence="MEDIUM"):
    return m.FindingView(
        status=status,
        claim=claim,
        headline="Two independent sources say so.",
        confidence=confidence,
        confidence_reason="Two independent source groups were found.",
    )


def test_single_result_leads_with_verdict_then_claim_then_why():
    text = m.result_message(
        [_finding()],
        sources=[("Constitution", "https://kenyalaw.org/constitution")],
        limitations=[],
        reference="AZ-261028-ABC123",
    )
    assert text.startswith("*Evidence supports this claim*")
    assert text.index("*Claim:*") < text.index("*Why:*") < text.index("*Evidence strength:*")
    assert "https://kenyalaw.org/constitution" in text
    assert text.endswith("_Ref: AZ-261028-ABC123_")
    assert "probability" not in text.lower()  # wording is "chance the claim is true"


def test_every_verdict_has_distinct_plain_headline():
    labels = set(m.VERDICT_HEADLINES.values())
    assert len(labels) == 5
    for status in m.VERDICT_HEADLINES:
        text = m.result_message(
            [_finding(status=status)], sources=[], limitations=[], reference="AZ-1"
        )
        assert m.VERDICT_HEADLINES[status] in text


def test_insufficient_evidence_never_reads_as_false():
    text = m.result_message(
        [_finding(status="INSUFFICIENT_EVIDENCE", confidence="LOW")],
        sources=[],
        limitations=[],
        reference="AZ-1",
    )
    assert "Not enough evidence yet" in text
    assert "false" not in text.lower()


def test_multiple_claims_are_numbered_with_their_own_verdicts():
    text = m.result_message(
        [_finding(), _finding(status="CONTRADICTED", claim="Mombasa is the capital.")],
        sources=[],
        limitations=["Only public sources were reviewed."],
        reference="AZ-1",
    )
    assert "*2 claims checked*" in text
    assert "1. *" in text and "2. *" in text
    assert "Only public sources were reviewed." in text


def test_stopped_check_is_flagged_preliminary_with_retry_hint():
    text = m.result_message(
        [_finding()],
        sources=[],
        limitations=[],
        reference="AZ-1",
        stopped_early=True,
        stopped_reason=m.failure_reason("TIMEOUT"),
        retry_hint="Reply *RETRY AZ-1* to try again.",
    )
    assert text.startswith("*This check stopped early")
    assert "took too long" in text and "RETRY AZ-1" in text


def test_messages_fit_whatsapp_limit_and_keep_reference():
    long_claim = "word " * 2000
    text = m.result_message(
        [_finding(claim=long_claim)] * 3,
        sources=[("T" * 90, "https://example.org/" + "a" * 300)] * 3,
        limitations=["x" * 500],
        reference="AZ-261028-ABC123",
    )
    assert len(text) <= 4096
    assert text.endswith("_Ref: AZ-261028-ABC123_")


def test_failure_reasons_are_plain_language_without_internal_terms():
    for code, reason in m.FAILURE_REASONS.items():
        assert "model" not in reason.lower() and "provider" not in reason.lower(), code
    assert m.failure_reason("UNKNOWN_CODE") == m.DEFAULT_FAILURE_REASON
    assert m.failure_reason(None) == m.DEFAULT_FAILURE_REASON


def test_status_message_covers_progress_done_and_stopped():
    progress = m.status_message("RESEARCHING", "RESEARCHING", "AZ-1", queued_retry=False)
    assert "Searching for sources" in progress and "RESULT" in progress
    assert "Done" in m.status_message("COMPLETE", "COMPLETE", "AZ-1", queued_retry=False)
    stopped = m.status_message(
        "RESEARCHING", "NEEDS_REVIEW", "AZ-1", queued_retry=False, retry_hint="Reply *RETRY*."
    )
    assert "stopped before it finished" in stopped and "Reply *RETRY*." in stopped
    assert "waiting in line" in m.status_message(
        None, "NEEDS_REVIEW", "AZ-1", queued_retry=True
    )


def test_preview_states_nothing_started_and_lists_claims():
    text = m.preview_message(["A.", "B."], notification_notice="I’ll message you.")
    assert "Here are the claims" in text and "• A." in text and "• B." in text
    assert "Nothing has started yet" in text


def test_swahili_aliases_only_apply_to_bare_commands():
    assert m.normalize_command_alias("msaada") == "help"
    assert m.normalize_command_alias("Matokeo AZ-261028-ABC123") == "result AZ-261028-ABC123"
    assert m.normalize_command_alias("hali") == "status"
    assert m.normalize_command_alias("jaribu tena") == "retry"
    # Ordinary sentences are never rewritten.
    assert m.normalize_command_alias("hali ya hewa ni mbaya") == "hali ya hewa ni mbaya"
    assert m.normalize_command_alias("Is the menu price 500?") == "Is the menu price 500?"


def test_help_lists_main_actions_in_both_languages():
    text = m.help_message()
    for word in ("RESULT", "HISTORY", "STATUS", "STOP", "MSAADA"):
        assert word in text


def test_user_facing_copy_contains_no_emoji():
    import inspect
    import re

    emoji = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\uFE0F]")
    source = inspect.getsource(m)
    assert not emoji.search(source)
    sample = m.result_message(
        [_finding()], sources=[], limitations=[], reference="AZ-1"
    ) + m.help_message() + m.registered_message("AZ-1", "x")
    assert not emoji.search(sample)
