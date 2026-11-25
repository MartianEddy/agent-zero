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
        [_finding()], source_names=["Kenya Law", "Wikipedia"], reference="AZ-7KQ2F"
    )
    assert text.startswith("*Evidence supports this claim*")
    assert text.index("Nairobi is the capital") < text.index("Two independent sources say so.")
    assert text.index("*Sources:* Kenya Law, Wikipedia") < text.index("*How sure:* Medium")
    assert text.endswith("_Ref: AZ-7KQ2F_")
    assert len(text) <= m.INTERACTIVE_BODY_LIMIT
    assert "threshold" not in text and "source group" not in text


def test_every_verdict_has_distinct_plain_headline():
    labels = set(m.VERDICT_HEADLINES.values())
    assert len(labels) == 5
    for status in m.VERDICT_HEADLINES:
        text = m.result_message([_finding(status=status)], source_names=[], reference="AZ-1")
        assert m.VERDICT_HEADLINES[status] in text
        assert status in m.PLAIN_REASONS


def test_insufficient_evidence_never_reads_as_false():
    text = m.result_message(
        [_finding(status="INSUFFICIENT_EVIDENCE", confidence="LOW")],
        source_names=[],
        reference="AZ-1",
    )
    assert "Not enough evidence yet" in text
    assert "false" not in text.lower()
    assert "true or false" in m.PLAIN_REASONS["INSUFFICIENT_EVIDENCE"]


def test_multiple_claims_are_numbered_with_their_own_verdicts():
    text = m.result_message(
        [_finding(), _finding(status="CONTRADICTED", claim="Mombasa is the capital.")],
        source_names=["Wikipedia"],
        reference="AZ-1",
    )
    assert "*2 claims checked*" in text
    assert "1. *" in text and "2. *" in text
    assert "Mombasa is the capital." in text


def test_stopped_check_is_flagged_preliminary_with_retry_hint():
    text = m.result_message(
        [_finding()],
        source_names=[],
        reference="AZ-1",
        stopped_early=True,
        stopped_reason=m.failure_reason("TIMEOUT"),
        retry_hint="Reply *RETRY AZ-1* to try again.",
    )
    assert text.startswith("*This check stopped early")
    assert "took too long" in text and "RETRY AZ-1" in text


def test_result_always_fits_a_message_with_buttons():
    long_claim = "word " * 2000
    text = m.result_message(
        [_finding(claim=long_claim)] * 5,
        source_names=["T" * 90] * 3,
        reference="AZ-7KQ2F",
    )
    assert len(text) <= m.INTERACTIVE_BODY_LIMIT
    assert "*5 claims checked*" in text


def test_result_buttons_are_valid_meta_quick_replies():
    buttons = m.result_buttons("AZ-7KQ2F")
    assert [title for _id, title in buttons] == ["Sources", "Share", "Check another"]
    assert all(len(title) <= 20 and len(button_id) <= 256 for button_id, title in buttons)
    assert buttons[0][0] == "SOURCES AZ-7KQ2F" and buttons[2][0] == "NEW"


def test_share_card_is_self_contained_and_has_no_commands():
    card = m.share_card(
        [("Kenya won the 2022 FIFA World Cup.", "CONTRADICTED", "FIFA records show Argentina won.")],
        source_names=["FIFA", "Wikipedia"],
        reference="AZ-7KQ2F",
        whatsapp_number="+254 750 288 942",
        site_url="https://agent-zero-web.onrender.com/",
    )
    assert card.startswith("*Agent Zero fact-check*")
    assert "Evidence challenges this claim" in card and "Argentina" in card
    assert "https://wa.me/254750288942" in card
    assert "https://agent-zero-web.onrender.com" in card and card.endswith("Ref: AZ-7KQ2F")
    for command in ("RESULT", "HELP", "STATUS", "Tap"):
        assert command not in card


def test_sources_message_quotes_each_source():
    text = m.sources_message(
        [("FIFA", "https://www.fifa.com/x", "Argentina won the final.")], reference="AZ-7KQ2F"
    )
    assert "*1. FIFA*" in text and "Argentina won the final." in text
    assert "https://www.fifa.com/x" in text and text.endswith("_Ref: AZ-7KQ2F_")


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
    sample = (
        m.result_message([_finding()], source_names=[], reference="AZ-1")
        + m.help_message()
        + m.registered_message("AZ-1", "x")
        + m.share_card([("a", "SUPPORTED", "b")], source_names=[], reference="AZ-1",
                       whatsapp_number=None, site_url=None)
        + m.new_check_prompt()
        + m.no_result_yet()
    )
    assert not emoji.search(sample)


def test_questions_about_agent_zero_are_recognised_in_english_and_kiswahili():
    for text in ("who are you?", "Who built you", "who made u", "are you chatgpt?",
                 "Are you an AI?", "what model do you use", "Tell me about yourself",
                 "wewe ni nani", "nani alikutengeneza?", "umetengenezwa na nani"):
        assert m.is_question_about_agent_zero(text), text
    for text in ("Who built the Thika superhighway?", "Who owns Safaricom?",
                 "What are you checking for me?", "Is Nairobi the capital of Kenya?"):
        assert not m.is_question_about_agent_zero(text), text


def test_about_message_names_sinaps_and_is_honest_about_openai():
    text = m.about_agent_zero("Sinaps Technology", "https://agent-zero-web.onrender.com/")
    assert "built by Sinaps Technology" in text
    assert "including models from OpenAI" in text and "not ChatGPT" in text
    assert "https://agent-zero-web.onrender.com/methodology" in text


def test_share_card_keeps_its_line_breaks_and_drops_emoji():
    card = m.share_card(
        [("Big news \U0001F4A1 today", "SUPPORTED", "Two sources agree.")],
        source_names=["Wikipedia"], reference="AZ-1", whatsapp_number=None, site_url=None,
    )
    assert "\n\nClaim:" in card and "\n\nSources: Wikipedia" in card
    assert "\U0001F4A1" not in card


def test_without_sources_there_is_no_sources_button_or_hint():
    assert [t for _i, t in m.result_buttons("AZ-1", has_sources=False)] == [
        "Share", "Check another"
    ]
    text = m.result_message([_finding()], source_names=[], reference="AZ-1")
    assert "Tap *Share* to forward it." in text and "*Sources*" not in text


def test_quoted_source_text_has_no_emoji():
    text = m.sources_message(
        [("LinkedIn", "https://linkedin.com/x", "\U0001F4A1 How It Started")], reference="AZ-1"
    )
    assert "\U0001F4A1" not in text and "How It Started" in text
