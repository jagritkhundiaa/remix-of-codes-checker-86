"""
Microsoft Store Purchaser — exact 1:1 port of microsoft-purchaser.js
Two purchase flows:
  1. Primary: WLID store checkout (buynow.production.store-web.dynamics.com)
  2. Fallback: Xbox Live OAuth → XBL3.0 → purchase.xboxlive.com
"""
import re
import json
import time
import uuid
import requests
import urllib.parse
import threading

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0"
)

DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://account.microsoft.com/",
    "Origin": "https://account.microsoft.com",
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


# ═══════════════════════════════════════════════════════════════
#  FLOW 1: WLID Store Checkout (primary)
# ═══════════════════════════════════════════════════════════════

def login_to_store(email, password):
    """Login to Microsoft Store via WLID flow. Returns session dict or None."""
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)

    try:
        print(f"[PURCHASER] WLID login for {email}")

        # Step 1: Load the login page to get PPFT + urlPost dynamically
        init_url = (
            f"https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=19"
            f"&ct={int(time.time())}&rver=7.0.6738.0&wp=MBI_SSL"
            f"&wreply=https://account.microsoft.com/auth/complete-signin"
            f"&lc=1033&id=292666&username={urllib.parse.quote(email)}"
        )
        r = s.get(init_url, allow_redirects=True, timeout=20)
        login_page = r.text

        # Extract PPFT dynamically (multiple patterns like mody.py)
        ppft = ""
        url_post = ""

        # Try ServerData JSON first
        server_data_match = re.search(r'var ServerData = ({.*?});', login_page, re.DOTALL)
        if server_data_match:
            try:
                server_data = json.loads(server_data_match.group(1))
                if server_data.get("sFTTag"):
                    ppft_match = re.search(r'value="([^"]+)"', server_data["sFTTag"])
                    if ppft_match:
                        ppft = ppft_match.group(1)
                if server_data.get("urlPost"):
                    url_post = server_data["urlPost"]
            except Exception:
                pass

        # Fallback patterns
        if not ppft:
            m = re.search(r'"sFTTag":"[^"]*value=\\"([^"\\]+)\\"', login_page)
            if m:
                ppft = m.group(1)
        if not ppft:
            m = re.search(r'name="PPFT"[^>]*value="([^"]+)"', login_page)
            if m:
                ppft = m.group(1)
        if not ppft:
            try:
                ppft = login_page.split('name="PPFT" id="i0327" value="')[1].split('"')[0]
            except Exception:
                pass

        if not url_post:
            m = re.search(r'"urlPost":"([^"]+)"', login_page)
            if m:
                url_post = m.group(1)
        if not url_post:
            try:
                url_post = login_page.split("urlPost:'")[1].split("'")[0]
            except Exception:
                pass

        if not ppft or not url_post:
            print(f"[PURCHASER] Failed to extract PPFT/urlPost for {email}")
            return None

        # Step 2: Submit credentials
        login_data = urllib.parse.urlencode({
            "i13": "1",
            "login": email,
            "loginfmt": email,
            "type": "11",
            "LoginOptions": "1",
            "passwd": password,
            "ps": "2",
            "PPFT": ppft,
            "PPSX": "PassportR",
            "NewUser": "1",
            "FoundMSAs": "",
            "fspost": "0",
            "i21": "0",
            "CookieDisclosure": "0",
            "IsFidoSupported": "0",
            "isSignupPost": "0",
            "isRecoveryAttemptPost": "0",
            "i19": "9960",
        })
        r = s.post(
            url_post, data=login_data,
            headers={**DEFAULT_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
            allow_redirects=True, timeout=20,
        )
        login_text = r.text

        # Check for login errors
        cleaned = login_text.replace("\\", "")
        if "sErrTxt" in cleaned or "account or password is incorrect" in cleaned or "doesn't exist" in cleaned:
            print(f"[PURCHASER] Bad credentials for {email}")
            return None
        if "identity/confirm" in cleaned or "Abuse" in cleaned:
            print(f"[PURCHASER] Account locked/MFA for {email}")
            return None

        # Step 3: Follow redirect chain
        reurl_match = re.search(r'replace\("([^"]+)"', cleaned)
        if reurl_match:
            r = s.get(reurl_match.group(1), allow_redirects=True, timeout=20)
            reresp = r.text

            # Process hidden form redirect (e.g., jsDisabled.srf)
            action_match = re.search(r'<form.*?action="(.*?)".*?>', reresp)
            if action_match:
                input_matches = re.findall(r'<input.*?name="(.*?)".*?value="(.*?)".*?>', reresp)
                if input_matches:
                    form_data = urllib.parse.urlencode({n: v for n, v in input_matches})
                    s.post(
                        action_match.group(1), data=form_data,
                        headers={**DEFAULT_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
                        allow_redirects=True, timeout=20,
                    )

        # Step 4: Acquire store auth token
        try:
            s.get("https://buynowui.production.store-web.dynamics.com/akam/13/79883e11", timeout=10)
        except Exception:
            pass

        token_r = s.get(
            "https://account.microsoft.com/auth/acquire-onbehalf-of-token?scopes=MSComServiceMBISSL",
            headers={
                **TOKEN_HEADERS,
                "User-Agent": UA,
                "Referer": "https://account.microsoft.com/billing/redeem",
            },
            timeout=20,
        )

        if token_r.status_code != 200:
            print(f"[PURCHASER] Token request returned {token_r.status_code} for {email}")
            return None

        try:
            token_data = token_r.json()
        except Exception:
            print(f"[PURCHASER] Invalid token response for {email}")
            return None

        if not token_data or not isinstance(token_data, list) or not token_data[0].get("token"):
            print(f"[PURCHASER] No token in response for {email}")
            return None

        print(f"[PURCHASER] WLID login SUCCESS for {email}")
        return {
            "method": "wlid",
            "token": token_data[0]["token"],
            "session": s,
            "email": email,
        }

    except Exception as err:
        print(f"[PURCHASER] WLID login EXCEPTION for {email}: {err}")
        return None


# ═══════════════════════════════════════════════════════════════
#  FLOW 2: Xbox Live OAuth → XBL3.0 (fallback)
# ═══════════════════════════════════════════════════════════════

SFTTAG_URL = (
    "https://login.live.com/oauth20_authorize.srf"
    "?client_id=00000000402B5328"
    "&redirect_uri=https://login.live.com/oauth20_desktop.srf"
    "&scope=service::user.auth.xboxlive.com::MBI_SSL"
    "&display=touch&response_type=token&locale=en"
)


def login_xbox_live(email, password):
    """Login via Xbox Live OAuth → XBL3.0. Returns session dict or None."""
    try:
        print(f"[PURCHASER] XBL3.0 fallback login for {email}")

        s = requests.Session()
        s.headers.update({"User-Agent": UA})

        # Step 1: Get login form
        r = s.get(SFTTAG_URL, allow_redirects=True, timeout=20)
        form_text = r.text

        # Extract PPFT and urlPost dynamically
        sft_tag = ""
        url_post = ""

        server_data_match = re.search(r'var ServerData = ({.*?});', form_text, re.DOTALL)
        if server_data_match:
            try:
                server_data = json.loads(server_data_match.group(1))
                if server_data.get("sFTTag"):
                    ppft_match = re.search(r'value="([^"]+)"', server_data["sFTTag"])
                    if ppft_match:
                        sft_tag = ppft_match.group(1)
                if server_data.get("urlPost"):
                    url_post = server_data["urlPost"]
            except Exception:
                pass

        if not sft_tag:
            m = re.search(r'"sFTTag":"[^"]*value=\\"([^"\\]+)\\"', form_text)
            if m:
                sft_tag = m.group(1)
        if not url_post:
            m = re.search(r'"urlPost":"([^"]+)"', form_text)
            if m:
                url_post = m.group(1)
        if not sft_tag:
            try:
                sft_tag = form_text.split('name="PPFT" id="i0327" value="')[1].split('"')[0]
            except Exception:
                pass
        if not url_post:
            try:
                url_post = form_text.split("urlPost:'")[1].split("'")[0]
            except Exception:
                pass

        if not sft_tag or not url_post:
            print(f"[PURCHASER] XBL: Failed to extract PPFT/urlPost for {email}")
            return None

        # Step 2: Submit credentials
        login_data = urllib.parse.urlencode({
            "login": email,
            "loginfmt": email,
            "passwd": password,
            "PPFT": sft_tag,
        })
        r = s.post(
            url_post, data=login_data,
            headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
            allow_redirects=True, timeout=20,
        )

        final_url = str(r.url)
        access_token = ""

        if "access_token=" in final_url:
            access_token = final_url.split("access_token=")[1].split("&")[0]

        # Check redirect headers if no token in URL
        if not access_token and r.headers.get("location"):
            loc = r.headers["location"]
            if "access_token=" in loc:
                access_token = loc.split("access_token=")[1].split("&")[0]

        if not access_token:
            print(f"[PURCHASER] XBL: Login failed for {email} (bad creds or MFA)")
            return None

        # Step 3: XBL User Token
        xbl_r = requests.post(
            "https://user.auth.xboxlive.com/user/authenticate",
            json={
                "Properties": {
                    "AuthMethod": "RPS",
                    "SiteName": "user.auth.xboxlive.com",
                    "RpsTicket": access_token,
                },
                "RelyingParty": "http://auth.xboxlive.com",
                "TokenType": "JWT",
            },
            headers={"Content-Type": "application/json", "x-xbl-contract-version": "1"},
            timeout=15,
        )

        if xbl_r.status_code != 200:
            print(f"[PURCHASER] XBL: User token failed ({xbl_r.status_code}) for {email}")
            return None

        xbl_data = xbl_r.json()
        xbox_token = xbl_data.get("Token")
        uhs = (xbl_data.get("DisplayClaims") or {}).get("xui", [{}])[0].get("uhs")

        if not xbox_token or not uhs:
            print(f"[PURCHASER] XBL: Missing token/uhs for {email}")
            return None

        # Step 4: XSTS Token
        xsts_r = requests.post(
            "https://xsts.auth.xboxlive.com/xsts/authorize",
            json={
                "Properties": {
                    "SandboxId": "RETAIL",
                    "UserTokens": [xbox_token],
                },
                "RelyingParty": "http://xboxlive.com",
                "TokenType": "JWT",
            },
            headers={"Content-Type": "application/json", "x-xbl-contract-version": "1"},
            timeout=15,
        )

        if xsts_r.status_code == 401:
            print(f"[PURCHASER] XBL: No Xbox account for {email}")
            return None
        if xsts_r.status_code != 200:
            print(f"[PURCHASER] XBL: XSTS failed ({xsts_r.status_code}) for {email}")
            return None

        xsts_data = xsts_r.json()
        xsts_token = xsts_data.get("Token")
        xsts_uhs = (xsts_data.get("DisplayClaims") or {}).get("xui", [{}])[0].get("uhs") or uhs

        if not xsts_token:
            print(f"[PURCHASER] XBL: XSTS token missing for {email}")
            return None

        print(f"[PURCHASER] XBL3.0 login SUCCESS for {email}")
        return {
            "method": "xbl",
            "xbl_auth": f"XBL3.0 x={xsts_uhs};{xsts_token}",
            "uhs": xsts_uhs,
            "email": email,
        }

    except Exception as err:
        print(f"[PURCHASER] XBL login EXCEPTION for {email}: {err}")
        return None


# ── Product Search & Details ─────────────────────────────────

def search_products(query, market="US", language="en-US"):
    """Search Microsoft Store products."""
    try:
        r = requests.get(
            f"https://displaycatalog.mp.microsoft.com/v7.0/productFamilies/autosuggest"
            f"?market={market}&languages={language}&query={urllib.parse.quote(query)}&mediaType=games,apps",
            headers=DEFAULT_HEADERS, timeout=15,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        results = []
        for family in data.get("ResultSets", []):
            for suggest in family.get("Suggests", []):
                pid = suggest.get("ProductId")
                if not pid:
                    metas = suggest.get("Metas", [])
                    for meta in metas:
                        if meta.get("Key") == "BigCatId":
                            pid = meta.get("Value")
                            break
                results.append({
                    "title": suggest.get("Title"),
                    "productId": pid,
                    "type": suggest.get("Type") or family.get("Type"),
                    "imageUrl": suggest.get("ImageUrl"),
                })
        return results
    except Exception:
        return []


def get_product_details(product_id, market="US", language="en-US"):
    """Get detailed product info including SKUs and pricing."""
    try:
        r = requests.get(
            f"https://displaycatalog.mp.microsoft.com/v7.0/products"
            f"?bigIds={product_id}&market={market}&languages={language}",
            headers=DEFAULT_HEADERS, timeout=15,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        if not data.get("Products") or len(data["Products"]) == 0:
            return None
        product = data["Products"][0]
        title = (product.get("LocalizedProperties") or [{}])[0].get("ProductTitle", "Unknown")
        description = (product.get("LocalizedProperties") or [{}])[0].get("ShortDescription", "")

        skus = []
        for dsa in product.get("DisplaySkuAvailabilities", []):
            sku = dsa.get("Sku", {})
            sku_title = (sku.get("LocalizedProperties") or [{}])[0].get("SkuTitle") or title
            sku_id = sku.get("SkuId")
            for avail in dsa.get("Availabilities", []):
                price = (avail.get("OrderManagementData") or {}).get("Price")
                if price:
                    skus.append({
                        "skuId": sku_id,
                        "availabilityId": avail.get("AvailabilityId"),
                        "title": sku_title,
                        "price": price.get("ListPrice"),
                        "currency": price.get("CurrencyCode"),
                        "msrp": price.get("MSRP"),
                    })

        return {"productId": product_id, "title": title, "description": description, "skus": skus}
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
#  Store Cart State
# ═══════════════════════════════════════════════════════════════

def _generate_reference_id():
    timestamp_val = int(time.time() / 30)
    n = format(timestamp_val, "08X")
    o = (uuid.uuid4().hex + uuid.uuid4().hex).upper()
    result = []
    for e in range(64):
        if e % 8 == 1:
            idx = (e - 1) // 8
            result.append(n[idx] if idx < len(n) else "0")
        else:
            result.append(o[e] if e < len(o) else "0")
    return "".join(result)


def get_store_cart_state(session_info):
    """Get store cart state for WLID purchase flow."""
    s = session_info["session"]
    token = session_info["token"]
    try:
        ms_cv = "xddT7qMNbECeJpTq.6.2"
        payload = urllib.parse.urlencode({
            "data": '{"usePurchaseSdk":true}',
            "market": "US",
            "cV": ms_cv,
            "locale": "en-GB",
            "msaTicket": token,
            "pageFormat": "full",
            "urlRef": "https://account.microsoft.com/billing/redeem",
            "isRedeem": "true",
            "clientType": "AccountMicrosoftCom",
            "layout": "Inline",
            "cssOverride": "AMC",
            "scenario": "redeem",
            "timeToInvokeIframe": "4977",
            "sdkVersion": "VERSION_PLACEHOLDER",
        })

        r = s.post(
            f"https://www.microsoft.com/store/purchase/buynowui/redeemnow?ms-cv={ms_cv}&market=US&locale=en-GB&clientName=AccountMicrosoftCom",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )

        m = re.search(r'window\.__STORE_CART_STATE__=({.*?});', r.text, re.DOTALL)
        if not m:
            return None

        store_state = json.loads(m.group(1))
        ctx = store_state.get("appContext", {})
        return {
            "ms_cv": ctx.get("cv", ms_cv),
            "correlation_id": ctx.get("correlationId", ""),
            "tracking_id": ctx.get("trackingId", ""),
            "vector_id": ctx.get("muid", ""),
            "muid": ctx.get("alternativeMuid", ""),
        }
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
#  WLID Purchase Flow (Store Checkout)
# ═══════════════════════════════════════════════════════════════

def purchase_via_wlid(session_info, product_id, sku_id, availability_id, store_state):
    """Execute purchase via WLID store checkout."""
    s = session_info["session"]
    token = session_info["token"]
    try:
        reference_id = _generate_reference_id()

        purchase_headers = {
            "host": "buynow.production.store-web.dynamics.com",
            "connection": "keep-alive",
            "x-ms-tracking-id": store_state["tracking_id"],
            "authorization": f"WLID1.0=t={token}",
            "x-ms-client-type": "MicrosoftCom",
            "x-ms-market": "US",
            "ms-cv": store_state["ms_cv"],
            "x-ms-reference-id": reference_id,
            "x-ms-vector-id": store_state["vector_id"],
            "user-agent": UA,
            "x-ms-correlation-id": store_state["correlation_id"],
            "content-type": "application/json",
            "x-authorization-muid": store_state["muid"],
            "accept": "*/*",
        }

        # Step 1: Add to cart
        add_r = s.post(
            "https://buynow.production.store-web.dynamics.com/v1.0/Cart/AddToCart",
            headers=purchase_headers,
            json={"productId": product_id, "skuId": sku_id, "availabilityId": availability_id, "quantity": 1},
            timeout=20,
        )

        if add_r.status_code == 429:
            return {"success": False, "error": "Rate limited"}
        add_data = add_r.json()
        cart_events = (add_data.get("events", {}).get("cart") or [None])
        if cart_events[0] and cart_events[0].get("type") == "error":
            return {"success": False, "error": (cart_events[0].get("data") or {}).get("reason", "Cart error")}

        # Step 2: Prepare purchase
        prepare_r = s.post(
            "https://buynow.production.store-web.dynamics.com/v1.0/Purchase/PreparePurchase",
            headers={**purchase_headers, "x-ms-reference-id": _generate_reference_id()},
            json={},
            timeout=20,
        )

        if prepare_r.status_code == 429:
            return {"success": False, "error": "Rate limited during prepare"}
        prepare_data = prepare_r.json()

        payment_instruments = prepare_data.get("paymentInstruments", [])
        prep_cart = (prepare_data.get("events", {}).get("cart") or [None])
        if prep_cart[0] and prep_cart[0].get("type") == "error":
            return {"success": False, "error": (prep_cart[0].get("data") or {}).get("reason", "Prepare error")}

        total = (prepare_data.get("legalTextInfo") or {}).get("orderTotal") or prepare_data.get("orderTotal")

        # Step 3: Complete purchase
        purchase_payload = {}
        has_balance = any(pi.get("type") in ("storedValue", "balance") for pi in payment_instruments)

        if has_balance:
            balance_inst = next((pi for pi in payment_instruments if pi.get("type") in ("storedValue", "balance")), None)
            if balance_inst:
                purchase_payload["paymentInstrumentId"] = balance_inst["id"]
        elif len(payment_instruments) > 0:
            purchase_payload["paymentInstrumentId"] = payment_instruments[0]["id"]
        else:
            return {"success": False, "error": "No payment method available"}

        complete_r = s.post(
            "https://buynow.production.store-web.dynamics.com/v1.0/Purchase/CompletePurchase",
            headers={**purchase_headers, "x-ms-reference-id": _generate_reference_id()},
            json=purchase_payload,
            timeout=20,
        )

        if complete_r.status_code == 429:
            return {"success": False, "error": "Rate limited during purchase"}
        complete_data = complete_r.json()

        comp_cart = (complete_data.get("events", {}).get("cart") or [None])
        if comp_cart[0] and comp_cart[0].get("type") == "error":
            return {"success": False, "error": (comp_cart[0].get("data") or {}).get("reason", "Purchase failed")}

        if complete_data.get("orderId") or complete_data.get("events", {}).get("purchase"):
            return {"success": True, "orderId": complete_data.get("orderId", "N/A"), "total": total or "N/A", "method": "WLID Store"}

        return {"success": True, "orderId": "Completed", "total": total or "N/A", "method": "WLID Store"}

    except Exception as err:
        return {"success": False, "error": str(err)}


# ═══════════════════════════════════════════════════════════════
#  XBL3.0 Purchase Flow (Xbox purchase API — fallback)
# ═══════════════════════════════════════════════════════════════

def purchase_via_xbl(session_info, product_id, sku_id):
    """Execute purchase via XBL3.0 Xbox Live API."""
    try:
        print(f"[PURCHASER] XBL3.0 purchase attempt for {session_info['email']}")

        purchase_headers = {
            "Authorization": session_info["xbl_auth"],
            "Content-Type": "application/json",
            "x-xbl-contract-version": "1",
            "User-Agent": UA,
        }

        purchase_payload = {
            "purchaseRequest": {
                "productId": product_id,
                "skuId": sku_id,
                "quantity": 1,
            },
        }

        r = requests.post(
            "https://purchase.xboxlive.com/v7.0/purchases",
            headers=purchase_headers,
            json=purchase_payload,
            timeout=20,
        )

        status = r.status_code

        if 200 <= status < 300:
            try:
                res_data = r.json()
            except Exception:
                res_data = {}
            print(f"[PURCHASER] XBL3.0 purchase SUCCESS for {session_info['email']}")
            return {
                "success": True,
                "orderId": res_data.get("orderId", "XBL-Completed"),
                "total": "N/A",
                "method": "XBL3.0",
            }

        err_msg = f"HTTP {status}"
        try:
            err_data = r.json()
            err_msg = f"{err_data.get('code', status)} - {err_data.get('description') or err_data.get('message', '')}".strip()
        except Exception:
            pass

        print(f"[PURCHASER] XBL3.0 purchase FAILED for {session_info['email']}: {err_msg}")
        return {"success": False, "error": err_msg, "method": "XBL3.0"}

    except Exception as err:
        return {"success": False, "error": str(err), "method": "XBL3.0"}


# ═══════════════════════════════════════════════════════════════
#  Main Purchase Pipeline — tries WLID first, then XBL3.0
# ═══════════════════════════════════════════════════════════════

def purchase_items(accounts, product_id, sku_id, availability_id, on_progress=None, stop_event=None):
    """
    Purchase an item on multiple accounts.
    Tries WLID store checkout first, falls back to XBL3.0.
    """
    parsed = []
    for a in accounts:
        i = a.find(":")
        if i == -1:
            parsed.append({"email": a, "password": ""})
        else:
            parsed.append({"email": a[:i], "password": a[i + 1:]})

    results = []

    for idx, acc in enumerate(parsed):
        if stop_event and stop_event.is_set():
            break

        email = acc["email"]
        password = acc["password"]

        if on_progress:
            on_progress("login", {"email": email, "done": idx, "total": len(parsed)})

        # ── Try WLID store login first ──
        session = login_to_store(email, password)
        purchase_result = None

        if session:
            if on_progress:
                on_progress("cart", {"email": email, "done": idx, "total": len(parsed)})

            store_state = get_store_cart_state(session)
            if store_state:
                if on_progress:
                    on_progress("purchase", {"email": email, "done": idx, "total": len(parsed)})
                purchase_result = purchase_via_wlid(session, product_id, sku_id, availability_id, store_state)
            else:
                print(f"[PURCHASER] WLID store state failed for {email}, trying XBL3.0 fallback...")
        else:
            print(f"[PURCHASER] WLID login failed for {email}, trying XBL3.0 fallback...")

        # ── Fallback to XBL3.0 if WLID failed ──
        if not purchase_result or not purchase_result.get("success"):
            wlid_error = (purchase_result or {}).get("error", "WLID flow failed")

            xbl_session = login_xbox_live(email, password)
            if xbl_session:
                if on_progress:
                    on_progress("purchase", {"email": email, "done": idx, "total": len(parsed), "method": "XBL3.0"})
                purchase_result = purchase_via_xbl(xbl_session, product_id, sku_id)

                if not purchase_result.get("success"):
                    # Both failed — report both errors
                    purchase_result["error"] = f"WLID: {wlid_error} | XBL: {purchase_result.get('error', '')}"
            else:
                purchase_result = {"success": False, "error": f"WLID: {wlid_error} | XBL: Login failed"}

        results.append({"email": email, **purchase_result})

        if on_progress:
            on_progress("result", {"email": email, **purchase_result, "done": idx + 1, "total": len(parsed)})

        # Small delay between accounts
        if idx < len(parsed) - 1:
            time.sleep(2)

    return results
