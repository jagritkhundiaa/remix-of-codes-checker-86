# ═══════════════════════════════════════════════
#  Hijra Scraper — Main Entry Point
# ═══════════════════════════════════════════════
#
#  A real-time Telegram group/channel monitor that:
#  - Watches multiple source groups via userbot
#  - Filters for CC patterns and custom keywords
#  - Forwards with branded format to destination
#  - Lifetime deduplication via content hashing
#  - Full admin control via bot commands
#
# ═══════════════════════════════════════════════

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scraper.log", mode="a"),
    ],
)
log = logging.getLogger("main")


async def main():
    from config import API_ID, API_HASH, BOT_TOKEN, ADMIN_IDS, DEST_CHAT_ID

    # ── Validate config ──
    errors = []
    if not API_ID:
        errors.append("TG_API_ID not set")
    if not API_HASH:
        errors.append("TG_API_HASH not set")
    if not BOT_TOKEN:
        errors.append("SCRAPER_BOT_TOKEN not set")
    if not ADMIN_IDS:
        errors.append("ADMIN_IDS not set")
    if not DEST_CHAT_ID:
        errors.append("DEST_CHAT_ID not set (can be set later via /setdest)")

    if errors and "TG_API_ID" in errors[0]:
        log.error("Missing required config:\n" + "\n".join(f"  - {e}" for e in errors))
        sys.exit(1)

    log.info("═══ Hijra Scraper Starting ═══")

    # Start userbot monitor
    from monitor import start_monitor
    userbot = await start_monitor()
    log.info("✅ Userbot monitor active")

    # Start admin bot
    from commands import start_bot
    admin_bot = await start_bot()
    log.info("✅ Admin bot active")

    log.info("═══ Hijra Scraper Running ═══")
    log.info(f"Admin IDs: {ADMIN_IDS}")
    log.info(f"Destination: {DEST_CHAT_ID}")

    # Keep both clients running
    await asyncio.gather(
        userbot.run_until_disconnected(),
        admin_bot.run_until_disconnected(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Scraper stopped by user")
    except Exception as e:
        log.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
