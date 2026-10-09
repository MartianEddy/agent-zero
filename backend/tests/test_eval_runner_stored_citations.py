import runpy
from pathlib import Path


def test_eval_citation_validity_is_derived_from_stored_evidence_rows():
    scorer = runpy.run_path(str(Path(__file__).parents[2] / "evals" / "run_eval.py"))["score"]
    predictions = {
        "GC-001": {
            "stored_result": {
                "investigation_id": "case-1",
                "claims": [{"type": "SETTLED_FACT"}],
                "findings": [
                    {
                        "status": "SUPPORTED",
                        "explanation": [
                            {"sentence": "Mangoes are fruit.", "evidence_ids": ["valid", "bad"]}
                        ],
                    }
                ],
                "evidence": [
                    {
                        "id": "valid",
                        "run_id": "case-1",
                        "excerpt_validated": True,
                        "source": {"retrieval_status": "RETRIEVED"},
                    },
                    {
                        "id": "bad",
                        "run_id": "old-case",
                        "excerpt_validated": False,
                        "source": {"retrieval_status": "CANDIDATE"},
                    },
                ],
            },
            "retrieved_urls": ["https://invented.example"],
            "cited_urls": ["https://invented.example"],
        }
    }
    result = scorer(predictions)
    assert result["citation_valid"] == 1
    assert result["citation_total"] == 2
