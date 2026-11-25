#!/usr/bin/env python3
"""End-to-end WhatsApp check against a real API process and a real PostgreSQL database.

What is real: the FastAPI app and its HTTP stack, Meta signature checks, the conversation
service, PostgreSQL (a throwaway database, created and dropped by this script) and the
outbound HTTP request to the Graph API. What is fake: Meta's Graph API, replaced by a local
server that records each request exactly as Meta would receive it.

It does not use a real phone. For that, follow docs/engineering/testing/whatsapp-live-test.md.

Run from the repo root (needs the local Postgres container on 127.0.0.1:5433):
    backend/.venv/bin/python e2e/whatsapp_e2e.py
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PYTHON = BACKEND / ".venv" / "bin" / "python"
DB_NAME = "agent_zero_e2e"
DB_ADMIN = ["docker", "exec", "agent-zero-postgres-1", "psql", "-U", "agent_zero", "-d", "agent_zero", "-tAc"]
API_PORT = 18010
GRAPH_PORT = 18999
APP_SECRET = "e2e-app-secret"
VERIFY_TOKEN = "e2e-verify-token"
PHONE_NUMBER_ID = "100000000000001"
IDENTITY_KEY = "e2e-identity-key-" + "x" * 32
OWNER_ID = "00000000-0000-0000-0000-0000000000e2"

sent: list[dict] = []


class FakeGraph(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # noqa: D401 - silence default logging
        return

    def do_POST(self) -> None:  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
        sent.append({"path": self.path, "auth": self.headers.get("authorization", ""), "body": body})
        reply = json.dumps({"messaging_product": "whatsapp", "messages": [{"id": f"wamid.out{len(sent)}"}]})
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(reply.encode())


def env() -> dict[str, str]:
    base = dict(os.environ)
    base.update({
        "APP_ENV": "development",
        "AUTH_MODE": "disabled",
        "DATABASE_URL": f"postgresql+psycopg://agent_zero:agent_zero_local@localhost:5433/{DB_NAME}",
        "REDIS_URL": "redis://localhost:16379/9",
        "OBJECT_STORAGE_ENDPOINT": "http://localhost:8333",
        "OBJECT_STORAGE_SECURE": "false",
        "WHATSAPP_ACCESS_TOKEN": "e2e-access-token",
        "WHATSAPP_APP_SECRET": APP_SECRET,
        "WHATSAPP_VERIFY_TOKEN": VERIFY_TOKEN,
        "WHATSAPP_PHONE_NUMBER_ID": PHONE_NUMBER_ID,
        "WHATSAPP_IDENTITY_KEY": IDENTITY_KEY,
        "WHATSAPP_OWNER_ID": OWNER_ID,
        "WHATSAPP_CONVERSATION_ENABLED": "true",
        "WHATSAPP_GRAPH_BASE_URL": f"http://127.0.0.1:{GRAPH_PORT}",
    })
    return base


def http(method: str, path: str, body: bytes | None = None, headers: dict | None = None) -> tuple[int, str]:
    request = urllib.request.Request(f"http://127.0.0.1:{API_PORT}{path}", data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def webhook(message: dict, contacts: list[dict], *, signature: str | None = None) -> int:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "waba", "changes": [{"field": "messages", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "254711000000", "phone_number_id": PHONE_NUMBER_ID},
            "contacts": contacts,
            "messages": [message],
        }}]}],
    }
    raw = json.dumps(payload).encode()
    digest = "sha256=" + hmac.new(APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    status, _ = http("POST", "/api/v1/channels/whatsapp/webhook", raw, {
        "content-type": "application/json", "X-Hub-Signature-256": signature or digest,
    })
    return status


def text(message_id: str, body: str, *, phone: str | None = None, bsuid: str | None = None) -> tuple[dict, list]:
    message = {"id": message_id, "timestamp": str(int(time.time())), "type": "text", "text": {"body": body}}
    contact: dict = {"profile": {"name": "E2E"}}
    if phone:
        message["from"] = phone
        contact["wa_id"] = phone
    if bsuid:
        message["from_user_id"] = bsuid
        contact["user_id"] = bsuid
    return message, [contact]


def replies() -> list[dict]:
    """Outbound messages, excluding read receipts and typing indicators."""
    return [item for item in sent if item["body"].get("status") != "read"]


def typing_for(message_id: str) -> bool:
    return any(item["body"].get("message_id") == message_id and "typing_indicator" in item["body"] for item in sent)


def wait_for_replies(count: int, timeout: float = 30) -> list[dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and len(replies()) < count:
        time.sleep(0.1)
    return replies()


def sql(query: str) -> str:
    return subprocess.run(
        ["docker", "exec", "agent-zero-postgres-1", "psql", "-U", "agent_zero", "-d", DB_NAME, "-tAc", query],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def ref(value: str) -> str:
    return hmac.new(IDENTITY_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def main() -> int:
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))

    subprocess.run([*DB_ADMIN, f"DROP DATABASE IF EXISTS {DB_NAME}"], check=True, capture_output=True)
    subprocess.run([*DB_ADMIN, f"CREATE DATABASE {DB_NAME}"], check=True, capture_output=True)
    graph = HTTPServer(("127.0.0.1", GRAPH_PORT), FakeGraph)
    threading.Thread(target=graph.serve_forever, daemon=True).start()
    api = None
    try:
        subprocess.run([str(PYTHON), "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env(), check=True, capture_output=True)
        api = subprocess.Popen(
            [str(PYTHON), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(API_PORT)],
            cwd=BACKEND, env=env(), stdout=subprocess.DEVNULL, stderr=open("/tmp/whatsapp-e2e-api.log", "w"),
        )
        for _ in range(60):
            try:
                if http("GET", "/api/v1/health")[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(0.5)

        status, body = http("GET", f"/api/v1/channels/whatsapp/webhook?hub.mode=subscribe&hub.verify_token={VERIFY_TOKEN}&hub.challenge=12345")
        check("Meta webhook verification returns the challenge", status == 200 and body == "12345", f"{status} {body[:40]}")

        message, contacts = text("wamid.e2e.bad", "help", phone="254700000001")
        check("Unsigned or wrongly signed webhook is rejected", webhook(message, contacts, signature="sha256=" + "0" * 64) == 401)

        before = len(replies())
        message, contacts = text("wamid.e2e.1", "help", bsuid="KE.E2E111")
        started = time.monotonic()
        status = webhook(message, contacts)
        ack_seconds = time.monotonic() - started
        out = wait_for_replies(before + 1)[before:]
        check("Meta is acknowledged at once (reply follows in the background)", status == 200 and ack_seconds < 2, f"{ack_seconds:.2f}s")
        check("User sees typing while the reply is prepared", typing_for("wamid.e2e.1"))
        ok = status == 200 and len(out) == 1 and out[0]["body"].get("recipient") == "KE.E2E111" and "to" not in out[0]["body"]
        check("Username user (BSUID only): reply sent with recipient, not to", ok, json.dumps(out[0]["body"] if out else {})[:160])
        check("Reply is plain language and lists the shortcuts", bool(out) and "RESULT" in json.dumps(out[0]["body"]))
        check("Outbound request carries the access token", bool(out) and out[0]["auth"] == "Bearer e2e-access-token")

        before = len(replies())
        status = webhook(message, contacts)
        time.sleep(2)
        check("Duplicate delivery of the same message is not answered twice", status == 200 and len(replies()) == before)

        before = len(replies())
        message, contacts = text("wamid.e2e.2", "help", phone="254700000002")
        webhook(message, contacts)
        out = wait_for_replies(before + 1)[before:]
        check("Phone user: reply sent with to", bool(out) and out[0]["body"].get("to") == "254700000002" and "recipient" not in out[0]["body"])

        # Legacy history: a conversation saved under the phone key, then the same person
        # arrives with phone and BSUID. Their conversation should move to the BSUID key.
        message, contacts = text("wamid.e2e.3", "help", phone="254700000003")
        before = len(replies())
        webhook(message, contacts)
        wait_for_replies(before + 1)
        legacy_before = sql(f"SELECT count(*) FROM whatsapp_conversations WHERE sender_ref = '{ref('254700000003')}'")
        message, contacts = text("wamid.e2e.4", "history", phone="254700000003", bsuid="KE.E2E333")
        before = len(replies())
        webhook(message, contacts)
        wait_for_replies(before + 1)
        moved = sql(f"SELECT count(*) FROM whatsapp_conversations WHERE sender_ref = '{ref('KE.E2E333')}'")
        legacy_after = sql(f"SELECT count(*) FROM whatsapp_conversations WHERE sender_ref = '{ref('254700000003')}'")
        check("Phone-keyed conversation moves to the BSUID key (real PostgreSQL)", (legacy_before, moved, legacy_after) == ("1", "1", "0"), f"{legacy_before}/{moved}/{legacy_after}")

        before = len(replies())
        message, contacts = text("wamid.e2e.5", "Is Nairobi the capital of Kenya?", bsuid="KE.E2E444")
        status = webhook(message, contacts)
        out = wait_for_replies(before + 1, timeout=60)[before:]
        reply_text = json.dumps(out[0]["body"]) if out else ""
        check("When the AI fails, a claim still gets a claim preview, not an error",
              status == 200 and "Is Nairobi the capital of Kenya?" in reply_text and "Submit claim" in reply_text
              and "trouble" not in reply_text, reply_text[:160] or "no reply")

        before = len(replies())
        message, contacts = text("wamid.e2e.6", "habari", bsuid="KE.E2E555")
        webhook(message, contacts)
        out = wait_for_replies(before + 1, timeout=60)[before:]
        check("When the AI fails, a greeting gets a greeting", bool(out) and "Hi!" in json.dumps(out[0]["body"]), json.dumps(out[0]["body"])[:120] if out else "no reply")
    finally:
        if api:
            api.terminate()
            api.wait(timeout=15)
        graph.shutdown()
        subprocess.run([*DB_ADMIN, f"DROP DATABASE IF EXISTS {DB_NAME}"], capture_output=True)

    width = max(len(name) for name, _, _ in results)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail if not ok else ''}")
    failed = sum(not ok for _, ok, _ in results)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
