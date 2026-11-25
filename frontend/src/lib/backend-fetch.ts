import { randomBytes } from "node:crypto";
import { cookies } from "next/headers";
import { backendUrl } from "@/lib/backend-url";

// Each browser gets a random, httpOnly identifier; the API derives the case owner from
// it, so a browser only sees its own cases. The proxy secret proves the request came
// from this server, so the public API does not answer anyone who calls it directly.
const CLIENT_COOKIE = "az_client";
const CLIENT_TOKEN = /^[A-Za-z0-9_-]{32,128}$/;
const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365;

async function clientToken(): Promise<string> {
  const jar = await cookies();
  const existing = jar.get(CLIENT_COOKIE)?.value;
  if (existing && CLIENT_TOKEN.test(existing)) return existing;
  const token = randomBytes(32).toString("base64url");
  jar.set(CLIENT_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: ONE_YEAR_SECONDS,
  });
  return token;
}

export async function backendFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("x-agent-zero-client", await clientToken());
  const secret = process.env.AGENT_ZERO_PROXY_SECRET?.trim();
  if (secret) headers.set("x-agent-zero-proxy", secret);
  return fetch(`${backendUrl}${path}`, { ...init, headers });
}
