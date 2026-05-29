"use client";

import { useEffect, useMemo, useState } from "react";

type ConnectionType = "qr" | "pairing";

type BotConfig = {
  connectionType: ConnectionType;
  pairingNumber: string;
  ownerNumber: string;
  backendUrl: string;
  notificationPollMs: number;
  sendLatestOnStart: boolean;
  botNumber?: string;
  lastNotificationId?: number;
  lastNotificationAt?: string;
};

type BotHealth = {
  ok: boolean;
  status: "connecting" | "open" | "close";
  self_jid: string;
  connection: ConnectionType;
};

const DEFAULT_CONFIG: BotConfig = {
  connectionType: "qr",
  pairingNumber: "",
  ownerNumber: "",
  backendUrl: "http://localhost:8000",
  notificationPollMs: 8000,
  sendLatestOnStart: true,
  botNumber: "",
  lastNotificationId: 0,
  lastNotificationAt: "",
};

const WA_BOT_URL = process.env.NEXT_PUBLIC_WA_BOT_URL ?? "http://localhost:3001";
const WA_BASE = WA_BOT_URL.replace(/\/+$/, "");

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    ...(init?.headers ? Object.fromEntries(Object.entries(init.headers)) : {}),
  };
  if (init?.body) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${WA_BASE}${path}`, {
    ...init,
    headers,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request gagal (${res.status})`);
  }
  return res.json();
}

async function fetchMaybeQr(path: "/qr" | "/pairing") {
  const res = await fetch(`${WA_BASE}${path}`, { cache: "no-store" });
  if (res.status === 404) {
    return null;
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request gagal (${res.status})`);
  }
  return res.json() as Promise<{ ok: boolean; qr?: string; code?: string }>;
}

export default function WhatsAppBotPanel() {
  const [config, setConfig] = useState<BotConfig>(DEFAULT_CONFIG);
  const [health, setHealth] = useState<BotHealth | null>(null);
  const [qrData, setQrData] = useState<string | null>(null);
  const [pairingCode, setPairingCode] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const botNumber = useMemo(() => {
    if (config.botNumber) return config.botNumber;
    const jid = health?.self_jid ?? "";
    const beforeAt = jid.split("@")[0] ?? "";
    const withoutDevice = beforeAt.split(":")[0] ?? beforeAt;
    return withoutDevice.replace(/\D/g, "");
  }, [config.botNumber, health?.self_jid]);

  useEffect(() => {
    void refreshAll();
    const timer = setInterval(() => {
      void refreshHealth();
    }, 5000);
    return () => clearInterval(timer);
  }, []);

  const refreshAll = async () => {
    try {
      setError(null);
      const [cfg, status] = await Promise.all([
        fetchJson<{ ok: boolean; config: BotConfig }>("/config"),
        fetchJson<BotHealth>("/health"),
      ]);
      setConfig((prev) => ({ ...prev, ...cfg.config }));
      setHealth(status);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const refreshHealth = async () => {
    try {
      const status = await fetchJson<BotHealth>("/health");
      setHealth(status);
    } catch {
      // ignore refresh error
    }
  };

  const handleSave = async () => {
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      const payload = {
        connectionType: config.connectionType,
        pairingNumber: config.pairingNumber,
        ownerNumber: config.ownerNumber,
        backendUrl: config.backendUrl,
        notificationPollMs: config.notificationPollMs,
        sendLatestOnStart: config.sendLatestOnStart,
      };
      const res = await fetchJson<{ ok: boolean; config: BotConfig }>("/config", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setConfig((prev) => ({ ...prev, ...res.config }));
      setNotice("Konfigurasi tersimpan.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleGenerate = async () => {
    setBusy(true);
    setNotice(null);
    setError(null);
    setQrData(null);
    setPairingCode(null);

    try {
      await fetchJson("/connect", { method: "POST" });
      setNotice("Menunggu QR/pairing code dari bot...");

      if (config.connectionType === "qr") {
        await pollQr();
      } else {
        await pollPairing();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleSync = async () => {
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      const res = await fetchJson<{ ok: boolean; lastNotificationAt: string }>(
        "/sync",
        {
          method: "POST",
        }
      );
      if (res.lastNotificationAt) {
        setNotice(`Sinkron terkirim: ${res.lastNotificationAt.replace("T", " ")}`);
      } else {
        setNotice("Sinkron terkirim.");
      }
      await refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleLogout = async () => {
    setBusy(true);
    setNotice(null);
    setError(null);
    setQrData(null);
    setPairingCode(null);
    try {
      await fetchJson("/logout", { method: "POST" });
      setNotice("Berhasil logout. Silakan generate QR untuk login ulang.");
      await refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const pollQr = async () => {
    for (let i = 0; i < 30; i += 1) {
      try {
        const res = await fetchMaybeQr("/qr");
        if (res?.qr) {
          setQrData(res.qr);
          setNotice("QR siap dipindai.");
          return;
        }
      } catch {
        // ignore and retry
      }
      if (i % 5 === 4) {
        try {
          const status = await fetchJson<BotHealth>("/health");
          setHealth(status);
          if (status.status === "open") {
            setNotice("Bot sudah terkoneksi. QR tidak diperlukan.");
            return;
          }
        } catch {
          // ignore
        }
      }
      await sleep(1000);
    }
    setError("QR belum tersedia. Coba ulangi.");
  };

  const pollPairing = async () => {
    for (let i = 0; i < 30; i += 1) {
      try {
        const res = await fetchMaybeQr("/pairing");
        if (res?.code) {
          setPairingCode(res.code);
          setNotice("Pairing code siap.");
          return;
        }
      } catch {
        // ignore and retry
      }
      if (i % 5 === 4) {
        try {
          const status = await fetchJson<BotHealth>("/health");
          setHealth(status);
          if (status.status === "open") {
            setNotice("Bot sudah terkoneksi. Pairing code tidak diperlukan.");
            return;
          }
        } catch {
          // ignore
        }
      }
      await sleep(1000);
    }
    setError("Pairing code belum tersedia. Coba ulangi.");
  };

  return (
    <section className="rounded-3xl bg-white/70 p-6 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">WhatsApp Bot</h2>
          <p className="mt-1 text-sm text-neutral-500">
            Atur nomor owner, koneksi bot, dan sinkronisasi notifikasi.
          </p>
        </div>
        <button
          type="button"
          onClick={refreshAll}
          className="rounded-2xl border border-neutral-200 px-4 py-2 text-sm font-semibold text-neutral-700 hover:bg-neutral-100"
        >
          Refresh
        </button>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="grid grid-cols-1 gap-4">
          <div>
            <label className="text-sm font-semibold">Nomor Owner (WhatsApp)</label>
            <input
              value={config.ownerNumber}
              onChange={(event) =>
                setConfig((prev) => ({ ...prev, ownerNumber: event.target.value }))
              }
              placeholder="6281234567890"
              className="mt-2 w-full rounded-2xl bg-white px-4 py-3 text-sm shadow-sm outline-none ring-1 ring-transparent focus:ring-[#F6C1C1]"
            />
          </div>

          <div>
            <label className="text-sm font-semibold">Backend URL</label>
            <input
              value={config.backendUrl}
              onChange={(event) =>
                setConfig((prev) => ({ ...prev, backendUrl: event.target.value }))
              }
              placeholder="http://localhost:8000"
              className="mt-2 w-full rounded-2xl bg-white px-4 py-3 text-sm shadow-sm outline-none ring-1 ring-transparent focus:ring-[#F6C1C1]"
            />
          </div>

          <div>
            <label className="text-sm font-semibold">Metode Koneksi</label>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() =>
                  setConfig((prev) => ({ ...prev, connectionType: "qr" }))
                }
                className={`rounded-2xl px-4 py-2 text-sm font-semibold transition ${
                  config.connectionType === "qr"
                    ? "bg-neutral-900 text-white"
                    : "bg-white text-neutral-700 ring-1 ring-neutral-200"
                }`}
              >
                Generate QR
              </button>
              <button
                type="button"
                onClick={() =>
                  setConfig((prev) => ({ ...prev, connectionType: "pairing" }))
                }
                className={`rounded-2xl px-4 py-2 text-sm font-semibold transition ${
                  config.connectionType === "pairing"
                    ? "bg-neutral-900 text-white"
                    : "bg-white text-neutral-700 ring-1 ring-neutral-200"
                }`}
              >
                Pairing Code
              </button>
            </div>
          </div>

          {config.connectionType === "pairing" ? (
            <div>
              <label className="text-sm font-semibold">Nomor Pairing</label>
              <input
                value={config.pairingNumber}
                onChange={(event) =>
                  setConfig((prev) => ({ ...prev, pairingNumber: event.target.value }))
                }
                placeholder="6281234567890"
                className="mt-2 w-full rounded-2xl bg-white px-4 py-3 text-sm shadow-sm outline-none ring-1 ring-transparent focus:ring-[#F6C1C1]"
              />
            </div>
          ) : null}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="text-sm font-semibold">Interval Polling (ms)</label>
              <input
                type="number"
                value={config.notificationPollMs}
                onChange={(event) =>
                  setConfig((prev) => ({
                    ...prev,
                    notificationPollMs: Number(event.target.value),
                  }))
                }
                className="mt-2 w-full rounded-2xl bg-white px-4 py-3 text-sm shadow-sm outline-none ring-1 ring-transparent focus:ring-[#F6C1C1]"
              />
            </div>
            <div className="flex items-center gap-3 pt-6">
              <input
                id="sendLatest"
                type="checkbox"
                checked={config.sendLatestOnStart}
                onChange={(event) =>
                  setConfig((prev) => ({
                    ...prev,
                    sendLatestOnStart: event.target.checked,
                  }))
                }
                className="h-4 w-4 rounded border-neutral-300"
              />
              <label htmlFor="sendLatest" className="text-sm text-neutral-700">
                Kirim notifikasi terbaru saat bot online
              </label>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleSave}
              disabled={busy}
              className="rounded-2xl bg-neutral-900 px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:translate-y-0.5 disabled:opacity-70"
            >
              {busy ? "Menyimpan..." : "Simpan"}
            </button>
            <button
              type="button"
              onClick={handleGenerate}
              disabled={busy}
              className="rounded-2xl border border-neutral-200 px-6 py-3 text-sm font-semibold text-neutral-700 hover:bg-neutral-100 disabled:opacity-70"
            >
              {config.connectionType === "qr" ? "Generate QR" : "Generate Pairing"}
            </button>
            <button
              type="button"
              onClick={handleSync}
              disabled={busy}
              className="rounded-2xl border border-neutral-200 px-6 py-3 text-sm font-semibold text-neutral-700 hover:bg-neutral-100 disabled:opacity-70"
            >
              Sinkron Sekarang
            </button>
            <button
              type="button"
              onClick={handleLogout}
              disabled={busy}
              className="rounded-2xl border border-rose-200 px-6 py-3 text-sm font-semibold text-rose-600 hover:bg-rose-50 disabled:opacity-70"
            >
              Logout
            </button>
          </div>

          {notice ? (
            <div className="rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
              {notice}
            </div>
          ) : null}
          {error ? (
            <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {error}
            </div>
          ) : null}
        </div>

        <div className="flex flex-col gap-6">
          <div className="rounded-3xl bg-white/70 p-6 shadow-sm">
            <h3 className="text-lg font-semibold">Status</h3>
            <div className="mt-4 grid gap-3 text-sm text-neutral-700">
              <div className="flex items-center justify-between">
                <span>Status koneksi</span>
                <span className="font-semibold">{health?.status ?? "-"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Nomor bot</span>
                <span className="font-semibold">{botNumber || "-"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Nomor owner</span>
                <span className="font-semibold">{config.ownerNumber || "-"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Notifikasi terakhir</span>
                <span className="font-semibold">
                  {config.lastNotificationAt
                    ? config.lastNotificationAt.replace("T", " ")
                    : "-"}
                </span>
              </div>
            </div>
          </div>

          <div className="rounded-3xl bg-white/70 p-6 shadow-sm">
            <h3 className="text-lg font-semibold">
              {config.connectionType === "qr" ? "QR Code" : "Pairing Code"}
            </h3>
            <div className="mt-4 flex min-h-[320px] items-center justify-center rounded-2xl border border-dashed border-neutral-200 bg-white">
              {config.connectionType === "qr" ? (
                qrData ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={qrData} alt="QR" className="h-64 w-64" />
                ) : (
                  <div className="text-sm text-neutral-500">
                    Klik Generate QR untuk menampilkan kode.
                  </div>
                )
              ) : pairingCode ? (
                <div className="text-2xl font-semibold tracking-widest">
                  {pairingCode}
                </div>
              ) : (
                <div className="text-sm text-neutral-500">
                  Klik Generate Pairing untuk menampilkan kode.
                </div>
              )}
            </div>
            <p className="mt-3 text-xs text-neutral-500">
              Pastikan bot WhatsApp berjalan di port 3001 agar halaman ini bisa
              mengambil QR/pairing code.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
