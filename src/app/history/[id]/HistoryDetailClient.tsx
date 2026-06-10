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

      <section className="flex flex-col gap-10 rounded-[34px] bg-white/70 p-6 md:p-10 shadow-sm lg:flex-row items-stretch">
        <div className="w-full lg:w-[45%] xl:w-1/2 relative bg-neutral-900 rounded-[28px] shrink-0 min-h-[400px] lg:min-h-[500px] flex items-center justify-center overflow-hidden shadow-[0_4px_20px_rgba(0,0,0,0.08)]">
          {event.image_url ? (
            <>
              <div 
                className="absolute inset-0 bg-cover bg-center opacity-40 blur-2xl scale-110"
                style={{ backgroundImage: `url(${backendUrl}${event.image_url})` }}
              />
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img 
                src={backendUrl + event.image_url} 
                alt="Face Capture Evidence" 
                className="relative z-10 w-full h-full object-contain drop-shadow-2xl" 
              />
            </>
          ) : (
            <div className="flex flex-col items-center justify-center text-neutral-400 w-full h-full absolute inset-0 bg-neutral-100">
              <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" className="mb-4 opacity-50"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>
              <span className="font-semibold text-lg tracking-wide uppercase">Tidak ada gambar</span>
            </div>
          )}
        </div>

        {/* Informasi Spesifik (Kanan) */}
        <div className="flex flex-col justify-center w-full lg:w-[55%] xl:w-1/2">
          <div className="flex items-center gap-4 mb-4">
            <div className={`text-xs font-bold px-4 py-1.5 rounded-full border uppercase tracking-widest shadow-sm ${accent}`}>
              {parsed.type}
            </div>
            <div className="flex items-center text-neutral-500 text-sm font-medium bg-white/60 px-4 py-1.5 rounded-full border border-neutral-200/50">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mr-2 text-neutral-400"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              {parsed.time}
            </div>
          </div>
          
          <h2 className="text-4xl md:text-5xl font-extrabold text-neutral-800 mb-8 leading-tight tracking-tight">
            {parsed.message}
          </h2>

          <div className="grid gap-5 sm:grid-cols-2">
            <div className="rounded-[28px] border border-neutral-200/80 bg-neutral-50/80 p-6 shadow-[0_1px_0_rgba(0,0,0,0.03)] sm:col-span-2">
              <div className="flex items-center text-xs text-neutral-400 font-bold uppercase tracking-[0.2em] mb-2">
                Identitas AI
              </div>
              <div className="text-3xl font-bold text-neutral-700 capitalize">
                {parsed.label || "Tidak Dikenal"}
              </div>
            </div>

            <div className="rounded-[24px] border border-neutral-200/80 bg-white p-6 shadow-sm">
              <div className="flex items-center text-xs text-neutral-400 font-bold uppercase tracking-[0.2em] mb-2">
                Akurasi AI
              </div>
              <div className="text-2xl font-bold text-neutral-700">
                {parsed.confidence !== null && parsed.confidence !== undefined 
                  ? `${(parsed.confidence * 100).toFixed(1)}%` 
                  : "N/A"}
              </div>
            </div>
            
            <div className="rounded-[24px] border border-neutral-200/80 bg-white p-6 shadow-sm">
              <div className="flex items-center text-xs text-neutral-400 font-bold uppercase tracking-[0.2em] mb-2">
                Perangkat
              </div>
              <div className="text-2xl font-bold text-neutral-700">
                {parsed.device}
              </div>
            </div>
          </div>
          
        </div>
      </section>
    </div>
  );
}
