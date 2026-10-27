import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import worker from "../src/index.js";

const APP_SECRET = "test-app-secret";
const VERIFY_TOKEN = "test-verify-token";
const UPSTREAM_URL = "https://api.example.test/api/v1/channels/whatsapp/webhook";
const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

async function signatureFor(body) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(APP_SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = new Uint8Array(await crypto.subtle.sign("HMAC", key, body));
  return `sha256=${Array.from(signature, (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

const env = {
  WA_APP_SECRET: APP_SECRET,
  WA_VERIFY_TOKEN: VERIFY_TOKEN,
  AGENT_ZERO_WEBHOOK_URL: UPSTREAM_URL,
};

test("verification GET forwards query parameters and returns Agent Zero challenge", async () => {
  let observed;
  globalThis.fetch = async (url, options) => {
    observed = { url: new URL(url), options };
    return new Response("challenge-123", { status: 200, headers: { "content-type": "text/plain" } });
  };

  const response = await worker.fetch(
    new Request(
      `https://worker.example/webhook?hub.mode=subscribe&hub.verify_token=${VERIFY_TOKEN}&hub.challenge=challenge-123`,
    ),
    env,
  );

  assert.equal(response.status, 200);
  assert.equal(await response.text(), "challenge-123");
  assert.equal(observed.options.method, "GET");
  assert.equal(observed.url.pathname, "/api/v1/channels/whatsapp/webhook");
  assert.equal(observed.url.searchParams.get("hub.challenge"), "challenge-123");
  assert.equal(observed.url.searchParams.get("hub.verify_token"), VERIFY_TOKEN);
});

test("verification GET with a wrong token is rejected before forwarding", async () => {
  let called = false;
  globalThis.fetch = async () => {
    called = true;
    return new Response("unexpected");
  };

  const response = await worker.fetch(
    new Request("https://worker.example/webhook?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=x"),
    env,
  );
  assert.equal(response.status, 403);
  assert.equal(called, false);
});

test("POST forwards identical signed bytes and signature without logging message content", async () => {
  const body = new TextEncoder().encode(
    '{"object":"whatsapp_business_account","entry":[{"messages":[{"text":"private text"}]}]}',
  );
  const signature = await signatureFor(body);
  let observed;
  globalThis.fetch = async (url, options) => {
    observed = { url: new URL(url), options };
    return Response.json({ status: "ok" });
  };

  const response = await worker.fetch(
    new Request("https://worker.example/webhook", {
      method: "POST",
      headers: { "content-type": "application/json", "X-Hub-Signature-256": signature },
      body,
    }),
    env,
  );

  assert.equal(response.status, 200);
  assert.equal(observed.options.method, "POST");
  assert.equal(observed.options.redirect, "manual");
  assert.deepEqual(new Uint8Array(observed.options.body), body);
  assert.equal(observed.options.headers.get("X-Hub-Signature-256"), signature);
  assert.equal(observed.url.pathname, "/api/v1/channels/whatsapp/webhook");
});

test("invalid signatures never reach Agent Zero", async () => {
  let called = false;
  globalThis.fetch = async () => {
    called = true;
    return new Response("unexpected");
  };

  const response = await worker.fetch(
    new Request("https://worker.example/webhook", {
      method: "POST",
      headers: { "X-Hub-Signature-256": `sha256=${"0".repeat(64)}` },
      body: "{}",
    }),
    env,
  );
  assert.equal(response.status, 401);
  assert.equal(called, false);
});

test("missing or unsafe upstream configuration fails closed", async () => {
  const request = new Request("https://worker.example/webhook", { method: "POST", body: "{}" });
  const response = await worker.fetch(request, { ...env, AGENT_ZERO_WEBHOOK_URL: "http://api.example.test/hook" });
  assert.equal(response.status, 503);
});

test("oversized event payload is rejected before forwarding", async () => {
  let called = false;
  globalThis.fetch = async () => {
    called = true;
    return new Response("unexpected");
  };

  const response = await worker.fetch(
    new Request("https://worker.example/webhook", {
      method: "POST",
      headers: { "content-length": "1000001" },
      body: "{}",
    }),
    env,
  );
  assert.equal(response.status, 413);
  assert.equal(called, false);
});

test("chunked payloads are bounded even without content-length", async () => {
  let called = false;
  globalThis.fetch = async () => {
    called = true;
    return new Response("unexpected");
  };

  const response = await worker.fetch(
    new Request("https://worker.example/webhook", {
      method: "POST",
      body: "x".repeat(1_000_001),
    }),
    env,
  );
  assert.equal(response.status, 413);
  assert.equal(called, false);
});

test("upstream redirects are not followed or exposed", async () => {
  globalThis.fetch = async () =>
    new Response(null, { status: 302, headers: { location: "https://attacker.example/" } });
  const body = new TextEncoder().encode("{}");
  const response = await worker.fetch(
    new Request("https://worker.example/webhook", {
      method: "POST",
      headers: { "X-Hub-Signature-256": await signatureFor(body) },
      body,
    }),
    env,
  );
  assert.equal(response.status, 502);
  assert.equal(response.headers.get("location"), null);
});

test("upstream failures remain failures so Meta can retry delivery", async () => {
  globalThis.fetch = async () => new Response("temporarily unavailable", { status: 503 });
  const body = new TextEncoder().encode("{}");
  const response = await worker.fetch(
    new Request("https://worker.example/webhook", {
      method: "POST",
      headers: { "X-Hub-Signature-256": await signatureFor(body) },
      body,
    }),
    env,
  );
  assert.equal(response.status, 503);
  assert.equal(await response.text(), "temporarily unavailable");
});
