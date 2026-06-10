"use client";

import { useState } from "react";
import type { BackendEvent } from "@/lib/backend";

function formatDateTime(iso: string) {
  const d = new Date(iso);
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(d);
}

export default function GalleryClient({
  imageEvents,
  backendUrl,
}: {
  imageEvents: BackendEvent[];
  backendUrl: string;
}) {
  const [selectedEvent, setSelectedEvent] = useState<BackendEvent | null>(null);

  const handleDownload = async (imageUrl: string, filename: string) => {
    try {
      const response = await fetch(imageUrl);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Gagal mendownload gambar:", error);
      // Fallback jika fetch gagal (misal karena CORS policy pada backend)
      const link = document.createElement("a");
      link.href = imageUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  };

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-6">
        {imageEvents.map((ev) => (
          <div
            key={ev.id}
            onClick={() => setSelectedEvent(ev)}
            className="bg-white/70 backdrop-blur-md rounded-3xl shadow-sm border border-neutral-200/80 overflow-hidden flex flex-col h-[360px] cursor-pointer hover:shadow-md transition-shadow group"
          >
            {/* Gambar 60% */}
            <div className="h-[60%] w-full relative bg-neutral-100 shrink-0 border-b border-neutral-200/50 overflow-hidden">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={backendUrl + ev.image_url}
                alt={ev.predicted_label || "Wajah tertangkap"}
                className="absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
              />
              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors" />
            </div>

            {/* Info 40% */}
            <div className="h-[40%] p-5 flex flex-col justify-center">
              <h2 className="font-bold text-xl text-neutral-800 capitalize truncate mb-1">
                {ev.predicted_label || "Tidak Dikenal"}
              </h2>
              <div className="text-sm text-neutral-500 font-medium">
                {formatDateTime(ev.server_received_at)}
              </div>
              <div className="mt-3 flex items-center gap-3">
                <span
                  className={`px-3 py-1 rounded-full text-xs font-bold tracking-wide ${
                    ev.predicted_label && ev.predicted_label !== "unknown"
                      ? "bg-emerald-100 text-emerald-700"
                      : "bg-rose-100 text-rose-700"
                  }`}
                >
                  {ev.predicted_label && ev.predicted_label !== "unknown"
                    ? "Dikenali"
                    : "Tidak Dikenal"}
                </span>

                {ev.confidence !== null && ev.confidence !== undefined && (
                  <span className="text-xs font-semibold text-neutral-400">
                    Ak: {(ev.confidence * 100).toFixed(1)}%
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}

        {imageEvents.length === 0 && (
          <div className="col-span-full py-16 text-center text-neutral-500">
            Belum ada gambar wajah yang direkam di riwayat.
          </div>
        )}
      </div>

      {/* MODAL */}
      {selectedEvent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/60 backdrop-blur-sm transition-opacity">
          {/* Backdrop click to close */}
          <div
            className="absolute inset-0"
            onClick={() => setSelectedEvent(null)}
          />

          <div className="relative bg-white rounded-3xl shadow-2xl w-full max-w-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-4 border-b border-neutral-100">
              <h3 className="font-bold text-lg text-neutral-800 capitalize">
                {selectedEvent.predicted_label || "Tidak Dikenal"}
              </h3>
              <button
                onClick={() => setSelectedEvent(null)}
                className="p-2 bg-neutral-100 hover:bg-neutral-200 rounded-full text-neutral-600 transition"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M18 6 6 18" />
                  <path d="m6 6 12 12" />
                </svg>
              </button>
            </div>

            {/* Modal Image */}
            <div className="relative w-full aspect-video bg-neutral-900 flex items-center justify-center">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={backendUrl + selectedEvent.image_url}
                alt="Preview"
                className="max-w-full max-h-full object-contain"
              />
            </div>

            {/* Modal Footer (Info & Download) */}
            <div className="p-5 sm:p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-neutral-500 mb-1">
                  Direkam pada
                </p>
                <p className="font-semibold text-neutral-800">
                  {formatDateTime(selectedEvent.server_received_at)}
                </p>
              </div>

              <button
                onClick={() =>
                  handleDownload(
                    backendUrl + selectedEvent.image_url,
                    `face_${selectedEvent.id}_${selectedEvent.predicted_label || "unknown"}.jpg`
                  )
                }
                className="flex items-center justify-center gap-2 px-6 py-3 bg-neutral-900 hover:bg-neutral-800 text-white font-semibold rounded-xl transition shadow-sm"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" x2="12" y1="15" y2="3" />
                </svg>
                Download
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
