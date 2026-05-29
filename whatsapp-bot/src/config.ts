import dotenv from "dotenv";

dotenv.config();

export type ConnectionType = "qr" | "pairing";

export function normalizeConnection(value: string | undefined): ConnectionType {
  const raw = (value ?? "qr").toLowerCase().trim();
  if (raw === "qr" || raw === "pairing") return raw;
  throw new Error(`Invalid WA_CONNECTION value: "${value}". Use "qr" or "pairing".`);
}

export function parseBool(value: string | undefined): boolean {
  if (!value) return false;
  const v = value.toLowerCase().trim();
  return v === "1" || v === "true" || v === "yes" || v === "on";
}

export const config = {
  port: Number(process.env.PORT ?? 3001),
  pageNotificationUrl: process.env.PAGE_NOTIFICATION_URL ?? "",
  typingMinMs: Number(process.env.TYPING_MIN_MS ?? 800),
  typingMaxMs: Number(process.env.TYPING_MAX_MS ?? 1500),
  dedupeTtlSeconds: Number(process.env.DEDUPE_TTL_SECONDS ?? 600),
  redisUrl: process.env.REDIS_URL ?? "",
  connectionType: normalizeConnection(process.env.WA_CONNECTION),
  pairingNumber: process.env.WA_PAIRING_NUMBER ?? "",
  sessionDir: process.env.WA_SESSION_DIR ?? "wa-session",
  allowGroups: parseBool(process.env.WA_ALLOW_GROUPS),
  disableTerminalQr: parseBool(process.env.WA_DISABLE_TERMINAL_QR),
  botNumber: process.env.WA_BOT_NUMBER ?? "",
  ownerNumber: process.env.WA_OWNER_NUMBER ?? "",
  backendUrl: process.env.WA_BACKEND_URL ?? "http://localhost:8000",
  notificationPollMs: Number(process.env.WA_NOTIFICATION_POLL_MS ?? 8000),
  sendLatestOnStart: parseBool(process.env.WA_SEND_LATEST_ON_START ?? "true"),
};
