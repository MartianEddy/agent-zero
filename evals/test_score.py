"""Offline tests for the scorer; run with pytest from the repo root."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("score", Path(__file__).with_name("score.py"))
score_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score_module)

CASES = [
    {"id": "a", "group": "g", "language": "en", "claim_text": "x", "expected_claim_type": "SETTLED_FACT", "expected_verdict": "SUPPORTED"},
    {"id": "b", "group": "g", "language": "sw", "claim_text": "y", "expected_claim_type": "STATISTICAL", "expected_verdict": "INSUFFICIENT_EVIDENCE"},
    {"id": "c", "group": "h", "language": "en", "claim_text": "z", "expected_claim_type": "CHECKABLE_EVENT", "expected_verdict": "CLARIFY"},
    {"id": "d", "group": "h", "language": "en", "claim_text": "w", "expected_claim_type": "SETTLED_FACT", "expected_verdict": "CONTRADICTED"},
]


def _case(claim_type, status, cited_valid=True):
    return {"outcome": "CASE", "latency_s": 30, "stored_result": {
        "investigation_id": "run",
        "claims": [{"type": claim_type}],
        "findings": [{"status": status, "explanation": [{"sentence": "s", "evidence_ids": ["e1"]}]}],
        "evidence": [{"id": "e1", "source": {"url": "u"}, "excerpt_validated": cited_valid, "run_id": "run"}],
        "usage_summary": {"model_calls": 3},
    }}


def test_scores_each_stage_and_flags_unsafe_verdicts():
    predictions = {
        "a": _case("SETTLED_FACT", "SUPPORTED"),
        "b": _case("STATISTICAL", "INSUFFICIENT_EVIDENCE", cited_valid=False),
        "c": {"outcome": "CLARIFY", "latency_s": 5},
        "d": _case("SETTLED_FACT", "SUPPORTED"),
    }
    result = score_module.score(CASES, predictions)
    metrics = result["metrics"]
    assert metrics["verdict"] == {"correct": 3, "total": 4}
    assert metrics["clarify"] == {"correct": 4, "total": 4}
    assert metrics["triage"] == {"correct": 3, "total": 3}
    assert metrics["citations"] == {"correct": 2, "total": 3}
    assert result["unsafe_verdicts"] == ["d: expected CONTRADICTED, got SUPPORTED"]
    assert result["by_language"]["sw"] == {"correct": 1, "total": 1}
    assert result["model_calls_mean"] == 3


def test_missing_predictions_are_reported_not_counted_as_correct():
    result = score_module.score(CASES, {"a": _case("SETTLED_FACT", "SUPPORTED")})
    assert result["scored"] == 1
    assert result["missing_or_errored"] == ["b", "c", "d"]
    assert "Scored 1 of 4" in score_module.render(result, label="t")
