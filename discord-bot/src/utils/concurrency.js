// ============================================================
//  Concurrency limiter — max N users running commands at once
// ============================================================

class ConcurrencyLimiter {
  constructor(maxConcurrent) {
    this.max = maxConcurrent;
    this.active = new Map(); // userId → commandName
  }

  acquire(userId, commandName) {
    if (this.active.has(userId)) return { ok: false, reason: "busy" };
    if (this.active.size >= this.max) return { ok: false, reason: "full" };
    this.active.set(userId, commandName);
    return { ok: true };
  }

  release(userId) {
    this.active.delete(userId);
  }

  getActiveCount() {
    return this.active.size;
  }

  isUserActive(userId) {
    return this.active.has(userId);
  }
}

module.exports = { ConcurrencyLimiter };
