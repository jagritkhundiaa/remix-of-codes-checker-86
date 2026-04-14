# ═══════════════════════════════════════════════
#  Hijra Scraper — Configuration
# ═══════════════════════════════════════════════

import os

# ── Telegram User Account (for monitoring groups) ──
API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
PHONE = os.getenv("TG_PHONE", "")          # e.g. +1234567890

# ── Bot Token (for admin commands) ──
BOT_TOKEN = os.getenv("SCRAPER_BOT_TOKEN", "")

# ── Admin ──
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# ── Default destination group/channel ID ──
DEST_CHAT_ID = int(os.getenv("DEST_CHAT_ID", "0"))

# ── Database ──
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "scraper.db")

# ── Session files ──
SESSION_DIR = os.path.join(os.path.dirname(__file__), "sessions")

# ── Filters ──
DEFAULT_KEYWORDS = ["cc", "card", "bin", "cvv", "exp", "live", "approved", "charged"]
