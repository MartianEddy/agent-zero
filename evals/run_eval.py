#!/usr/bin/env python3
"""Score captured Agent 0 outputs against the golden set; never invokes a provider."""
from __future__ import annotations
import argparse, json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GOLDEN = json.loads((ROOT / "golden_claims.json").read_text())


def score(predictions: dict[str, dict]) -> dict[str, object]:
    triage_ok = verdict_ok = citation_ok = 0
    citation_total = 0
    for item in GOLDEN:
        prediction = predictions.get(item["id"], {})
        triage_ok += prediction.get("claim_type") == item["expected_claim_type"]
        verdict_ok += prediction.get("verdict") == item["expected_verdict"]
        retrieved = set(prediction.get("retrieved_urls", []))
        cited = prediction.get("cited_urls", [])
        citation_total += len(cited)
        citation_ok += sum(url in retrieved for url in cited)
    return {
        "claims": len(GOLDEN),
        "triage_correct": triage_ok,
        "triage_accuracy": triage_ok / len(GOLDEN),
        "verdict_correct": verdict_ok,
        "verdict_accuracy": verdict_ok / len(GOLDEN),
        "citation_valid": citation_ok,
        "citation_total": citation_total,
        "citation_validity": citation_ok / citation_total if citation_total else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, help="JSON object keyed by golden claim id")
    parser.add_argument("--model", default="not recorded")
    parser.add_argument("--provider", default="not recorded")
    args = parser.parse_args()
    if not args.predictions:
        print(f"Golden claims: {len(GOLDEN)}")
        print("No predictions supplied; no accuracy or citation score was measured.")
        print("Capture real outputs in the documented JSON format, then pass --predictions.")
        return 2
    predictions = json.loads(args.predictions.read_text())
    result = score(predictions)
    print("Metric | Result")
    print(f"Triage accuracy | {result['triage_correct']}/{result['claims']} ({result['triage_accuracy']:.1%})")
    print(f"Verdict accuracy | {result['verdict_correct']}/{result['claims']} ({result['verdict_accuracy']:.1%})")
    citation = result["citation_validity"]
    print(f"Citation validity | {result['citation_valid']}/{result['citation_total']} ({'n/a' if citation is None else f'{citation:.1%}'})")
    report = [f"# Evaluation results — {date.today().isoformat()}", "", f"Model: {args.model}", f"Provider: {args.provider}", "", "| Metric | Result |", "|---|---:|", f"| Triage accuracy | {result['triage_correct']}/{result['claims']} ({result['triage_accuracy']:.1%}) |", f"| Verdict accuracy | {result['verdict_correct']}/{result['claims']} ({result['verdict_accuracy']:.1%}) |", f"| Citation validity | {result['citation_valid']}/{result['citation_total']} ({'not measured' if citation is None else f'{citation:.1%}'}) |", "", "These are measured scores for the supplied predictions. Missing predictions are counted as incorrect. Citation validity checks that each cited URL is listed among URLs retrieved for that claim."]
    (ROOT / "RESULTS.md").write_text("\n".join(report) + "\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
