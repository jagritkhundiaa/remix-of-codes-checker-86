# ═══════════════════════════════════════════════
#  Hijra Scraper — Admin Bot Commands
# ═══════════════════════════════════════════════

import asyncio
import logging
import time
import os
import io

from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeFilename

from config import BOT_TOKEN, ADMIN_IDS, SESSION_DIR
from db import (
    add_source, remove_source, get_sources, toggle_source,
    get_stats, reset_stats, add_filter, remove_filter, get_filters,
    get_recent_logs, get_log_count, set_setting, get_setting, inc_stat
)
from formatter import format_stats_message, format_source_list
from monitor import load_source_ids, join_source, is_paused

log = logging.getLogger("commands")

bot: TelegramClient = None


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def fmt_uptime(started: float) -> str:
    if not started:
        return "N/A"
    secs = int(time.time() - started)
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{mins}m")
    return " ".join(parts)


HELP_TEXT = """
[ϟ] 𝗛𝗶𝗷𝗿𝗮 𝗦𝗰𝗿𝗮𝗽𝗲𝗿 — 𝗖𝗼𝗺𝗺𝗮𝗻𝗱𝘀 [ϟ]
━━━━━━━━━━━━━━━━━━━━

📡 𝗦𝗼𝘂𝗿𝗰𝗲𝘀
/addsrc <link>     — Add a source group/channel
/rmsrc <chat_id>   — Remove a source
/sources           — List all sources
/pausesrc <id>     — Pause a source
/resumesrc <id>    — Resume a source
/bulk              — Reply to .txt file to bulk add sources

📊 𝗔𝗻𝗮𝗹𝘆𝘁𝗶𝗰𝘀
/stats             — View scraper statistics
/logs              — Recent forwarded entries
/export            — Export full logs as .txt
/resetstats        — Reset all counters

⚙️ 𝗖𝗼𝗻𝘁𝗿𝗼𝗹
/pause             — Pause the scraper
/resume            — Resume the scraper
/setdest <chat_id> — Change destination group
/status            — Current bot status

🔍 𝗙𝗶𝗹𝘁𝗲𝗿𝘀
/addkw <keyword>   — Add keyword filter
/addregex <pattern>— Add regex filter
/filters           — List active filters
/rmfilter <id>     — Remove a filter

━━━━━━━━━━━━━━━━━━━━
"""


async def start_bot():
    """Start the admin command bot."""
    global bot

    os.makedirs(SESSION_DIR, exist_ok=True)
    session_path = os.path.join(SESSION_DIR, "bot_session")
    bot = TelegramClient(session_path, 1, "x")  # API creds not needed for bot
    await bot.start(bot_token=BOT_TOKEN)
    log.info("Admin bot started")

    # ── /start & /help ──
    @bot.on(events.NewMessage(pattern=r"^/(start|help)$"))
    async def cmd_help(event):
        if not is_admin(event.sender_id):
            return await event.reply("⛔ Unauthorized")
        await event.reply(HELP_TEXT)

    # ── /addsrc ──
    @bot.on(events.NewMessage(pattern=r"^/addsrc\s+(.+)$"))
    async def cmd_add_source(event):
        if not is_admin(event.sender_id):
            return await event.reply("⛔ Unauthorized")
        link = event.pattern_match.group(1).strip()
        msg = await event.reply("⏳ Joining and adding source...")
        result = await join_source(link)
        if result["success"]:
            await add_source(result["chat_id"], result["title"], link)
            await load_source_ids()
            await msg.edit(
                f"✅ Source added!\n"
                f"Title: {result['title']}\n"
                f"Chat ID: {result['chat_id']}"
            )
        else:
            await msg.edit(f"❌ Failed: {result.get('error', 'Unknown error')}")

    # ── /rmsrc ──
    @bot.on(events.NewMessage(pattern=r"^/rmsrc\s+(-?\d+)$"))
    async def cmd_remove_source(event):
        if not is_admin(event.sender_id):
            return await event.reply("⛔ Unauthorized")
        chat_id = int(event.pattern_match.group(1))
        await remove_source(chat_id)
        await load_source_ids()
        await event.reply(f"✅ Source {chat_id} removed")

    # ── /sources ──
    @bot.on(events.NewMessage(pattern=r"^/sources$"))
    async def cmd_sources(event):
        if not is_admin(event.sender_id):
            return await event.reply("⛔ Unauthorized")
        sources = await get_sources(active_only=False)
        await event.reply(format_source_list(sources))

    # ── /pausesrc & /resumesrc ──
    @bot.on(events.NewMessage(pattern=r"^/pausesrc\s+(-?\d+)$"))
    async def cmd_pause_source(event):
        if not is_admin(event.sender_id):
            return await event.reply("⛔ Unauthorized")
        chat_id = int(event.pattern_match.group(1))
        await toggle_source(chat_id, False)
        await load_source_ids()
        await event.reply(f"⏸️ Source {chat_id} paused")

    @bot.on(events.NewMessage(pattern=r"^/resumesrc\s+(-?\d+)$"))
    async def cmd_resume_source(event):
        if not is_admin(event.sender_id):
            return await event.reply("⛔ Unauthorized")
        chat_id = int(event.pattern_match.group(1))
        await toggle_source(chat_id, True)
        await load_source_ids()
        await event.reply(f"▶️ Source {chat_id} resumed")

    # ── /bulk (reply to .txt file) ──
    @bot.on(events.NewMessage(pattern=r"^/bulk$"))
    async def cmd_bulk(event):
        if not is_admin(event.sender_id):
            return await event.reply("⛔ Unauthorized")
        reply = await event.get_reply_message()
        if not reply or not reply.file:
            return await event.reply("⚠️ Reply to a .txt file with source links")

        data = await reply.download_media(bytes)
        text = data.decode("utf-8", errors="ignore")
        links = [l.strip() for l in text.splitlines() if l.strip() and ("t.me" in l or "+" in l)]

        if not links:
            return await event.reply("⚠️ No valid Telegram links found in file")

        msg = await event.reply(f"⏳ Processing {len(links)} links...")
        added, failed = 0, 0
        for link in links:
            result = await join_source(link)
            if result["success"]:
                await add_source(result["chat_id"], result["title"], link)
                added += 1
            else:
                failed += 1
            await asyncio.sleep(1)  # Rate limit

        await load_source_ids()
        await msg.edit(f"✅ Bulk import done\nAdded: {added}\nFailed: {failed}")

    # ── /stats ──
    @bot.on(events.NewMessage(pattern=r"^/stats$"))
    async def cmd_stats(event):
        if not is_admin(event.sender_id):
            return await event.reply("⛔ Unauthorized")
        stats = await get_stats()
        sources = await get_sources()
        uptime = fmt_uptime(stats.get("started_at", 0))
        await event.reply(format_stats_message(stats, len(sources), uptime))

    # ── /logs ──
    @bot.on(events.NewMessage(pattern=r"^/logs$"))
    async def cmd_logs(event):
        if not is_admin(event.sender_id):
            return await event.reply("⛔ Unauthorized")
        logs = await get_recent_logs(20)
        if not logs:
            return await event.reply("[ϟ] No logs yet.")
        lines = ["[ϟ] Recent Forwards [ϟ]", "━━━━━━━━━━━━━"]
        for l in logs:
            t = time.strftime("%H:%M:%S", time.localtime(l["time"]))
            lines.append(f"{t} | {l['source'][:15]} | {l['cc'] or 'keyword'}")
        await event.reply("\n".join(lines))

    # ── /export ──
    @bot.on(events.NewMessage(pattern=r"^/export$"))
    async def cmd_export(event):
        if not is_admin(event.sender_id):
            return await event.reply("⛔ Unauthorized")
        logs = await get_recent_logs(5000)
        if not logs:
            return await event.reply("[ϟ] No logs to export.")
        lines = []
        for l in logs:
            t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(l["time"]))
            lines.append(f"{t} | {l['source']} | {l['cc'] or 'keyword_match'}")
        content = "\n".join(lines)
        buf = io.BytesIO(content.encode())
        buf.name = "hijra_scraper_logs.txt"
        await event.reply(file=buf)

    # ── /resetstats ──
    @bot.on(events.NewMessage(pattern=r"^/resetstats$"))
    async def cmd_reset(event):
        if not is_admin(event.sender_id):
            return await event.reply("⛔ Unauthorized")
        await reset_stats()
        await event.reply("✅ Stats reset")

    # ── /pause & /resume (global) ──
    @bot.on(events.NewMessage(pattern=r"^/pause$"))
    async def cmd_pause(event):
        if not is_admin(event.sender_id):
            return await event.reply("⛔ Unauthorized")
        import monitor
        monitor.is_paused = True
        await event.reply("⏸️ Scraper paused")

    @bot.on(events.NewMessage(pattern=r"^/resume$"))
    async def cmd_resume(event):
        if not is_admin(event.sender_id):
            return await event.reply("⛔ Unauthorized")
        import monitor
        monitor.is_paused = False
        await event.reply("▶️ Scraper resumed")

    # ── /setdest ──
    @bot.on(events.NewMessage(pattern=r"^/setdest\s+(-?\d+)$"))
    async def cmd_setdest(event):
        if not is_admin(event.sender_id):
            return await event.reply("⛔ Unauthorized")
        dest = event.pattern_match.group(1)
        await set_setting("dest_chat_id", dest)
        await event.reply(f"✅ Destination set to {dest}")

    # ── /status ──
    @bot.on(events.NewMessage(pattern=r"^/status$"))
    async def cmd_status(event):
        if not is_admin(event.sender_id):
            return await event.reply("⛔ Unauthorized")
        import monitor
        sources = await get_sources()
        dest = await monitor.get_dest_chat()
        status = "⏸️ Paused" if monitor.is_paused else "▶️ Running"
        await event.reply(
            f"[ϟ] Scraper Status [ϟ]\n"
            f"━━━━━━━━━━━━━\n"
            f"Status: {status}\n"
            f"Sources: {len(sources)}\n"
            f"Destination: {dest}\n"
        )

    # ── /addkw ──
    @bot.on(events.NewMessage(pattern=r"^/addkw\s+(.+)$"))
    async def cmd_addkw(event):
        if not is_admin(event.sender_id):
            return await event.reply("⛔ Unauthorized")
        kw = event.pattern_match.group(1).strip()
        await add_filter(kw, "keyword")
        await event.reply(f"✅ Keyword filter added: {kw}")

    # ── /addregex ──
    @bot.on(events.NewMessage(pattern=r"^/addregex\s+(.+)$"))
    async def cmd_addregex(event):
        if not is_admin(event.sender_id):
            return await event.reply("⛔ Unauthorized")
        pattern = event.pattern_match.group(1).strip()
        await add_filter(pattern, "regex")
        await event.reply(f"✅ Regex filter added: {pattern}")

    # ── /filters ──
    @bot.on(events.NewMessage(pattern=r"^/filters$"))
    async def cmd_filters(event):
        if not is_admin(event.sender_id):
            return await event.reply("⛔ Unauthorized")
        filters = await get_filters()
        if not filters:
            return await event.reply("[ϟ] No custom filters. Default CC pattern detection is always active.")
        lines = ["[ϟ] Custom Filters [ϟ]", "━━━━━━━━━━━━━"]
        for f in filters:
            lines.append(f"ID {f['id']} | {f['type']} | {f['pattern']}")
        await event.reply("\n".join(lines))

    # ── /rmfilter ──
    @bot.on(events.NewMessage(pattern=r"^/rmfilter\s+(\d+)$"))
    async def cmd_rmfilter(event):
        if not is_admin(event.sender_id):
            return await event.reply("⛔ Unauthorized")
        fid = int(event.pattern_match.group(1))
        await remove_filter(fid)
        await event.reply(f"✅ Filter {fid} removed")

    return bot
