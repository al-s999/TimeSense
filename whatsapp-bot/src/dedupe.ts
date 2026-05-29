import Redis from "ioredis";
import { config } from "./config";

export interface DedupeStore {
  has(id: string): Promise<boolean>;
  mark(id: string): Promise<void>;
}

class MemoryDedupe implements DedupeStore {
  private readonly seen = new Map<string, number>();

  async has(id: string): Promise<boolean> {
    const now = Date.now();
    const expiresAt = this.seen.get(id);
    if (!expiresAt) return false;
    if (expiresAt <= now) {
      this.seen.delete(id);
      return false;
    }
    return true;
  }

  async mark(id: string): Promise<void> {
    const expiresAt = Date.now() + config.dedupeTtlSeconds * 1000;
    this.seen.set(id, expiresAt);
  }
}

class RedisDedupe implements DedupeStore {
  private readonly client: Redis;
  constructor(url: string) {
    this.client = new Redis(url);
  }

  async has(id: string): Promise<boolean> {
    const val = await this.client.get(this.key(id));
    return val === "1";
  }

  async mark(id: string): Promise<void> {
    await this.client.setex(this.key(id), config.dedupeTtlSeconds, "1");
  }

  private key(id: string) {
    return `dedupe:${id}`;
  }
}

export function createDedupeStore(): DedupeStore {
  if (config.redisUrl) {
    return new RedisDedupe(config.redisUrl);
  }
  return new MemoryDedupe();
}
