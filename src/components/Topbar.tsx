"use client";

import { useProfile } from "@/lib/profile";
import { useEffect, useState } from "react";

function getCurrentDateIndonesian(): string {
  const now = new Date();
  const months = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
  ];
  return `${now.getDate()} ${months[now.getMonth()]} ${now.getFullYear()}`;
}

export default function Topbar() {
  const profile = useProfile();
  const [dateStr, setDateStr] = useState("");

  useEffect(() => {
    setDateStr(getCurrentDateIndonesian());
    // Update date at midnight
    const timer = setInterval(() => {
      setDateStr(getCurrentDateIndonesian());
    }, 60000);
    return () => clearInterval(timer);
  }, []);

  return (
    <header className="flex items-center justify-between gap-6">
      <div className="flex items-center gap-4">
        <div className="w-56 bg-white/70 rounded-2xl px-4 py-2 shadow-sm flex items-center gap-2">
          <input
            className="w-full bg-transparent outline-none text-sm placeholder:text-neutral-400"
            placeholder="Search..."
          />
          <span aria-hidden>🔍</span>
        </div>
      </div>

      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2 rounded-2xl bg-white px-4 py-2 text-sm font-semibold text-neutral-800 shadow-sm ring-1 ring-[#F6C1C1]">
          <span aria-hidden>📅</span>
          <span>{dateStr || "..."}</span>
        </div>

        <div className="flex items-center gap-3 bg-white/70 rounded-2xl px-3 py-2 shadow-sm">
          <div className="w-9 h-9 rounded-full bg-neutral-200 overflow-hidden">
            {profile.avatar ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={profile.avatar}
                alt="Foto profil"
                className="h-full w-full object-cover"
              />
            ) : null}
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold">{profile.name}</div>
            <div className="text-xs text-neutral-500">{profile.role}</div>
          </div>
        </div>
      </div>
    </header>
  );
}
