import { NextRequest, NextResponse } from "next/server";
import { backendUrl } from "@/lib/backend-url";

export async function POST(request: NextRequest) {
  try {
    const response = await fetch(`${backendUrl}/api/v1/investigations/triage`, {
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
      { detail: "Claim triage is unavailable because the investigation API could not be reached. No source check was started." },
      { status: 503 },
    );
  }
}
