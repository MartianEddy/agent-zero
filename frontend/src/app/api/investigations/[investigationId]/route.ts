import { NextRequest, NextResponse } from "next/server";

const backend = process.env.AGENT_ZERO_API_URL ?? "http://127.0.0.1:18000";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ investigationId: string }> },
) {
  const { investigationId } = await params;
  try {
    const response = await fetch(
      `${backend}/api/v1/investigations/${encodeURIComponent(investigationId)}`,
      { cache: "no-store" },
    );
    return new NextResponse(response.body, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "The investigation API is unavailable." }, { status: 503 });
  }
}

export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ investigationId: string }> },
) {
  const { investigationId } = await params;
  try {
    const response = await fetch(
      `${backend}/api/v1/investigations/${encodeURIComponent(investigationId)}/retry`,
      { method: "POST", cache: "no-store" },
    );
    return new NextResponse(response.body, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "The investigation API is unavailable." }, { status: 503 });
  }
}
