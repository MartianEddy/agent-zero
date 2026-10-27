const MAX_WEBHOOK_BYTES = 1_000_000;
const UPSTREAM_TIMEOUT_MS = 10_000;
const AGENT_ZERO_PATH = "/api/v1/channels/whatsapp/webhook";

export default {
  async fetch(request, env) {
    const incomingUrl = new URL(request.url);
    if (incomingUrl.pathname !== "/webhook") {
      return new Response("Sinaps WhatsApp webhook is running.", { status: 200 });
    }

    if (request.method === "GET") {
      return forwardVerification(request, incomingUrl, env);
    }
    if (request.method === "POST") {
      return forwardEvent(request, incomingUrl, env);
    }
    return new Response("Method not allowed", { status: 405 });
  },
};

function configuredUpstream(env) {
  if (typeof env.AGENT_ZERO_WEBHOOK_URL !== "string") return null;
  try {
    const target = new URL(env.AGENT_ZERO_WEBHOOK_URL);
    if (
      target.protocol !== "https:" ||
      target.username ||
      target.password ||
      target.pathname !== AGENT_ZERO_PATH ||
      target.search ||
      target.hash
    ) {
      return null;
    }
    return target;
  } catch {
    return null;
  }
}

async function forwardVerification(request, incomingUrl, env) {
  const mode = incomingUrl.searchParams.get("hub.mode");
  const token = incomingUrl.searchParams.get("hub.verify_token");
  if (
    mode !== "subscribe" ||
    !token ||
    !env.WA_VERIFY_TOKEN ||
    token !== env.WA_VERIFY_TOKEN
  ) {
    return new Response("Forbidden", { status: 403 });
  }

  const target = configuredUpstream(env);
  if (!target) return new Response("Webhook upstream is not configured", { status: 503 });
  target.search = incomingUrl.search;
  return proxy(target, "GET", undefined, undefined, request.headers.get("content-type"));
}

async function forwardEvent(request, incomingUrl, env) {
  const target = configuredUpstream(env);
  if (!target) return new Response("Webhook upstream is not configured", { status: 503 });

  const declaredLength = Number(request.headers.get("content-length"));
  if (Number.isFinite(declaredLength) && declaredLength > MAX_WEBHOOK_BYTES) {
    return new Response("Payload too large", { status: 413 });
  }

  const rawBody = await readBoundedBody(request);
  if (rawBody === null) {
    return new Response("Payload too large", { status: 413 });
  }

  const signature = request.headers.get("X-Hub-Signature-256");
  if (!(await isValidSignature(rawBody, signature, env.WA_APP_SECRET))) {
    return new Response("Invalid signature", { status: 401 });
  }

  return proxy(target, "POST", rawBody, signature, request.headers.get("content-type"));
}

async function readBoundedBody(request) {
  if (!request.body) return new ArrayBuffer(0);
  const reader = request.body.getReader();
  const chunks = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_WEBHOOK_BYTES) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body.buffer;
}

async function proxy(target, method, rawBody, signature, contentType) {
  const headers = new Headers();
  if (contentType) headers.set("content-type", contentType);
  if (signature) headers.set("X-Hub-Signature-256", signature);

  let upstream;
  try {
    upstream = await fetch(target, {
      method,
      headers,
      body: rawBody,
      redirect: "manual",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch {
    return new Response("Agent Zero webhook is unavailable", { status: 502 });
  }

  // Never follow or expose a redirect containing webhook credentials/signatures.
  if (upstream.status >= 300 && upstream.status < 400) {
    return new Response("Agent Zero webhook returned an invalid redirect", { status: 502 });
  }

  const responseHeaders = new Headers();
  const upstreamType = upstream.headers.get("content-type");
  const retryAfter = upstream.headers.get("retry-after");
  if (upstreamType) responseHeaders.set("content-type", upstreamType);
  if (retryAfter) responseHeaders.set("retry-after", retryAfter);
  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

async function isValidSignature(rawBody, header, appSecret) {
  if (!header || !appSecret || !header.startsWith("sha256=")) return false;
  const hex = header.slice("sha256=".length);
  if (hex.length !== 64 || !/^[0-9a-f]{64}$/i.test(hex)) return false;

  const signature = new Uint8Array(hex.match(/../g).map((pair) => Number.parseInt(pair, 16)));
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(appSecret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"],
  );
  return crypto.subtle.verify("HMAC", key, signature, rawBody);
}
