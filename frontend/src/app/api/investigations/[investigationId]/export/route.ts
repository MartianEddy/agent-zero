import { NextRequest, NextResponse } from "next/server";
import { backendUrl } from "@/lib/backend-url";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ investigationId: string }> },
) {
  const { investigationId } = await params;
  try {
    const response = await fetch(
      `${backendUrl}/api/v1/investigations/${encodeURIComponent(investigationId)}/export`,
      { cache: "no-store" },
    );
    return new NextResponse(response.body, {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") ?? "application/json",
        "content-disposition": response.headers.get("content-disposition") ?? "",
        "cache-control": "private, no-store",
        "x-content-type-options": "nosniff",
      },
    });
  } catch {
    return NextResponse.json({ detail: "The investigation API is unavailable." }, { status: 503 });
  }
}
