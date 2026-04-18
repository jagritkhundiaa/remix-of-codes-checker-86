// Persists user IDs that have already received the welcome DM.
const fs = require("fs");
const path = require("path");

const FILE = path.join(__dirname, "..", "..", "data", "welcomed.json");

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

function save(set) {
  try {
    ensureDir();
    fs.writeFileSync(FILE, JSON.stringify([...set]));
  } catch {}
}

const welcomed = load();

module.exports = {
  has: (id) => welcomed.has(String(id)),
  add: (id) => { welcomed.add(String(id)); save(welcomed); },
};
