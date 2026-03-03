// ============================================================
//  Microsoft Store Purchaser
//  Logs into Microsoft Store, searches for products, and
//  completes purchases using account balance or payment methods.
// ============================================================

const crypto = require("crypto");
const { proxiedFetch } = require("./proxy-manager");

// ── Cookie-aware fetch (reused pattern from puller) ──────────

function extractCookiesFromResponse(res, cookieJar) {
  const setCookies = res.headers.getSetCookie?.() || [];
  for (const c of setCookies) {
    const parts = c.split(";")[0].trim();
    if (parts.includes("=")) {
      cookieJar.push(parts);
    }
  }
}

function getCookieString(cookieJar) {
  return cookieJar.join("; ");
}

async function sessionFetch(url, options, cookieJar) {
  let currentUrl = url;
  let method = options.method || "GET";
  let body = options.body;
  let maxRedirects = 15;

  while (maxRedirects-- > 0) {
    const res = await proxiedFetch(currentUrl, {
      ...options,
      method,
      body,
      headers: {
        ...options.headers,
        Cookie: getCookieString(cookieJar),
      },
      redirect: "manual",
    });

    extractCookiesFromResponse(res, cookieJar);

    const status = res.status;
    if (status >= 300 && status < 400) {
      const location = res.headers.get("location");
      if (!location) break;
      currentUrl = new URL(location, currentUrl).href;
      if (status !== 307 && status !== 308) {
        method = "GET";
        body = undefined;
      }
      try { await res.text(); } catch {}
      continue;
    }

    const text = await res.text();
    return { res, text, finalUrl: currentUrl };
  }

  throw new Error("Too many redirects");
}

// ── Microsoft Store Login ────────────────────────────────────

const DEFAULT_HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
  Accept:
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
  "Accept-Language": "en-US,en;q=0.9",
};

async function loginToStore(email, password) {
  const cookieJar = [];
  const headers = { ...DEFAULT_HEADERS };

  try {
    // Step 1: Navigate to store login
    console.log(`[PURCHASER] Step 1: Fetching login page for ${email}`);
    const { text: loginPage } = await sessionFetch(
      "https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=173&ct=&rver=7.5.2211.0&wp=MBI_SSL&wreply=https://account.microsoft.com/auth/complete-signin&lc=1033&id=292666&contextid=&bk=&uaid=&pid=0",
      { headers },
      cookieJar
    );

    // Extract PPFT and urlPost
    const ppftMatch = loginPage.match(/name="PPFT".*?value="([^"]+)"/s) || loginPage.match(/value="([^"]+)".*?name="PPFT"/s);
    const urlPostMatch = loginPage.match(/"urlPost":"([^"]+)"/s) || loginPage.match(/urlPost:'([^']+)'/s);

    if (!ppftMatch || !urlPostMatch) {
      console.log(`[PURCHASER] PPFT found: ${!!ppftMatch}, urlPost found: ${!!urlPostMatch}`);
      console.log(`[PURCHASER] Login page length: ${loginPage.length}, snippet: ${loginPage.substring(0, 500)}`);
      return null;
    }
    console.log(`[PURCHASER] Step 1 OK - PPFT and urlPost extracted`);

    // Step 2: Submit credentials
    const loginBody = new URLSearchParams({
      login: email,
      loginfmt: email,
      passwd: password,
      PPFT: ppftMatch[1],
    });

    const { text: loginResp, finalUrl } = await sessionFetch(urlPostMatch[1], {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/x-www-form-urlencoded" },
      body: loginBody.toString(),
    }, cookieJar);

    console.log(`[PURCHASER] Step 2 OK - Login submitted, finalUrl: ${finalUrl}`);

    // Check for login errors in response
    if (loginResp.includes("Your account or password is incorrect") || loginResp.includes("AADSTS50126")) {
      console.log(`[PURCHASER] Bad credentials for ${email}`);
      return null;
    }

    // Step 3: Handle post-login redirect forms
    const formAction = loginResp.match(/<form[^>]*action="([^"]+)"/);
    if (formAction) {
      console.log(`[PURCHASER] Step 3: Following redirect form to ${formAction[1]}`);
      const inputMatches = [...loginResp.matchAll(/<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"/g)];
      const formData = new URLSearchParams();
      for (const m of inputMatches) formData.append(m[1], m[2]);

      await sessionFetch(formAction[1], {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/x-www-form-urlencoded" },
        body: formData.toString(),
      }, cookieJar);
      console.log(`[PURCHASER] Step 3 OK - Redirect form submitted`);
    } else {
      console.log(`[PURCHASER] Step 3: No redirect form found`);
    }

    // Step 4: Get store auth token
    console.log(`[PURCHASER] Step 4: Acquiring store token`);
    const tokenRes = await proxiedFetch(
      "https://account.microsoft.com/auth/acquire-onbehalf-of-token?scopes=MSComServiceMBISSL",
      {
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
          Referer: "https://account.microsoft.com/",
          "User-Agent": headers["User-Agent"],
          Cookie: getCookieString(cookieJar),
        },
      }
    );

    console.log(`[PURCHASER] Token response status: ${tokenRes.status}`);
    if (tokenRes.status !== 200) {
      const errText = await tokenRes.text();
      console.log(`[PURCHASER] Token error: ${errText.substring(0, 300)}`);
      return null;
    }
    const tokenData = await tokenRes.json();
    if (!tokenData || !tokenData[0]?.token) {
      console.log(`[PURCHASER] No token in response:`, JSON.stringify(tokenData).substring(0, 300));
      return null;
    }

    console.log(`[PURCHASER] Login SUCCESS for ${email}`);
    return {
      token: tokenData[0].token,
      cookieJar,
      headers,
      email,
    };
  } catch (err) {
    console.error(`[PURCHASER] Login EXCEPTION for ${email}:`, err.message);
    return null;
  }
}

// ── Product Search ───────────────────────────────────────────

async function searchProducts(query, market = "US", language = "en-US") {
  try {
    const res = await proxiedFetch(
      `https://displaycatalog.mp.microsoft.com/v7.0/productFamilies/autosuggest?market=${market}&languages=${language}&query=${encodeURIComponent(query)}&mediaType=games,apps`,
      { headers: DEFAULT_HEADERS }
    );

    if (res.status !== 200) return [];
    const data = await res.json();

    const results = [];
    for (const family of data.ResultSets || []) {
      for (const suggest of family.Suggests || []) {
        results.push({
          title: suggest.Title,
          productId: suggest.ProductId || suggest.Metas?.find(m => m.Key === "BigCatId")?.Value,
          type: suggest.Type || family.Type,
          imageUrl: suggest.ImageUrl,
        });
      }
    }
    return results;
  } catch {
    return [];
  }
}

async function getProductDetails(productId, market = "US", language = "en-US") {
  try {
    const res = await proxiedFetch(
      `https://displaycatalog.mp.microsoft.com/v7.0/products?bigIds=${productId}&market=${market}&languages=${language}`,
      { headers: DEFAULT_HEADERS }
    );

    if (res.status !== 200) return null;
    const data = await res.json();

    if (!data.Products || data.Products.length === 0) return null;
    const product = data.Products[0];

    const title = product.LocalizedProperties?.[0]?.ProductTitle || "Unknown";
    const description = product.LocalizedProperties?.[0]?.ShortDescription || "";

    const skus = [];
    for (const dsa of product.DisplaySkuAvailabilities || []) {
      const sku = dsa.Sku;
      const skuTitle = sku?.LocalizedProperties?.[0]?.SkuTitle || title;
      const skuId = sku?.SkuId;

      for (const avail of dsa.Availabilities || []) {
        const price = avail.OrderManagementData?.Price;
        if (price) {
          skus.push({
            skuId,
            availabilityId: avail.AvailabilityId,
            title: skuTitle,
            price: price.ListPrice,
            currency: price.CurrencyCode,
            msrp: price.MSRP,
          });
        }
      }
    }

    return { productId, title, description, skus };
  } catch {
    return null;
  }
}

// ── Purchase Flow ────────────────────────────────────────────

function generateReferenceId() {
  const timestampVal = Math.floor(Date.now() / 30000);
  const n = timestampVal.toString(16).toUpperCase().padStart(8, "0");
  const o = (crypto.randomUUID().replace(/-/g, "") + crypto.randomUUID().replace(/-/g, "")).toUpperCase();
  const result = [];
  for (let e = 0; e < 64; e++) {
    if (e % 8 === 1) {
      result.push(n[Math.floor((e - 1) / 8)] || "0");
    } else {
      result.push(o[e] || "0");
    }
  }
  return result.join("");
}

async function getStoreCartState(session) {
  try {
    const msCv = crypto.randomUUID().replace(/-/g, "").substring(0, 16) + ".1";
    const payload = new URLSearchParams({
      data: '{"usePurchaseSdk":true}',
      market: "US",
      cV: msCv,
      locale: "en-US",
      msaTicket: session.token,
      pageFormat: "full",
      urlRef: "https://www.microsoft.com/store",
      clientType: "MicrosoftCom",
      layout: "Inline",
      cssOverride: "StorePurchase",
      scenario: "purchase",
      sdkVersion: "VERSION_PLACEHOLDER",
    });

    const res = await proxiedFetch(
      `https://www.microsoft.com/store/purchase/buynowui/checkout?ms-cv=${msCv}&market=US&locale=en-US&clientName=MicrosoftCom`,
      {
        method: "POST",
        headers: {
          ...session.headers,
          Cookie: getCookieString(session.cookieJar),
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: payload.toString(),
      }
    );

    const text = await res.text();
    const match = text.match(/window\.__STORE_CART_STATE__=({.*?});/s);
    if (!match) return null;

    const storeState = JSON.parse(match[1]);
    return {
      ms_cv: storeState.appContext?.cv || msCv,
      correlation_id: storeState.appContext?.correlationId || "",
      tracking_id: storeState.appContext?.trackingId || "",
      vector_id: storeState.appContext?.muid || "",
      muid: storeState.appContext?.alternativeMuid || "",
    };
  } catch {
    return null;
  }
}

async function purchaseProduct(session, productId, skuId, availabilityId, storeState) {
  try {
    const referenceId = generateReferenceId();

    const purchaseHeaders = {
      host: "buynow.production.store-web.dynamics.com",
      connection: "keep-alive",
      "x-ms-tracking-id": storeState.tracking_id,
      authorization: `WLID1.0=t=${session.token}`,
      "x-ms-client-type": "MicrosoftCom",
      "x-ms-market": "US",
      "ms-cv": storeState.ms_cv,
      "x-ms-reference-id": referenceId,
      "x-ms-vector-id": storeState.vector_id,
      "user-agent": session.headers["User-Agent"],
      "x-ms-correlation-id": storeState.correlation_id,
      "content-type": "application/json",
      "x-authorization-muid": storeState.muid,
      accept: "*/*",
      Cookie: getCookieString(session.cookieJar),
    };

    // Step 1: Add to cart
    const addToCartRes = await proxiedFetch(
      "https://buynow.production.store-web.dynamics.com/v1.0/Cart/AddToCart",
      {
        method: "POST",
        headers: purchaseHeaders,
        body: JSON.stringify({
          productId,
          skuId,
          availabilityId,
          quantity: 1,
        }),
      }
    );

    if (addToCartRes.status === 429) {
      return { success: false, error: "Rate limited" };
    }

    const addData = await addToCartRes.json();

    // Check for errors
    if (addData.events?.cart?.[0]?.type === "error") {
      const reason = addData.events.cart[0].data?.reason || "Unknown error";
      return { success: false, error: reason };
    }

    // Step 2: Prepare purchase
    const prepareRes = await proxiedFetch(
      "https://buynow.production.store-web.dynamics.com/v1.0/Purchase/PreparePurchase",
      {
        method: "POST",
        headers: {
          ...purchaseHeaders,
          "x-ms-reference-id": generateReferenceId(),
        },
        body: JSON.stringify({}),
      }
    );

    if (prepareRes.status === 429) {
      return { success: false, error: "Rate limited during prepare" };
    }

    const prepareData = await prepareRes.json();

    // Check available payment instruments
    const paymentInstruments = prepareData.paymentInstruments || [];
    const hasBalance = paymentInstruments.some(pi => pi.type === "storedValue" || pi.type === "balance");

    if (prepareData.events?.cart?.[0]?.type === "error") {
      const reason = prepareData.events.cart[0].data?.reason || "Unknown error";
      return { success: false, error: reason };
    }

    // Check total price
    const total = prepareData.legalTextInfo?.orderTotal || prepareData.orderTotal;

    // Step 3: Complete purchase
    const purchasePayload = {};

    // Use account balance if available
    if (hasBalance) {
      const balanceInstrument = paymentInstruments.find(pi => pi.type === "storedValue" || pi.type === "balance");
      if (balanceInstrument) {
        purchasePayload.paymentInstrumentId = balanceInstrument.id;
      }
    } else if (paymentInstruments.length > 0) {
      // Use first available payment method
      purchasePayload.paymentInstrumentId = paymentInstruments[0].id;
    } else {
      return { success: false, error: "No payment method available" };
    }

    const completeRes = await proxiedFetch(
      "https://buynow.production.store-web.dynamics.com/v1.0/Purchase/CompletePurchase",
      {
        method: "POST",
        headers: {
          ...purchaseHeaders,
          "x-ms-reference-id": generateReferenceId(),
        },
        body: JSON.stringify(purchasePayload),
      }
    );

    if (completeRes.status === 429) {
      return { success: false, error: "Rate limited during purchase" };
    }

    const completeData = await completeRes.json();

    if (completeData.events?.cart?.[0]?.type === "error") {
      const reason = completeData.events.cart[0].data?.reason || "Purchase failed";
      return { success: false, error: reason };
    }

    // Check for success indicators
    if (completeData.orderId || completeData.events?.purchase) {
      return {
        success: true,
        orderId: completeData.orderId || "N/A",
        total: total || "N/A",
      };
    }

    return { success: true, orderId: "Completed", total: total || "N/A" };
  } catch (err) {
    return { success: false, error: err.message };
  }
}

// ── Main Purchase Pipeline ───────────────────────────────────

async function purchaseItems(accounts, productId, skuId, availabilityId, onProgress, signal) {
  const parsed = accounts.map((a) => {
    const i = a.indexOf(":");
    return i === -1 ? { email: a, password: "" } : { email: a.substring(0, i), password: a.substring(i + 1) };
  });

  const results = [];

  for (let i = 0; i < parsed.length; i++) {
    if (signal && signal.aborted) break;

    const { email, password } = parsed[i];

    if (onProgress) onProgress("login", { email, done: i, total: parsed.length });

    // Login to store
    const session = await loginToStore(email, password);
    if (!session) {
      results.push({ email, success: false, error: "Login failed" });
      if (onProgress) onProgress("result", { email, success: false, error: "Login failed", done: i + 1, total: parsed.length });
      continue;
    }

    if (onProgress) onProgress("cart", { email, done: i, total: parsed.length });

    // Get store cart state
    const storeState = await getStoreCartState(session);
    if (!storeState) {
      results.push({ email, success: false, error: "Failed to get store state" });
      if (onProgress) onProgress("result", { email, success: false, error: "Store state failed", done: i + 1, total: parsed.length });
      continue;
    }

    if (onProgress) onProgress("purchase", { email, done: i, total: parsed.length });

    // Purchase
    const result = await purchaseProduct(session, productId, skuId, availabilityId, storeState);
    results.push({ email, ...result });

    if (onProgress) onProgress("result", { email, ...result, done: i + 1, total: parsed.length });

    // Small delay between accounts
    if (i < parsed.length - 1) {
      await new Promise(r => setTimeout(r, 2000));
    }
  }

  return results;
}

module.exports = {
  loginToStore,
  searchProducts,
  getProductDetails,
  purchaseItems,
  getStoreCartState,
  purchaseProduct,
};
