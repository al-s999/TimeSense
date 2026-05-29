import Image from "next/image";
import { getHistory, type BackendEvent } from "@/lib/backend";

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

export default async function HistoryPage() {
  let rows: BackendEvent[] = [];
  let errorMessage: string | null = null;

  try {
    rows = await getHistory({ limit: 20 });
  } catch (err) {
    console.warn("HistoryPage: gagal memuat history", err);
    errorMessage = "Gagal memuat riwayat. Pastikan backend berjalan dan URL sudah benar.";
  }

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-4">Riwayat Aktivitas</h1>

      <section className="bg-white/70 rounded-[26px] shadow-sm overflow-hidden">
        {/* header row */}
        <div className="bg-neutral-200/60 px-6 py-4">
          <div className="grid grid-cols-[120px_1.6fr_140px_180px_80px] text-xs font-semibold text-neutral-700 tracking-wide">
            <div>ID</div>
            <div>DAY/DATE</div>
            <div className="text-center">TIME</div>
            <div className="text-center">INFORMATION</div>
            <div className="text-center">ACTION</div>
          </div>
        </div>

        {/* body */}
        <div className="divide-y divide-neutral-200/70">
          {errorMessage ? (
            <div className="px-6 py-10 text-sm text-red-600">{errorMessage}</div>
          ) : rows.length === 0 ? (
            <div className="px-6 py-10 text-sm text-neutral-600">Belum ada data.</div>
          ) : (
            rows.map((e) => {
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
                <div
                  key={e.id}
                  className="grid grid-cols-[120px_1.6fr_140px_180px_80px] items-center px-6 py-4 text-sm"
                >
                  <div className="text-neutral-500">#{e.id}</div>

                  <div className="text-neutral-700">{dayDate}</div>

                  <div className="text-center text-neutral-500">{t}</div>

                  <div className="flex justify-center">
                    <span className={`px-5 py-2 rounded-full text-xs font-semibold ${badge}`}>
                      {info.text}
                    </span>
                  </div>

                  <div className="flex justify-center">
                    {/* sementara UI only (nanti kalau endpoint delete sudah ada baru dihubungkan) */}
                    <button
                      className="p-2 rounded-full hover:bg-neutral-200/60"
                      title="Delete"
                      aria-label={`Delete event ${e.id}`}
                    >
                      <Image src="/trash.svg" alt="" width={18} height={18} aria-hidden />
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>

      </section>
    </div>
  );
}
