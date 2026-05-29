"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.createDedupeStore = createDedupeStore;
const ioredis_1 = __importDefault(require("ioredis"));
const config_1 = require("./config");
class MemoryDedupe {
    seen = new Map();
    async has(id) {
        const now = Date.now();
        const expiresAt = this.seen.get(id);
        if (!expiresAt)
            return false;
        if (expiresAt <= now) {
            this.seen.delete(id);
            return false;
        }
        return true;
    }
    async mark(id) {
        const expiresAt = Date.now() + config_1.config.dedupeTtlSeconds * 1000;
        this.seen.set(id, expiresAt);
    }
}
class RedisDedupe {
    client;
    constructor(url) {
        this.client = new ioredis_1.default(url);
    }
    async has(id) {
        const val = await this.client.get(this.key(id));
        return val === "1";
    }
    async mark(id) {
        await this.client.setex(this.key(id), config_1.config.dedupeTtlSeconds, "1");
    }
    key(id) {
        return `dedupe:${id}`;
    }
}
function createDedupeStore() {
    if (config_1.config.redisUrl) {
        return new RedisDedupe(config_1.config.redisUrl);
    }
    return new MemoryDedupe();
}
