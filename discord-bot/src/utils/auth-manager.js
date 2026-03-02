// ============================================================
//  Authorization Manager
//  - Owner can .auth @user <duration>
//  - Tracks expiration, persists to JSON file
// ============================================================

const fs = require("fs");
const path = require("path");

const AUTH_FILE = path.join(__dirname, "..", "..", "data", "authorized.json");

// Ensure data directory exists
function ensureDataDir() {
  const dir = path.dirname(AUTH_FILE);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

function loadAuth() {
  ensureDataDir();
  if (!fs.existsSync(AUTH_FILE)) return {};
  try {
    return JSON.parse(fs.readFileSync(AUTH_FILE, "utf-8"));
  } catch {
    return {};
  }
}

function saveAuth(data) {
  ensureDataDir();
  fs.writeFileSync(AUTH_FILE, JSON.stringify(data, null, 2));
}

/**
 * Parse a human-readable duration string into milliseconds.
 * Supports: 30s, 5m, 2h, 1d, 7d, 1w, 1mo, forever/perm
 */
function parseDuration(str) {
  if (!str) return null;
  const s = str.trim().toLowerCase();
  if (s === "forever" || s === "perm" || s === "permanent") return Infinity;

  const match = s.match(/^(\d+)\s*(s|sec|m|min|h|hr|hour|d|day|w|week|mo|month)s?$/i);
  if (!match) return null;

  const n = parseInt(match[1], 10);
  const unit = match[2].toLowerCase();
  const multipliers = {
    s: 1000, sec: 1000,
    m: 60_000, min: 60_000,
    h: 3_600_000, hr: 3_600_000, hour: 3_600_000,
    d: 86_400_000, day: 86_400_000,
    w: 604_800_000, week: 604_800_000,
    mo: 2_592_000_000, month: 2_592_000_000,
  };
  const mult = multipliers[unit];
  return mult ? n * mult : null;
}

function formatDuration(ms) {
  if (ms === Infinity) return "Permanent";
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}

function formatExpiry(expiresAt) {
  if (expiresAt === Infinity || expiresAt === "Infinity") return "Never";
  return new Date(expiresAt).toUTCString();
}

class AuthManager {
  constructor() {
    this.data = loadAuth(); // { [userId]: { expiresAt: number|"Infinity", authorizedBy: string } }
  }

  authorize(userId, durationMs, authorizedBy) {
    const expiresAt = durationMs === Infinity ? "Infinity" : Date.now() + durationMs;
    this.data[userId] = { expiresAt, authorizedBy, authorizedAt: Date.now() };
    saveAuth(this.data);
  }

  deauthorize(userId) {
    delete this.data[userId];
    saveAuth(this.data);
  }

  isAuthorized(userId) {
    const entry = this.data[userId];
    if (!entry) return false;
    if (entry.expiresAt === "Infinity") return true;
    if (Date.now() < entry.expiresAt) return true;
    // Expired — clean up
    delete this.data[userId];
    saveAuth(this.data);
    return false;
  }

  getEntry(userId) {
    return this.data[userId] || null;
  }

  getAllAuthorized() {
    const now = Date.now();
    const active = [];
    for (const [userId, entry] of Object.entries(this.data)) {
      if (entry.expiresAt === "Infinity" || now < entry.expiresAt) {
        active.push({ userId, ...entry });
      }
    }
    return active;
  }
}

module.exports = { AuthManager, parseDuration, formatDuration, formatExpiry };
