import { NextResponse } from "next/server";
import { backendUrl } from "@/lib/backend-url";

export async function GET() {
  try {
    const response = await fetch(`${backendUrl}/api/v1/investigations/history`, { cache: "no-store" });
    return new NextResponse(response.body, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "Investigation history is unavailable. Try again shortly." }, { status: 503 });
  }
}
