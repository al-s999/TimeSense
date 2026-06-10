import { getNotifications, type BackendEvent } from "@/lib/backend";
import NotificationsClient from "./NotificationsClient";

export const dynamic = "force-dynamic";

export default async function NotificationsPage() {
  let initialEvents: BackendEvent[] = [];
  let errorMessage: string | null = null;

  try {
    initialEvents = await getNotifications(50);
  } catch (err) {
    console.warn("NotificationsPage: gagal memuat notifications", err);
    errorMessage = "Gagal memuat notifikasi. Pastikan backend berjalan dan URL sudah benar.";
  }
  const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "";

  return (
    <div className="p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Notifications</h1>
        <a className="text-sm text-neutral-500 hover:text-neutral-800" href="/dashboard">
          Back to dashboard
        </a>
      </div>

      {errorMessage ? (
        <div className="mt-4 text-sm text-red-600">{errorMessage}</div>
      ) : (
        <NotificationsClient initialEvents={initialEvents} backendBaseUrl={backendBaseUrl} />
      )}
    </div>
  );
}
