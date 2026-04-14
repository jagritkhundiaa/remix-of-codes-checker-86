# ═══════════════════════════════════════════════
#  Hijra Scraper — CC Detection & Filters
# ═══════════════════════════════════════════════

import re
from typing import List, Optional

# ── CC pattern: 16 digits with separators, month, year, cvv ──
CC_PATTERNS = [
    # Full CC with separators: 4111111111111111|12|2025|123
    re.compile(
        r'(\d{15,16})\s*[\|/]\s*(\d{1,2})\s*[\|/]\s*(\d{2,4})\s*[\|/]\s*(\d{3,4})'
    ),
    # With spaces or dashes in card number
    re.compile(
        r'(\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{3,4})\s*[\|/]\s*(\d{1,2})\s*[\|/]\s*(\d{2,4})\s*[\|/]\s*(\d{3,4})'
    ),
]


def extract_ccs(text: str) -> List[dict]:
    """Extract all CC entries from text. Returns list of {cc, month, year, cvv, raw}."""
    results = []
    seen = set()
    for pattern in CC_PATTERNS:
        for match in pattern.finditer(text):
            card = re.sub(r'[\s\-]', '', match.group(1))
            month = match.group(2).zfill(2)
            year = match.group(3)
            cvv = match.group(4)
            # Normalize year
            if len(year) == 2:
                year = "20" + year
            raw = f"{card}|{month}|{year}|{cvv}"
            if raw not in seen:
                seen.add(raw)
                results.append({
                    "cc": card,
                    "month": month,
                    "year": year,
                    "cvv": cvv,
                    "raw": raw,
                    "bin": card[:6],
                })
    return results


def mask_cc(card: str) -> str:
    """Mask middle digits: 411111**1111"""
    if len(card) < 10:
        return card
    return card[:6] + "**" + card[-4:]


def matches_keywords(text: str, keywords: List[str]) -> bool:
    """Check if text contains any keyword."""
    lower = text.lower()
    return any(kw.lower() in lower for kw in keywords)


def matches_regex(text: str, pattern: str) -> bool:
    """Check if text matches a regex pattern."""
    try:
        return bool(re.search(pattern, text, re.IGNORECASE))
    except re.error:
        return False


def should_forward(text: str, keywords: List[str], custom_filters: List[dict]) -> tuple:
    """
    Determine if a message should be forwarded.
    Returns (should_forward: bool, ccs: list, reason: str)
    """
    # 1. Check for CC patterns (primary filter)
    ccs = extract_ccs(text)
    if ccs:
        return True, ccs, "cc_pattern"

    # 2. Check custom regex filters
    for f in custom_filters:
        if f["type"] == "regex" and matches_regex(text, f["pattern"]):
            return True, [], f"regex:{f['pattern']}"

    # 3. Check keywords
    if matches_keywords(text, keywords):
        return True, [], "keyword"

    return False, [], ""
