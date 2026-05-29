import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/$/, "");
const VALID_ACTIONS = new Set(["enable", "disable", "open_door", "close_door"]);

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

export async function POST(request: NextRequest) {
  if (!BACKEND_URL) {
    return NextResponse.json(
      { error: "NEXT_PUBLIC_BACKEND_URL belum di-set." },
      { status: 500 },
    );
  }

  let payload: { device_id?: unknown; action?: unknown };

  try {
    payload = (await request.json()) as { device_id?: unknown; action?: unknown };
  } catch {
    return NextResponse.json({ error: "Body JSON tidak valid." }, { status: 400 });
  }

  const deviceId = typeof payload.device_id === "string" ? payload.device_id.trim() : "";
  const action = typeof payload.action === "string" ? payload.action.trim() : "";

  if (!deviceId) {
    return NextResponse.json({ error: "device_id wajib diisi." }, { status: 400 });
  }

  if (!VALID_ACTIONS.has(action)) {
    return NextResponse.json(
      { error: "action harus salah satu dari enable, disable, open_door, close_door." },
      { status: 400 },
    );
  }

  try {
    const response = await fetch(`${BACKEND_URL}/api/command/execute`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json, text/plain;q=0.9",
      },
      cache: "no-store",
      body: JSON.stringify({
        device_id: deviceId,
        action,
      }),
    });

    return readBackendResponse(response);
  } catch (error) {
    console.error("POST /api/command gagal", error);
    return NextResponse.json(
      { error: "Gagal meneruskan command ke backend." },
      { status: 502 },
    );
  }
}
