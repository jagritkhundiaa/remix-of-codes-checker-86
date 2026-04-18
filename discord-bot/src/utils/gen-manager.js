// Gen system — mirrors the Python xbox-checker-bot-py/gen_manager.py layout.
//   - Per-product stock files at data/gen/stock/<product>.txt
//   - Config + user state at data/gen/{config.json,users.json}
//
// User cooldown: 200s, max 1 per request.
// Admin: no cooldown, max 50 per request.

const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..", "data", "gen");
const STOCK_DIR = path.join(ROOT, "stock");
const USERS_FILE = path.join(ROOT, "users.json");
const CONFIG_FILE = path.join(ROOT, "config.json");

const USER_COOLDOWN_MS = 200 * 1000;
const USER_MAX_PER_REQUEST = 1;
const ADMIN_MAX_PER_REQUEST = 50;

function ensure() {
  if (!fs.existsSync(STOCK_DIR)) fs.mkdirSync(STOCK_DIR, { recursive: true });
}

function safeKey(name) {
  return String(name || "").toLowerCase().trim().replace(/[^a-z0-9_-]/g, "_");
}

function load(file, fallback) {
  try {
    if (!fs.existsSync(file)) return fallback;
    return JSON.parse(fs.readFileSync(file, "utf-8"));
  } catch { return fallback; }
}

function save(file, data) {
  ensure();
  fs.writeFileSync(file, JSON.stringify(data, null, 2));
}

let config = load(CONFIG_FILE, { products: [] });
config.products = config.products || [];
let users = load(USERS_FILE, {});

function persistConfig() { save(CONFIG_FILE, config); }
function persistUsers() { save(USERS_FILE, users); }

function listProducts() { return [...config.products]; }

function productExists(name) {
  return config.products.includes(safeKey(name));
}

function ensureProduct(name) {
  ensure();
  const key = safeKey(name);
  if (!config.products.includes(key)) {
    config.products.push(key);
    persistConfig();
  }
  const file = path.join(STOCK_DIR, `${key}.txt`);
  if (!fs.existsSync(file)) fs.writeFileSync(file, "");
  return key;
}

function getStock(name) {
  const key = safeKey(name);
  const file = path.join(STOCK_DIR, `${key}.txt`);
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, "utf-8")
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
}

function stockCount(name) { return getStock(name).length; }

function allStockCounts() {
  const out = {};
  for (const p of config.products) out[p] = stockCount(p);
  return out;
}

function appendStock(name, lines) {
  const key = ensureProduct(name);
  const clean = (lines || []).map((l) => String(l).trim()).filter(Boolean);
  if (clean.length === 0) return 0;
  const file = path.join(STOCK_DIR, `${key}.txt`);
  const existing = fs.existsSync(file) ? fs.readFileSync(file, "utf-8") : "";
  const sep = existing && !existing.endsWith("\n") ? "\n" : "";
  fs.appendFileSync(file, sep + clean.join("\n") + "\n");
  return clean.length;
}

function replaceStock(name, lines) {
  const key = ensureProduct(name);
  const clean = (lines || []).map((l) => String(l).trim()).filter(Boolean);
  const file = path.join(STOCK_DIR, `${key}.txt`);
  fs.writeFileSync(file, clean.join("\n") + (clean.length ? "\n" : ""));
  return clean.length;
}

function pullMany(name, count) {
  const key = safeKey(name);
  const file = path.join(STOCK_DIR, `${key}.txt`);
  if (!fs.existsSync(file)) return [];
  const lines = fs.readFileSync(file, "utf-8")
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length === 0) return [];
  const taken = lines.slice(0, count);
  const remaining = lines.slice(count);
  fs.writeFileSync(file, remaining.join("\n") + (remaining.length ? "\n" : ""));
  return taken;
}

function getStockFilePath(name) {
  return path.join(STOCK_DIR, `${safeKey(name)}.txt`);
}

// ── Cooldowns ────────────────────────────────────────────────

function _user(uid) {
  const k = String(uid);
  if (!users[k]) users[k] = { lastGen: 0, totalPulled: 0 };
  return users[k];
}

function cooldownRemainingMs(uid, isAdmin) {
  if (isAdmin) return 0;
  const u = _user(uid);
  const elapsed = Date.now() - (u.lastGen || 0);
  const left = USER_COOLDOWN_MS - elapsed;
  return left > 0 ? left : 0;
}

function recordGen(uid, count) {
  const u = _user(uid);
  u.lastGen = Date.now();
  u.totalPulled = (u.totalPulled || 0) + count;
  persistUsers();
}

function maxPerRequest(isAdmin) {
  return isAdmin ? ADMIN_MAX_PER_REQUEST : USER_MAX_PER_REQUEST;
}

ensure();

module.exports = {
  USER_COOLDOWN_MS, USER_MAX_PER_REQUEST, ADMIN_MAX_PER_REQUEST,
  listProducts, productExists, ensureProduct,
  getStock, stockCount, allStockCounts,
  appendStock, replaceStock, pullMany, getStockFilePath,
  cooldownRemainingMs, recordGen, maxPerRequest,
  safeKey,
};
