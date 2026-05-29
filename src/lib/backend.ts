export type BackendEvent = {
  id: number;
  device_id: string;
  raw_event: string;
  predicted_label: string | null;
  confidence: number | null;
  server_received_at: string;
};

const BASE_URL = process.env.NEXT_PUBLIC_BACKEND_URL;

if (!BASE_URL) {
  // Biar gampang debug
  console.warn("NEXT_PUBLIC_BACKEND_URL belum di-set. Buat .env.local");
}

function requireBaseUrl() {
  if (!BASE_URL) throw new Error("NEXT_PUBLIC_BACKEND_URL belum di-set. Buat .env.local di root project.");
  return BASE_URL;
}

export async function getNotifications(limit = 50) {
  const base = requireBaseUrl();
  const res = await fetch(`${base}/api/notifications?limit=${limit}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getHistory(params?: {
  limit?: number;
  device_id?: string;
  type?: string;
}): Promise<BackendEvent[]> {
  const base = requireBaseUrl();
  const limit = params?.limit ?? 200;

  const qs = new URLSearchParams();
  qs.set("limit", String(limit));
  if (params?.device_id) qs.set("device_id", params.device_id);
  if (params?.type) qs.set("type", params.type);

  const res = await fetch(`${base}/api/history?${qs.toString()}`, {
    cache: "no-store",
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to fetch history: ${res.status} ${text}`);
  }

  return res.json();
}
