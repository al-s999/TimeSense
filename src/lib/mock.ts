export type Activity = {
  id: string;
  dayDate: string;
  time: string;
  info: "Masuk" | "Keluar";
};

export type Notif = {
  id: string;
  type: "Information" | "Warning";
  message: string;
};

export const activities: Activity[] = [
  { id: "#1", dayDate: "Senin, 09 Januari 2026", time: "01.56", info: "Masuk" },
  { id: "#2", dayDate: "Senin, 09 Januari 2026", time: "18.56", info: "Keluar" },
];

export const notifs: Notif[] = [
  { id: "n1", type: "Information", message: "Anda telah masuk rumah waktu: 18:42 WIB" },
  { id: "n2", type: "Information", message: "Anda telah keluar rumah waktu: 07:15 WIB..." },
  { id: "n3", type: "Warning", message: "Orang tidak dikenal terdeteksi masuk rumah..." },
];
