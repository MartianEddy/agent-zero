import { NextRequest, NextResponse } from "next/server";

const backend = process.env.AGENT_ZERO_API_URL ?? "http://127.0.0.1:18000";

export async function GET() {
  try {
    const response = await fetch(`${backend}/api/v1/investigations`, { cache: "no-store" });
    return new NextResponse(response.body, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "The investigation API is unavailable. Try again shortly." }, { status: 503 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const response = await fetch(`${backend}/api/v1/investigations`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: await request.text(),
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
