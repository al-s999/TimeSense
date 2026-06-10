import { getHistory } from "@/lib/backend";
import GalleryClient from "./GalleryClient";

export const dynamic = "force-dynamic";

export default async function GalleryPage() {
  let allEvents = [];
  try {
    allEvents = await getHistory({ limit: 10000 });
  } catch (err) {
    console.error("GalleryPage: failed to fetch history", err);
  }

  // Filter yang punya gambar
  const imageEvents = allEvents.filter((e) => !!e.image_url);

  // Sorting terbaru di paling atas
  imageEvents.sort(
    (a, b) =>
      new Date(b.server_received_at).getTime() -
      new Date(a.server_received_at).getTime()
  );

  const backendUrl =
    process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-neutral-900 mb-6">Galeri Wajah Tertangkap</h1>
      <GalleryClient imageEvents={imageEvents} backendUrl={backendUrl} />
    </div>
  );
}
