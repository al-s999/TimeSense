import axios from "axios";
import { config } from "./config";

export type NotificationEvent = {
  event: "incoming_message" | "bot_reply";
  timestamp: string;
  wa_from: string;
  wa_to: string;
  message_id?: string;
  text: string;
  meta?: Record<string, unknown>;
};

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function sendNotification(event: NotificationEvent): Promise<void> {
  if (!config.pageNotificationUrl) return;

  const maxAttempts = 5;
  let attempt = 0;
  let delay = 400;

  while (attempt < maxAttempts) {
    attempt += 1;
    try {
      await axios.post(config.pageNotificationUrl, event, { timeout: 5000 });
      return;
    } catch (err) {
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
