"use client";

import { useEffect, useState } from "react";

export type ProfileData = {
  name: string;
  whatsapp: string;
  avatar: string | null;
  role: string;
};

const DEFAULT_PROFILE: ProfileData = {
  name: "A. Rosyid",
  whatsapp: "+62 812 3456 7890",
  avatar: null,
  role: "Pengguna",
};

const STORAGE_KEY = "time-sense.profile";

export function getStoredProfile(): ProfileData {
  if (typeof window === "undefined") {
    return DEFAULT_PROFILE;
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return DEFAULT_PROFILE;
    }
    const parsed = JSON.parse(raw) as Partial<ProfileData>;
    return {
      name: parsed.name ?? DEFAULT_PROFILE.name,
      whatsapp: parsed.whatsapp ?? DEFAULT_PROFILE.whatsapp,
      avatar: parsed.avatar ?? DEFAULT_PROFILE.avatar,
      role: parsed.role ?? DEFAULT_PROFILE.role,
    };
  } catch {
    return DEFAULT_PROFILE;
  }
}

export function saveProfile(nextProfile: ProfileData) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(nextProfile));
  window.dispatchEvent(new Event("profile-updated"));
}

export function subscribeProfile(callback: (profile: ProfileData) => void) {
  if (typeof window === "undefined") {
    return () => {};
  }

  const handler = () => callback(getStoredProfile());
  window.addEventListener("profile-updated", handler);
  window.addEventListener("storage", handler);
  return () => {
    window.removeEventListener("profile-updated", handler);
    window.removeEventListener("storage", handler);
  };
}

export function useProfile() {
  const [profile, setProfile] = useState<ProfileData>(DEFAULT_PROFILE);

  useEffect(() => {
    setProfile(getStoredProfile());
    return subscribeProfile(setProfile);
  }, []);

  return profile;
}
