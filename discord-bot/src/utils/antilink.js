// Anti-link guard for a specific channel.
//   - Deletes messages from non-bypass users that contain links
//   - Whitelist persisted in data/antilink-whitelist.json
//
// Bypass list = OWNER_ID + entries in whitelist file.

const fs = require("fs");
const path = require("path");

const ANTI_LINK_CHANNEL_ID = "1467456493703008378";
const FILE = path.join(__dirname, "..", "..", "data", "antilink-whitelist.json");

const URL_RE = /(https?:\/\/[^\s]+|www\.[^\s]+|discord\.gg\/[^\s]+|\b[a-z0-9-]+\.(?:com|net|org|io|gg|xyz|me|tv|co|app|dev|store|shop|live|biz|info|cc|to)(?:\/\S*)?)/i;

function ensureDir() {
  const dir = path.dirname(FILE);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

function load() {
  try {
    ensureDir();
    if (!fs.existsSync(FILE)) return new Set();
    return new Set(JSON.parse(fs.readFileSync(FILE, "utf-8")));
  } catch { return new Set(); }
}

let whitelist = load();

function persist() {
  try {
    ensureDir();
    fs.writeFileSync(FILE, JSON.stringify([...whitelist], null, 2));
  } catch {}
}

function addWhitelist(userId) { whitelist.add(String(userId)); persist(); }
function removeWhitelist(userId) {
  const had = whitelist.delete(String(userId));
  if (had) persist();
  return had;
}
function isWhitelisted(userId) { return whitelist.has(String(userId)); }
function listWhitelist() { return [...whitelist]; }

function containsLink(text) {
  if (!text) return false;
  return URL_RE.test(text);
}

module.exports = {
  ANTI_LINK_CHANNEL_ID,
  containsLink,
  addWhitelist, removeWhitelist, isWhitelisted, listWhitelist,
};
