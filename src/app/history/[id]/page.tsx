import { getHistoryById } from "@/lib/backend";
import HistoryDetailClient from "./HistoryDetailClient";
import { notFound } from "next/navigation";

export default async function HistoryDetailPage(props: { params: Promise<{ id: string }> }) {
  const params = await props.params;
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
    <div className="p-6">
      <h1 className="text-4xl font-extrabold tracking-tight text-neutral-900 mb-2">Detail Riwayat</h1>
      <p className="text-neutral-500 mb-8 font-medium">Informasi lengkap akses masuk yang terekam sistem.</p>
      
      <HistoryDetailClient event={event} />
    </div>
  );
}
