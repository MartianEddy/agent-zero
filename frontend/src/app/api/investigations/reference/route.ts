import { NextRequest, NextResponse } from "next/server";
import { backendUrl } from "@/lib/backend-url";

export async function GET(request: NextRequest) {
  const reference = request.nextUrl.searchParams.get("reference")?.trim().toUpperCase();
  // The API normalises spacing, a missing "AZ-" and look-alike letters; this only
  // rejects input that cannot be a reference.
  if (!reference || !/^[A-Z0-9][A-Z0-9 _#-]{3,22}[A-Z0-9]$/.test(reference)) {
    return NextResponse.json({ detail: "Enter a reference such as AZ-7KQ2F." }, { status: 400 });
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
