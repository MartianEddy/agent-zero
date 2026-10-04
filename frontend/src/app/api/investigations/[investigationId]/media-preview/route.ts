import { NextResponse } from "next/server";
import { backendUrl } from "@/lib/backend-url";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ investigationId: string }> },
) {
  const { investigationId } = await params;
  try {
    const response = await fetch(
      `${backendUrl}/api/v1/investigations/${encodeURIComponent(investigationId)}/media-preview`,
      { cache: "no-store" },
    );
    return new NextResponse(response.body, {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") ?? "application/octet-stream",
        "cache-control": "private, no-store",
        "x-content-type-options": "nosniff",
      },
    });
  } catch {
    return NextResponse.json({ detail: "Image preview is unavailable." }, { status: 503 });
  }
}
