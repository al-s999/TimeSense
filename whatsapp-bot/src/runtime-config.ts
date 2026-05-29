import fs from "fs/promises";
import path from "path";
import { config as envConfig, normalizeConnection, parseBool } from "./config";

export type RuntimeConfig = typeof envConfig & {
  botNumber?: string;
  updatedAt?: string;
  lastNotificationId?: number;
  lastNotificationAt?: string;
};

const CONFIG_PATH = path.resolve(process.cwd(), "runtime-config.json");

const defaultConfig: RuntimeConfig = {
  ...envConfig,
  updatedAt: "",
  lastNotificationId: 0,
  lastNotificationAt: "",
};

function coerceNumber(value: unknown, fallback: number) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function coerceString(value: unknown, fallback: string) {
  return typeof value === "string" ? value : fallback;
}

function coerceBool(value: unknown, fallback: boolean) {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") return parseBool(value);
  return fallback;
}

function sanitizeConfig(input: Partial<RuntimeConfig>): RuntimeConfig {
  const connectionType = normalizeConnection(
    coerceString(input.connectionType, defaultConfig.connectionType)
  );
  return {
    ...defaultConfig,
    ...input,
    connectionType,
    pairingNumber: coerceString(input.pairingNumber, defaultConfig.pairingNumber),
    sessionDir: coerceString(input.sessionDir, defaultConfig.sessionDir),
    allowGroups: coerceBool(input.allowGroups, defaultConfig.allowGroups),
    ownerNumber: coerceString(input.ownerNumber, defaultConfig.ownerNumber),
    backendUrl: coerceString(input.backendUrl, defaultConfig.backendUrl),
    notificationPollMs: coerceNumber(
      input.notificationPollMs,
      defaultConfig.notificationPollMs
    ),
    sendLatestOnStart: coerceBool(
      input.sendLatestOnStart,
      defaultConfig.sendLatestOnStart
    ),
    botNumber: coerceString(input.botNumber, defaultConfig.botNumber ?? ""),
    updatedAt: coerceString(input.updatedAt, ""),
    lastNotificationId: coerceNumber(
      input.lastNotificationId,
      defaultConfig.lastNotificationId ?? 0
    ),
    lastNotificationAt: coerceString(
      input.lastNotificationAt,
      defaultConfig.lastNotificationAt ?? ""
    ),
  };
}

export async function loadRuntimeConfig(): Promise<RuntimeConfig> {
  try {
    const raw = await fs.readFile(CONFIG_PATH, "utf-8");
    const parsed = JSON.parse(raw) as Partial<RuntimeConfig>;
    return sanitizeConfig(parsed);
  } catch {
    return sanitizeConfig({});
  }
}

export async function saveRuntimeConfig(nextConfig: RuntimeConfig): Promise<RuntimeConfig> {
  const sanitized = sanitizeConfig({
    ...nextConfig,
    updatedAt: new Date().toISOString(),
  });
  await fs.writeFile(CONFIG_PATH, JSON.stringify(sanitized, null, 2));
  return sanitized;
}

export async function updateRuntimeConfig(
  partial: Partial<RuntimeConfig>
): Promise<RuntimeConfig> {
  const current = await loadRuntimeConfig();
  const merged = sanitizeConfig({
    ...current,
    ...partial,
    updatedAt: new Date().toISOString(),
  });
  await fs.writeFile(CONFIG_PATH, JSON.stringify(merged, null, 2));
  return merged;
}

export function configSignature(cfg: RuntimeConfig) {
  return JSON.stringify({
    connectionType: cfg.connectionType,
    pairingNumber: cfg.pairingNumber,
    sessionDir: cfg.sessionDir,
  });
}
