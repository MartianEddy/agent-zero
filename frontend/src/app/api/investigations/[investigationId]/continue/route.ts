import { NextRequest, NextResponse } from "next/server";
import { backendUrl } from "@/lib/backend-url";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ investigationId: string }> },
) {
  const { investigationId } = await params;
  try {
    const response = await fetch(
      `${backendUrl}/api/v1/investigations/${encodeURIComponent(investigationId)}/continue`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: await request.text(),
        cache: "no-store",
      },
    );
    return new NextResponse(response.body, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "The investigation API is unavailable." }, { status: 503 });
  }
}
