# WLID Claimer Script
# Made by TalkNeon

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

RESULTS_DIR = "results"
OUTPUT_FILE = os.path.join(RESULTS_DIR, "valid_wlid.txt")

lock = threading.Lock()
stats = {"success": 0, "failed": 0}


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


def login(session, email, password):
    r = session.get(
        "https://account.microsoft.com/billing/redeem",
        headers={**HEADERS, "Referer": "https://account.microsoft.com/"},
        allow_redirects=True, timeout=30,
    )
    text = r.text

    rurl_match = extract_pattern(text, r'"urlPost":"([^"]+)"')
    if not rurl_match:
        return None, "Could not extract redirect URL from billing page"

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
        return None, "Could not extract PPFT token"

    url_post = extract_pattern(text, r'"urlPost":"([^"]+)"')
    if not url_post:
        url_post = extract_pattern(text, r"urlPost:'([^']+)'")
    if not url_post:
        return None, "Could not extract urlPost"

    login_data = {
        "login": email,
        "loginfmt": email,
        "passwd": password,
        "PPFT": ppft,
    }
    r = session.post(
        url_post, data=login_data,
        headers={
            **HEADERS,
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": furl,
            "Origin": "https://login.live.com",
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
        return None, "Could not extract second sFT token"

    lurl = extract_pattern(login_text, r'"urlPost":"([^"]+)"')
    if not lurl:
        return None, "Could not extract final login URL"

    final_data = {
        "LoginOptions": "1",
        "type": "28",
        "ctx": "",
        "hpgrequestid": "",
        "PPFT": ppft2,
        "canary": "",
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
        return None, "Invalid token response (not JSON)"

    if not isinstance(data, list) or len(data) == 0:
        return None, "Invalid token structure (not a list)"

    token = data[0].get("token") if isinstance(data[0], dict) else None
    if not token:
        return None, "Token field missing or empty"

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


def load_accounts(source):
    accounts = []
    if os.path.isfile(source):
        with open(source, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if ":" in line:
                    accounts.append(line)
    elif ":" in source:
        accounts.append(source)
    else:
        print(f"[!] Invalid input: {source}")
        sys.exit(1)
    return accounts


def print_banner():
    print()
    print("=" * 50)
    print("  WLID Claimer")
    print("  Made by TalkNeon")
    print("=" * 50)
    print()


def main():
    print_banner()

    if len(sys.argv) < 2:
        print("Usage: python wlid_claimer.py <email:pass or accounts.txt> [threads]")
        print()
        print("Examples:")
        print("  python wlid_claimer.py accounts.txt")
        print("  python wlid_claimer.py accounts.txt 5")
        print("  python wlid_claimer.py user@outlook.com:password123")
        sys.exit(1)

    source = sys.argv[1]
    threads = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    threads = max(1, min(threads, 10))

    accounts = load_accounts(source)
    if not accounts:
        print("[!] No valid accounts found")
        sys.exit(1)

    total = len(accounts)
    print(f"[*] Loaded {total} account(s)")
    print(f"[*] Threads: {threads}")
    print(f"[*] Output:  {OUTPUT_FILE}")
    print("-" * 50)

    completed = [0]
    start_time = time.time()

    def worker(acc):
        idx = acc.index(":")
        email = acc[:idx]
        password = acc[idx + 1:]

        with lock:
            completed[0] += 1
            current = completed[0]
        print(f"[{current}/{total}] Checking: {email}")

        result = process_account(email, password)

        if result["success"]:
            save_token(result["token"])
            with lock:
                stats["success"] += 1
            print(f"  -> SUCCESS")
        else:
            with lock:
                stats["failed"] += 1
            print(f"  -> FAILED ({result['error']})")

        return result

    with ThreadPoolExecutor(max_workers=min(threads, total)) as pool:
        futures = [pool.submit(worker, acc) for acc in accounts]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception:
                pass

    elapsed = time.time() - start_time
    print()
    print("-" * 50)
    print(f"[*] Completed in {elapsed:.1f}s")
    print(f"[*] Success: {stats['success']}")
    print(f"[*] Failed:  {stats['failed']}")
    if stats["success"] > 0:
        print(f"[*] Tokens saved to: {OUTPUT_FILE}")
    print()


if __name__ == "__main__":
    main()
