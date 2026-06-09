import { getHistoryById } from "@/lib/backend";
import HistoryDetailClient from "./HistoryDetailClient";
import { notFound } from "next/navigation";

export default async function HistoryDetailPage({ params }: { params: { id: string } }) {
  const id = parseInt(params.id, 10);
  if (isNaN(id)) return notFound();

  let event;
  try {
    event = await getHistoryById(id);
  } catch (error) {
    console.error("Failed to load history detail:", error);
    return notFound();
  }

  return (
    <main className="min-h-screen bg-neutral-100 p-6 md:p-12 font-sans selection:bg-black selection:text-white">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-3xl font-bold tracking-tight text-neutral-900 mb-2">Detail Riwayat</h1>
        <p className="text-neutral-600 mb-8">Informasi lengkap akses masuk yang terekam sistem.</p>
        <HistoryDetailClient event={event} />
      </div>
    </main>
  );
}
