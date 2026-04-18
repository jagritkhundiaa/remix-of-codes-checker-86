// Extracts only valid email:password pairs from arbitrary text.
// Tolerates extra fields (e.g. "url|email|pass|extra"), prefixes/suffixes,
// and common separators.
//
// extractCombos(text) -> string[]   "email:password" entries (deduped, lowercased email)

const EMAIL_RE = /([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})/i;

function _splitFields(line) {
  // Try each common delimiter; keep only fields with content
  const seps = [":", "|", ";", "\t", " - ", ",", " "];
  for (const s of seps) {
    if (line.includes(s)) {
      return line.split(s).map((p) => p.trim()).filter(Boolean);
    }
  }
  return [line];
}

function extractOne(rawLine) {
  if (!rawLine) return null;
  const line = rawLine.replace(/^\uFEFF/, "").trim();
  if (!line) return null;

  const m = line.match(EMAIL_RE);
  if (!m) return null;
  const email = m[1].toLowerCase();

  const fields = _splitFields(line);
  // Find email index, password is the next non-empty, non-email field
  let pwd = null;
  for (let i = 0; i < fields.length; i++) {
    if (fields[i].toLowerCase() === email) {
      // candidate after
      for (let j = i + 1; j < fields.length; j++) {
        const cand = fields[j];
        if (!cand) continue;
        if (EMAIL_RE.test(cand)) continue;
        // skip pure URL fields
        if (/^https?:\/\//i.test(cand)) continue;
        pwd = cand;
        break;
      }
      if (pwd) break;
    }
  }

  // Fallback: if we never found email as a standalone field, try matching after :
  if (!pwd) {
    const idx = line.toLowerCase().indexOf(email);
    if (idx !== -1) {
      let tail = line.slice(idx + email.length);
      tail = tail.replace(/^[\s:|;,\-\t]+/, "");
      if (tail) {
        const next = tail.split(/[\s|;, \t]/)[0];
        if (next && !EMAIL_RE.test(next) && !/^https?:\/\//i.test(next)) pwd = next;
      }
    }
  }

  if (!pwd) return null;
  if (pwd.length < 2 || pwd.length > 256) return null;
  return `${email}:${pwd}`;
}

function extractCombos(text, { max = Infinity } = {}) {
  if (!text) return [];
  const out = [];
  const seen = new Set();
  const lines = String(text).split(/\r?\n/);
  for (const line of lines) {
    if (out.length >= max) break;
    const combo = extractOne(line);
    if (!combo) continue;
    if (seen.has(combo)) continue;
    seen.add(combo);
    out.push(combo);
  }
  return out;
}

module.exports = { extractCombos, extractOne };
