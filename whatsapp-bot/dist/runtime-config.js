"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.loadRuntimeConfig = loadRuntimeConfig;
exports.saveRuntimeConfig = saveRuntimeConfig;
exports.updateRuntimeConfig = updateRuntimeConfig;
exports.configSignature = configSignature;
const promises_1 = __importDefault(require("fs/promises"));
const path_1 = __importDefault(require("path"));
const config_1 = require("./config");
const CONFIG_PATH = path_1.default.resolve(process.cwd(), "runtime-config.json");
const defaultConfig = {
    ...config_1.config,
    updatedAt: "",
    lastNotificationId: 0,
    lastNotificationAt: "",
};
function coerceNumber(value, fallback) {
    if (typeof value === "number" && Number.isFinite(value))
        return value;
    if (typeof value === "string" && value.trim() !== "") {
        const parsed = Number(value);
        if (Number.isFinite(parsed))
            return parsed;
    }
    return fallback;
}
function coerceString(value, fallback) {
    return typeof value === "string" ? value : fallback;
}
function coerceBool(value, fallback) {
    if (typeof value === "boolean")
        return value;
    if (typeof value === "string")
        return (0, config_1.parseBool)(value);
    return fallback;
}
function sanitizeConfig(input) {
    const connectionType = (0, config_1.normalizeConnection)(coerceString(input.connectionType, defaultConfig.connectionType));
    return {
        ...defaultConfig,
        ...input,
        connectionType,
        pairingNumber: coerceString(input.pairingNumber, defaultConfig.pairingNumber),
        sessionDir: coerceString(input.sessionDir, defaultConfig.sessionDir),
        allowGroups: coerceBool(input.allowGroups, defaultConfig.allowGroups),
        ownerNumber: coerceString(input.ownerNumber, defaultConfig.ownerNumber),
        backendUrl: coerceString(input.backendUrl, defaultConfig.backendUrl),
        notificationPollMs: coerceNumber(input.notificationPollMs, defaultConfig.notificationPollMs),
        sendLatestOnStart: coerceBool(input.sendLatestOnStart, defaultConfig.sendLatestOnStart),
        botNumber: coerceString(input.botNumber, defaultConfig.botNumber ?? ""),
        updatedAt: coerceString(input.updatedAt, ""),
        lastNotificationId: coerceNumber(input.lastNotificationId, defaultConfig.lastNotificationId ?? 0),
        lastNotificationAt: coerceString(input.lastNotificationAt, defaultConfig.lastNotificationAt ?? ""),
    };
}
async function loadRuntimeConfig() {
    try {
        const raw = await promises_1.default.readFile(CONFIG_PATH, "utf-8");
        const parsed = JSON.parse(raw);
        return sanitizeConfig(parsed);
    }
    catch {
        return sanitizeConfig({});
    }
}
async function saveRuntimeConfig(nextConfig) {
    const sanitized = sanitizeConfig({
        ...nextConfig,
        updatedAt: new Date().toISOString(),
    });
    await promises_1.default.writeFile(CONFIG_PATH, JSON.stringify(sanitized, null, 2));
    return sanitized;
}
async function updateRuntimeConfig(partial) {
    const current = await loadRuntimeConfig();
    const merged = sanitizeConfig({
        ...current,
        ...partial,
        updatedAt: new Date().toISOString(),
    });
    await promises_1.default.writeFile(CONFIG_PATH, JSON.stringify(merged, null, 2));
    return merged;
}
function configSignature(cfg) {
    return JSON.stringify({
        connectionType: cfg.connectionType,
        pairingNumber: cfg.pairingNumber,
        sessionDir: cfg.sessionDir,
    });
}
