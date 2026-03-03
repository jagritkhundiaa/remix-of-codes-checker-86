// ============================================================
//  Microsoft Account Password Changer
//  Logs into accounts and changes the password
// ============================================================

const { proxiedFetch } = require("./proxy-manager");

// ── Cookie-aware fetch ───────────────────────────────────────

function extractCookiesFromResponse(res, cookieJar) {
  const setCookies = res.headers.getSetCookie?.() || [];
  for (const c of setCookies) {
    const parts = c.split(";")[0].trim();
    if (parts.includes("=")) cookieJar.push(parts);
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
      headers: { ...options.headers, Cookie: getCookieString(cookieJar) },
      redirect: "manual",
    });

    extractCookiesFromResponse(res, cookieJar);
    const status = res.status;

    if (status >= 300 && status < 400) {
      const location = res.headers.get("location");
      if (!location) break;
      currentUrl = new URL(location, currentUrl).href;
      if (status !== 307 && status !== 308) { method = "GET"; body = undefined; }
      try { await res.text(); } catch {}
      continue;
    }

    const text = await res.text();
    return { res, text, finalUrl: currentUrl };
  }
  throw new Error("Too many redirects");
}

// ── Password Change Flow ─────────────────────────────────────

const DEFAULT_HEADERS = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
  Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
  "Accept-Language": "en-US,en;q=0.9",
};

async function changePassword(email, oldPassword, newPassword) {
  const cookieJar = [];
  const headers = { ...DEFAULT_HEADERS };

  try {
    // Step 1: Navigate to Microsoft account security/password page
    const { text: securityPage } = await sessionFetch(
      "https://account.live.com/password/Change",
      { headers },
      cookieJar
    );

    // Extract PPFT and urlPost for login
    const ppftMatch = securityPage.match(/name="PPFT"[^>]*value="([^"]+)"/s) ||
                      securityPage.match(/value="([^"]+)"[^>]*name="PPFT"/s) ||
                      securityPage.match(/sFT:'([^']+)'/s) ||
                      securityPage.match(/"sFT":"([^"]+)"/s);
    const urlPostMatch = securityPage.match(/"urlPost":"([^"]+)"/s) ||
                         securityPage.match(/urlPost:'([^']+)'/s);

    if (!ppftMatch || !urlPostMatch) {
      // Maybe we need to go through login.live.com first
      const { text: loginPage } = await sessionFetch(
        "https://login.live.com/login.srf?wa=wsignin1.0&wreply=https://account.live.com/password/Change",
        { headers },
        cookieJar
      );

      const ppft2 = loginPage.match(/name="PPFT"[^>]*value="([^"]+)"/s) ||
                     loginPage.match(/sFT:'([^']+)'/s) ||
                     loginPage.match(/"sFT":"([^"]+)"/s);
      const urlPost2 = loginPage.match(/"urlPost":"([^"]+)"/s) ||
                       loginPage.match(/urlPost:'([^']+)'/s);

      if (!ppft2 || !urlPost2) {
        return { email, success: false, error: "Could not extract login form" };
      }

      // Submit login
      const loginBody = new URLSearchParams({
        login: email,
        loginfmt: email,
        passwd: oldPassword,
        PPFT: ppft2[1],
      });

      const { text: afterLogin, finalUrl } = await sessionFetch(urlPost2[1], {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/x-www-form-urlencoded" },
        body: loginBody.toString(),
      }, cookieJar);

      // Handle post-login forms (consent, etc.)
      const formAction = afterLogin.match(/<form[^>]*action="([^"]+)"/);
      if (formAction) {
        const inputMatches = [...afterLogin.matchAll(/<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"/g)];
        const formData = new URLSearchParams();
        for (const m of inputMatches) formData.append(m[1], m[2]);
        await sessionFetch(formAction[1], {
          method: "POST",
          headers: { ...headers, "Content-Type": "application/x-www-form-urlencoded" },
          body: formData.toString(),
        }, cookieJar);
      }

      // Check if login failed
      if (afterLogin.includes("incorrect") || afterLogin.includes("AADSTS50126") || afterLogin.includes("password is incorrect")) {
        return { email, success: false, error: "Invalid credentials" };
      }

      // Navigate to password change page after login
      const { text: pwdPage } = await sessionFetch(
        "https://account.live.com/password/Change",
        { headers },
        cookieJar
      );

      return await submitPasswordChange(pwdPage, email, oldPassword, newPassword, cookieJar, headers);
    }

    // We landed on the login page directly
    const loginBody = new URLSearchParams({
      login: email,
      loginfmt: email,
      passwd: oldPassword,
      PPFT: ppftMatch[1],
    });

    const { text: afterLogin } = await sessionFetch(urlPostMatch[1], {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/x-www-form-urlencoded" },
      body: loginBody.toString(),
    }, cookieJar);

    if (afterLogin.includes("incorrect") || afterLogin.includes("password is incorrect")) {
      return { email, success: false, error: "Invalid credentials" };
    }

    // Handle consent form
    const formAction = afterLogin.match(/<form[^>]*action="([^"]+)"/);
    if (formAction) {
      const inputMatches = [...afterLogin.matchAll(/<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"/g)];
      const formData = new URLSearchParams();
      for (const m of inputMatches) formData.append(m[1], m[2]);
      const { text: pwdPage } = await sessionFetch(formAction[1], {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/x-www-form-urlencoded" },
        body: formData.toString(),
      }, cookieJar);
      return await submitPasswordChange(pwdPage, email, oldPassword, newPassword, cookieJar, headers);
    }

    return await submitPasswordChange(afterLogin, email, oldPassword, newPassword, cookieJar, headers);
  } catch (err) {
    return { email, success: false, error: err.message };
  }
}

async function submitPasswordChange(pageHtml, email, oldPassword, newPassword, cookieJar, headers) {
  try {
    // Look for the password change form
    // Microsoft uses either an API or form-based approach

    // Try API approach first (modern Microsoft account)
    const canaryMatch = pageHtml.match(/"canary":"([^"]+)"/s) ||
                        pageHtml.match(/canary\s*=\s*'([^']+)'/s) ||
                        pageHtml.match(/name="canary"[^>]*value="([^"]+)"/s);

    const apiCanary = pageHtml.match(/"apiCanary":"([^"]+)"/s);

    if (apiCanary) {
      // Modern API-based password change
      const changeRes = await proxiedFetch(
        "https://account.live.com/password/Change",
        {
          method: "POST",
          headers: {
            ...headers,
            Cookie: getCookieString(cookieJar),
            "Content-Type": "application/x-www-form-urlencoded",
            canary: apiCanary[1],
          },
          body: new URLSearchParams({
            OldPassword: oldPassword,
            NewPassword: newPassword,
            RetypePassword: newPassword,
            ...(canaryMatch ? { canary: canaryMatch[1] } : {}),
          }).toString(),
        }
      );

      extractCookiesFromResponse(changeRes, cookieJar);
      const changeText = await changeRes.text();

      if (changeRes.status === 200 || changeRes.status === 302) {
        if (changeText.includes("PasswordChanged") || changeText.includes("success") ||
            changeText.includes("Your password has been changed") || changeRes.status === 302) {
          return { email, success: true, newPassword };
        }
      }

      // Check for specific errors
      if (changeText.includes("TooShort") || changeText.includes("too short")) {
        return { email, success: false, error: "New password too short" };
      }
      if (changeText.includes("SameAsOld") || changeText.includes("same as your current")) {
        return { email, success: false, error: "New password same as old" };
      }
      if (changeText.includes("PasswordIncorrect") || changeText.includes("incorrect")) {
        return { email, success: false, error: "Current password incorrect" };
      }
    }

    // Try form-based approach
    const formAction = pageHtml.match(/<form[^>]*id="(?:ChangePasswordForm|iForm)"[^>]*action="([^"]+)"/s) ||
                       pageHtml.match(/<form[^>]*action="([^"]*[Pp]assword[^"]*)"[^>]*/s);

    if (formAction) {
      const action = formAction[1].startsWith("http") ? formAction[1] : `https://account.live.com${formAction[1]}`;
      
      const formBody = new URLSearchParams({
        OldPassword: oldPassword,
        NewPassword: newPassword,
        RetypePassword: newPassword,
      });
      if (canaryMatch) formBody.append("canary", canaryMatch[1]);

      // Extract hidden inputs
      const hiddenInputs = [...pageHtml.matchAll(/<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"/g)];
      for (const m of hiddenInputs) {
        if (!formBody.has(m[1])) formBody.append(m[1], m[2]);
      }

      const { res: changeRes, text: changeText } = await sessionFetch(action, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/x-www-form-urlencoded" },
        body: formBody.toString(),
      }, cookieJar);

      if (changeRes.status === 302 || changeText.includes("success") || changeText.includes("PasswordChanged")) {
        return { email, success: true, newPassword };
      }

      if (changeText.includes("incorrect")) {
        return { email, success: false, error: "Current password incorrect" };
      }

      return { email, success: false, error: "Password change did not confirm success" };
    }

    return { email, success: false, error: "Password change form not found" };
  } catch (err) {
    return { email, success: false, error: err.message };
  }
}

// ── Bulk Password Changer ────────────────────────────────────

async function changePasswords(accounts, newPassword, threads = 5, onProgress, signal) {
  const parsed = accounts.map((a) => {
    const i = a.indexOf(":");
    return i === -1 ? { email: a, password: "" } : { email: a.substring(0, i), password: a.substring(i + 1) };
  });

  const results = [];
  let currentIndex = 0;

  async function worker() {
    while (true) {
      if (signal && signal.aborted) break;
      const idx = currentIndex++;
      if (idx >= parsed.length) break;

      const { email, password } = parsed[idx];
      const result = await changePassword(email, password, newPassword);
      results.push(result);

      if (onProgress) onProgress(results.length, parsed.length);
    }
  }

  const workerCount = Math.min(threads, parsed.length);
  const workers = Array(workerCount).fill(null).map(() => worker());
  await Promise.all(workers);

  return results;
}

module.exports = { changePassword, changePasswords };
