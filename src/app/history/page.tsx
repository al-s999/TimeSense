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

export const dynamic = "force-dynamic";

export default async function HistoryPage(props: {
  searchParams?: Promise<{ page?: string }>;
}) {
  const searchParams = await props.searchParams;
  let allRows: BackendEvent[] = [];
  let errorMessage: string | null = null;

  try {
    allRows = await getHistory({ limit: 10000 });
  } catch (err) {
    console.warn("HistoryPage: gagal memuat history", err);
    errorMessage = "Gagal memuat riwayat. Pastikan backend berjalan dan URL sudah benar.";
  }

  const currentPage = parseInt(searchParams?.page || "1", 10);
  const itemsPerPage = 10;
  const totalPages = Math.ceil(allRows.length / itemsPerPage) || 1;
  const page = Math.min(Math.max(1, currentPage), totalPages);

  const startIndex = (page - 1) * itemsPerPage;
  const rows = allRows.slice(startIndex, startIndex + itemsPerPage);

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-4">Riwayat Aktivitas</h1>

      <section className="bg-white/70 rounded-[26px] shadow-sm overflow-hidden">
        {/* header row */}
        <div className="bg-neutral-200/60 px-6 py-4">
          <div className="grid grid-cols-[120px_1.6fr_140px_180px_100px] text-xs font-semibold text-neutral-700 tracking-wide">
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
                  ? "bg-emerald-500 text-white"
                  : info.kind === "OUT"
                  ? "bg-rose-500 text-white"
                  : "bg-neutral-400 text-white";

              return (
                <div
                  key={e.id}
                  className="grid grid-cols-[120px_1.6fr_140px_180px_100px] items-center px-6 py-4 text-sm hover:bg-white/50 transition-colors"
                >
                  <div className="text-neutral-500 font-medium">#{e.id}</div>

                  <div className="text-neutral-700 font-medium">
                    {dayDate}
                    <div className="text-xs text-neutral-500 mt-0.5">{e.predicted_label || e.raw_event}</div>
                  </div>

                  <div className="text-center text-neutral-500 font-medium">{t}</div>

                  <div className="flex justify-center">
                    <span className={`px-5 py-2 rounded-full text-xs font-bold tracking-wide ${badge}`}>
                      {info.text}
                    </span>
                  </div>

                  <div className="flex justify-center items-center gap-2">
                    <a href={`/history/${e.id}`} className="px-3 py-1.5 rounded-xl bg-neutral-100 hover:bg-neutral-200 text-neutral-700 text-xs font-bold transition-colors">
                      Detail
                    </a>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-6 py-4 bg-neutral-50/50 border-t border-neutral-200/70">
            <div className="text-sm text-neutral-500 font-medium">
              Menampilkan {startIndex + 1} - {Math.min(startIndex + itemsPerPage, allRows.length)} dari {allRows.length} riwayat
            </div>
            <div className="flex items-center gap-2">
              <a
                href={page > 1 ? `/history?page=${page - 1}` : "#"}
                className={`px-4 py-2 rounded-xl text-sm font-semibold transition-all ${
                  page > 1
                    ? "bg-white border border-neutral-200 text-neutral-700 hover:bg-neutral-50 shadow-sm"
                    : "bg-neutral-100/50 text-neutral-400 cursor-not-allowed"
                }`}
              >
                Previous
              </a>
              <span className="text-sm font-bold text-neutral-700 px-3">
                {page} / {totalPages}
              </span>
              <a
                href={page < totalPages ? `/history?page=${page + 1}` : "#"}
                className={`px-4 py-2 rounded-xl text-sm font-semibold transition-all ${
                  page < totalPages
                    ? "bg-white border border-neutral-200 text-neutral-700 hover:bg-neutral-50 shadow-sm"
                    : "bg-neutral-100/50 text-neutral-400 cursor-not-allowed"
                }`}
              >
                Next
              </a>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
