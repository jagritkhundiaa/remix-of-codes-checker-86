# ═══════════════════════════════════════════════
#  Hijra Scraper — Database (SQLite)
# ═══════════════════════════════════════════════

import aiosqlite
import os
import time
import hashlib
from config import DB_PATH

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS sources (
                chat_id INTEGER PRIMARY KEY,
                title TEXT,
                link TEXT,
                category TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                added_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS message_hashes (
                hash TEXT PRIMARY KEY,
                source_id INTEGER,
                forwarded_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS forwarded_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER,
                source_title TEXT,
                cc_masked TEXT,
                message_hash TEXT,
                forwarded_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                total_scanned INTEGER DEFAULT 0,
                total_forwarded INTEGER DEFAULT 0,
                total_duplicates INTEGER DEFAULT 0,
                total_filtered INTEGER DEFAULT 0,
                started_at REAL
            );

            CREATE TABLE IF NOT EXISTS custom_filters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern TEXT NOT NULL,
                filter_type TEXT DEFAULT 'keyword',
                is_active INTEGER DEFAULT 1,
                added_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            INSERT OR IGNORE INTO stats (id, total_scanned, total_forwarded, total_duplicates, total_filtered, started_at)
            VALUES (1, 0, 0, 0, 0, 0);
        """)
        await db.commit()


# ── Content hashing for dedup ──

def hash_content(text: str) -> str:
    """Create a fingerprint of message content for dedup."""
    cleaned = "".join(text.split()).lower()
    return hashlib.sha256(cleaned.encode()).hexdigest()


async def is_duplicate(text: str) -> bool:
    h = hash_content(text)
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db.execute_fetchall(
            "SELECT 1 FROM message_hashes WHERE hash = ?", (h,)
        )
        return len(row) > 0


async def mark_forwarded(text: str, source_id: int, cc_masked: str = "", source_title: str = ""):
    h = hash_content(text)
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO message_hashes (hash, source_id, forwarded_at) VALUES (?, ?, ?)",
            (h, source_id, now),
        )
        await db.execute(
            "INSERT INTO forwarded_log (source_id, source_title, cc_masked, message_hash, forwarded_at) VALUES (?, ?, ?, ?, ?)",
            (source_id, source_title, cc_masked, h, now),
        )
        await db.commit()


# ── Sources CRUD ──

async def add_source(chat_id: int, title: str = "", link: str = "", category: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO sources (chat_id, title, link, category, is_active, added_at) VALUES (?, ?, ?, ?, 1, ?)",
            (chat_id, title, link, category, time.time()),
        )
        await db.commit()


async def remove_source(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM sources WHERE chat_id = ?", (chat_id,))
        await db.commit()


async def get_sources(active_only=True):
    async with aiosqlite.connect(DB_PATH) as db:
        q = "SELECT chat_id, title, link, category, is_active FROM sources"
        if active_only:
            q += " WHERE is_active = 1"
        rows = await db.execute_fetchall(q)
        return [
            {"chat_id": r[0], "title": r[1], "link": r[2], "category": r[3], "is_active": bool(r[4])}
            for r in rows
        ]


async def toggle_source(chat_id: int, active: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sources SET is_active = ? WHERE chat_id = ?", (1 if active else 0, chat_id)
        )
        await db.commit()


# ── Stats ──

async def inc_stat(field: str, amount: int = 1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE stats SET {field} = {field} + ? WHERE id = 1", (amount,))
        await db.commit()


async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db.execute_fetchall("SELECT * FROM stats WHERE id = 1")
        if not row:
            return {}
        r = row[0]
        return {
            "total_scanned": r[1],
            "total_forwarded": r[2],
            "total_duplicates": r[3],
            "total_filtered": r[4],
            "started_at": r[5],
        }


async def set_started():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE stats SET started_at = ? WHERE id = 1", (time.time(),))
        await db.commit()


async def reset_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE stats SET total_scanned=0, total_forwarded=0, total_duplicates=0, total_filtered=0, started_at=? WHERE id=1",
            (time.time(),),
        )
        await db.commit()


# ── Custom filters ──

async def add_filter(pattern: str, filter_type: str = "keyword"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO custom_filters (pattern, filter_type, added_at) VALUES (?, ?, ?)",
            (pattern, filter_type, time.time()),
        )
        await db.commit()


async def remove_filter(filter_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM custom_filters WHERE id = ?", (filter_id,))
        await db.commit()


async def get_filters():
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            "SELECT id, pattern, filter_type, is_active FROM custom_filters WHERE is_active = 1"
        )
        return [{"id": r[0], "pattern": r[1], "type": r[2], "active": bool(r[3])} for r in rows]


# ── Settings ──

async def get_setting(key: str, default: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db.execute_fetchall("SELECT value FROM settings WHERE key = ?", (key,))
        return row[0][0] if row else default


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
        await db.commit()


# ── Logs export ──

async def get_recent_logs(limit: int = 50):
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            "SELECT source_title, cc_masked, forwarded_at FROM forwarded_log ORDER BY forwarded_at DESC LIMIT ?",
            (limit,),
        )
        return [{"source": r[0], "cc": r[1], "time": r[2]} for r in rows]


async def get_log_count():
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db.execute_fetchall("SELECT COUNT(*) FROM forwarded_log")
        return row[0][0] if row else 0
