"use client";

import type { BackendEvent } from "@/lib/backend";
import Link from "next/link";
import { useMemo } from "react";

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

function mapType(label: string | null, raw: string): "Warning" | "Info" | "Success" | "Danger" {
  const key = getEventKey(label, raw);
  if (key === "ORANG_MASUK" || key === "ORANG_KELUAR" || key.startsWith("SOMEONE_")) return "Warning";
  if (key.endsWith("_MASUK") || key === "SAYA_MASUK" || key === "TEMAN_MASUK") return "Success";
  if (key.endsWith("_KELUAR") || key === "SAYA_KELUAR" || key === "TEMAN_KELUAR") return "Danger";
  return "Info";
}

function formatTime(iso: string): string {
  return iso.replace("T", " ").split(".")[0];
}

export default function HistoryDetailClient({ event }: { event: BackendEvent }) {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";
  
  const parsed = useMemo(() => {
    return {
      type: mapType(event.predicted_label, event.raw_event),
      message: mapMessage(event.predicted_label, event.raw_event),
      time: formatTime(event.server_received_at),
      device: event.device_id,
      label: event.predicted_label,
      confidence: event.confidence,
    };
  }, [event]);

  const accent = parsed.type === "Warning" ? "bg-amber-100 text-amber-900 border-amber-200" : parsed.type === "Success" ? "bg-emerald-100 text-emerald-900 border-emerald-200" : parsed.type === "Danger" ? "bg-rose-100 text-rose-900 border-rose-200" : "bg-sky-100 text-sky-900 border-sky-200";

  return (
    <div className="flex flex-col gap-6">
      <Link href="/history" className="inline-flex items-center text-sm font-medium text-neutral-500 hover:text-neutral-900 transition w-fit">
        ‹ Kembali ke Riwayat
      </Link>

      <div className="bg-white/80 backdrop-blur-xl border border-neutral-200 rounded-3xl shadow-sm overflow-hidden flex flex-col md:flex-row">
        
        {/* Gambar Bukti */}
        <div className="w-full md:w-1/2 aspect-[4/3] md:aspect-auto bg-neutral-100 relative shrink-0">
          {event.image_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={backendUrl + event.image_url} alt="Face Capture Evidence" className="w-full h-full object-cover absolute inset-0" />
          ) : (
            <div className="w-full h-full absolute inset-0 flex items-center justify-center text-neutral-400 font-medium">
              Tidak ada gambar
            </div>
          )}
        </div>

        {/* Informasi Spesifik */}
        <div className="p-6 md:p-8 flex flex-col justify-center w-full md:w-1/2">
          <div className={`text-xs font-semibold px-3 py-1 rounded-full w-fit mb-4 border ${accent}`}>
            {parsed.type.toUpperCase()}
          </div>
          
          <h2 className="text-2xl font-bold text-neutral-900 mb-1">{parsed.message}</h2>
          <p className="text-neutral-500 text-sm mb-6">{parsed.time}</p>

          <div className="space-y-4">
            <div className="bg-neutral-50 p-4 rounded-2xl border border-neutral-100">
              <div className="text-xs text-neutral-500 font-medium uppercase tracking-wider mb-1">Identitas AI</div>
              <div className="font-semibold text-neutral-800">{parsed.label || "Tidak Dikenal"}</div>
            </div>

            <div className="flex gap-4">
              <div className="bg-neutral-50 p-4 rounded-2xl border border-neutral-100 flex-1">
                <div className="text-xs text-neutral-500 font-medium uppercase tracking-wider mb-1">Akurasi AI</div>
                <div className="font-semibold text-neutral-800">
                  {parsed.confidence !== null && parsed.confidence !== undefined 
                    ? `${(parsed.confidence * 100).toFixed(1)}%` 
                    : "N/A"}
                </div>
              </div>
              
              <div className="bg-neutral-50 p-4 rounded-2xl border border-neutral-100 flex-1">
                <div className="text-xs text-neutral-500 font-medium uppercase tracking-wider mb-1">Perangkat</div>
                <div className="font-semibold text-neutral-800">{parsed.device}</div>
              </div>
            </div>
          </div>
          
        </div>
      </div>
    </div>
  );
}
