#!/usr/bin/env python3
"""Score captured predictions by stage. Never calls a model or the network.

Metrics (each reported with its count, never as a bare percentage):
- triage: claim type matches the expected type
- clarify: cases expected to ask a question did so, and no others did
- verdict: final status matches the expected status
- abstention: of cases expected to be undecided, how many the system left undecided
  (and the reverse: how often it decided when it should not have)
- unsafe: a decided verdict (supported or contradicted) in the wrong direction
- citations: share of cited evidence ids that are validated, retrieved, same-run evidence
- latency and model calls per case

    python evals/score.py --set evals/kenya_claims.json --predictions evals/runs/x.json
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

UNDECIDED = {"INSUFFICIENT_EVIDENCE", "NOT_VERIFIABLE", "CLARIFY"}
DECIDED = {"SUPPORTED", "CONTRADICTED"}


def _first(stored: dict, key: str) -> dict:
    items = stored.get(key) or []
    return items[0] if items else {}


def predicted(record: dict) -> tuple[str | None, str | None]:
    if record.get("outcome") == "CLARIFY":
        return None, "CLARIFY"
    stored = record.get("stored_result") or {}
    return _first(stored, "claims").get("type"), _first(stored, "findings").get("status")


def citation_counts(stored: dict) -> tuple[int, int]:
    evidence = {item.get("id"): item for item in stored.get("evidence", [])}
    run_id = stored.get("investigation_id")
    valid = total = 0
    for finding in stored.get("findings", []):
        for sentence in finding.get("explanation") or []:
            for evidence_id in sentence.get("evidence_ids", []):
                total += 1
                item = evidence.get(evidence_id) or {}
                source = item.get("source") or {}
                retrieved = bool(item.get("media_asset")) or bool(source)
                valid += bool(item and retrieved and item.get("excerpt_validated") is True and item.get("run_id") == run_id)
    return valid, total


def score(cases: list[dict], predictions: dict[str, dict]) -> dict:
    tally: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    groups: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    languages: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    unsafe: list[str] = []
    missing: list[str] = []
    latencies: list[float] = []
    model_calls: list[int] = []
    for case in cases:
        record = predictions.get(case["id"])
        if record is None or record.get("error"):
            missing.append(case["id"])
            continue
        claim_type, verdict = predicted(record)
        expected = case["expected_verdict"]
        if expected != "CLARIFY" and verdict != "CLARIFY":
            tally["triage"][0] += claim_type == case["expected_claim_type"]
            tally["triage"][1] += 1
        tally["clarify"][0] += (expected == "CLARIFY") == (verdict == "CLARIFY")
        tally["clarify"][1] += 1
        ok = verdict == expected
        tally["verdict"][0] += ok
        tally["verdict"][1] += 1
        groups[case["group"]][0] += ok
        groups[case["group"]][1] += 1
        languages[case.get("language", "en")][0] += ok
        languages[case.get("language", "en")][1] += 1
        if expected in UNDECIDED:
            tally["abstained_when_expected"][0] += verdict in UNDECIDED
            tally["abstained_when_expected"][1] += 1
        if expected in DECIDED:
            tally["decided_when_expected"][0] += verdict in DECIDED
            tally["decided_when_expected"][1] += 1
        if verdict in DECIDED and verdict != expected:
            unsafe.append(f"{case['id']}: expected {expected}, got {verdict}")
        stored = record.get("stored_result") or {}
        valid, total = citation_counts(stored)
        tally["citations"][0] += valid
        tally["citations"][1] += total
        if record.get("latency_s") is not None:
            latencies.append(float(record["latency_s"]))
        usage = stored.get("usage_summary") or {}
        if usage.get("model_calls") is not None:
            model_calls.append(int(usage["model_calls"]))
    return {
        "cases": len(cases),
        "scored": len(cases) - len(missing),
        "missing_or_errored": missing,
        "metrics": {key: {"correct": a, "total": b} for key, (a, b) in tally.items()},
        "by_group": {key: {"correct": a, "total": b} for key, (a, b) in sorted(groups.items())},
        "by_language": {key: {"correct": a, "total": b} for key, (a, b) in sorted(languages.items())},
        "unsafe_verdicts": unsafe,
        "latency_s": {"p50": statistics.median(latencies), "max": max(latencies)} if latencies else None,
        "model_calls_mean": round(statistics.mean(model_calls), 2) if model_calls else None,
    }


def render(result: dict, *, label: str) -> str:
    def rate(item: dict) -> str:
        return f"{item['correct']}/{item['total']}" + (f" ({item['correct'] / item['total']:.0%})" if item["total"] else "")

    names = {
        "triage": "Claim type correct", "clarify": "Clarification behaviour correct",
        "verdict": "Verdict correct", "abstained_when_expected": "Left undecided when it should",
        "decided_when_expected": "Decided when it should", "citations": "Citations valid",
    }
    lines = [f"# Evaluation: {label}", "", f"Scored {result['scored']} of {result['cases']} cases.", "", "| Metric | Result |", "|---|---:|"]
    lines += [f"| {names.get(key, key)} | {rate(item)} |" for key, item in result["metrics"].items()]
    lines += ["", "**Unsafe verdicts** (decided in the wrong direction): " + (str(len(result["unsafe_verdicts"])) if result["unsafe_verdicts"] else "none")]
    lines += [f"- {item}" for item in result["unsafe_verdicts"]]
    lines += ["", "| Group | Verdict correct |", "|---|---:|"] + [f"| {k} | {rate(v)} |" for k, v in result["by_group"].items()]
    lines += ["", "| Language | Verdict correct |", "|---|---:|"] + [f"| {k} | {rate(v)} |" for k, v in result["by_language"].items()]
    if result["latency_s"]:
        lines += ["", f"Latency per case: median {result['latency_s']['p50']:.0f}s, max {result['latency_s']['max']:.0f}s."]
    if result["model_calls_mean"] is not None:
        lines += [f"Model calls per case: mean {result['model_calls_mean']}."]
    if result["missing_or_errored"]:
        lines += ["", "Not scored (missing or errored): " + ", ".join(result["missing_or_errored"])]
    lines += ["", "Expected labels are drafts pending editorial review (`label_status`)."]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--report", type=Path, help="Write a Markdown report here")
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    result = score(json.loads(args.set.read_text()), json.loads(args.predictions.read_text()))
    report = render(result, label=args.label or args.predictions.stem)
    print(report)
    if args.report:
        args.report.write_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
