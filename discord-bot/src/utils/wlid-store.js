// ============================================================
//  WLID Storage — persistent WLID tokens set via .wlidset
// ============================================================

const fs = require("fs");
const path = require("path");

const WLID_FILE = path.join(__dirname, "..", "..", "data", "wlids.json");

function ensureDataDir() {
  const dir = path.dirname(WLID_FILE);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

function loadWlids() {
  ensureDataDir();
  if (!fs.existsSync(WLID_FILE)) return [];
  try {
    return JSON.parse(fs.readFileSync(WLID_FILE, "utf-8"));
  } catch {
    return [];
  }
}

function saveWlids(wlids) {
  ensureDataDir();
  fs.writeFileSync(WLID_FILE, JSON.stringify(wlids, null, 2));
}

function setWlids(wlids) {
  saveWlids(wlids);
}

function getWlids() {
  return loadWlids();
}

function getWlidCount() {
  return loadWlids().length;
}

module.exports = { setWlids, getWlids, getWlidCount };
