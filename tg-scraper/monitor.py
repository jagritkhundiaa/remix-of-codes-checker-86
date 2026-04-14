# ═══════════════════════════════════════════════
#  Hijra Scraper — Userbot Monitor (Telethon)
# ═══════════════════════════════════════════════

import asyncio
import logging
import os
import time

from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat, User

from config import API_ID, API_HASH, PHONE, DEST_CHAT_ID, DEFAULT_KEYWORDS, SESSION_DIR
from db import (
    init_db, get_sources, is_duplicate, mark_forwarded, inc_stat,
    get_filters, set_started, get_setting
)
from filters import should_forward, extract_ccs, mask_cc
from formatter import format_scraper_hit

log = logging.getLogger("scraper")

# ── Globals ──
client: TelegramClient = None
is_paused = False
source_ids: set = set()


async def load_source_ids():
    """Refresh monitored source chat IDs from DB."""
    global source_ids
    sources = await get_sources(active_only=True)
    source_ids = {s["chat_id"] for s in sources}
    log.info(f"Loaded {len(source_ids)} active sources")


async def get_dest_chat():
    """Get current destination chat ID (supports runtime change)."""
    custom = await get_setting("dest_chat_id", "")
    if custom:
        try:
            return int(custom)
        except ValueError:
            pass
    return DEST_CHAT_ID


async def handle_message(event):
    """Process an incoming message from a monitored source."""
    global is_paused
    if is_paused:
        return

    chat_id = event.chat_id
    if chat_id not in source_ids:
        return

    text = event.raw_text or ""
    if not text.strip():
        return

    await inc_stat("total_scanned")

    # Get filters
    custom_filters = await get_filters()
    keywords = DEFAULT_KEYWORDS

    # Check if message should be forwarded
    forward, ccs, reason = should_forward(text, keywords, custom_filters)

    if not forward:
        await inc_stat("total_filtered")
        return

    # Dedup check
    if await is_duplicate(text):
        await inc_stat("total_duplicates")
        return

    # Also dedup individual CCs
    if ccs:
        unique_ccs = []
        for cc in ccs:
            if not await is_duplicate(cc["raw"]):
                unique_ccs.append(cc)
        if not unique_ccs:
            await inc_stat("total_duplicates")
            return
        ccs = unique_ccs

    dest = await get_dest_chat()
    if not dest:
        log.warning("No destination chat configured")
        return

    # Get source title
    try:
        chat = await client.get_entity(chat_id)
        source_title = getattr(chat, "title", str(chat_id))
    except Exception:
        source_title = str(chat_id)

    # Forward each CC with formatted message
    if ccs:
        for cc in ccs:
            try:
                msg = await format_scraper_hit(cc, source_title)
                await client.send_message(dest, msg)
                await mark_forwarded(cc["raw"], chat_id, mask_cc(cc["cc"]), source_title)
                await inc_stat("total_forwarded")
                await asyncio.sleep(0.3)  # Rate limit protection
            except Exception as e:
                log.error(f"Forward error: {e}")
    else:
        # Keyword/regex match without CC — forward raw text
        try:
            await client.send_message(
                dest,
                f"[ϟ] Hijra Scraper [ϟ]\n━━━━━━━━━━━━━\n"
                f"[ϟ] Source: {source_title}\n"
                f"[ϟ] Match: {reason}\n"
                f"━━━━━━━━━━━━━\n{text[:3000]}"
            )
            await mark_forwarded(text, chat_id, "", source_title)
            await inc_stat("total_forwarded")
        except Exception as e:
            log.error(f"Forward error: {e}")


async def start_monitor():
    """Initialize and start the userbot monitor."""
    global client

    os.makedirs(SESSION_DIR, exist_ok=True)
    session_path = os.path.join(SESSION_DIR, "scraper_session")

    client = TelegramClient(session_path, API_ID, API_HASH)

    await client.start(phone=PHONE)
    log.info("Userbot connected successfully")

    await init_db()
    await set_started()
    await load_source_ids()

    # Register handler for ALL new messages
    @client.on(events.NewMessage())
    async def on_new_message(event):
        try:
            await handle_message(event)
        except Exception as e:
            log.error(f"Handler error: {e}")

    log.info(f"Monitoring {len(source_ids)} sources → destination {await get_dest_chat()}")
    return client


async def join_source(link: str) -> dict:
    """Join a group/channel by link and return its info."""
    global client
    try:
        entity = await client.get_entity(link)
        chat_id = entity.id
        title = getattr(entity, "title", str(chat_id))
        return {"chat_id": chat_id, "title": title, "success": True}
    except Exception as e:
        # Try joining if not already a member
        try:
            from telethon.tl.functions.channels import JoinChannelRequest
            from telethon.tl.functions.messages import ImportChatInviteRequest

            if "joinchat" in link or "+": 
                hash_part = link.split("/")[-1].replace("+", "")
                result = await client(ImportChatInviteRequest(hash_part))
                chat = result.chats[0]
                return {"chat_id": chat.id, "title": chat.title, "success": True}
            else:
                result = await client(JoinChannelRequest(link))
                chat = result.chats[0]
                return {"chat_id": chat.id, "title": chat.title, "success": True}
        except Exception as e2:
            return {"chat_id": 0, "title": "", "success": False, "error": str(e2)}
