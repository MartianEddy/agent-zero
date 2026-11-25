import json

from app.modules.investigations.bounding import TRUNCATION_NOTE, clip_text, fit_evidence_packet


def test_short_text_is_unchanged():
    assert clip_text("Nairobi is the capital.", 100) == "Nairobi is the capital."


def test_long_text_is_cut_at_a_sentence_and_says_so():
    text = ("The ministry announced the budget on Tuesday. " * 40).strip()
    clipped = clip_text(text, 300)
    assert len(clipped) <= 300
    assert clipped.endswith(TRUNCATION_NOTE)
    assert clipped[: -len(TRUNCATION_NOTE)].endswith("Tuesday.")


def _packet(n: int, excerpt_len: int) -> str:
    return json.dumps({
        "claims": [{"id": "c1", "text": "A claim."}, {"id": "c2", "text": "Another claim."}],
        "evidence": [
            {
                "evidence_id": f"e{i}",
                "claim_id": f"c{1 + i % 2}",
                "excerpt": ("word " * excerpt_len).strip(),
            }
            for i in range(n)
        ],
        "limitations": [],
    })


def test_packet_within_budget_is_unchanged():
    packet = _packet(2, 10)
    assert fit_evidence_packet(packet, 10_000) == packet


def test_oversized_packet_stays_valid_json_and_keeps_every_claim():
    packet = _packet(12, 900)
    fitted = fit_evidence_packet(packet, 9_000)
    assert len(fitted) <= 9_000
    data = json.loads(fitted)
    assert [claim["id"] for claim in data["claims"]] == ["c1", "c2"]
    assert data["evidence"], "some evidence must survive"
    assert any("shortened or omitted" in item for item in data["limitations"])


def test_excerpts_are_shortened_before_any_are_dropped():
    packet = _packet(4, 1200)
    fitted = json.loads(fit_evidence_packet(packet, 12_000))
    assert len(fitted["evidence"]) == 4
    assert all(item["excerpt"].endswith("[...]") for item in fitted["evidence"])


def test_invalid_json_falls_back_to_a_text_cut():
    assert len(fit_evidence_packet("x" * 5000, 1000)) <= 1000
