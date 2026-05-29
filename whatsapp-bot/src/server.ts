import express from "express";
import path from "path";
import fs from "fs/promises";
import pino from "pino";
import qrcodeTerminal from "qrcode-terminal";
import QRCode from "qrcode";
import axios from "axios";
import { Boom } from "@hapi/boom";
import makeWASocket, {
  DisconnectReason,
  fetchLatestBaileysVersion,
  useMultiFileAuthState as createMultiFileAuthState,
} from "baileys";
import type { proto } from "baileys";
import { config as envConfig } from "./config";
import { createDedupeStore } from "./dedupe";
import { sendNotification } from "./notifications";
import {
  configSignature,
  loadRuntimeConfig,
  updateRuntimeConfig,
  type RuntimeConfig,
} from "./runtime-config";

type ConnectionState = "connecting" | "open" | "close";

type BackendEvent = {
  id: number;
  device_id: string;
  raw_event: string;
  predicted_label: string | null;
  confidence: number | null;
  server_received_at: string;
};

const app = express();
const dedupe = createDedupeStore();
const logger = pino({ level: "silent" });

let sock: ReturnType<typeof makeWASocket> | null = null;
let selfJid = "";
let connectionState: ConnectionState = "connecting";
let reconnecting = false;
let restarting = false;
let qrCount = 0;
let lastQr: string | null = null;
let lastPairingCode: string | null = null;

let runtimeConfig: RuntimeConfig | null = null;
let runtimeSignature = "";
let notificationTimer: NodeJS.Timeout | null = null;
let notificationSyncing = false;
let lastNotificationId = 0;
let lastNotificationAt = "";

app.use(express.json({ limit: "1mb" }));
app.use((_req, res, next) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (_req.method === "OPTIONS") {
    res.sendStatus(204);
    return;
  }
  next();
});

app.get("/health", (_req, res) => {
  res.json({
    ok: true,
    status: connectionState,
    self_jid: selfJid,
    connection: getConfig().connectionType,
  });
});

app.get("/config", (_req, res) => {
  res.json({ ok: true, config: toClientConfig(getConfig()) });
});

app.post("/config", async (req, res) => {
  try {
    const body = (req.body ?? {}) as Partial<RuntimeConfig>;
    const payload: Partial<RuntimeConfig> = {};

    if (typeof body.connectionType === "string") {
      payload.connectionType = body.connectionType;
    }
    if (typeof body.pairingNumber === "string") {
      payload.pairingNumber = body.pairingNumber.trim();
    }
    if (typeof body.ownerNumber === "string") {
      payload.ownerNumber = body.ownerNumber.trim();
    }
    if (typeof body.backendUrl === "string") {
      payload.backendUrl = body.backendUrl.trim();
    }
    if (typeof body.notificationPollMs !== "undefined") {
      payload.notificationPollMs = Number(body.notificationPollMs);
    }
    if (typeof body.sendLatestOnStart !== "undefined") {
      payload.sendLatestOnStart = Boolean(body.sendLatestOnStart);
    }

    const next = await updateRuntimeConfig(payload);
    runtimeConfig = next;
    if (typeof next.lastNotificationId === "number") {
      lastNotificationId = next.lastNotificationId;
    }
    if (typeof next.lastNotificationAt === "string") {
      lastNotificationAt = next.lastNotificationAt;
    }

    const nextSignature = configSignature(next);
    if (nextSignature !== runtimeSignature) {
      runtimeSignature = nextSignature;
      void restartSocket("config update");
    }

    restartNotificationLoop();

    res.json({ ok: true, config: toClientConfig(next) });
  } catch (err) {
    res.status(400).json({
      ok: false,
      error: err instanceof Error ? err.message : String(err),
    });
  }
});

app.post("/connect", async (_req, res) => {
  await restartSocket("manual connect");
  res.json({ ok: true });
});

app.get("/qr", async (_req, res) => {
  if (!lastQr) {
    res.status(404).json({ ok: false, error: "QR belum tersedia" });
    return;
  }
  try {
    const dataUrl = await QRCode.toDataURL(lastQr, { margin: 1, scale: 6 });
    res.json({ ok: true, qr: dataUrl });
  } catch (err) {
    res.status(500).json({
      ok: false,
      error: err instanceof Error ? err.message : String(err),
    });
  }
});

app.get("/pairing", (_req, res) => {
  if (!lastPairingCode) {
    res.status(404).json({ ok: false, error: "Pairing code belum tersedia" });
    return;
  }
  res.json({ ok: true, code: lastPairingCode });
});

app.post("/sync", async (_req, res) => {
  await syncNotifications("manual");
  res.json({ ok: true, lastNotificationId, lastNotificationAt });
});

app.post("/logout", async (_req, res) => {
  await logoutAndReset();
  res.json({ ok: true });
});

void bootstrap();

async function bootstrap() {
  runtimeConfig = await loadRuntimeConfig();
  runtimeSignature = configSignature(runtimeConfig);
  lastNotificationId = runtimeConfig.lastNotificationId ?? 0;
  lastNotificationAt = runtimeConfig.lastNotificationAt ?? "";

  app.listen(envConfig.port, () => {
    console.log(`[WA] bot listening on :${envConfig.port}`);
  });

  await startSocket();
  restartNotificationLoop();
}

function getConfig(): RuntimeConfig {
  const base =
    runtimeConfig ?? ({
      ...envConfig,
      botNumber: envConfig.botNumber ?? "",
      updatedAt: "",
      lastNotificationId: 0,
      lastNotificationAt: "",
    } as RuntimeConfig);

  if (envConfig.botNumber) {
    return {
      ...base,
      botNumber: envConfig.botNumber,
    };
  }

  return base;
}

function toClientConfig(cfg: RuntimeConfig) {
  return {
    connectionType: cfg.connectionType,
    pairingNumber: cfg.pairingNumber,
    ownerNumber: cfg.ownerNumber,
    backendUrl: cfg.backendUrl,
    notificationPollMs: cfg.notificationPollMs,
    sendLatestOnStart: cfg.sendLatestOnStart,
    botNumber: cfg.botNumber ?? "",
    lastNotificationId: cfg.lastNotificationId ?? 0,
    lastNotificationAt: cfg.lastNotificationAt ?? "",
  };
}

async function startSocket() {
  const cfg = getConfig();
  const sessionDir = path.resolve(cfg.sessionDir);
  const { state, saveCreds } = await createMultiFileAuthState(sessionDir);
  const { version } = await fetchLatestBaileysVersion();

  const nextSock = makeWASocket({
    version,
    logger,
    printQRInTerminal: false,
    auth: state,
    browser: ["Time Sense", "Chrome", "1.0.0"],
  });

  sock = nextSock;
  connectionState = "connecting";

  nextSock.ev.on("creds.update", saveCreds);

  nextSock.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr && cfg.connectionType === "qr") {
      qrCount += 1;
      lastQr = qr;
      if (!cfg.disableTerminalQr) {
        qrcodeTerminal.generate(qr, { small: true });
      }
      console.log(`[WA] Scan QR di WhatsApp (percobaan ${qrCount}/5).`);
      if (qrCount >= 5) {
        console.error("[WA] Terlalu banyak percobaan QR. Hentikan proses.");
        process.exit(1);
      }
    }

    if (connection === "open") {
      connectionState = "open";
      qrCount = 0;
      selfJid = nextSock.user?.id ?? "";
      lastQr = null;
      lastPairingCode = null;
      console.log(`[WA] connected as ${selfJid || "unknown"}`);

      const botNumber = extractNumberFromJid(selfJid);
      if (botNumber && !envConfig.botNumber && runtimeConfig?.botNumber !== botNumber) {
        runtimeConfig = {
          ...getConfig(),
          botNumber,
        };
        void updateRuntimeConfig({ botNumber });
      }

      void syncNotifications("initial");
    }

    if (connection === "close") {
      connectionState = "close";
      const statusCode = new Boom(lastDisconnect?.error)?.output?.statusCode;

      if (statusCode === DisconnectReason.loggedOut) {
        console.error("[WA] Logged out. Hapus session dan login ulang.");
        return;
      }

      if (!reconnecting) {
        reconnecting = true;
        setTimeout(async () => {
          reconnecting = false;
          try {
            await startSocket();
          } catch (err) {
            console.error("[WA] Reconnect failed:", err);
          }
        }, 1000);
      }
    }
  });

  nextSock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    for (const msg of messages) {
      const remoteJid = msg.key.remoteJid;
      if (!remoteJid) continue;
      if (msg.key.fromMe) continue;
      if (!cfg.allowGroups && remoteJid.endsWith("@g.us")) continue;

      const messageId = msg.key.id;
      if (!messageId || (await dedupe.has(messageId))) continue;
      await dedupe.mark(messageId);

      const text = extractText(msg.message).trim();
      if (!text) continue;

      const fromJid = msg.key.participant ?? remoteJid;

      await sendNotification({
        event: "incoming_message",
        timestamp: new Date().toISOString(),
        wa_from: fromJid,
        wa_to: selfJid,
        message_id: messageId,
        text,
      });

      const reply = await buildReply(text);

      try {
        await sendTyping(remoteJid, true);
        await sleep(randomInt(cfg.typingMinMs, cfg.typingMaxMs));
        const sent = await nextSock.sendMessage(remoteJid, { text: reply });
        await sendTyping(remoteJid, false);

        await sendNotification({
          event: "bot_reply",
          timestamp: new Date().toISOString(),
          wa_from: fromJid,
          wa_to: selfJid,
          message_id: sent?.key?.id ?? undefined,
          text: reply,
        });
      } catch (err) {
        console.error("[WA] reply failed:", err);
      }
    }
  });

  if (!nextSock.authState.creds.registered && cfg.connectionType === "pairing") {
    if (!cfg.pairingNumber) {
      throw new Error("WA_PAIRING_NUMBER wajib diisi saat WA_CONNECTION=pairing.");
    }
    const requestPairingCode = (
      nextSock as unknown as {
        requestPairingCode?: (phoneNumber: string) => Promise<string>;
      }
    ).requestPairingCode;
    if (!requestPairingCode) {
      throw new Error("Baileys tidak mendukung pairing code pada versi ini.");
    }
    const code = await requestPairingCode(cfg.pairingNumber.trim());
    const formatted = formatPairingCode(code);
    lastPairingCode = formatted;
    console.log(`[WA] Pairing code: ${formatted}`);
  }
}

async function restartSocket(reason: string) {
  if (restarting) return;
  restarting = true;
  reconnecting = true;

  try {
    if (sock) {
      try {
        sock.end(new Error(`restart: ${reason}`));
      } catch {
        // ignore
      }
    }

    sock = null;
    connectionState = "connecting";
    selfJid = "";
    qrCount = 0;
    lastQr = null;
    lastPairingCode = null;

    await startSocket();
  } finally {
    reconnecting = false;
    restarting = false;
  }
}

async function logoutAndReset() {
  if (restarting) return;
  restarting = true;
  reconnecting = true;

  try {
    if (sock) {
      const maybeLogout = (sock as unknown as { logout?: () => Promise<void> }).logout;
      if (maybeLogout) {
        try {
          await maybeLogout();
        } catch {
          // ignore logout errors
        }
      }
      try {
        sock.end(new Error("logout"));
      } catch {
        // ignore
      }
    }

    sock = null;
    connectionState = "close";
    selfJid = "";
    qrCount = 0;
    lastQr = null;
    lastPairingCode = null;

    const sessionDir = path.resolve(getConfig().sessionDir);
    try {
      await fs.rm(sessionDir, { recursive: true, force: true });
    } catch {
      // ignore session cleanup errors
    }

    runtimeConfig = {
      ...getConfig(),
      botNumber: envConfig.botNumber ?? "",
    };
    void updateRuntimeConfig({ botNumber: runtimeConfig.botNumber ?? "" });
  } finally {
    reconnecting = false;
    restarting = false;
  }
}

function restartNotificationLoop() {
  if (notificationTimer) {
    clearInterval(notificationTimer);
    notificationTimer = null;
  }

  const cfg = getConfig();
  if (!cfg.backendUrl || !cfg.ownerNumber) return;

  const interval = Math.max(cfg.notificationPollMs, 2000);
  notificationTimer = setInterval(() => {
    void syncNotifications("poll");
  }, interval);
}

async function syncNotifications(mode: "initial" | "poll" | "manual") {
  if (notificationSyncing) return;
  notificationSyncing = true;

  try {
    const cfg = getConfig();
    if (!sock || connectionState !== "open") return;

    const ownerJid = toOwnerJid(cfg.ownerNumber);
    if (!ownerJid || !cfg.backendUrl) return;

    const base = trimBaseUrl(cfg.backendUrl);
    const limit = mode === "poll" ? 10 : 1;
    const res = await axios.get<BackendEvent[]>(`${base}/api/notifications?limit=${limit}`,
      { timeout: 5000 }
    );
    const events = Array.isArray(res.data) ? res.data : [];
    if (events.length === 0) return;

    const latest = events[0];

    if (lastNotificationId === 0) {
      if (mode === "poll" && !cfg.sendLatestOnStart) {
        lastNotificationId = latest.id;
        lastNotificationAt = latest.server_received_at;
        persistNotificationState();
        return;
      }
      if (latest.id > lastNotificationId) {
        await sendOwnerNotification(latest);
      }
      return;
    }

    if (mode === "initial") {
      if (cfg.sendLatestOnStart && latest.id > lastNotificationId) {
        await sendOwnerNotification(latest);
      }
      return;
    }

    if (mode === "manual") {
      if (latest.id > lastNotificationId) {
        await sendOwnerNotification(latest);
      }
      return;
    }

    const pending = events.filter((evt) => evt.id > lastNotificationId);
    if (pending.length === 0) return;
    pending.sort((a, b) => a.id - b.id);

    for (const evt of pending) {
      await sendOwnerNotification(evt);
    }
  } catch (err) {
    console.error("[WA] sync notifications failed:", err);
  } finally {
    notificationSyncing = false;
  }
}

async function sendOwnerNotification(event: BackendEvent) {
  if (!sock) return;

  const cfg = getConfig();
  const ownerJid = toOwnerJid(cfg.ownerNumber);
  if (!ownerJid) return;

  const text = formatNotificationMessage(event);
  await sock.sendMessage(ownerJid, { text });

  lastNotificationId = Math.max(lastNotificationId, event.id);
  lastNotificationAt = event.server_received_at;
  persistNotificationState();
}

function persistNotificationState() {
  runtimeConfig = {
    ...getConfig(),
    lastNotificationId,
    lastNotificationAt,
  };
  void updateRuntimeConfig({ lastNotificationId, lastNotificationAt });
}

function toOwnerJid(number: string): string {
  const digits = number.replace(/\D/g, "");
  if (!digits) return "";
  return `${digits}@s.whatsapp.net`;
}

function trimBaseUrl(url: string): string {
  return url.replace(/\/+$/, "");
}

function formatNotificationMessage(event: BackendEvent): string {
  const message = mapNotificationMessage(event.predicted_label, event.raw_event);
  const time = formatTime(event.server_received_at);

  return [
    "Notifikasi Time Sense",
    message,
    `Waktu: ${time}`,
    `Device: ${event.device_id}`,
  ].join("\n");
}

const semanticEventKeys = new Set([
  "SAYA_MASUK",
  "TEMAN_MASUK",
  "ORANG_MASUK",
  "SAYA_KELUAR",
  "TEMAN_KELUAR",
  "ORANG_KELUAR",
]);

function getEventKey(label: string | null, raw: string): string {
  const rawKey = (raw ?? "").toUpperCase();
  if (semanticEventKeys.has(rawKey)) return rawKey;
  return (label ?? raw ?? "").toUpperCase();
}

function mapNotificationMessage(label: string | null, raw: string): string {
  const key = getEventKey(label, raw);
  switch (key) {
    case "SAYA_MASUK": return "Saya masuk";
    case "TEMAN_MASUK": return "Teman masuk";
    case "ORANG_MASUK": return "Orang tidak dikenal masuk";
    case "SAYA_KELUAR": return "Saya keluar";
    case "TEMAN_KELUAR": return "Teman keluar";
    case "ORANG_KELUAR": return "Orang tidak dikenal keluar";
    case "ANDA_PERGI": return "Anda pergi";
    case "ANDA_PULANG": return "Anda pulang";
    case "ME_MASUK":
    case "ME": return "Saya masuk";
    case "ME_KELUAR": return "Saya keluar";
    case "SOMEONE":
    case "SOMEONE_MASUK": return "Orang tidak dikenal masuk";
    case "SOMEONE_KELUAR": return "Orang tidak dikenal keluar";
    default:
      if (key.endsWith("_MASUK")) {
        let name = key.replace("_MASUK", "");
        if (name === "SOMEONE") return "Orang tidak dikenal masuk";
        return `${name} masuk`;
      }
      if (key.endsWith("_KELUAR")) {
        let name = key.replace("_KELUAR", "");
        if (name === "SOMEONE") return "Orang tidak dikenal keluar";
        return `${name} keluar`;
      }
      return label ?? raw;
  }
}

function formatTime(iso: string): string {
  return iso.replace("T", " ").split(".")[0];
}

function extractNumberFromJid(jid: string): string {
  if (!jid) return "";
  const beforeAt = jid.split("@")[0] ?? "";
  const withoutDevice = beforeAt.split(":")[0] ?? beforeAt;
  return withoutDevice.replace(/\D/g, "");
}

function extractText(message?: proto.IMessage | null): string {
  const msg = unwrapMessage(message ?? undefined);
  if (!msg) return "";
  return (
    msg.conversation ||
    msg.extendedTextMessage?.text ||
    msg.imageMessage?.caption ||
    msg.videoMessage?.caption ||
    ""
  );
}

function unwrapMessage(message?: proto.IMessage): proto.IMessage | undefined {
  if (!message) return undefined;
  if (message.ephemeralMessage?.message) {
    return unwrapMessage(message.ephemeralMessage.message);
  }
  if (message.viewOnceMessage?.message) {
    return unwrapMessage(message.viewOnceMessage.message);
  }
  if (message.viewOnceMessageV2?.message) {
    return unwrapMessage(message.viewOnceMessageV2.message);
  }
  return message;
}

const HELP_MESSAGE = [
  "🚪 *Smart Door Bot*",
  "",
  "Perintah yang tersedia:",
  "• *buka pintu* / *open* — Buka pintu",
  "• *tutup pintu* / *close* — Tutup pintu",
  "• *status* — Cek status pintu & sensor",
  "• *aktifkan* / *enable* — Aktifkan sistem",
  "• *matikan* / *disable* — Nonaktifkan sistem",
  "• *help* / *bantuan* — Tampilkan pesan ini",
].join("\n");

async function sendBackendCommand(action: string): Promise<string> {
  const cfg = getConfig();
  if (!cfg.backendUrl) return "❌ Backend URL belum dikonfigurasi";
  const base = trimBaseUrl(cfg.backendUrl);
  try {
    const res = await axios.post(
      `${base}/api/command/execute`,
      { device_id: "esp32-1", action, requester: "wa_bot" },
      { timeout: 5000 }
    );
    if (res.data?.ok) return `✅ Perintah *${action}* berhasil dikirim`;
    return `⚠️ ${res.data?.error || res.data?.reason || "Gagal"}`;
  } catch (err) {
    console.error("[WA] sendBackendCommand failed:", err);
    return "❌ Gagal mengirim perintah ke backend";
  }
}

async function getBackendDoorStatus(): Promise<string> {
  const cfg = getConfig();
  if (!cfg.backendUrl) return "❌ Backend URL belum dikonfigurasi";
  const base = trimBaseUrl(cfg.backendUrl);
  try {
    const res = await axios.get(`${base}/api/door/status`, { timeout: 5000 });
    const d = res.data;
    const lines = [
      "🚪 *Status Smart Door*",
      "",
      `Pintu: ${d.door_open ? "🟢 TERBUKA" : "🔴 TERTUTUP"}`,
      `Sistem: ${d.system_enabled !== false ? "✅ Aktif" : "⚠️ Nonaktif"}`,
      `Identitas: ${d.last_identity || "-"}`,
      `Akses: ${d.access_granted ? "✅ Granted" : "❌ Denied"}`,
    ];
    if (d.sensor) {
      lines.push(`Sensor 1: ${d.sensor.distance1 ?? 0} cm`);
      lines.push(`Sensor 2: ${d.sensor.distance2 ?? 0} cm`);
    }
    if (d.last_open_at) lines.push(`Terakhir buka: ${formatTime(d.last_open_at)}`);
    if (d.last_close_at) lines.push(`Terakhir tutup: ${formatTime(d.last_close_at)}`);
    return lines.join("\n");
  } catch (err) {
    console.error("[WA] getBackendDoorStatus failed:", err);
    return "❌ Gagal mengambil status dari backend";
  }
}

async function buildReply(text: string): Promise<string> {
  const lower = text.toLowerCase().trim();

  if (lower === "buka pintu" || lower === "buka" || lower === "open")
    return sendBackendCommand("open_door");
  if (lower === "tutup pintu" || lower === "tutup" || lower === "close")
    return sendBackendCommand("close_door");
  if (lower === "status" || lower === "cek")
    return getBackendDoorStatus();
  if (lower === "matikan" || lower === "disable" || lower === "off")
    return sendBackendCommand("disable");
  if (lower === "aktifkan" || lower === "enable" || lower === "on")
    return sendBackendCommand("enable");
  if (lower === "help" || lower === "bantuan" || lower === "?")
    return HELP_MESSAGE;
  if (lower.includes("halo") || lower.includes("hi"))
    return "Halo! Ketik *help* untuk melihat perintah.";

  return `Perintah tidak dikenali: "${text}"\nKetik *help* untuk bantuan.`;
}

async function sendTyping(jid: string, on: boolean) {
  if (!sock) return;
  const presence = on ? "composing" : "paused";
  try {
    await sock.sendPresenceUpdate(presence, jid);
  } catch {
    // ignore typing errors
  }
}

function formatPairingCode(code: string): string {
  const groups = code.match(/.{1,4}/g);
  return groups ? groups.join("-") : code;
}

function randomInt(min: number, max: number) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
