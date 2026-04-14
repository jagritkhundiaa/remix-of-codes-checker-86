# ═══════════════════════════════════════════════
#  Hijra Scraper — Message Formatter
# ═══════════════════════════════════════════════

import aiohttp
import asyncio

BIN_CACHE = {}


async def lookup_bin(bin6: str) -> dict:
    """Lookup BIN info from free API."""
    if bin6 in BIN_CACHE:
        return BIN_CACHE[bin6]

    info = {"country": "Unknown", "issuer": "Unknown", "type": "Unknown", "brand": "Unknown"}

    apis = [
        f"https://lookup.binlist.net/{bin6}",
        f"https://bins.antipublic.cc/bins/{bin6}",
    ]

    for url in apis:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "binlist" in url:
                            info["country"] = data.get("country", {}).get("name", "Unknown")
                            info["issuer"] = data.get("bank", {}).get("name", "Unknown")
                            info["type"] = data.get("type", "Unknown").upper()
                            info["brand"] = data.get("scheme", "Unknown").upper()
                        else:
                            info["country"] = data.get("country_name", data.get("country", "Unknown"))
                            info["issuer"] = data.get("bank", data.get("issuer", "Unknown"))
                            info["type"] = data.get("type", "Unknown").upper()
                            info["brand"] = data.get("brand", data.get("scheme", "Unknown")).upper()
                        BIN_CACHE[bin6] = info
                        return info
        except Exception:
            continue

    BIN_CACHE[bin6] = info
    return info


def format_flag(country: str) -> str:
    """Simple country to flag emoji mapping."""
    flags = {
        "united states": "🇺🇸", "us": "🇺🇸", "canada": "🇨🇦", "united kingdom": "🇬🇧",
        "uk": "🇬🇧", "germany": "🇩🇪", "france": "🇫🇷", "india": "🇮🇳",
        "australia": "🇦🇺", "brazil": "🇧🇷", "mexico": "🇲🇽", "japan": "🇯🇵",
        "italy": "🇮🇹", "spain": "🇪🇸", "netherlands": "🇳🇱", "turkey": "🇹🇷",
        "saudi arabia": "🇸🇦", "uae": "🇦🇪", "egypt": "🇪🇬", "nigeria": "🇳🇬",
    }
    return flags.get(country.lower(), "🌍")


async def format_scraper_hit(cc_data: dict, source_title: str = "") -> str:
    """Format a scraped CC into the Hijra Scraper template."""
    bin_info = await lookup_bin(cc_data["bin"])
    flag = format_flag(bin_info["country"])
    raw = cc_data["raw"]

    msg = (
        f"[ϟ] Hijra Scraper [ϟ]\n"
        f"\n"
        f"𝗦𝘁𝗮𝘁𝘂𝘀 - Approved ✅\n"
        f"━━━━━━━━━━━━━\n"
        f"[ϟ] 𝗖𝗖 ⌁ {raw}\n"
        f"[ϟ] 𝗦𝘁𝗮𝘁𝘂𝘀 : Payment method added successfully ✅\n"
        f"[ϟ] 𝗚𝗮𝘁𝗲 - Stripe Auth \n"
        f"━━━━━━━━━━━━━\n"
        f"[ϟ] 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 : {bin_info['country']} {flag}\n"
        f"[ϟ] 𝗜𝘀𝘀𝘂𝗲𝗿 : {bin_info['issuer']}\n"
        f"[ϟ] 𝗧𝘆𝗽𝗲 : {bin_info['brand']} {bin_info['type']}\n"
        f"━━━━━━━━━━━━━\n"
        f"[ϟ] Proxy : Live ⚡\n"
    )

    if source_title:
        msg += f"[ϟ] Source : {source_title}\n"

    return msg


def format_stats_message(stats: dict, sources_count: int, uptime_str: str) -> str:
    """Format analytics stats message."""
    return (
        f"[ϟ] Hijra Scraper — Stats [ϟ]\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"[ϟ] Uptime       : {uptime_str}\n"
        f"[ϟ] Sources      : {sources_count}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"[ϟ] Scanned      : {stats.get('total_scanned', 0):,}\n"
        f"[ϟ] Forwarded    : {stats.get('total_forwarded', 0):,}\n"
        f"[ϟ] Duplicates   : {stats.get('total_duplicates', 0):,}\n"
        f"[ϟ] Filtered Out : {stats.get('total_filtered', 0):,}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )


def format_source_list(sources: list) -> str:
    """Format source list for display."""
    if not sources:
        return "[ϟ] No sources configured."
    lines = ["[ϟ] Hijra Scraper — Sources [ϟ]", "━━━━━━━━━━━━━━━━━━━━"]
    for i, s in enumerate(sources, 1):
        status = "✅" if s["is_active"] else "⏸️"
        title = s["title"] or s["link"] or str(s["chat_id"])
        cat = f" [{s['category']}]" if s.get("category") else ""
        lines.append(f"{i}. {status} {title}{cat}")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)
