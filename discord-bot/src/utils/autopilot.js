// Autopilot access system.
//   - Unauthorized users are prompted to reply "milk"
//   - Replying "milk" grants 10 days of access (autopilot_grants.json)
//   - Owner can toggle the whole system off (.autopilotoff)
//
// State lives in data/autopilot.json:
//   { enabled: bool, grants: { [userId]: expiryMs }, prompted: [userId,...] }

const fs = require("fs");
const path = require("path");

const FILE = path.join(__dirname, "..", "..", "data", "autopilot.json");
const TEN_DAYS = 10 * 24 * 60 * 60 * 1000;

function ensureDir() {
  const dir = path.dirname(FILE);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

function load() {
  try {
    ensureDir();
    if (!fs.existsSync(FILE)) return { enabled: true, grants: {}, prompted: [] };
    const raw = JSON.parse(fs.readFileSync(FILE, "utf-8"));
    return {
      enabled: raw.enabled !== false,
      grants: raw.grants || {},
      prompted: raw.prompted || [],
    };
  } catch {
    return { enabled: true, grants: {}, prompted: [] };
  }
}

let state = load();

function persist() {
  try {
    ensureDir();
    fs.writeFileSync(FILE, JSON.stringify(state, null, 2));
  } catch {}
}

function isEnabled() { return state.enabled; }

function setEnabled(v) {
  state.enabled = !!v;
  persist();
}

function isGranted(userId) {
  if (!state.enabled) return false;
  const exp = state.grants[String(userId)];
  if (!exp) return false;
  if (Date.now() > exp) {
    delete state.grants[String(userId)];
    persist();
    return false;
  }
  return true;
}

function grant(userId, ms = TEN_DAYS) {
  state.grants[String(userId)] = Date.now() + ms;
  persist();
  return state.grants[String(userId)];
}

function getExpiry(userId) {
  return state.grants[String(userId)] || null;
}

function listGrants() {
  const now = Date.now();
  return Object.entries(state.grants)
    .filter(([, exp]) => exp > now)
    .map(([userId, exp]) => ({ userId, expiresAt: exp }));
}

function wasPrompted(userId) {
  return state.prompted.includes(String(userId));
}

function markPrompted(userId) {
  if (!wasPrompted(userId)) {
    state.prompted.push(String(userId));
    persist();
  }
}

function clearPrompted(userId) {
  state.prompted = state.prompted.filter((id) => id !== String(userId));
  persist();
}

module.exports = {
  isEnabled, setEnabled,
  isGranted, grant, getExpiry, listGrants,
  wasPrompted, markPrompted, clearPrompted,
  TEN_DAYS,
};
