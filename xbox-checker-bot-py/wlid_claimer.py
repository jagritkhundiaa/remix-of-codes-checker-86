# made by talkneon
# WLID Claimer

import re
import sys
import os
import time
import urllib.parse
import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
              "image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

TOKEN_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

THREADS = 3
RESULTS_DIR = "results"
OUTPUT_FILE = os.path.join(RESULTS_DIR, "valid_wlid.txt")
FAILED_FILE = os.path.join(RESULTS_DIR, "failed_wlid.txt")

lock = threading.Lock()
stats = {"success": 0, "failed": 0, "total": 0}


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def decode_json_string(text):
    try:
        return text.encode().decode("unicode_escape")
    except Exception:
        return text


def extract_pattern(text, pattern):
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1) if m else None


def extract_all_inputs(text, pattern):
    return re.findall(pattern, text, re.DOTALL)


def progress_bar(current, total, width=30):
    if total == 0:
        return "[" + "-" * width + "]"
    filled = int(width * current / total)
    bar = "#" * filled + "-" * (width - filled)
    pct = int(100 * current / total)
    return f"[{bar}] {pct}%"


def print_header():
    clear()
    print()
    print("  +-----------------------------------------+")
    print("  |            WLID Claimer                  |")
    print("  |            made by talkneon              |")
    print("  +-----------------------------------------+")
    print()


def print_separator():
    print("  " + "-" * 43)


def login(session, email, password):
    r = session.get(
        "https://account.microsoft.com/billing/redeem",
        headers={**HEADERS, "Referer": "https://account.microsoft.com/"},
        allow_redirects=True, timeout=30,
    )
    text = r.text

    rurl_match = extract_pattern(text, r'"urlPost":"([^"]+)"')
    if not rurl_match:
        return None, "Could not extract redirect URL"

    rurl = "https://login.microsoftonline.com" + decode_json_string(rurl_match)
    r = session.get(
        rurl,
        headers={**HEADERS, "Referer": "https://account.microsoft.com/"},
        allow_redirects=True, timeout=30,
    )
    text = r.text

    furl_match = extract_pattern(text, r'urlGoToAADError":"([^"]+)"')
    if not furl_match:
        return None, "Could not extract AAD URL"

    furl = decode_json_string(furl_match)
    furl = furl.replace(
        "&jshs=0",
        f"&jshs=2&jsh=&jshp=&username={urllib.parse.quote(email)}"
        f"&login_hint={urllib.parse.quote(email)}",
    )

    r = session.get(
        furl,
        headers={**HEADERS, "Referer": "https://login.microsoftonline.com/"},
        allow_redirects=True, timeout=30,
    )
    text = r.text

    ppft = None
    for pat in [
        r'name="PPFT"[^>]+value="([^"]+)"',
        r'value="([^"]+)"[^>]+name="PPFT"',
        r'value=\\?"([^"\\]+)\\?"',
    ]:
        ppft = extract_pattern(text, pat)
        if ppft:
            break
    if not ppft:
        if "captcha" in text.lower() or "hip_challenge" in text.lower():
            return None, "CAPTCHA_REQUIRED"
        return None, "Could not extract PPFT"

    url_post = extract_pattern(text, r'"urlPost":"([^"]+)"')
    if not url_post:
        url_post = extract_pattern(text, r"urlPost:'([^']+)'")
    if not url_post:
        return None, "Could not extract urlPost"

    login_data = {
        "login": email, "loginfmt": email,
        "passwd": password, "PPFT": ppft,
    }
    r = session.post(
        url_post, data=login_data,
        headers={
            **HEADERS,
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": furl, "Origin": "https://login.live.com",
        },
        allow_redirects=True, timeout=30,
    )
    login_text = r.text.replace("\\", "")

    if "Your account or password is incorrect" in login_text or "sErrTxt" in login_text:
        return None, "INVALID_CREDENTIALS"

    if "captcha" in login_text.lower() or "hip_challenge" in login_text.lower():
        return None, "CAPTCHA_REQUIRED"

    ppft2 = extract_pattern(login_text, r'"sFT":"([^"]+)"')
    if not ppft2:
        action_url = extract_pattern(login_text, r'<form[^>]*action="([^"]+)"')
        if action_url and "privacynotice" in action_url:
            inputs = extract_all_inputs(
                login_text,
                r'<input[^>]+type="hidden"[^>]+name="([^"]+)"[^>]+value="([^"]*)"',
            )
            if inputs:
                form_data = {n: v for n, v in inputs}
                r = session.post(
                    action_url, data=form_data,
                    headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
                    allow_redirects=True, timeout=30,
                )
                redirect_m = re.search(r"ucis\.RedirectUrl\s*=\s*'([^']+)'", r.text)
                if redirect_m:
                    redir = redirect_m.group(1).replace("u0026", "&").replace("\\&", "&")
                    r = session.get(redir, headers=HEADERS, allow_redirects=True, timeout=30)
                    login_text = r.text.replace("\\", "")
        ppft2 = extract_pattern(login_text, r'"sFT":"([^"]+)"')

    if not ppft2:
        return None, "Could not extract second sFT"

    lurl = extract_pattern(login_text, r'"urlPost":"([^"]+)"')
    if not lurl:
        return None, "Could not extract final login URL"

    final_data = {
        "LoginOptions": "1", "type": "28", "ctx": "",
        "hpgrequestid": "", "PPFT": ppft2, "canary": "",
    }
    r = session.post(
        lurl, data=final_data,
        headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        allow_redirects=True, timeout=30,
    )
    finish_text = r.text

    reurl = extract_pattern(finish_text, r'replace\("([^"]+)"\)')
    reresp = finish_text
    if reurl:
        r = session.get(
            reurl,
            headers={**HEADERS, "Referer": "https://login.live.com/"},
            allow_redirects=True, timeout=30,
        )
        reresp = r.text

    action_m = extract_pattern(reresp, r'<form[^>]*action="([^"]+)"')
    if action_m and "javascript" not in action_m:
        inputs = extract_all_inputs(
            reresp, r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"'
        )
        if not inputs:
            raw = extract_all_inputs(
                reresp, r'<input[^>]*value="([^"]*)"[^>]*name="([^"]+)"'
            )
            inputs = [(n, v) for v, n in raw]
        if inputs:
            form_data = {n: v for n, v in inputs}
            session.post(
                action_m, data=form_data,
                headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
                allow_redirects=True, timeout=30,
            )

    return session, None


def extract_token(session):
    r = session.get(
        "https://account.microsoft.com/auth/acquire-onbehalf-of-token"
        "?scopes=MSComServiceMBISSL",
        headers={
            **TOKEN_HEADERS,
            "User-Agent": HEADERS["User-Agent"],
            "Referer": "https://account.microsoft.com/billing/redeem",
        },
        timeout=30,
    )
    try:
        data = r.json()
    except Exception:
        return None, "Invalid token response"

    if not isinstance(data, list) or len(data) == 0:
        return None, "Invalid token structure"

    token = data[0].get("token") if isinstance(data[0], dict) else None
    if not token:
        return None, "Token field empty"

    return token, None


def process_account(email, password):
    session = requests.Session()
    session.max_redirects = 15
    session.headers.update(HEADERS)

    try:
        result_session, err = login(session, email, password)
        if err:
            return {"email": email, "success": False, "error": err}

        token, err = extract_token(result_session)
        if err:
            return {"email": email, "success": False, "error": err}

        return {"email": email, "success": True, "token": token}

    except requests.exceptions.Timeout:
        return {"email": email, "success": False, "error": "LOGIN_FAILED (timeout)"}
    except requests.exceptions.ConnectionError:
        return {"email": email, "success": False, "error": "LOGIN_FAILED (connection)"}
    except Exception as ex:
        return {"email": email, "success": False, "error": f"LOGIN_FAILED ({ex})"}


def save_token(token):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with lock:
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(token + "\n")


def save_failed(email, reason):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with lock:
        with open(FAILED_FILE, "a", encoding="utf-8") as f:
            f.write(f"{email} | {reason}\n")


def load_accounts(path):
    accounts = []
    if not os.path.isfile(path):
        return accounts
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if ":" in line and len(line) > 3:
                accounts.append(line)
    return accounts


def run_claimer(accounts):
    total = len(accounts)
    stats["total"] = total
    stats["success"] = 0
    stats["failed"] = 0

    print(f"  > accounts loaded : {total}")
    print(f"  > threads         : {THREADS}")
    print(f"  > output          : {OUTPUT_FILE}")
    print_separator()
    print()

    start_time = time.time()
    completed = [0]

    def worker(acc):
        idx = acc.index(":")
        email = acc[:idx]
        password = acc[idx + 1:]

        result = process_account(email, password)

        with lock:
            completed[0] += 1
            current = completed[0]

            if result["success"]:
                stats["success"] += 1
                save_token(result["token"])
                status_text = "SUCCESS"
            else:
                stats["failed"] += 1
                save_failed(email, result["error"])
                status_text = result["error"]

            bar = progress_bar(current, total)
            print(f"  {bar}  {current}/{total}")
            print(f"  > {email}")
            print(f"  > {status_text}")
            print()

        return result

    thread_count = min(THREADS, total)
    with ThreadPoolExecutor(max_workers=thread_count) as pool:
        futures = [pool.submit(worker, acc) for acc in accounts]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception:
                pass

    elapsed = time.time() - start_time
    print_separator()
    print()
    print(f"  > completed in {elapsed:.1f}s")
    print(f"  > success : {stats['success']}")
    print(f"  > failed  : {stats['failed']}")
    if stats["success"] > 0:
        print(f"  > saved to {OUTPUT_FILE}")
    print()


def main():
    print_header()

    print("  [1] Load accounts from file")
    print("  [2] Paste accounts manually")
    print()

    choice = input("  > select option: ").strip()

    accounts = []

    if choice == "1":
        print()
        path = input("  > drag/drop file or enter path: ").strip()
        path = path.strip('"').strip("'")
        if not os.path.isfile(path):
            print(f"\n  file not found: {path}")
            return
        accounts = load_accounts(path)
        if not accounts:
            print("\n  no valid accounts found in file")
            return

    elif choice == "2":
        print()
        print("  paste accounts (email:pass), one per line")
        print("  type 'done' when finished")
        print()
        while True:
            line = input("  > ").strip()
            if line.lower() == "done":
                break
            if ":" in line and len(line) > 3:
                accounts.append(line)
        if not accounts:
            print("\n  no valid accounts entered")
            return

    else:
        print("\n  invalid option")
        return

    print()
    print_separator()
    print()

    run_claimer(accounts)

    input("  press enter to exit...")


if __name__ == "__main__":
    main()
