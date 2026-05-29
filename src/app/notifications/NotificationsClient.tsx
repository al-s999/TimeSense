"use client";

import type { BackendEvent } from "@/lib/backend";
import { useEffect, useMemo, useState } from "react";

type Item = {
  id: number;
  type: "Warning" | "Info" | "Success" | "Danger";
  message: string;
  time: string;
  device: string;
  label: string | null;
  raw: string;
};

const semanticEventKeys = new Set([
  "SAYA_MASUK",
  "TEMAN_MASUK",
  "ORANG_MASUK",
  "SAYA_KELUAR",
  "TEMAN_KELUAR",
  "ORANG_KELUAR",
]);

function getEventKey(label: string | null, raw: string): string {
  const rawKey = (raw ?? "").toUpperCase();
  if (semanticEventKeys.has(rawKey)) return rawKey;
  return (label ?? raw ?? "").toUpperCase();
}

function mapType(label: string | null, raw: string): Item["type"] {
  const key = getEventKey(label, raw);
  if (key === "ORANG_MASUK" || key === "ORANG_KELUAR" || key.startsWith("SOMEONE_")) return "Warning";
  if (key.endsWith("_MASUK") || key === "SAYA_MASUK" || key === "TEMAN_MASUK") return "Success";
  if (key.endsWith("_KELUAR") || key === "SAYA_KELUAR" || key === "TEMAN_KELUAR") return "Danger";
  return "Info";
}

function mapMessage(label: string | null, raw: string): string {
  switch (getEventKey(label, raw)) {
    case "SAYA_MASUK":
      return "Saya masuk";
    case "TEMAN_MASUK":
      return "Teman masuk";
    case "ORANG_MASUK":
      return "Orang tidak dikenal masuk";
    case "SAYA_KELUAR":
      return "Saya keluar";
    case "TEMAN_KELUAR":
      return "Teman keluar";
    case "ORANG_KELUAR":
      return "Orang tidak dikenal keluar";
    case "ANDA_PERGI":
      return "Anda pergi";
    case "ANDA_PULANG":
      return "Anda pulang";
    case "PINTU_BUKA":
      return "Pintu dibuka";
    case "PINTU_TUTUP":
      return "Pintu ditutup";
    default:
      const k = getEventKey(label, raw);
      if (k.endsWith("_MASUK")) {
        let name = k.replace("_MASUK", "").toLowerCase();
        if (name === "me") name = "saya";
        return name.charAt(0).toUpperCase() + name.slice(1) + " masuk";
      }
      if (k.endsWith("_KELUAR")) {
        let name = k.replace("_KELUAR", "").toLowerCase();
        if (name === "me") name = "saya";
        return name.charAt(0).toUpperCase() + name.slice(1) + " keluar";
      }
      return label ?? raw;
  }
}

function formatTime(iso: string): string {
  return iso.replace("T", " ").split(".")[0];
}

export default function NotificationsClient({
  initialEvents,
  backendBaseUrl,
}: {
  initialEvents: BackendEvent[];
  backendBaseUrl: string;
}) {
  const [events, setEvents] = useState<BackendEvent[]>(initialEvents);

  useEffect(() => {
    if (!backendBaseUrl) return;

    const es = new EventSource(`${backendBaseUrl}/api/stream/notifications`);

    es.onmessage = (msg) => {
      try {
        const data: BackendEvent = JSON.parse(msg.data);

        setEvents((prev) => {
          // dedupe by id
          if (prev.some((p) => p.id === data.id)) return prev;
          return [data, ...prev].slice(0, 200);
        });
      } catch (e) {
        console.error("SSE parse error", e);
      }
    };

    es.addEventListener("ping", () => {
      // optional
    });

    es.onerror = (e) => {
      console.warn("SSE error", e);
      // browser akan auto-reconnect SSE sendiri
    };

    return () => {
      es.close();
    };
  }, [backendBaseUrl]);

  const items: Item[] = useMemo(() => {
    return events.map((e) => ({
      id: e.id,
      type: mapType(e.predicted_label, e.raw_event),
      message: mapMessage(e.predicted_label, e.raw_event),
      time: formatTime(e.server_received_at),
      device: e.device_id,
      label: e.predicted_label,
      raw: e.raw_event,
    }));
  }, [events]);

  return (
    <div className="mt-4 flex flex-col gap-4">
      {items.map((n) => {
        const accent = n.type === "Warning" ? "bg-amber-200/70" : n.type === "Success" ? "bg-emerald-200/70" : n.type === "Danger" ? "bg-rose-200/70" : "bg-sky-200/70";
        const icon = n.type === "Warning" ? "⚠️" : n.type === "Success" ? "✅" : n.type === "Danger" ? "🚪" : "ⓘ";

        return (
          <div key={n.id} className={`rounded-2xl p-5 flex items-center justify-between gap-4 ${accent}`}>
            <div className="flex items-center gap-4">
              <div className="w-11 h-11 rounded-2xl bg-white/70 flex items-center justify-center">{icon}</div>
              <div>
                <div className="font-semibold">{n.message}</div>
                <div className="text-sm text-neutral-600">
                  {n.time} • {n.device}
                </div>
              </div>
            </div>
            <div className="text-neutral-700">›</div>
          </div>
        );
      })}
    </div>
  );
}
