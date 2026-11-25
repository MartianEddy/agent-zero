#!/usr/bin/env python3
"""Run every migration on a throwaway PostgreSQL database and check what can be saved.

SQLite unit tests do not run the migrations, so database rules that only exist in
migrations are checked here. Needs the local Postgres container on 127.0.0.1:5433.
    backend/.venv/bin/python e2e/migrations_check.py
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
DB = "agent_zero_migrations_check"
PSQL = ["docker", "exec", "agent-zero-postgres-1", "psql", "-U", "agent_zero"]
DB_URL = f"postgresql+psycopg://agent_zero:agent_zero_local@localhost:5433/{DB}"


def sql(query: str, db: str = DB) -> subprocess.CompletedProcess:
    return subprocess.run([*PSQL, "-d", db, "-tAc", query], capture_output=True, text=True, check=False)


def setup_rows(owner: uuid.UUID, inv: uuid.UUID, claim: uuid.UUID) -> str:
    return (
        "INSERT INTO users (id, external_subject, created_at) "
        f"VALUES ('{owner}', 'check', now());"
        "INSERT INTO investigations (id, owner_id, reference, input_type, channel, status, "
        "current_stage, created_at, updated_at) "
        f"VALUES ('{inv}', '{owner}', 'AZ-CHECK-000001', 'TEXT', 'WEB', 'COMPLETE', "
        "'COMPLETE', now(), now());"
        "INSERT INTO claims (id, investigation_id, text, normalized_text, claim_type, "
        "needs_deep_investigation, created_at) "
        f"VALUES ('{claim}', '{inv}', 'x', 'x', 'CHECKABLE_EVENT', true, now());"
    )


def finding_row(inv: uuid.UUID, claim: uuid.UUID, strength: str) -> str:
    return (
        "INSERT INTO findings (id, investigation_id, claim_id, status, statement, "
        "evidence_confidence, confidence_rationale, explanation_json, "
        "unsupported_statements_removed, created_at) "
        f"VALUES ('{uuid.uuid4()}', '{inv}', '{claim}', 'SUPPORTED', 's', '{strength}', "
        "'r', '[]', false, now());"
    )


def main() -> int:
    sql(f"DROP DATABASE IF EXISTS {DB}", "agent_zero")
    sql(f"CREATE DATABASE {DB}", "agent_zero")
    failures = []
    try:
        env = {**os.environ, "DATABASE_URL": DB_URL, "APP_ENV": "development"}
        result = subprocess.run(
            [str(BACKEND / ".venv/bin/python"), "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            print(result.stderr[-2000:])
            return 1
        owner, inv, claim = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        done = sql(setup_rows(owner, inv, claim))
        if done.returncode or "ERROR" in done.stderr:
            print("setup failed:", done.stderr[-800:])
            return 1
        for strength in ("LOW", "MEDIUM", "HIGH"):
            out = sql(finding_row(inv, claim, strength))
            ok = out.returncode == 0 and "ERROR" not in out.stderr
            detail = "" if ok else out.stderr.strip()[:160]
            label = "PASS" if ok else "FAIL"
            print(f"{label}  finding with {strength} evidence strength can be saved  {detail}")
            if not ok:
                failures.append(strength)
    finally:
        sql(f"DROP DATABASE IF EXISTS {DB}", "agent_zero")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
