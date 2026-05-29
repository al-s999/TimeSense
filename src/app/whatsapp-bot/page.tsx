"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function WhatsAppBotRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/settings");
  }, [router]);

  return (
    <div className="p-6 text-sm text-neutral-600">
      Halaman WhatsApp Bot telah dipindahkan ke Settings.
    </div>
  );
}
