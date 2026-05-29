import { getHistory, type BackendEvent } from "@/lib/backend";
import RevealOnScroll from "@/components/RevealOnScroll";

function formatDayDate(iso: string) {
  const d = new Date(iso);
  return new Intl.DateTimeFormat("id-ID", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(d);
}

function formatTime(iso: string) {
  const d = new Date(iso);
  return new Intl.DateTimeFormat("id-ID", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d);
}

// Map label backend -> Masuk / Keluar
function infoFromLabel(label: string | null, raw: string) {
  const l = (label ?? raw ?? "").toUpperCase();

  // Masuk
  if (l.includes("PULANG") || l.includes("MASUK")) return { text: "Masuk", kind: "IN" as const };

  // Keluar
  if (l.includes("PERGI") || l.includes("KELUAR")) return { text: "Keluar", kind: "OUT" as const };

  // fallback dari raw_event
  if (l === "S2_S1") return { text: "Masuk", kind: "IN" as const };
  if (l === "S1_S2") return { text: "Keluar", kind: "OUT" as const };

  return { text: "—", kind: "UNKNOWN" as const };
}

export default async function ActivityPreview() {
  let rows: BackendEvent[] = [];
  let errorMessage: string | null = null;

  try {
    rows = await getHistory({ limit: 5 });
  } catch (err) {
    console.warn("ActivityPreview: gagal memuat history", err);
    errorMessage = "Gagal memuat riwayat. Pastikan backend berjalan dan URL sudah benar.";
  }

  return (
    <section className="bg-white/70 rounded-[26px] shadow-sm p-6 h-full flex flex-col">
      <div className="flex items-center justify-between">
        <div className="font-semibold flex items-center gap-2">
          <span aria-hidden>▤</span> Riwayat aktivitas
        </div>
        <a className="text-sm text-neutral-500 hover:text-neutral-800" href="/history">
          See all
        </a>
      </div>

      <div className="mt-4 overflow-hidden rounded-2xl border border-neutral-200/70">
        <div className="grid grid-cols-5 bg-neutral-100/70 text-xs font-semibold text-neutral-600 px-4 py-3">
          <div>ID</div>
          <div className="col-span-2">DAY/DATE</div>
          <div>TIME</div>
          <div className="text-center">INFORMATION</div>
        </div>

        {errorMessage ? (
          <div className="px-4 py-6 text-sm text-red-600">{errorMessage}</div>
        ) : rows.length === 0 ? (
          <div className="px-4 py-6 text-sm text-neutral-500">Belum ada data.</div>
        ) : (
          rows.map((e, index) => {
            const dayDate = formatDayDate(e.server_received_at);
            const t = formatTime(e.server_received_at);
            const info = infoFromLabel(e.predicted_label, e.raw_event);
            const badge =
              info.kind === "IN"
                ? "bg-sky-500 text-white"
                : info.kind === "OUT"
                ? "bg-red-600 text-white"
                : "bg-neutral-400 text-white";

            return (
              <RevealOnScroll key={e.id} delayMs={index * 60}>
                <div className="grid grid-cols-5 items-center px-4 py-3 text-sm border-t border-neutral-200/60">
                  <div className="text-neutral-400">#{e.id}</div>
                  <div className="col-span-2 text-neutral-400">{dayDate}</div>
                  <div className="text-neutral-400">{t}</div>
                  <div className="flex justify-center">
                    <span className={`px-6 py-2 rounded-full font-semibold text-white text-sm ${badge}`}>
                      {info.text}
                    </span>
                  </div>
                </div>
              </RevealOnScroll>
            );
          })
        )}
      </div>
    </section>
  );
}
