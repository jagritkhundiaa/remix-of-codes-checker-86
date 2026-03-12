// ============================================================
//  Microsoft Rewards Balance Checker
//  Logs into Microsoft accounts and checks Rewards point balance
// ============================================================

const { HttpsProxyAgent } = require("https-proxy-agent");

/**
 * Login to Microsoft and get authenticated cookies for rewards.bing.com
 */
async function loginMicrosoft(email, password) {
  const cookieJar = {};

  function extractCookies(res) {
    const setCookies = res.headers.getSetCookie?.() || [];
    for (const sc of setCookies) {
      const [pair] = sc.split(";");
      const [name, ...valParts] = pair.split("=");
      cookieJar[name.trim()] = valParts.join("=").trim();
    }
  }

  function getCookieString() {
    return Object.entries(cookieJar)
      .map(([k, v]) => `${k}=${v}`)
      .join("; ");
  }

  try {
    // Step 1: Hit login.live.com to get PPFT and urlPost
    const loginPageRes = await fetch("https://login.live.com/login.srf?wa=wsignin1.0&wreply=https://rewards.bing.com/signin", {
      redirect: "manual",
      headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" },
    });
    extractCookies(loginPageRes);

    // Follow redirects manually
    let html;
    let currentRes = loginPageRes;
    let redirectCount = 0;
    while (currentRes.status >= 300 && currentRes.status < 400 && redirectCount < 5) {
      const loc = currentRes.headers.get("location");
      if (!loc) break;
      currentRes = await fetch(loc, {
        redirect: "manual",
        headers: {
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
          Cookie: getCookieString(),
        },
      });
      extractCookies(currentRes);
      redirectCount++;
    }
    html = await currentRes.text();

    // Extract PPFT
    const ppftMatch = html.match(/name="PPFT".*?value="([^"]+)"/);
    if (!ppftMatch) return { success: false, error: "Failed to get login token" };

    // Extract urlPost
    const urlPostMatch = html.match(/urlPost:\s*'([^']+)'/);
    if (!urlPostMatch) return { success: false, error: "Failed to get login URL" };

    // Step 2: Submit credentials
    const loginRes = await fetch(urlPostMatch[1], {
      method: "POST",
      redirect: "manual",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        Cookie: getCookieString(),
      },
      body: new URLSearchParams({
        login: email,
        loginfmt: email,
        passwd: password,
        PPFT: ppftMatch[1],
        PPSX: "PassportRN",
        type: "11",
        LoginOptions: "3",
        NewUser: "1",
        i21: "0",
        CookieDisclosure: "0",
        i19: "25069",
      }).toString(),
    });
    extractCookies(loginRes);

    // Follow all redirects to get authenticated cookies
    let nextRes = loginRes;
    let hops = 0;
    while (nextRes.status >= 300 && nextRes.status < 400 && hops < 10) {
      const loc = nextRes.headers.get("location");
      if (!loc) break;
      nextRes = await fetch(loc, {
        redirect: "manual",
        headers: {
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
          Cookie: getCookieString(),
        },
      });
      extractCookies(nextRes);
      hops++;
    }

    const finalHtml = await nextRes.text();

    // Check if login failed
    if (finalHtml.includes("Your account or password is incorrect") || finalHtml.includes("Sign in to your account")) {
      return { success: false, error: "Invalid credentials" };
    }

    return { success: true, cookieJar, getCookieString };
  } catch (err) {
    return { success: false, error: err.message };
  }
}

/**
 * Fetch rewards balance from rewards.bing.com API
 */
async function fetchRewardsBalance(getCookieString) {
  try {
    const res = await fetch("https://rewards.bing.com/api/getuserinfo?type=1", {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        Cookie: getCookieString(),
        Accept: "application/json",
      },
    });

    if (!res.ok) return { success: false, error: `HTTP ${res.status}` };

    const data = await res.json();

    if (!data || !data.dashboard) {
      return { success: false, error: "No rewards data returned" };
    }

    const dashboard = data.dashboard;
    const userStatus = dashboard.userStatus || {};
    const streakInfo = dashboard.streaks || {};

    return {
      success: true,
      balance: userStatus.availablePoints || 0,
      lifetimePoints: userStatus.lifetimePoints || 0,
      level: userStatus.levelInfo?.activeLevel || "Unknown",
      levelName: userStatus.levelInfo?.activeLevelName || "Unknown",
      streak: streakInfo.currentStreak || 0,
      redeemGoal: userStatus.redeemGoal?.price || 0,
      redeemGoalName: userStatus.redeemGoal?.title || "None set",
    };
  } catch (err) {
    return { success: false, error: err.message };
  }
}

/**
 * Check rewards balance for a single account
 */
async function checkRewardsAccount(email, password) {
  const loginResult = await loginMicrosoft(email, password);
  if (!loginResult.success) {
    return { email, success: false, error: loginResult.error };
  }

  const rewardsResult = await fetchRewardsBalance(loginResult.getCookieString);
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
    redeemGoal: rewardsResult.redeemGoal,
    redeemGoalName: rewardsResult.redeemGoalName,
  };
}

/**
 * Check rewards balances for multiple accounts
 * @param {string[]} accounts - Array of "email:password"
 * @param {number} threads - Concurrency
 * @param {Function} onProgress - (done, total) callback
 * @param {AbortSignal} signal - Optional abort signal
 */
async function checkRewardsBalances(accounts, threads = 3, onProgress, signal) {
  const results = [];
  let done = 0;

  const queue = [...accounts];

  async function worker() {
    while (queue.length > 0) {
      if (signal?.aborted) break;
      const account = queue.shift();
      if (!account) break;

      const [email, password] = account.split(":");
      if (!email || !password) {
        results.push({ email: account, success: false, error: "Invalid format" });
        done++;
        onProgress?.(done, accounts.length);
        continue;
      }

      const result = await checkRewardsAccount(email.trim(), password.trim());
      results.push(result);
      done++;
      onProgress?.(done, accounts.length);
    }
  }

  const workers = Array.from({ length: Math.min(threads, accounts.length) }, () => worker());
  await Promise.all(workers);

  return results;
}

module.exports = { checkRewardsBalances, checkRewardsAccount };
