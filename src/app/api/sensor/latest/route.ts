import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/$/, "");
const DEFAULT_DEVICE_ID = "esp32-1";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function readBackendResponse(response: Response) {
  const contentType = response.headers.get("content-type") ?? "";
  const rawBody = await response.text();

  if (contentType.includes("application/json")) {
    if (!rawBody.trim()) {
      return NextResponse.json({ ok: response.ok }, { status: response.status });
    }

    try {
      return NextResponse.json(JSON.parse(rawBody), { status: response.status });
    } catch {
      return NextResponse.json({ message: rawBody }, { status: response.status });
    }
  }

  return new NextResponse(rawBody, {
    status: response.status,
    headers: {
      "Content-Type": contentType || "text/plain; charset=utf-8",
    },
  });
}

export async function GET(request: NextRequest) {
  if (!BACKEND_URL) {
    return NextResponse.json(
      { error: "NEXT_PUBLIC_BACKEND_URL belum di-set." },
      { status: 500 },
    );
  }

  const deviceId = request.nextUrl.searchParams.get("device_id")?.trim() || DEFAULT_DEVICE_ID;
  const target = new URL(`${BACKEND_URL}/api/sensor/latest`);
  target.searchParams.set("device_id", deviceId);

  try {
    const response = await fetch(target.toString(), {
      headers: {
        Accept: "application/json, text/plain;q=0.9",
      },
      cache: "no-store",
    });

    return readBackendResponse(response);
  } catch (error) {
    console.error("GET /api/sensor/latest gagal", error);
    return NextResponse.json(
      { error: "Gagal mengambil data sensor terbaru dari backend." },
      { status: 502 },
    );
  }
}
