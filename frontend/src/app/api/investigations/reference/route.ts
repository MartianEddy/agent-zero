import { NextRequest, NextResponse } from "next/server";
import { backendUrl } from "@/lib/backend-url";

export async function GET(request: NextRequest) {
  const reference = request.nextUrl.searchParams.get("reference")?.trim().toUpperCase();
  if (!reference || !/^AZ-\d{6}-[A-F0-9]{6}$/.test(reference)) {
    return NextResponse.json({ detail: "Enter a reference such as AZ-261004-ABC123." }, { status: 400 });
  }

  try {
    const response = await fetch(
      `${backendUrl}/api/v1/investigations/reference/${encodeURIComponent(reference)}`,
      { cache: "no-store" },
    );
    return new NextResponse(response.body, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "The investigation service is unavailable. Try again shortly." }, { status: 503 });
  }
}
