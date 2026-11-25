"""WhatsApp result, sources and share replies against a real database.

Covers the plain-language result (what the sources say, named), the Sources and Share
replies behind its buttons, and sender scoping: another sender never sees the case.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.investigation import Channel, InputType, InvestigationStatus
from app.modules.conversations.service import case_replies
from app.modules.investigations.models import (
    Claim,
    Evidence,
    Finding,
    FindingEvidence,
    Source,
    VerificationBrief,
)
from app.modules.investigations.service import DEV_USER_ID, InvestigationService

SENDER = "sender-hmac"


@pytest.fixture
def case():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    investigation = InvestigationService(session).create(
        owner_id=DEV_USER_ID,
        content="Kenya won the 2022 FIFA World Cup.",
        input_type=InputType.TEXT,
        idempotency_key=f"results-{uuid4()}",
        channel=Channel.WHATSAPP,
        source_metadata={"sender_ref": SENDER},
    )
    investigation.status = InvestigationStatus.COMPLETE
    claim = Claim(
        investigation_id=investigation.id,
        text="Kenya won the 2022 FIFA World Cup.",
        normalized_text="kenya won the 2022 fifa world cup",
        claim_type="SETTLED_FACT",
    )
    now = datetime.now(UTC)

    def source(url, domain, publisher, title):
        return Source(
            investigation_id=investigation.id, url=url, domain=domain, publisher=publisher,
            title=title, retrieval_status="RETRIEVED", retrieved_at=now,
        )

    fifa = source("https://www.fifa.com/qatar2022?utm_source=x", "www.fifa.com", "fifa.com",
                  "Qatar 2022")
    wiki = source("https://en.wikipedia.org/wiki/2022_FIFA_World_Cup", "en.wikipedia.org",
                  "Wikipedia", "2022 FIFA World Cup")
    unlinked = source("https://unrelated.example/page", "unrelated.example", "x", "Unrelated")
    session.add_all([claim, fifa, wiki, unlinked])
    session.flush()
    finding = Finding(
        investigation_id=investigation.id,
        claim_id=claim.id,
        status="CONTRADICTED",
        statement="Retrieved evidence meets the challenge threshold through 1 independent "
        "source group(s). Review the linked passages and context before publication.",
        evidence_confidence="MEDIUM",
        explanation_json=[
            {"sentence": "FIFA's records show Argentina won the 2022 final against France.",
             "evidence_ids": []},
            {"sentence": "This does not meet the threshold for a second source group.",
             "evidence_ids": []},
        ],
    )
    session.add(finding)
    session.flush()
    for item, stance, text in (
        (wiki, "CONTEXT", "The 2022 FIFA World Cup was held in Qatar."),
        (fifa, "CONTRADICTS", "Lionel Messi of Argentina lifts the FIFA World Cup trophy."),
    ):
        evidence = Evidence(
            investigation_id=investigation.id, source_id=item.id, content=text, stance=stance,
            method="CLAIM_ANCHOR_MATCH",
        )
        session.add(evidence)
        session.flush()
        session.add(FindingEvidence(finding_id=finding.id, evidence_id=evidence.id))
    session.add(
        VerificationBrief(
            investigation_id=investigation.id,
            summary="x",
            limitations=["Case deadline reached; remaining source retrieval steps were cut."],
        )
    )
    session.commit()
    settings = SimpleNamespace(
        whatsapp_owner_id=None,
        whatsapp_public_number="254750288942",
        public_site_url="https://agent-zero-web.onrender.com",
    )
    yield session, settings, investigation.reference
    session.close()


def test_result_says_what_the_sources_found_in_plain_words(case):
    session, settings, reference = case
    text = case_replies._result_message(
        session, settings=settings, sender_ref=SENDER, reference=reference
    )
    assert text.startswith("*Evidence challenges this claim*")
    assert "Argentina won the 2022 final" in text
    for internal in ("threshold", "source group", "before publication", "Case deadline"):
        assert internal not in text
    assert "*Sources:* FIFA, Wikipedia" in text  # deciding source first, named
    assert "unrelated.example" not in text
    assert "*How sure:* Medium" in text
    assert text.endswith(f"_Ref: {reference}_")
    buttons = case_replies._result_buttons(
        session, settings=settings, sender_ref=SENDER, reference=reference
    )
    assert [title for _id, title in buttons] == ["Sources", "Share", "Check another"]


def test_sources_reply_lists_links_and_quotes_without_tracking(case):
    session, settings, reference = case
    text = case_replies._sources_message(
        session, settings=settings, sender_ref=SENDER, reference=reference
    )
    assert "*1. FIFA*" in text and "Lionel Messi of Argentina" in text
    assert "https://www.fifa.com/qatar2022" in text and "utm_source" not in text
    assert "unrelated.example" not in text


def test_share_card_is_ready_to_forward(case):
    session, settings, reference = case
    card = case_replies._share_message(
        session, settings=settings, sender_ref=SENDER, reference=reference
    )
    assert card.startswith("*Agent Zero fact-check*")
    assert "Kenya won the 2022 FIFA World Cup." in card and "Argentina" in card
    assert "https://wa.me/254750288942" in card
    assert "RESULT" not in card and card.endswith(f"Ref: {reference}")


def test_other_senders_never_see_the_case(case):
    session, settings, reference = case
    for build in (
        case_replies._result_message,
        case_replies._sources_message,
        case_replies._share_message,
    ):
        text = build(session, settings=settings, sender_ref="someone-else", reference=reference)
        assert "Argentina" not in text and "fifa.com" not in text
    assert case_replies._result_buttons(
        session, settings=settings, sender_ref="someone-else", reference=reference
    ) is None


def test_fast_result_is_noticed_while_the_typing_indicator_shows(case):
    import asyncio

    from app.modules.conversations.service import drafts
    from app.modules.investigations.models import Investigation

    session, _settings, reference = case
    investigation = session.query(Investigation).filter_by(reference=reference).one()
    assert asyncio.run(drafts._finished_within(session, investigation.id, 2.0)) is True
    assert asyncio.run(drafts._finished_within(session, uuid4(), 1.2)) is False


def test_an_empty_reply_is_not_sent_but_the_turn_is_closed():
    import asyncio
    from unittest.mock import MagicMock, patch

    from app.modules.conversations.schemas import ConversationTurn
    from app.modules.conversations.service import inbound

    send = MagicMock()
    turn = ConversationTurn(message_id="m1", sender="254700000000", message_type="text", text="x")
    with patch.object(inbound, "_mark_delivered") as delivered:
        asyncio.run(inbound._deliver(MagicMock(), event=turn, send_message=send, reply=""))
    send.assert_not_called()
    delivered.assert_called_once()
