"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.sendNotification = sendNotification;
const axios_1 = __importDefault(require("axios"));
const config_1 = require("./config");
function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}
async function sendNotification(event) {
    if (!config_1.config.pageNotificationUrl)
        return;
    const maxAttempts = 5;
    let attempt = 0;
    let delay = 400;
    while (attempt < maxAttempts) {
        attempt += 1;
        try {
            await axios_1.default.post(config_1.config.pageNotificationUrl, event, { timeout: 5000 });
            return;
        }
        catch (err) {
            if (attempt >= maxAttempts) {
                console.error("[NOTIFY] failed after retries:", err);
                return;
            }
            const jitter = Math.floor(Math.random() * 200);
            await sleep(delay + jitter);
            delay = Math.min(delay * 2, 4000);
        }
    }
}
