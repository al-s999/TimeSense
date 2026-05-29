"use client";

import { useProfile } from "@/lib/profile";
import { useEffect, useState } from "react";

const DEVICE_ID = "esp32-1";
const SENSOR_POLL_INTERVAL_MS = 2000;

type CommandAction = "enable" | "disable" | "open_door" | "close_door";
type SensorResponse = {
  distance1?: number | null;
  distance2?: number | null;
  temperature?: number | null;
  ts?: number | null;
  status?: string | null;
};

const CONTROLS: Array<{
  action: CommandAction;
  label: string;
  tone: "green" | "red" | "blue";
}> = [
  { action: "enable", label: "Aktifkan Sistem", tone: "green" },
  { action: "disable", label: "Matikan Sistem", tone: "red" },
  { action: "open_door", label: "Buka Pintu", tone: "blue" },
  { action: "close_door", label: "Tutup Pintu", tone: "blue" },
];

function formatDistance(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value) ? `${value} cm` : "-- cm";
}

function normalizeSensorStatus(status?: string | null) {
  return (status ?? "").trim().toLowerCase();
}

function translateSensorStatus(status?: string | null) {
  const normalized = normalizeSensorStatus(status);

  if (!normalized) return "Tidak ada aktivitas";

  if (
    normalized.includes("masuk") && normalized.includes("keluar") ||
    normalized.includes("entry") && normalized.includes("exit") ||
    normalized.includes("in") && normalized.includes("out")
  ) {
    return "Mendeteksi orang masuk/keluar";
  }

  if (
    normalized.includes("masuk") ||
    normalized.includes("entry") ||
    normalized.includes("incoming")
  ) {
    return "Mendeteksi orang masuk";
  }

  if (
    normalized.includes("keluar") ||
    normalized.includes("exit") ||
    normalized.includes("outgoing")
  ) {
    return "Mendeteksi orang keluar";
  }

  if (
    normalized.includes("move") ||
    normalized.includes("motion") ||
    normalized.includes("gerak")
  ) {
    return "Ada pergerakan";
  }

  if (
    normalized.includes("idle") ||
    normalized.includes("quiet") ||
    normalized.includes("still") ||
    normalized.includes("no_activity") ||
    normalized.includes("no activity") ||
    normalized.includes("inactive")
  ) {
    return "Tidak ada aktivitas";
  }

  return status ?? "Tidak ada aktivitas";
}

function getStatusTone(status?: string | null) {
  const normalized = normalizeSensorStatus(status);

  if (
    normalized.includes("masuk") ||
    normalized.includes("keluar") ||
    normalized.includes("entry") ||
    normalized.includes("exit") ||
    normalized.includes("in") && normalized.includes("out")
  ) {
    return {
      badge: "bg-sky-100 text-sky-700 border-sky-200/80",
      dot: "bg-sky-500",
    };
  }

  if (
    normalized.includes("move") ||
    normalized.includes("motion") ||
    normalized.includes("gerak")
  ) {
    return {
      badge: "bg-amber-100 text-amber-700 border-amber-200/80",
      dot: "bg-amber-500",
    };
  }

  return {
    badge: "bg-emerald-100 text-emerald-700 border-emerald-200/80",
    dot: "bg-emerald-500",
  };
}

function getButtonClass(tone: "green" | "red" | "blue") {
  if (tone === "green") {
    return "bg-emerald-600 text-white hover:bg-emerald-700";
  }

  if (tone === "red") {
    return "bg-rose-600 text-white hover:bg-rose-700";
  }

  return "bg-sky-600 text-white hover:bg-sky-700";
}

async function readResponseMessage(response: Response) {
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    const raw = await response.text();

    if (!raw.trim()) {
      return "";
    }

    try {
      const data = JSON.parse(raw) as
        | string
        | {
            message?: string;
            error?: string;
            detail?: string;
          };

      if (typeof data === "string") {
        return data;
      }

      return data.message ?? data.error ?? data.detail ?? raw;
    } catch {
      return raw;
    }
  }

  return response.text();
}

export default function GreetingCard() {
  const profile = useProfile();
  const [sensor, setSensor] = useState<SensorResponse | null>(null);
  const [sensorLoading, setSensorLoading] = useState(true);
  const [sensorError, setSensorError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<CommandAction | null>(null);
  const [commandFeedback, setCommandFeedback] = useState<{
    kind: "success" | "error";
    text: string;
  } | null>(null);

  useEffect(() => {
    let active = true;
    const controllers = new Set<AbortController>();

    async function loadSensorData() {
      const controller = new AbortController();
      controllers.add(controller);

      try {
        const response = await fetch(`/api/sensor/latest?device_id=${DEVICE_ID}`, {
          cache: "no-store",
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error((await readResponseMessage(response)) || `HTTP ${response.status}`);
        }

        const data = (await response.json()) as SensorResponse;
        if (!active) return;

        setSensor(data);
        setSensorError(null);
      } catch (error) {
        if ((error as Error).name === "AbortError" || !active) return;
        console.warn("GreetingCard: gagal memuat sensor", error);
        setSensorError("Data sensor belum bisa dimuat. Periksa koneksi backend dan perangkat.");
      } finally {
        controllers.delete(controller);
        if (active) {
          setSensorLoading(false);
        }
      }
    }

    void loadSensorData();
    const timer = window.setInterval(() => {
      void loadSensorData();
    }, SENSOR_POLL_INTERVAL_MS);

    return () => {
      active = false;
      window.clearInterval(timer);
      controllers.forEach((controller) => controller.abort());
    };
  }, []);

  async function handleCommand(action: CommandAction, label: string) {
    try {
      setPendingAction(action);
      setCommandFeedback(null);

      const response = await fetch("/api/command", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          device_id: DEVICE_ID,
          action,
        }),
      });

      const message = await readResponseMessage(response);

      if (!response.ok) {
        throw new Error(message || `HTTP ${response.status}`);
      }

      setCommandFeedback({
        kind: "success",
        text: message || `${label} berhasil dikirim ke ${DEVICE_ID}.`,
      });
    } catch (error) {
      console.warn(`GreetingCard: gagal mengirim command ${action}`, error);
      setCommandFeedback({
        kind: "error",
        text: error instanceof Error ? error.message : "Command gagal dikirim.",
      });
    } finally {
      setPendingAction(null);
    }
  }

  const translatedStatus = translateSensorStatus(sensor?.status);
  const statusTone = getStatusTone(sensor?.status);

  return (
    <section className="flex flex-col gap-10 rounded-[34px] bg-white/70 p-10 shadow-sm xl:flex-row xl:items-center xl:justify-between">
      <div className="w-full max-w-xl">
        <div className="text-5xl font-extrabold tracking-tight text-neutral-700">
          Hi, {profile.name}!{" "}
          <span className="ml-2 text-lg align-middle">✏️</span>
        </div>
        <div
          className="mt-4 rounded-[28px] border border-neutral-200/80 bg-neutral-50/80 px-5 py-5 shadow-[0_1px_0_rgba(0,0,0,0.03)]"
          aria-live="polite"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-neutral-400">
                Panel Kontrol IoT
              </p>
              <p className="mt-2 text-sm text-neutral-500">
                Kontrol perangkat {DEVICE_ID} dan pantau sensor secara realtime tanpa reload halaman.
              </p>
            </div>
            <div className="rounded-full border border-neutral-200 bg-white px-3 py-1 text-xs font-semibold text-neutral-500">
              Polling 2 detik
            </div>
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {CONTROLS.map((control) => {
              const isPending = pendingAction !== null;
              return (
                <button
                  key={control.action}
                  type="button"
                  disabled={isPending}
                  onClick={() => void handleCommand(control.action, control.label)}
                  className={`rounded-2xl px-4 py-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${getButtonClass(control.tone)}`}
                >
                  {pendingAction === control.action ? "Mengirim..." : control.label}
                </button>
              );
            })}
          </div>

          {commandFeedback ? (
            <div
              className={`mt-4 rounded-2xl border px-4 py-3 text-sm ${
                commandFeedback.kind === "success"
                  ? "border-emerald-200/80 bg-emerald-50 text-emerald-700"
                  : "border-rose-200/80 bg-rose-50 text-rose-700"
              }`}
            >
              {commandFeedback.text}
            </div>
          ) : null}

          <div className="mt-5 grid gap-3 md:grid-cols-3">
            <div className="rounded-2xl border border-neutral-200 bg-white px-4 py-4">
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-neutral-400">
                Sensor 1
              </div>
              <div className="mt-2 text-2xl font-bold text-neutral-700">
                {sensorLoading ? "..." : formatDistance(sensor?.distance1)}
              </div>
            </div>

            <div className="rounded-2xl border border-neutral-200 bg-white px-4 py-4">
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-neutral-400">
                Sensor 2
              </div>
              <div className="mt-2 text-2xl font-bold text-neutral-700">
                {sensorLoading ? "..." : formatDistance(sensor?.distance2)}
              </div>
            </div>

            <div
              className={`rounded-2xl border px-4 py-4 ${statusTone.badge}`}
            >
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em]">
                <span className={`h-2.5 w-2.5 rounded-full ${statusTone.dot}`} />
                Status
              </div>
              <div className="mt-2 text-lg font-bold">
                {sensorLoading ? "Memuat data sensor..." : translatedStatus}
              </div>
            </div>
          </div>

          {sensorError ? (
            <div className="mt-4 rounded-2xl border border-rose-200/80 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {sensorError}
            </div>
          ) : (
            <p className="mt-4 text-xs text-neutral-500">
              Nilai sensor diperbarui otomatis setiap 2 detik dari endpoint terbaru perangkat.
            </p>
          )}
        </div>
      </div>

      <div className="h-[240px] w-full rounded-3xl bg-neutral-100 p-6 text-neutral-600 xl:w-[420px]">
        <div className="flex h-full flex-col justify-between rounded-[26px] border border-white/70 bg-white/60 p-6">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.28em] text-neutral-400">
              Device Overview
            </div>
            <div className="mt-3 text-3xl font-bold text-neutral-700">{DEVICE_ID}</div>
            <p className="mt-2 text-sm leading-relaxed text-neutral-500">
              Kontrol pintu dan pemantauan sensor terpusat langsung dari dashboard utama.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-2xl bg-neutral-900 px-4 py-3 text-white">
              <div className="text-xs uppercase tracking-[0.2em] text-white/60">Sensor 1</div>
              <div className="mt-2 text-xl font-semibold">
                {sensorLoading ? "..." : formatDistance(sensor?.distance1)}
              </div>
            </div>
            <div className="rounded-2xl bg-neutral-900 px-4 py-3 text-white">
              <div className="text-xs uppercase tracking-[0.2em] text-white/60">Sensor 2</div>
              <div className="mt-2 text-xl font-semibold">
                {sensorLoading ? "..." : formatDistance(sensor?.distance2)}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
