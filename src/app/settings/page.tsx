"use client";

import { useEffect, useState } from "react";
import RevealOnScroll from "@/components/RevealOnScroll";
import WhatsAppBotPanel from "@/components/WhatsAppBotPanel";
import { saveProfile, useProfile } from "@/lib/profile";

type AvatarState = {
  file: File | null;
  previewUrl: string | null;
  objectUrl: string | null;
};

const emptyAvatarState: AvatarState = {
  file: null,
  previewUrl: null,
  objectUrl: null,
};

export default function SettingsPage() {
  const profile = useProfile();
  const [name, setName] = useState(profile.name);
  const [avatar, setAvatar] = useState<AvatarState>({
    ...emptyAvatarState,
    previewUrl: profile.avatar,
  });
  const [initialProfile, setInitialProfile] = useState(profile);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    return () => {
      if (avatar.objectUrl) {
        URL.revokeObjectURL(avatar.objectUrl);
      }
    };
  }, [avatar.objectUrl]);

  const handleAvatarChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    if (avatar.objectUrl) {
      URL.revokeObjectURL(avatar.objectUrl);
    }

    const nextUrl = URL.createObjectURL(file);
    setAvatar({
      file,
      previewUrl: nextUrl,
      objectUrl: nextUrl,
    });
  };

  const isDirty =
    name.trim() !== initialProfile.name ||
    Boolean(avatar.file);

  useEffect(() => {
    if (isDirty) {
      return;
    }

    setName(profile.name);
    setAvatar({
      ...emptyAvatarState,
      previewUrl: profile.avatar,
    });
    setInitialProfile(profile);
  }, [profile, isDirty]);

  const handleSubmit = async () => {
    if (!isDirty || isSaving) {
      return;
    }

    setIsSaving(true);

    try {
      let avatarDataUrl = initialProfile.avatar;
      if (avatar.file) {
        avatarDataUrl = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result as string);
          reader.onerror = () => reject(new Error("Gagal membaca file"));
          reader.readAsDataURL(avatar.file as File);
        });
      }

      const nextProfile = {
        ...initialProfile,
        name: name.trim() || initialProfile.name,
        whatsapp: initialProfile.whatsapp,
        avatar: avatarDataUrl ?? null,
      };

      saveProfile(nextProfile);
      setInitialProfile(nextProfile);
      setName(nextProfile.name);
      setAvatar({
        ...emptyAvatarState,
        previewUrl: nextProfile.avatar,
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div>
      <h1 className="text-4xl font-extrabold">Settings</h1>
      <p className="mt-2 text-neutral-600">
        Kelola profil dan informasi kontak yang ditampilkan di aplikasi.
      </p>

      <RevealOnScroll>
        <section className="mt-8 rounded-3xl bg-white/70 p-6 shadow-sm">
          <h2 className="text-xl font-semibold">Profil</h2>
          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[260px_1fr]">
            <div className="rounded-2xl bg-white p-5 shadow-sm">
              <div className="flex flex-col items-center text-center">
                <div className="h-28 w-28 overflow-hidden rounded-full bg-neutral-200">
                  {avatar.previewUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={avatar.previewUrl}
                      alt="Preview foto profil"
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center text-sm text-neutral-500">
                      Belum ada foto
                    </div>
                  )}
                </div>
                <div className="mt-4 text-base font-semibold">{name}</div>
                <div className="text-sm text-neutral-500">
                  {initialProfile.role}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-6">
              <div>
                <label className="text-sm font-semibold">
                  Ganti Foto Profil/Logo
                </label>
                <div className="mt-2 rounded-2xl border border-dashed border-neutral-200 bg-white px-4 py-6">
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleAvatarChange}
                    className="w-full text-sm text-neutral-600 file:mr-4 file:rounded-xl file:border-0 file:bg-neutral-900 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white"
                  />
                  <p className="mt-2 text-xs text-neutral-500">
                    Pilih gambar dari penyimpanan atau pengelola file perangkat.
                  </p>
                </div>
              </div>

              <div>
                <label className="text-sm font-semibold">Nama Lengkap</label>
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  className="mt-2 w-full rounded-2xl bg-white px-4 py-3 text-sm shadow-sm outline-none ring-1 ring-transparent focus:ring-[#F6C1C1]"
                />
              </div>

              {isDirty ? (
                <div className="flex items-center justify-end">
                  <button
                    type="button"
                    onClick={handleSubmit}
                    className="rounded-2xl bg-neutral-900 px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:translate-y-0.5"
                    disabled={isSaving}
                  >
                    {isSaving ? "Menyimpan..." : "Simpan Perubahan"}
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </section>
      </RevealOnScroll>

      <RevealOnScroll>
        <div className="mt-10">
          <WhatsAppBotPanel />
        </div>
      </RevealOnScroll>
    </div>
  );
}
