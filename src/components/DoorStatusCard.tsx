"use client";

import { useEffect, useState } from "react";

type DoorStatus = {
  ok: boolean;
  door_open: boolean;
  state: "open" | "closed" | "unknown";
  last_identity?: string | null;
  access_granted?: boolean;
  waiting_for_entry?: boolean;
  system_enabled?: boolean;
  access_source?: string | null;
  last_open_at?: string | null;
  last_close_at?: string | null;
};

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL;

function formatTime(value?: string | null) {
  if (!value) return "-";
  return value.replace("T", " ").split(".")[0];
}

export default function DoorStatusCard() {
  const [status, setStatus] = useState<DoorStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!BACKEND_URL) {
      setError("NEXT_PUBLIC_BACKEND_URL belum di-set.");
      return;
    }

    let active = true;

    const fetchStatus = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/api/door/status`, {
          cache: "no-store",
        });
        if (!res.ok) {
          throw new Error(`Status ${res.status}`);
        }
        const data = (await res.json()) as DoorStatus;
        if (active) {
          setStatus(data);
          setError(null);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Gagal memuat status pintu.");
        }
      }
    };

    void fetchStatus();
    const timer = setInterval(fetchStatus, 5000);

    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  const state = status?.state ?? "unknown";
  const badgeClass =
    state === "open"
      ? "bg-emerald-600 text-white"
      : state === "closed"
      ? "bg-rose-600 text-white"
      : "bg-neutral-400 text-white";

  const systemBadge = status?.system_enabled === false
    ? "bg-amber-500 text-white"
    : "bg-emerald-500 text-white";

  return (
    <section className="rounded-3xl bg-white/70 p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="text-lg font-semibold">Status Pintu</div>
        <div className="flex gap-2">
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ${systemBadge}`}>
            {status?.system_enabled === false ? "NONAKTIF" : "AKTIF"}
          </span>
          <span className={`rounded-full px-4 py-1 text-xs font-semibold ${badgeClass}`}>
            {state === "open" ? "TERBUKA" : state === "closed" ? "TERTUTUP" : "UNKNOWN"}
          </span>
        </div>
      </div>

      {error ? (
        <div className="mt-4 rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {error}
        </div>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-1 gap-3 text-sm text-neutral-700 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-2xl border border-neutral-200 bg-white px-4 py-3">
              <div className="text-xs text-neutral-500">Terakhir buka</div>
              <div className="mt-1 font-semibold">{formatTime(status?.last_open_at)}</div>
            </div>
            <div className="rounded-2xl border border-neutral-200 bg-white px-4 py-3">
              <div className="text-xs text-neutral-500">Terakhir tutup</div>
              <div className="mt-1 font-semibold">{formatTime(status?.last_close_at)}</div>
            </div>
            <div className="rounded-2xl border border-neutral-200 bg-white px-4 py-3">
              <div className="text-xs text-neutral-500">Identitas</div>
              <div className="mt-1 font-semibold">{status?.last_identity ?? "-"}</div>
            </div>
            <div className="rounded-2xl border border-neutral-200 bg-white px-4 py-3">
              <div className="text-xs text-neutral-500">Akses</div>
              <div className="mt-1 font-semibold">
                {status?.access_granted ? "✅ Granted" : "❌ Denied"}
                {status?.waiting_for_entry && " (menunggu masuk)"}
              </div>
            </div>
          </div>
        </>
      )}

      <p className="mt-3 text-xs text-neutral-500">
        Polling setiap 5 detik dari backend.
      </p>
    </section>
  );
}
