// ============================================================
//  Microsoft Bing Rewards Balance Checker
//  Logs into Microsoft accounts via Xbox OAuth and checks
//  Rewards point balance from rewards.bing.com
// ============================================================

const { proxiedFetch } = require("./proxy-manager");

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

const DEFAULT_HEADERS = {
  "User-Agent": UA,
  Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
  "Accept-Language": "en-US,en;q=0.9",
  "Sec-Fetch-Dest": "document",
  "Sec-Fetch-Mode": "navigate",
  "Sec-Fetch-Site": "same-origin",
  "Sec-Fetch-User": "?1",
  "Upgrade-Insecure-Requests": "1",
};

// ── Cookie Jar ────────────────────────────────────────────────

class CookieJar {
  constructor() { this.cookies = new Map(); }

  extractFromResponse(res) {
    const raw = res.headers.raw?.()?.["set-cookie"];
    if (raw && Array.isArray(raw)) {
      for (const c of raw) this._parse(c);
      return;
    }
    const sc = res.headers.get("set-cookie");
    if (sc) {
      const parts = sc.split(/,(?=\s*[^;,]+=[^;,]+)/);
      for (const c of parts) this._parse(c);
    }
  }

  _parse(str) {
    const parts = str.split(";")[0].trim();
    const eq = parts.indexOf("=");
    if (eq > 0) {
      const name = parts.substring(0, eq).trim();
      const value = parts.substring(eq + 1).trim();
      if (name && value) this.cookies.set(name, value);
    }
  }

  toString() {
    return Array.from(this.cookies.entries()).map(([k, v]) => `${k}=${v}`).join("; ");
  }

  get(name) { return this.cookies.get(name); }
}

// ── Session Fetch (manual redirects + cookies) ────────────────

async function sessionFetch(url, options, jar, maxRedirects = 12) {
  let currentUrl = url;
  let opts = { ...options };
  let hops = 0;

  while (hops < maxRedirects) {
    const headers = { ...(opts.headers || {}), Cookie: jar.toString() };
    const res = await proxiedFetch(currentUrl, { ...opts, headers, redirect: "manual" });
    jar.extractFromResponse(res);

    const loc = res.headers.get("location");
    if (res.status >= 300 && res.status < 400 && loc) {
      if (loc.startsWith("/")) {
        const u = new URL(currentUrl);
        currentUrl = `${u.origin}${loc}`;
      } else if (!loc.startsWith("http")) {
        const u = new URL(currentUrl);
        currentUrl = `${u.origin}/${loc}`;
      } else {
        currentUrl = loc;
      }
      opts = { ...opts, method: "GET", body: undefined };
      hops++;
      continue;
    }

    const text = await res.text();

    // Handle meta-refresh or JS redirects in page
    const metaRefresh = text.match(/<meta[^>]+http-equiv=["']?refresh["']?[^>]+content=["']?\d+;\s*url=([^"'\s>]+)/i);
    if (metaRefresh) {
      currentUrl = metaRefresh[1].replace(/&amp;/g, "&");
      opts = { ...opts, method: "GET", body: undefined };
      hops++;
      continue;
    }

    const jsReplace = text.match(/(?:location\.replace|location\.href\s*=)\s*\(\s*["']([^"']+)["']\s*\)/);
    if (jsReplace && !text.includes("<form")) {
      currentUrl = jsReplace[1].replace(/\\u0026/g, "&").replace(/\\\//g, "/");
      opts = { ...opts, method: "GET", body: undefined };
      hops++;
      continue;
    }

    // Handle hidden auto-submit forms (e.g., jsDisabled.srf)
    const formAction = text.match(/<form[^>]+action="([^"]+)"[^>]*>/);
    const hasAutoSubmit = text.includes("javascript") && text.includes("submit") && formAction;
    if (hasAutoSubmit) {
      const inputRegex = /<input[^>]+name="([^"]+)"[^>]+value="([^"]*)"/g;
      const formData = new URLSearchParams();
      let m;
      while ((m = inputRegex.exec(text)) !== null) formData.append(m[1], m[2]);

      // Also try reversed value/name order
      const inputRegex2 = /<input[^>]+value="([^"]*)"[^>]+name="([^"]+)"/g;
      while ((m = inputRegex2.exec(text)) !== null) {
        if (!formData.has(m[2])) formData.append(m[2], m[1]);
      }

      if (formData.toString()) {
        let actionUrl = formAction[1].replace(/&amp;/g, "&");
        if (actionUrl.startsWith("/")) {
          const u = new URL(currentUrl);
          actionUrl = `${u.origin}${actionUrl}`;
        }
        currentUrl = actionUrl;
        opts = {
          ...opts,
          method: "POST",
          body: formData.toString(),
          headers: { ...DEFAULT_HEADERS, "Content-Type": "application/x-www-form-urlencoded" },
        };
        hops++;
        continue;
      }
    }

    return { res, text, finalUrl: currentUrl };
  }
  throw new Error("Too many redirects");
}

// ── Extract helpers ───────────────────────────────────────────

function extractPPFT(html) {
  const m = html.match(/name="PPFT"[^>]*value="([^"]+)"/) ||
            html.match(/value="([^"]+)"[^>]*name="PPFT"/) ||
            html.match(/"sFT":"([^"]+)"/) ||
            html.match(/sFT\s*=\s*'([^']+)'/);
  return m ? m[1] : null;
}

function extractUrlPost(html) {
  const m = html.match(/urlPost:\s*'([^']+)'/) ||
            html.match(/"urlPost"\s*:\s*"([^"]+)"/) ||
            html.match(/urlPost\s*=\s*'([^']+)'/);
  return m ? m[1] : null;
}

// ── Login to Microsoft ────────────────────────────────────────

async function loginMicrosoft(email, password) {
  const jar = new CookieJar();

  try {
    // Step 1: Hit rewards.bing.com to get redirected to login
    const { text: loginPage } = await sessionFetch(
      "https://rewards.bing.com/signin",
      { method: "GET", headers: { ...DEFAULT_HEADERS, Referer: "https://rewards.bing.com/" } },
      jar
    );

    // Extract PPFT and urlPost from the login page
    let ppft = extractPPFT(loginPage);
    let urlPost = extractUrlPost(loginPage);

    // If we didn't land on a login page, try the direct login URL
    if (!ppft || !urlPost) {
      const { text: directLogin } = await sessionFetch(
        "https://login.live.com/login.srf?wa=wsignin1.0&wreply=https://rewards.bing.com/signin",
        { method: "GET", headers: DEFAULT_HEADERS },
        jar
      );
      ppft = extractPPFT(directLogin);
      urlPost = extractUrlPost(directLogin);
    }

    if (!ppft) return { success: false, error: "Failed to get login token (PPFT)" };
    if (!urlPost) return { success: false, error: "Failed to get login URL (urlPost)" };

    // Step 2: Submit credentials
    const loginData = new URLSearchParams({
      login: email,
      loginfmt: email,
      passwd: password,
      PPFT: ppft,
      PPSX: "PassportRN",
      type: "11",
      LoginOptions: "3",
      NewUser: "1",
      i21: "0",
      CookieDisclosure: "0",
      i19: "25069",
    });

    const { text: postLoginPage } = await sessionFetch(
      urlPost,
      {
        method: "POST",
        headers: {
          ...DEFAULT_HEADERS,
          "Content-Type": "application/x-www-form-urlencoded",
          Origin: "https://login.live.com",
        },
        body: loginData.toString(),
      },
      jar
    );

    // Check for login failure
    if (
      postLoginPage.includes("Your account or password is incorrect") ||
      postLoginPage.includes("sErrTxt") ||
      postLoginPage.includes("Sign in to your account")
    ) {
      // If we see "Sign in" but also have authenticated cookies, we might be OK
      // Double-check by looking for actual error indicators
      if (postLoginPage.includes("Your account or password is incorrect") || postLoginPage.includes("sErrTxt")) {
        return { success: false, error: "Invalid credentials" };
      }
    }

    // Handle "Stay signed in?" page
    const stayPpft = extractPPFT(postLoginPage);
    const stayUrlPost = extractUrlPost(postLoginPage);
    if (stayPpft && stayUrlPost && postLoginPage.includes("kmsi")) {
      const stayData = new URLSearchParams({
        LoginOptions: "1",
        type: "28",
        ctx: "",
        hpgrequestid: "",
        PPFT: stayPpft,
        canary: "",
      });

      await sessionFetch(
        stayUrlPost,
        {
          method: "POST",
          headers: {
            ...DEFAULT_HEADERS,
            "Content-Type": "application/x-www-form-urlencoded",
          },
          body: stayData.toString(),
        },
        jar
      );
    }

    return { success: true, jar };
  } catch (err) {
    return { success: false, error: err.message || String(err) };
  }
}

// ── Fetch Rewards Dashboard ───────────────────────────────────

async function fetchRewardsDashboard(jar) {
  try {
    // Try the main rewards API
    const res = await proxiedFetch("https://rewards.bing.com/api/getuserinfo?type=1", {
      headers: {
        "User-Agent": UA,
        Cookie: jar.toString(),
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
    });

    if (!res.ok) {
      // Fallback: try rewards.bing.com and parse from page
      const pageRes = await proxiedFetch("https://rewards.bing.com/", {
        headers: { "User-Agent": UA, Cookie: jar.toString(), Accept: "text/html" },
      });
      const pageText = await pageRes.text();

      // Try extracting from embedded JSON in page
      const pointsMatch = pageText.match(/"availablePoints"\s*:\s*(\d+)/);
      const lifetimeMatch = pageText.match(/"lifetimePoints"\s*:\s*(\d+)/);
      const levelMatch = pageText.match(/"activeLevelName"\s*:\s*"([^"]+)"/);
      const streakMatch = pageText.match(/"currentStreak"\s*:\s*(\d+)/);

      if (pointsMatch) {
        return {
          success: true,
          balance: parseInt(pointsMatch[1], 10),
          lifetimePoints: lifetimeMatch ? parseInt(lifetimeMatch[1], 10) : 0,
          levelName: levelMatch ? levelMatch[1] : "Unknown",
          streak: streakMatch ? parseInt(streakMatch[1], 10) : 0,
          redeemGoalName: "N/A",
          redeemGoal: 0,
          dailyPoints: { earned: 0, max: 0 },
          pcSearch: { earned: 0, max: 0 },
          mobileSearch: { earned: 0, max: 0 },
        };
      }

      return { success: false, error: `HTTP ${res.status} - Could not fetch rewards data` };
    }

    const data = await res.json();

    if (!data || !data.dashboard) {
      return { success: false, error: "No rewards dashboard data returned" };
    }

    const dashboard = data.dashboard;
    const userStatus = dashboard.userStatus || {};
    const streakInfo = dashboard.streaks || {};

    // Parse daily activity progress
    const dailySetCards = dashboard.dailySetPromotions || {};
    let dailyEarned = 0;
    let dailyMax = 0;
    for (const key of Object.keys(dailySetCards)) {
      const cards = dailySetCards[key];
      if (Array.isArray(cards)) {
        for (const card of cards) {
          dailyEarned += card.pointProgress || 0;
          dailyMax += card.pointProgressMax || 0;
        }
      }
    }

    // Parse search points (PC + Mobile)
    let pcEarned = 0, pcMax = 0, mobileEarned = 0, mobileMax = 0, edgeEarned = 0, edgeMax = 0;
    const morePromotions = dashboard.morePromotions || [];
    for (const promo of morePromotions) {
      const title = (promo.title || "").toLowerCase();
      if (title.includes("pc search") || title.includes("desktop search")) {
        pcEarned = promo.pointProgress || 0;
        pcMax = promo.pointProgressMax || 0;
      } else if (title.includes("mobile search")) {
        mobileEarned = promo.pointProgress || 0;
        mobileMax = promo.pointProgressMax || 0;
      } else if (title.includes("edge")) {
        edgeEarned = promo.pointProgress || 0;
        edgeMax = promo.pointProgressMax || 0;
      }
    }

    // Also check userStatus counters
    const counters = userStatus.counters || {};
    if (counters.pcSearch) {
      pcEarned = counters.pcSearch[0]?.pointProgress || pcEarned;
      pcMax = counters.pcSearch[0]?.pointProgressMax || pcMax;
    }
    if (counters.mobileSearch) {
      mobileEarned = counters.mobileSearch[0]?.pointProgress || mobileEarned;
      mobileMax = counters.mobileSearch[0]?.pointProgressMax || mobileMax;
    }
    if (counters.edgeSearch) {
      edgeEarned = counters.edgeSearch[0]?.pointProgress || edgeEarned;
      edgeMax = counters.edgeSearch[0]?.pointProgressMax || edgeMax;
    }

    return {
      success: true,
      balance: userStatus.availablePoints || 0,
      lifetimePoints: userStatus.lifetimePoints || 0,
      level: userStatus.levelInfo?.activeLevel || "Unknown",
      levelName: userStatus.levelInfo?.activeLevelName || "Unknown",
      streak: streakInfo.currentStreak || 0,
      maxStreak: streakInfo.longestStreak || 0,
      redeemGoal: userStatus.redeemGoal?.price || 0,
      redeemGoalName: userStatus.redeemGoal?.title || "None set",
      dailyPoints: { earned: dailyEarned, max: dailyMax },
      pcSearch: { earned: pcEarned, max: pcMax },
      mobileSearch: { earned: mobileEarned, max: mobileMax },
      edgeSearch: { earned: edgeEarned, max: edgeMax },
    };
  } catch (err) {
    return { success: false, error: err.message || String(err) };
  }
}

// ── Single Account Check ──────────────────────────────────────

async function checkRewardsAccount(email, password) {
  const loginResult = await loginMicrosoft(email, password);
  if (!loginResult.success) {
    return { email, success: false, error: loginResult.error };
  }

  const rewardsResult = await fetchRewardsDashboard(loginResult.jar);
  if (!rewardsResult.success) {
    return { email, success: false, error: rewardsResult.error };
  }

  return {
    email,
    success: true,
    balance: rewardsResult.balance,
    lifetimePoints: rewardsResult.lifetimePoints,
    level: rewardsResult.level,
    levelName: rewardsResult.levelName,
    streak: rewardsResult.streak,
    maxStreak: rewardsResult.maxStreak,
    redeemGoal: rewardsResult.redeemGoal,
    redeemGoalName: rewardsResult.redeemGoalName,
    dailyPoints: rewardsResult.dailyPoints,
    pcSearch: rewardsResult.pcSearch,
    mobileSearch: rewardsResult.mobileSearch,
    edgeSearch: rewardsResult.edgeSearch,
  };
}

// ── Multi-Account Check ───────────────────────────────────────

async function checkRewardsBalances(accounts, threads = 3, onProgress, signal) {
  const results = [];
  let currentIndex = 0;
  let completed = 0;

  async function worker() {
    while (true) {
      if (signal?.aborted) break;
      const idx = currentIndex++;
      if (idx >= accounts.length) break;

      const account = accounts[idx];
      const [email, password] = account.split(":");
      if (!email || !password) {
        results.push({ email: account, success: false, error: "Invalid format (need email:password)" });
        completed++;
        onProgress?.(completed, accounts.length);
        continue;
      }

      try {
        const result = await checkRewardsAccount(email.trim(), password.trim());
        results.push(result);
      } catch (err) {
        results.push({ email: email.trim(), success: false, error: String(err) });
      }
      completed++;
      onProgress?.(completed, accounts.length);
    }
  }

  const workers = Array.from({ length: Math.min(threads, accounts.length) }, () => worker());
  await Promise.all(workers);
  return results;
}

module.exports = { checkRewardsBalances, checkRewardsAccount };
