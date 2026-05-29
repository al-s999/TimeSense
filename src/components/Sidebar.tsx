"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useProfile } from "@/lib/profile";

const nav = [
  { href: "/dashboard", label: "Dashboard", icon: "/dashboardicon.svg" },
  { href: "/history", label: "Riwayat", icon: "/historyIcon.svg" },
  { href: "/notifications", label: "Notifikasi", icon: "/notifIcon.svg" },
  { href: "/enroll-face", label: "Enroll Face", icon: "/file.svg" },
  { href: "/live-face", label: "Live Face", icon: "/window.svg" },
];

export default function Sidebar() {
  const profile = useProfile();
  const pathname = usePathname();

  return (
    <aside className="sticky top-0 h-screen w-24 bg-white/60 backdrop-blur rounded-r-[28px] py-8 px-3 flex flex-col items-center gap-8">
      <div className="w-12 h-12 rounded-full bg-neutral-200 flex items-center justify-center text-xs overflow-hidden">
        {profile.avatar ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={profile.avatar}
            alt="Logo"
            className="h-full w-full object-cover"
          />
        ) : (
          "Logo"
        )}
      </div>

      <nav className="flex flex-col gap-6">
        {nav.map((it) => {
          const isActive = pathname === it.href || pathname.startsWith(`${it.href}/`);

          return (
            <Link
              key={it.href}
              href={it.href}
              className="relative w-12 h-12 flex items-center justify-center text-neutral-900hover:shadow transition"
              title={it.label}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={it.icon} alt="" className="h-6 w-6" aria-hidden />
              <span
                className={[
                  "pointer-events-none absolute -bottom-2 left-1/2 h-1 w-8 -translate-x-1/2 rounded-full bg-neutral-900 transition-opacity",
                  isActive ? "opacity-100" : "opacity-0",
                ].join(" ")}
                aria-hidden
              />
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto">
        <Link
          href="/settings"
          className="relative w-12 h-12 flex items-center justify-center"
          aria-label="Settings"
          title="Settings"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/settingsIcon.svg" alt="" className="h-6 w-6" aria-hidden />
          <span
            className={[
              "pointer-events-none absolute -bottom-2 left-1/2 h-1 w-8 -translate-x-1/2 rounded-full bg-neutral-900 transition-opacity",
              pathname === "/settings" || pathname.startsWith("/settings/")
                ? "opacity-100"
                : "opacity-0",
            ].join(" ")}
            aria-hidden
          />
        </Link>
      </div>
    </aside>
  );
}
