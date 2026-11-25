#!/usr/bin/env python3
"""Run evaluation claims through a live Agent 0 API and save each stored result.

This spends real model and search calls. It runs only with --confirm-spend, and only
against the API you name (default: the local API). Output is the predictions file that
score.py reads. Cases that ask for clarification are recorded as such, with no case.

    python evals/capture.py --set evals/kenya_claims.json --api http://127.0.0.1:18000 \
        --out evals/runs/kenya-$(date +%Y%m%d).json --confirm-spend --limit 5
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

TERMINAL = {"COMPLETE", "FAILED", "NEEDS_REVIEW", "CANCELLED"}


def _call(method: str, url: str, body: dict | None = None, timeout: float = 90) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read() or b"{}")
        except json.JSONDecodeError:
            return error.code, {}


def run_case(api: str, case: dict, *, max_wait: float) -> dict:
    started = time.monotonic()
    status, triage = _call("POST", f"{api}/api/v1/investigations/triage", {"input_type": "TEXT", "content": case["claim_text"]})
    record: dict = {"id": case["id"], "triage_status": status}
    if status != 200:
        record["error"] = triage.get("detail")
        return record
    if not triage.get("draft_id"):
        record.update(outcome="CLARIFY", clarification=triage.get("clarification_question"), latency_s=round(time.monotonic() - started, 2))
        return record
    record["triage_claims"] = triage.get("claims", [])
    status, created = _call("POST", f"{api}/api/v1/investigations/{triage['draft_id']}/continue", {"claims": triage["claims"]})
    if status not in (200, 202):
        record["error"] = created.get("detail")
        return record
    case_id = created["id"]
    while time.monotonic() - started < max_wait:
        _, current = _call("GET", f"{api}/api/v1/investigations/{case_id}")
        if current.get("status") in TERMINAL:
            break
        time.sleep(4)
    _, results = _call("GET", f"{api}/api/v1/investigations/{case_id}/results")
    record.update(outcome="CASE", stored_result=results, latency_s=round(time.monotonic() - started, 2))
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", type=Path, required=True)
    parser.add_argument("--api", default="http://127.0.0.1:18000")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0, help="Run only the first N cases")
    parser.add_argument("--only", default="", help="Comma-separated case ids")
    parser.add_argument("--max-wait", type=float, default=300)
    parser.add_argument("--confirm-spend", action="store_true", help="Required: this spends model and search calls")
    args = parser.parse_args()
    if not args.confirm_spend:
        print("Refusing to run: add --confirm-spend. Each case spends real model and search calls.")
        return 2
    cases = json.loads(args.set.read_text())
    if args.only:
        wanted = set(args.only.split(","))
        cases = [case for case in cases if case["id"] in wanted]
    if args.limit:
        cases = cases[: args.limit]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    predictions: dict[str, dict] = json.loads(args.out.read_text()) if args.out.exists() else {}
    for index, case in enumerate(cases, 1):
        if case["id"] in predictions:
            continue
        print(f"[{index}/{len(cases)}] {case['id']} {case['claim_text'][:60]}")
        predictions[case["id"]] = run_case(args.api, case, max_wait=args.max_wait)
        args.out.write_text(json.dumps(predictions, indent=1, ensure_ascii=False))  # save as we go
    print(f"Saved {len(predictions)} predictions to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
