import { NextRequest, NextResponse } from "next/server";

const backend = process.env.AGENT_ZERO_API_URL ?? "http://127.0.0.1:18000";

export async function POST(request: NextRequest) {
  try {
    const form = await request.formData();
    const headers = new Headers();
    const idempotencyKey = request.headers.get("idempotency-key");
    if (idempotencyKey) headers.set("idempotency-key", idempotencyKey);
    const response = await fetch(`${backend}/api/v1/investigations/media`, {
      method: "POST",
      headers,
      body: form,
      cache: "no-store",
    });
    return new NextResponse(response.body, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json(
      { detail: "The investigation API is unavailable. Start the backend and try again." },
      { status: 503 },
    );
  }
}
