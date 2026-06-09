"use client";

import type { BackendEvent } from "@/lib/backend";
import { useMemo, useState } from "react";
import Link from "next/link";

type Item = {
  id: number;
  type: "Warning" | "Info" | "Success" | "Danger";
  message: string;
  time: string;
  device: string;
  label: string | null;
  image_url?: string | null;
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

export default function HistoryClient({ events }: { events: BackendEvent[] }) {
  const [filter, setFilter] = useState<string>("ALL");

  const items: Item[] = useMemo(() => {
    const mapped = events.map((e) => ({
      id: e.id,
      type: mapType(e.predicted_label, e.raw_event),
      message: mapMessage(e.predicted_label, e.raw_event),
      time: formatTime(e.server_received_at),
      device: e.device_id,
      label: e.predicted_label,
      image_url: e.image_url,
    }));

    if (filter === "ALL") return mapped;
    return mapped.filter((x) => x.label === filter);
  }, [events, filter]);

  return (
    <div className="mt-4">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm text-neutral-600">
          Total: <span className="font-semibold text-neutral-800">{items.length}</span>
        </div>

        <select
          className="bg-white/70 rounded-xl px-3 py-2 text-sm shadow-sm border border-neutral-200"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="ALL">All</option>
          <option value="SAYA_MASUK">Saya masuk</option>
          <option value="TEMAN_MASUK">Teman masuk</option>
          <option value="ORANG_MASUK">Orang tidak dikenal masuk</option>
          <option value="SAYA_KELUAR">Saya keluar</option>
          <option value="TEMAN_KELUAR">Teman keluar</option>
          <option value="ORANG_KELUAR">Orang tidak dikenal keluar</option>
          <option value="ANDA_PERGI">Anda pergi</option>
          <option value="ANDA_PULANG">Anda pulang</option>
        </select>
      </div>

      <div className="mt-4 flex flex-col gap-4">
        {items.map((n) => {
          const accent = n.type === "Warning" ? "bg-amber-200/70" : n.type === "Success" ? "bg-emerald-200/70" : n.type === "Danger" ? "bg-rose-200/70" : "bg-sky-200/70";
          const icon = n.type === "Warning" ? "⚠️" : n.type === "Success" ? "✅" : n.type === "Danger" ? "🚪" : "ⓘ";

          const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

          return (
            <Link key={n.id} href={`/history/${n.id}`} className={`block rounded-2xl p-5 transition hover:brightness-95 flex items-center justify-between gap-4 ${accent}`}>
              <div className="flex items-center gap-4">
                {n.image_url ? (
                  <div className="w-12 h-12 rounded-2xl overflow-hidden bg-white/70 shadow-sm shrink-0 border border-black/5">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={backendUrl + n.image_url} alt="Face thumbnail" className="w-full h-full object-cover" />
                  </div>
                ) : (
                  <div className="w-11 h-11 rounded-2xl bg-white/70 flex items-center justify-center text-lg shrink-0 shadow-sm border border-black/5">{icon}</div>
                )}
                <div>
                  <div className="font-semibold text-neutral-800">{n.message}</div>
                  <div className="text-sm text-neutral-600 mt-0.5">
                    {n.time} • {n.device}
                  </div>
                </div>
              </div>
              <div className="text-neutral-500 font-medium">Lihat Detail ›</div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
