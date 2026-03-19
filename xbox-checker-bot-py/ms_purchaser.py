"""
Microsoft Store Purchaser -- Python terminal version
Uses the SAME login flow as ms_puller.py.
Two purchase flows:
  1. WLID Store Checkout (primary)
  2. XBL3.0 Xbox Live API (fallback)
"""
import re
import uuid
import time
import json
import threading
import urllib.parse
import requests

# ── Session helpers (same pattern as puller) ──────────────────

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0"

DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class CookieSession:
    """Simple cookie-preserving session mirroring the JS sessionFetch."""
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def get(self, url, **kwargs):
        return self.session.get(url, allow_redirects=True, timeout=20, **kwargs)

    def post(self, url, data=None, **kwargs):
        return self.session.post(url, data=data, allow_redirects=True, timeout=20, **kwargs)


# ── PPFT / urlPost extraction (same as puller) ────────────────

def _extract_ppft_urlpost(page_text):
    ppft = ""
    url_post = ""

    m = re.search(r'"sFTTag":"[^"]*value=\\"([^"\\]+)\\"', page_text)
    if m:
        ppft = m.group(1)
    if not ppft:
        m = re.search(r'name="PPFT"[^>]*value="([^"]+)"', page_text)
        if m:
            ppft = m.group(1)
    if not ppft:
        try:
            ppft = page_text.split('name="PPFT" id="i0327" value="')[1].split('"')[0]
        except (IndexError, ValueError):
            pass

    m = re.search(r'"urlPost":"([^"]+)"', page_text)
    if m:
        url_post = m.group(1)
    if not url_post:
        try:
            url_post = page_text.split("urlPost:'")[1].split("'")[0]
        except (IndexError, ValueError):
            pass

    return ppft, url_post


# ═══════════════════════════════════════════════════════════════
#  WLID Store Login (same flow as Puller)
# ═══════════════════════════════════════════════════════════════

def login_to_store(email, password):
    """Login to Microsoft Store and get WLID token."""
    cs = CookieSession()
    try:
        bk = int(time.time())
        init_url = (
            f"https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=19&ct={bk}"
            f"&rver=7.0.6738.0&wp=MBI_SSL"
            f"&wreply=https://account.microsoft.com/auth/complete-signin"
            f"&lc=1033&id=292666&username={urllib.parse.quote(email)}"
        )
        r = cs.get(init_url)
        ppft, url_post = _extract_ppft_urlpost(r.text)
        if not ppft or not url_post:
            return None, "Failed to extract PPFT/urlPost"

        # Submit credentials
        login_data = {
            "i13": "1", "login": email, "loginfmt": email,
            "type": "11", "LoginOptions": "1", "passwd": password,
            "ps": "2", "PPFT": ppft, "PPSX": "PassportR",
            "NewUser": "1", "FoundMSAs": "", "fspost": "0",
            "i21": "0", "CookieDisclosure": "0", "IsFidoSupported": "0",
            "isSignupPost": "0", "isRecoveryAttemptPost": "0", "i19": "9960",
        }
        r = cs.post(url_post, data=login_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"})

        cleaned = r.text.replace("\\", "")
        if "sErrTxt" in cleaned or "account or password is incorrect" in cleaned:
            return None, "Bad credentials"
        if "identity/confirm" in cleaned or "Abuse" in cleaned:
            return None, "Account locked/MFA"

        # Follow redirect chain
        reurl_m = re.search(r'replace\("([^"]+)"', cleaned)
        if reurl_m:
            r = cs.get(reurl_m.group(1))
            action_m = re.search(r'<form.*?action="(.*?)".*?>', r.text)
            if action_m:
                inputs = re.findall(r'<input.*?name="(.*?)".*?value="(.*?)".*?>', r.text)
                form_data = {n: v for n, v in inputs}
                cs.post(action_m.group(1), data=form_data,
                        headers={"Content-Type": "application/x-www-form-urlencoded"})

        # Acquire store auth token
        try:
            cs.get("https://buynowui.production.store-web.dynamics.com/akam/13/79883e11")
        except Exception:
            pass

        token_r = cs.session.get(
            "https://account.microsoft.com/auth/acquire-onbehalf-of-token?scopes=MSComServiceMBISSL",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Referer": "https://account.microsoft.com/billing/redeem",
            },
            timeout=20,
        )
        if token_r.status_code != 200:
            return None, f"Token request HTTP {token_r.status_code}"

        token_data = token_r.json()
        if not token_data or not token_data[0].get("token"):
            return None, "No token in response"

        return {
            "method": "wlid",
            "token": token_data[0]["token"],
            "session": cs,
            "email": email,
        }, None

    except Exception as ex:
        return None, str(ex)


# ═══════════════════════════════════════════════════════════════
#  XBL3.0 Fallback Login
# ═══════════════════════════════════════════════════════════════

XBOX_OAUTH_URL = (
    "https://login.live.com/oauth20_authorize.srf"
    "?client_id=00000000402B5328"
    "&redirect_uri=https://login.live.com/oauth20_desktop.srf"
    "&scope=service::user.auth.xboxlive.com::MBI_SSL"
    "&display=touch&response_type=token&locale=en"
)


def login_xbox_live(email, password):
    """XBL OAuth login -- returns xblAuth string or None."""
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    try:
        r = s.get(XBOX_OAUTH_URL, allow_redirects=True, timeout=15)
        ppft, url_post = _extract_ppft_urlpost(r.text)
        if not ppft or not url_post:
            return None, "Failed to extract PPFT/urlPost"

        r = s.post(url_post, data={
            "login": email, "loginfmt": email,
            "passwd": password, "PPFT": ppft,
        }, headers={"Content-Type": "application/x-www-form-urlencoded"},
            allow_redirects=True, timeout=15)

        final_url = str(r.url)
        access_token = ""
        if "access_token=" in final_url:
            access_token = final_url.split("access_token=")[1].split("&")[0]
        if not access_token and "#" in final_url:
            fragment = final_url.split("#", 1)[1]
            params = urllib.parse.parse_qs(fragment)
            access_token = params.get("access_token", [""])[0]

        if not access_token:
            return None, "Login failed (bad creds or MFA)"

        # XBL User Token
        xbl_r = requests.post("https://user.auth.xboxlive.com/user/authenticate",
                              json={
                                  "RelyingParty": "http://auth.xboxlive.com",
                                  "TokenType": "JWT",
                                  "Properties": {
                                      "AuthMethod": "RPS",
                                      "SiteName": "user.auth.xboxlive.com",
                                      "RpsTicket": access_token,
                                  },
                              }, timeout=15)
        if xbl_r.status_code != 200:
            return None, f"XBL user token failed ({xbl_r.status_code})"

        user_token = xbl_r.json()["Token"]

        # XSTS Token
        xsts_r = requests.post("https://xsts.auth.xboxlive.com/xsts/authorize",
                               json={
                                   "RelyingParty": "http://xboxlive.com",
                                   "TokenType": "JWT",
                                   "Properties": {
                                       "UserTokens": [user_token],
                                       "SandboxId": "RETAIL",
                                   },
                               }, timeout=15)
        if xsts_r.status_code != 200:
            return None, f"XSTS failed ({xsts_r.status_code})"

        xsts_data = xsts_r.json()
        uhs = xsts_data.get("DisplayClaims", {}).get("xui", [{}])[0].get("uhs", "")
        xsts_token = xsts_data["Token"]

        return {
            "method": "xbl",
            "xbl_auth": f"XBL3.0 x={uhs};{xsts_token}",
            "email": email,
        }, None

    except Exception as ex:
        return None, str(ex)


# ── Product Search & Details ──────────────────────────────────

def search_products(query, market="US"):
    """Search Microsoft Store for products."""
    try:
        r = requests.get(
            f"https://displaycatalog.mp.microsoft.com/v7.0/productFamilies/autosuggest"
            f"?market={market}&languages=en-US&query={urllib.parse.quote(query)}&mediaType=games,apps",
            headers={"User-Agent": UA, "Accept": "application/json"},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            results = []
            for family in data.get("ResultSets", []):
                for suggest in family.get("Suggests", []):
                    pid = suggest.get("ProductId") or ""
                    if not pid:
                        for meta in suggest.get("Metas", []):
                            if meta.get("Key") == "BigCatId":
                                pid = meta.get("Value", "")
                                break
                    results.append({
                        "title": suggest.get("Title", "Unknown"),
                        "productId": pid,
                        "type": suggest.get("Type") or family.get("Type", ""),
                    })
            if results:
                return results

        # Fallback: search API
        r2 = requests.get(
            f"https://displaycatalog.mp.microsoft.com/v7.0/products/search"
            f"?market={market}&languages=en-US&query={urllib.parse.quote(query)}&mediaType=games,apps&count=10",
            headers={"User-Agent": UA, "Accept": "application/json"},
            timeout=15,
        )
        if r2.status_code == 200:
            data2 = r2.json()
            return [
                {
                    "title": p.get("LocalizedProperties", [{}])[0].get("ProductTitle", "Unknown"),
                    "productId": p.get("ProductId", ""),
                    "type": p.get("ProductType", ""),
                }
                for p in data2.get("Products", [])
            ]
        return []
    except Exception:
        return []


def get_product_details(product_id, market="US"):
    """Get product details including SKUs."""
    try:
        r = requests.get(
            f"https://displaycatalog.mp.microsoft.com/v7.0/products?bigIds={product_id}&market={market}&languages=en-US",
            headers={"User-Agent": UA, "Accept": "application/json"},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        if not data.get("Products"):
            return None

        product = data["Products"][0]
        title = product.get("LocalizedProperties", [{}])[0].get("ProductTitle", "Unknown")

        skus = []
        for dsa in product.get("DisplaySkuAvailabilities", []):
            sku = dsa.get("Sku", {})
            sku_id = sku.get("SkuId")
            sku_title = sku.get("LocalizedProperties", [{}])[0].get("SkuTitle", title)
            for avail in dsa.get("Availabilities", []):
                price = avail.get("OrderManagementData", {}).get("Price", {})
                if price:
                    skus.append({
                        "skuId": sku_id,
                        "availabilityId": avail.get("AvailabilityId"),
                        "title": sku_title,
                        "price": price.get("ListPrice", 0),
                        "currency": price.get("CurrencyCode", "USD"),
                    })

        return {"productId": product_id, "title": title, "skus": skus}
    except Exception:
        return None


# ── Reference ID (same as JS) ────────────────────────────────

def _generate_reference_id():
    ts = int(time.time() / 30)
    n = format(ts, "08X")
    o = (uuid.uuid4().hex + uuid.uuid4().hex).upper()
    result = []
    for e in range(64):
        if e % 8 == 1:
            idx = (e - 1) // 8
            result.append(n[idx] if idx < len(n) else "0")
        else:
            result.append(o[e] if e < len(o) else "0")
    return "".join(result)


# ── WLID Purchase ────────────────────────────────────────────

def _get_store_cart_state(wlid_session):
    try:
        ms_cv = "xddT7qMNbECeJpTq.6.2"
        token = wlid_session["token"]
        cs = wlid_session["session"]

        payload = urllib.parse.urlencode({
            "data": '{"usePurchaseSdk":true}',
            "market": "US", "cV": ms_cv, "locale": "en-GB",
            "msaTicket": token, "pageFormat": "full",
            "urlRef": "https://account.microsoft.com/billing/redeem",
            "isRedeem": "true", "clientType": "AccountMicrosoftCom",
            "layout": "Inline", "cssOverride": "AMC", "scenario": "redeem",
            "timeToInvokeIframe": "4977", "sdkVersion": "VERSION_PLACEHOLDER",
        })
        r = cs.post(
            f"https://www.microsoft.com/store/purchase/buynowui/redeemnow?ms-cv={ms_cv}&market=US&locale=en-GB&clientName=AccountMicrosoftCom",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        m = re.search(r'window\.__STORE_CART_STATE__=({.*?});', r.text, re.DOTALL)
        if not m:
            return None
        state = json.loads(m.group(1))
        ctx = state.get("appContext", {})
        return {
            "ms_cv": ctx.get("cv", ms_cv),
            "correlation_id": ctx.get("correlationId", ""),
            "tracking_id": ctx.get("trackingId", ""),
            "vector_id": ctx.get("muid", ""),
            "muid": ctx.get("alternativeMuid", ""),
        }
    except Exception:
        return None


def _purchase_via_wlid(wlid_session, product_id, sku_id, availability_id, store_state):
    try:
        cs = wlid_session["session"]
        token = wlid_session["token"]

        hdrs = {
            "x-ms-tracking-id": store_state["tracking_id"],
            "authorization": f"WLID1.0=t={token}",
            "x-ms-client-type": "MicrosoftCom",
            "x-ms-market": "US",
            "ms-cv": store_state["ms_cv"],
            "x-ms-reference-id": _generate_reference_id(),
            "x-ms-vector-id": store_state["vector_id"],
            "x-ms-correlation-id": store_state["correlation_id"],
            "content-type": "application/json",
            "x-authorization-muid": store_state["muid"],
            "accept": "*/*",
        }

        # Add to cart
        r = cs.session.post(
            "https://buynow.production.store-web.dynamics.com/v1.0/Cart/AddToCart",
            headers=hdrs,
            json={"productId": product_id, "skuId": sku_id,
                  "availabilityId": availability_id, "quantity": 1},
            timeout=20,
        )
        if r.status_code == 429:
            return {"success": False, "error": "Rate limited"}
        data = r.json()
        cart_err = (data.get("events", {}).get("cart") or [{}])[0]
        if cart_err.get("type") == "error":
            reason = (cart_err.get("data") or {}).get("reason", "Cart error")
            return {"success": False, "error": reason}

        # Prepare purchase
        hdrs["x-ms-reference-id"] = _generate_reference_id()
        r = cs.session.post(
            "https://buynow.production.store-web.dynamics.com/v1.0/Purchase/PreparePurchase",
            headers=hdrs, json={}, timeout=20,
        )
        if r.status_code == 429:
            return {"success": False, "error": "Rate limited during prepare"}
        prep = r.json()
        prep_err = (prep.get("events", {}).get("cart") or [{}])[0]
        if prep_err.get("type") == "error":
            return {"success": False, "error": (prep_err.get("data") or {}).get("reason", "Prepare error")}

        pis = prep.get("paymentInstruments", [])
        total = prep.get("legalTextInfo", {}).get("orderTotal") or prep.get("orderTotal", "N/A")

        # Select payment method
        purchase_payload = {}
        balance = next((pi for pi in pis if pi.get("type") in ("storedValue", "balance")), None)
        if balance:
            purchase_payload["paymentInstrumentId"] = balance["id"]
        elif pis:
            purchase_payload["paymentInstrumentId"] = pis[0]["id"]
        else:
            return {"success": False, "error": "No payment method available"}

        # Complete purchase
        hdrs["x-ms-reference-id"] = _generate_reference_id()
        r = cs.session.post(
            "https://buynow.production.store-web.dynamics.com/v1.0/Purchase/CompletePurchase",
            headers=hdrs, json=purchase_payload, timeout=20,
        )
        if r.status_code == 429:
            return {"success": False, "error": "Rate limited during purchase"}
        comp = r.json()
        comp_err = (comp.get("events", {}).get("cart") or [{}])[0]
        if comp_err.get("type") == "error":
            return {"success": False, "error": (comp_err.get("data") or {}).get("reason", "Purchase failed")}

        order_id = comp.get("orderId", "Completed")
        return {"success": True, "orderId": order_id, "total": total, "method": "WLID Store"}

    except Exception as ex:
        return {"success": False, "error": str(ex)}


# ── XBL3.0 Purchase ──────────────────────────────────────────

def _purchase_via_xbl(xbl_session, product_id, sku_id):
    try:
        r = requests.post(
            "https://purchase.xboxlive.com/v7.0/purchases",
            headers={
                "Authorization": xbl_session["xbl_auth"],
                "Content-Type": "application/json",
                "x-xbl-contract-version": "1",
                "User-Agent": UA,
            },
            json={"purchaseRequest": {"productId": product_id, "skuId": sku_id, "quantity": 1}},
            timeout=15,
        )
        if 200 <= r.status_code < 300:
            data = r.json() if r.text else {}
            return {"success": True, "orderId": data.get("orderId", "XBL-Completed"),
                    "total": "N/A", "method": "XBL3.0"}

        err_msg = f"HTTP {r.status_code}"
        try:
            err_data = r.json()
            err_msg = f"{err_data.get('code', r.status_code)} - {err_data.get('description', '')}".strip()
        except Exception:
            pass
        return {"success": False, "error": err_msg, "method": "XBL3.0"}
    except Exception as ex:
        return {"success": False, "error": str(ex), "method": "XBL3.0"}


# ═══════════════════════════════════════════════════════════════
#  Main Pipeline
# ═══════════════════════════════════════════════════════════════

def purchase_items(accounts, product_id, sku_id, availability_id, on_progress=None, stop_event=None):
    """Purchase a product using multiple accounts. WLID first, XBL3.0 fallback."""
    parsed = []
    for a in accounts:
        i = a.find(":")
        if i == -1:
            parsed.append((a, ""))
        else:
            parsed.append((a[:i], a[i + 1:]))

    results = []

    for idx, (email, password) in enumerate(parsed):
        if stop_event and stop_event.is_set():
            break

        if on_progress:
            on_progress("login", {"email": email, "done": idx, "total": len(parsed)})

        # Try WLID first
        session, err = login_to_store(email, password)
        purchase_result = None

        if session:
            if on_progress:
                on_progress("cart", {"email": email, "done": idx, "total": len(parsed)})

            store_state = _get_store_cart_state(session)
            if store_state:
                if on_progress:
                    on_progress("purchase", {"email": email, "done": idx, "total": len(parsed)})
                purchase_result = _purchase_via_wlid(session, product_id, sku_id, availability_id, store_state)

        # Fallback to XBL3.0
        if not purchase_result or not purchase_result.get("success"):
            wlid_error = (purchase_result or {}).get("error", err or "WLID flow failed")

            xbl_session, xbl_err = login_xbox_live(email, password)
            if xbl_session:
                if on_progress:
                    on_progress("purchase", {"email": email, "done": idx, "total": len(parsed), "method": "XBL3.0"})
                purchase_result = _purchase_via_xbl(xbl_session, product_id, sku_id)
                if not purchase_result.get("success"):
                    purchase_result["error"] = f"WLID: {wlid_error} | XBL: {purchase_result['error']}"
            else:
                purchase_result = {"success": False, "error": f"WLID: {wlid_error} | XBL: {xbl_err or 'Login failed'}"}

        results.append({"email": email, **purchase_result})

        if on_progress:
            on_progress("result", {"email": email, **purchase_result, "done": idx + 1, "total": len(parsed)})

        if idx < len(parsed) - 1:
            time.sleep(2)

    return results


# ═══════════════════════════════════════════════════════════════
#  CLI entry point
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    import os

    print("=" * 60)
    print("  Microsoft Store Purchaser")
    print("  made by talkneon")
    print("=" * 60)
    print()

    # Load accounts
    accounts_file = input("Accounts file path (email:pass): ").strip()
    if not os.path.exists(accounts_file):
        print(f"[ERROR] File not found: {accounts_file}")
        sys.exit(1)

    with open(accounts_file, "r") as f:
        accounts = [l.strip() for l in f if ":" in l.strip()]

    if not accounts:
        print("[ERROR] No valid accounts found")
        sys.exit(1)

    print(f"[INFO] Loaded {len(accounts)} accounts")

    # Product input
    product_input = input("Product ID, URL, or search query: ").strip()
    if not product_input:
        print("[ERROR] No product specified")
        sys.exit(1)

    # Resolve product ID
    product_id = product_input
    url_match = re.search(r'/store/[^/]+/([a-zA-Z0-9]{12})', product_input) or re.search(r'/p/([a-zA-Z0-9]{12})', product_input)
    if url_match:
        product_id = url_match.group(1)

    if len(product_id) > 12 or " " in product_id:
        print(f"\n[SEARCH] Searching for: {product_id}")
        results = search_products(product_id)
        if not results:
            print("[ERROR] No products found")
            sys.exit(1)
        print()
        for i, r in enumerate(results[:10]):
            print(f"  {i + 1}. {r['title']}")
            print(f"     ID: {r['productId']}  Type: {r['type']}")
        print()
        choice = input("Enter product number or ID: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(results):
            product_id = results[int(choice) - 1]["productId"]
        else:
            product_id = choice

    # Get product details
    print(f"\n[INFO] Fetching product details for: {product_id}")
    product = get_product_details(product_id)
    if not product:
        print("[ERROR] Product not found")
        sys.exit(1)
    if not product.get("skus"):
        print("[ERROR] No purchasable SKUs found")
        sys.exit(1)

    sku = product["skus"][0]
    print(f"  Product: {product['title']}")
    print(f"  Price:   {sku['price']} {sku['currency']}")
    print(f"  SKU:     {sku['skuId']}")
    print()

    confirm = input("Proceed with purchase? (y/n): ").strip().lower()
    if confirm != "y":
        print("[INFO] Cancelled")
        sys.exit(0)

    print()
    purchased = 0
    failed = 0

    def progress_cb(phase, detail):
        nonlocal purchased, failed
        email = detail.get("email", "")
        done = detail.get("done", 0)
        total = detail.get("total", len(accounts))

        if phase == "login":
            print(f"  [{done + 1}/{total}] Logging in: {email}")
        elif phase == "cart":
            print(f"           Loading cart...")
        elif phase == "purchase":
            method = detail.get("method", "WLID")
            print(f"           Purchasing via {method}...")
        elif phase == "result":
            if detail.get("success"):
                purchased += 1
                order_id = detail.get("orderId", "OK")
                print(f"           [+] Success -- Order: {order_id}")
            else:
                failed += 1
                error = detail.get("error", "Unknown error")
                print(f"           [x] Failed -- {error}")

    results = purchase_items(
        accounts, product_id, sku["skuId"], sku.get("availabilityId", ""),
        on_progress=progress_cb,
    )

    # Save results
    os.makedirs("results", exist_ok=True)
    success_results = [r for r in results if r.get("success")]
    failed_results = [r for r in results if not r.get("success")]

    if success_results:
        with open("results/purchased.txt", "w") as f:
            for r in success_results:
                f.write(f"{r['email']} | {r.get('orderId', 'OK')} | {r.get('total', 'N/A')}\n")

    if failed_results:
        with open("results/purchase_failed.txt", "w") as f:
            for r in failed_results:
                f.write(f"{r['email']} | {r.get('error', 'Failed')}\n")

    print()
    print("=" * 60)
    print(f"  Purchase Complete")
    print(f"  Product:    {product['title']}")
    print(f"  Purchased:  {purchased}")
    print(f"  Failed:     {failed}")
    print(f"  Total:      {len(results)}")
    print("=" * 60)
