import { getNotifications, type BackendEvent } from "@/lib/backend";

type PreviewItem = {
  id: number;
  type: "Warning" | "Info" | "Success" | "Danger";
  message: string;
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

function mapType(label: string | null, raw: string): PreviewItem["type"] {
  const key = getEventKey(label, raw);
  if (key === "ORANG_MASUK" || key === "ORANG_KELUAR" || key.startsWith("SOMEONE_")) return "Warning";
  if (key.endsWith("_MASUK") || key === "SAYA_MASUK" || key === "TEMAN_MASUK") return "Success";
  if (key.endsWith("_KELUAR") || key === "SAYA_KELUAR" || key === "TEMAN_KELUAR") return "Danger";
  return "Info";
}

function mapMessage(e: BackendEvent): string {
  switch (getEventKey(e.predicted_label, e.raw_event)) {
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
    case "PINTU_BUKA":
      return "Pintu dibuka";
    case "PINTU_TUTUP":
      return "Pintu ditutup";
    default:
      const k = getEventKey(e.predicted_label, e.raw_event);
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
      return e.predicted_label ?? e.raw_event;
  }
}

export default async function NotificationPreview() {
  // ambil 5 terbaru
  let events: BackendEvent[] = [];
  let errorMessage: string | null = null;

  try {
    events = await getNotifications(5);
  } catch (err) {
    console.warn("NotificationPreview: gagal memuat notifications", err);
    errorMessage = "Gagal memuat notifikasi. Pastikan backend berjalan dan URL sudah benar.";
  }

  const items: PreviewItem[] = events.map((e: BackendEvent) => ({
    id: e.id,
    type: mapType(e.predicted_label, e.raw_event),
    message: mapMessage(e),
  }));

  return (
    <section className="bg-white/70 rounded-[26px] shadow-sm p-6 h-full flex flex-col">
      <div className="flex items-center justify-between">
        <div className="font-semibold flex items-center gap-2">
          <span aria-hidden>🔔</span> Notification
        </div>
        <a className="text-sm text-neutral-500 hover:text-neutral-800" href="/notifications">
          See all
        </a>
      </div>

      <div className="mt-4 flex flex-col gap-3">
        {errorMessage ? (
          <div className="px-4 py-4 text-sm text-red-600">{errorMessage}</div>
        ) : (
          items.map((n: PreviewItem) => {
            const accent = n.type === "Warning" ? "bg-amber-200/70" : n.type === "Success" ? "bg-emerald-200/70" : n.type === "Danger" ? "bg-rose-200/70" : "bg-sky-200/70";
            const icon = n.type === "Warning" ? "⚠️" : n.type === "Success" ? "✅" : n.type === "Danger" ? "🚪" : "ⓘ";

            return (
              <div
                key={n.id}
                className={`rounded-2xl px-5 py-3 flex items-center justify-between gap-4 ${accent}`}
              >
                <div className="flex items-center gap-4">
                  <div className="w-9 h-9 rounded-2xl bg-white/70 flex items-center justify-center text-sm">
                    {icon}
                  </div>
                  <div>
                    <div className="font-semibold text-sm leading-tight">{n.type}</div>
                    <div className="text-sm text-neutral-600 leading-tight">{n.message}</div>
                  </div>
                </div>
                <div className="text-neutral-700 text-sm">›</div>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}
