"use client";

import { useMemo, useState } from "react";

function trimUrl(url: string) {
  return url.replace(/\/+$/, "");
}

export default function LiveFacePage() {
  const [refreshKey, setRefreshKey] = useState(0);

  const faceBackendUrl = useMemo(() => {
    const configured = process.env.NEXT_PUBLIC_FACE_BACKEND_URL;
    if (configured && configured.trim()) return trimUrl(configured);
    return "http://127.0.0.1:8001";
  }, []);

  const streamUrl = `${faceBackendUrl}/live-preview?fps=30&ts=${refreshKey}`;

  return (
    <div className="space-y-6">
      <section className="rounded-[28px] bg-white/75 p-6 shadow-sm ring-1 ring-[#f2caca]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.28em] text-neutral-500">
              Live Face
            </p>
            <h1 className="mt-2 text-3xl font-extrabold text-neutral-900">
              Realtime Face Monitor
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-neutral-600">
              Halaman ini memakai stream dari face backend, jadi bisa dipakai bersamaan
              dengan service yang sudah kamu jalankan tanpa membuka kamera browser
              kedua kali.
            </p>
          </div>

          <button
            type="button"
            onClick={() => setRefreshKey((prev) => prev + 1)}
            className="rounded-2xl bg-neutral-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-neutral-700"
          >
            Refresh Stream
          </button>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.7fr)_360px]">
        <div className="overflow-hidden rounded-[30px] bg-neutral-950 shadow-[0_22px_70px_rgba(15,23,42,0.28)]">
          <div className="border-b border-white/10 px-5 py-4 text-sm text-white/72">
            Source: <span className="font-semibold text-white">{faceBackendUrl}</span>
          </div>

          <div className="bg-[radial-gradient(circle_at_top,#334155_0%,#0f172a_45%,#020617_100%)] p-4">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              key={refreshKey}
              src={streamUrl}
              alt="Live face preview"
              className="block h-auto w-full rounded-[24px] bg-black object-contain"
            />
          </div>
        </div>

        <div className="space-y-5">
          <div className="rounded-[28px] bg-white/75 p-6 shadow-sm ring-1 ring-[#f2caca]">
            <h2 className="text-lg font-bold text-neutral-900">Legend</h2>
            <div className="mt-4 space-y-3 text-sm text-neutral-600">
              <div className="flex items-center gap-3">
                <span className="h-3 w-3 rounded-full bg-emerald-500" aria-hidden />
                <span>Hijau: wajah dikenali dari face database</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="h-3 w-3 rounded-full bg-red-500" aria-hidden />
                <span>Merah: wajah belum dikenali / unknown</span>
              </div>
            </div>
          </div>

          <div className="rounded-[28px] bg-white/75 p-6 shadow-sm ring-1 ring-[#f2caca]">
            <h2 className="text-lg font-bold text-neutral-900">Label Di Video</h2>
            <div className="mt-4 space-y-2 text-sm leading-6 text-neutral-600">
              <p>
                <span className="font-semibold text-neutral-900">face_label</span>:
                identitas hasil recognition.
              </p>
              <p>
                <span className="font-semibold text-neutral-900">d</span>: distance
                embedding, makin kecil makin dekat ke data wajah.
              </p>
              <p>
                <span className="font-semibold text-neutral-900">c</span>: confidence
                hasil mapping recognition.
              </p>
              <p>
                <span className="font-semibold text-neutral-900">det</span>: skor
                deteksi wajah dari model.
              </p>
            </div>
          </div>

          <div className="rounded-[28px] bg-[#fff4f4] p-6 shadow-sm ring-1 ring-[#f2caca]">
            <h2 className="text-lg font-bold text-neutral-900">Run</h2>
            <div className="mt-4 space-y-2 text-sm leading-6 text-neutral-700">
              <p>
                Frontend: <code className="rounded bg-white px-2 py-1">npm run dev</code>
              </p>
              <p>
                Face backend:{" "}
                <code className="rounded bg-white px-2 py-1">
                  uvicorn app.face_service:app --reload --port 8001
                </code>
              </p>
              <p>
                Main backend:{" "}
                <code className="rounded bg-white px-2 py-1">
                  uvicorn app.main:app --reload --port 8000
                </code>
              </p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
