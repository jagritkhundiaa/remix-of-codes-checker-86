// ============================================================
//  Embed builders — monochrome, clean, no emojis
// ============================================================

const { EmbedBuilder, AttachmentBuilder, StringSelectMenuBuilder, ActionRowBuilder } = require("discord.js");
const { COLORS } = require("../config");

const FOOTER_TEXT = "AutizMens | TalkNeon";

function header() {
  return new EmbedBuilder()
    .setAuthor({ name: "AutizMens" })
    .setFooter({ text: FOOTER_TEXT })
    .setTimestamp();
}

function progressEmbed(completed, total, label = "Processing") {
  const pct = total === 0 ? 0 : Math.round((completed / total) * 100);
  const barLen = 20;
  const filled = Math.round((pct / 100) * barLen);
  const bar = "\u2588".repeat(filled) + "\u2591".repeat(barLen - filled);

  return header()
    .setColor(COLORS.INFO)
    .setTitle(label)
    .setDescription(`\`${bar}\` ${pct}%\n${completed.toLocaleString()} / ${total.toLocaleString()}`);
}

function checkResultsEmbed(results) {
  const valid = results.filter((r) => r.status === "valid");
  const used = results.filter((r) => r.status === "used");
  const expired = results.filter((r) => r.status === "expired");
  const invalid = results.filter((r) => r.status === "invalid" || r.status === "error");

  return header()
    .setColor(COLORS.PRIMARY)
    .setTitle("Check Results")
    .addFields(
      { name: "Valid", value: `\`${valid.length}\``, inline: true },
      { name: "Used", value: `\`${used.length}\``, inline: true },
      { name: "Expired", value: `\`${expired.length}\``, inline: true },
      { name: "Invalid", value: `\`${invalid.length}\``, inline: true },
      { name: "Total", value: `\`${results.length}\``, inline: true }
    );
}

function claimResultsEmbed(results) {
  const success = results.filter((r) => r.success);
  const failed = results.filter((r) => !r.success);

  return header()
    .setColor(COLORS.PRIMARY)
    .setTitle("Claim Results")
    .addFields(
      { name: "Success", value: `\`${success.length}\``, inline: true },
      { name: "Failed", value: `\`${failed.length}\``, inline: true },
      { name: "Total", value: `\`${results.length}\``, inline: true }
    );
}

function pullFetchProgressEmbed(details) {
  const pct = details.total === 0 ? 0 : Math.round((details.done / details.total) * 100);
  const barLen = 20;
  const filled = Math.round((pct / 100) * barLen);
  const bar = "\u2588".repeat(filled) + "\u2591".repeat(barLen - filled);

  const lines = [`\`${bar}\` ${pct}%`, `${details.done} / ${details.total} accounts`];
  if (details.lastAccount) {
    const status = details.lastError
      ? `${details.lastAccount} -- Failed`
      : `${details.lastAccount} -- ${details.lastCodes} codes`;
    lines.push(`\nLatest: \`${status}\``);
  }
  if (details.totalCodes !== undefined) {
    lines.push(`Total codes found: \`${details.totalCodes}\``);
  }

  return header()
    .setColor(COLORS.INFO)
    .setTitle("Fetching Codes")
    .setDescription(lines.join("\n"));
}

/**
 * Live structured pull progress — replaces the boring progress bar during validation
 * Shows real-time account analysis matching the final results style
 */
function pullLiveProgressEmbed(fetchResults, validateProgress, { username, startTime } = {}) {
  const totalAccounts = fetchResults.length;
  const workingAccounts = fetchResults.filter((r) => !r.error);
  const failedAccounts = fetchResults.filter((r) => r.error);
  const withCodes = workingAccounts.filter((r) => r.codes.length > 0);
  const noCodes = workingAccounts.filter((r) => r.codes.length === 0);
  const totalCodesFetched = fetchResults.reduce((sum, r) => sum + r.codes.length, 0);

  const pct = validateProgress.total === 0 ? 0 : Math.round((validateProgress.done / validateProgress.total) * 100);
  const barLen = 20;
  const filled = Math.round((pct / 100) * barLen);
  const bar = "\u2588".repeat(filled) + "\u2591".repeat(barLen - filled);

  const valid = validateProgress.valid || 0;
  const used = validateProgress.used || 0;
  const balance = validateProgress.balance || 0;
  const expired = validateProgress.expired || 0;
  const regionLocked = validateProgress.regionLocked || 0;
  const invalid = validateProgress.invalid || 0;

  const elapsed = startTime ? ((Date.now() - startTime) / 1000).toFixed(1) : "...";

  const lines = [
    `**Validating Codes...**`,
    `\`${bar}\` ${pct}%`,
    ``,
    `  **Account Analysis:**`,
    `- **Total Accounts:** ${totalAccounts}`,
    `- **Working Accounts:** ${workingAccounts.length}`,
    `  \u2514 With Codes: ${withCodes.length}`,
    `  \u2514 No Codes: ${noCodes.length}`,
    `- **Failed Accounts:** ${failedAccounts.length}`,
    `- **Codes Found:** ${totalCodesFetched}`,
    `  \u2514 Working: ${valid}`,
    `  \u2514 Claimed: ${used}`,
    `  \u2514 Balance: ${balance}`,
  ];

  if (expired > 0) lines.push(`  \u2514 Expired: ${expired}`);
  if (regionLocked > 0) lines.push(`  \u2514 Region Locked: ${regionLocked}`);
  if (invalid > 0) lines.push(`  \u2514 Invalid: ${invalid}`);

  lines.push(`\n**Time:** ${elapsed}s`);

  const embed = header().setColor(COLORS.INFO).setDescription(lines.join("\n"));

  if (username) {
    embed.setFooter({ text: `Pulled by ${username} | ${new Date().toLocaleDateString("en-GB")} ${new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}` });
  }

  return embed;
}

/**
 * Pull results embed — matches reference image layout exactly.
 */
function pullResultsEmbed(fetchResults, validateResults, { elapsed, dmSent, username } = {}) {
  const totalAccounts = fetchResults.length;
  const workingAccounts = fetchResults.filter((r) => !r.error);
  const failedAccounts = fetchResults.filter((r) => r.error);
  const withCodes = workingAccounts.filter((r) => r.codes.length > 0);
  const noCodes = workingAccounts.filter((r) => r.codes.length === 0);

  const totalCodesFetched = fetchResults.reduce((sum, r) => sum + r.codes.length, 0);

  const valid = validateResults.filter((r) => r.status === "valid");
  const used = validateResults.filter((r) => r.status === "used" || r.status === "REDEEMED");
  const expired = validateResults.filter((r) => r.status === "expired" || r.status === "EXPIRED");
  const invalid = validateResults.filter((r) => r.status === "invalid" || r.status === "error" || r.status === "INVALID");
  const balance = validateResults.filter((r) => r.status === "BALANCE_CODE");
  const regionLocked = validateResults.filter((r) => r.status === "REGION_LOCKED");

  const lines = [
    `**Fetching Complete!**`,
    ``,
    `  **Account Analysis:**`,
    `- **Total Accounts:** ${totalAccounts}`,
    `- **Working Accounts:** ${workingAccounts.length}`,
    `  \u2514 With Codes: ${withCodes.length}`,
    `  \u2514 No Codes: ${noCodes.length}`,
    `- **Failed Accounts:** ${failedAccounts.length}`,
    `- **Codes Found:** ${totalCodesFetched}`,
    `  \u2514 Working: ${valid.length}`,
    `  \u2514 Claimed: ${used.length}`,
    `  \u2514 Balance: ${balance.length}`,
  ];

  if (expired.length > 0) lines.push(`  \u2514 Expired: ${expired.length}`);
  if (regionLocked.length > 0) lines.push(`  \u2514 Region Locked: ${regionLocked.length}`);
  if (invalid.length > 0) lines.push(`  \u2514 Invalid: ${invalid.length}`);

  lines.push(`- **Links Found:** ${totalCodesFetched}`);

  if (elapsed) {
    lines.push(`\n**Time:** ${elapsed}s`);
  }

  const embed = header()
    .setColor(COLORS.PRIMARY)
    .setDescription(lines.join("\n"));

  if (dmSent) {
    embed.addFields({ name: "\u200b", value: "```\n>> Results sent to your DMs\n```", inline: false });
  }

  if (username) {
    embed.setFooter({ text: `Pulled by ${username} | ${new Date().toLocaleDateString("en-GB")} ${new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}` });
  }

  return embed;
}

function purchaseProgressEmbed(details) {
  const pct = details.total === 0 ? 0 : Math.round((details.done / details.total) * 100);
  const barLen = 20;
  const filled = Math.round((pct / 100) * barLen);
  const bar = "\u2588".repeat(filled) + "\u2591".repeat(barLen - filled);

  return header()
    .setColor(COLORS.INFO)
    .setTitle("Purchasing")
    .setDescription([
      `Product: \`${details.product}\``,
      `Price: \`${details.price}\``,
      "",
      `\`${bar}\` ${pct}%`,
      `${details.done} / ${details.total} accounts`,
      details.status ? `\nStatus: \`${details.status}\`` : "",
    ].join("\n"));
}

function purchaseResultsEmbed(results, productTitle, price) {
  const success = results.filter(r => r.success);
  const failed = results.filter(r => !r.success);

  return header()
    .setColor(COLORS.PRIMARY)
    .setTitle("Purchase Results")
    .addFields(
      { name: "Product", value: `\`${productTitle}\``, inline: false },
      { name: "Price", value: `\`${price}\``, inline: true },
      { name: "Purchased", value: `\`${success.length}\``, inline: true },
      { name: "Failed", value: `\`${failed.length}\``, inline: true },
      { name: "Total", value: `\`${results.length}\``, inline: true }
    );
}

function productSearchEmbed(results) {
  const lines = results.map((r, i) =>
    `\`${i + 1}.\` **${r.title}**\n    ID: \`${r.productId || "N/A"}\` | Type: ${r.type || "N/A"}`
  );

  return header()
    .setColor(COLORS.INFO)
    .setTitle("Search Results")
    .setDescription(lines.join("\n\n") || "No results found.");
}

function changerResultsEmbed(results) {
  const success = results.filter(r => r.success);
  const failed = results.filter(r => !r.success);

  return header()
    .setColor(COLORS.PRIMARY)
    .setTitle("Changer Results")
    .addFields(
      { name: "Changed", value: `\`${success.length}\``, inline: true },
      { name: "Failed", value: `\`${failed.length}\``, inline: true },
      { name: "Total", value: `\`${results.length}\``, inline: true }
    );
}

function accountCheckerResultsEmbed(results) {
  const valid = results.filter((r) => r.status === "valid").length;
  const locked = results.filter((r) => r.status === "locked").length;
  const invalid = results.filter((r) => r.status === "invalid").length;
  const rateLimited = results.filter((r) => r.status === "rate_limited").length;
  const errors = results.filter((r) => r.status === "error").length;

  return header()
    .setColor(COLORS.PRIMARY)
    .setTitle("Account Checker Results")
    .addFields(
      { name: "Valid", value: `\`${valid}\``, inline: true },
      { name: "Locked", value: `\`${locked}\``, inline: true },
      { name: "Invalid", value: `\`${invalid}\``, inline: true },
      { name: "Rate Limited", value: `\`${rateLimited}\``, inline: true },
      { name: "Errors", value: `\`${errors}\``, inline: true },
      { name: "Total", value: `\`${results.length}\``, inline: true }
    );
}

function rewardsResultsEmbed(results) {
  const success = results.filter(r => r.success);
  const failed = results.filter(r => !r.success);
  const totalPoints = success.reduce((sum, r) => sum + r.balance, 0);

  const lines = [
    `**Rewards Balance Check**`,
    ``,
    `- **Accounts Checked:** ${results.length}`,
    `- **Successful:** ${success.length}`,
    `- **Failed:** ${failed.length}`,
    ``,
    `- **Total Points:** ${totalPoints.toLocaleString()}`,
    `- **Average:** ${success.length > 0 ? Math.round(totalPoints / success.length).toLocaleString() : 0}`,
  ];

  if (success.length > 0) {
    const highest = success.reduce((max, r) => r.balance > max.balance ? r : max);
    lines.push(`- **Highest:** ${highest.balance.toLocaleString()} (${highest.email.split("@")[0]}...)`);
  }

  return header()
    .setColor(COLORS.PRIMARY)
    .setDescription(lines.join("\n"));
}

function errorEmbed(message) {
  return header().setColor(COLORS.ERROR).setTitle("Error").setDescription(message);
}

function successEmbed(message) {
  return header().setColor(COLORS.SUCCESS).setTitle("Success").setDescription(message);
}

function infoEmbed(title, description) {
  return header().setColor(COLORS.INFO).setTitle(title).setDescription(description);
}

/**
 * Owner-only restriction embed for features still under development.
 */
function ownerOnlyEmbed(featureName) {
  return header()
    .setColor(COLORS.PRIMARY)
    .setDescription(
      [
        `**${featureName}** is currently in a closed development phase.`,
        ``,
        `This feature is exclusively available to **TalkNeon** during the testing period.`,
        ``,
        `Access will be rolled out once the module has been fully validated and stabilized.`,
        `Check back later or contact TalkNeon for updates.`,
      ].join("\n")
    );
}

function authListEmbed(entries) {
  if (entries.length === 0) {
    return header().setColor(COLORS.MUTED).setTitle("Authorized Users").setDescription("No authorized users.");
  }

  const lines = entries.map((e, i) => {
    const expiry = e.expiresAt === "Infinity" ? "Permanent" : `<t:${Math.floor(e.expiresAt / 1000)}:R>`;
    return `\`${i + 1}.\` <@${e.userId}> -- Expires: ${expiry}`;
  });

  return header()
    .setColor(COLORS.INFO)
    .setTitle("Authorized Users")
    .setDescription(lines.join("\n"));
}

// ── Help System — Category Select Menu ──────────────────────

const HELP_CATEGORIES = {
  checker: {
    label: "Checker",
    description: "Check codes against WLID tokens",
    emoji: null,
    content: (p) => [
      `**Checker** — Validate codes against WLID tokens`,
      ``,
      `\`${p}check [wlids]\` + attach codes.txt`,
      `Check codes against WLID tokens.`,
      `Uses stored WLIDs if none provided.`,
      ``,
      `Results are always sent to your DMs.`,
    ].join("\n"),
  },
  claimer: {
    label: "Claimer",
    description: "Claim WLID tokens from accounts",
    emoji: null,
    content: (p) => [
      `**Claimer** — Extract WLID tokens from Microsoft accounts`,
      ``,
      `\`${p}claim <email:pass>\` or attach .txt`,
      `Claim WLID tokens from Microsoft accounts.`,
      ``,
      `Results are always sent to your DMs.`,
    ].join("\n"),
  },
  puller: {
    label: "Puller",
    description: "Fetch & validate Game Pass codes",
    emoji: null,
    content: (p) => [
      `**Puller** — Fetch codes from Game Pass accounts`,
      ``,
      `\`${p}pull <email:pass>\` or attach .txt`,
      `Fetches codes from Game Pass accounts,`,
      `then validates them automatically.`,
      ``,
      `Results are always sent to your DMs.`,
    ].join("\n"),
  },
  rewards: {
    label: "Rewards",
    description: "Check Microsoft Rewards balances",
    emoji: null,
    content: (p) => [
      `**Rewards** — Check Microsoft Rewards point balances`,
      ``,
      `\`${p}rewards <email:pass>\` or attach .txt`,
      `Check Rewards point balances for accounts.`,
      `Shows balance, lifetime points, and level.`,
      ``,
      `Results are always sent to your DMs.`,
    ].join("\n"),
  },
  purchaser: {
    label: "Purchaser",
    description: "Buy from Microsoft Store [Owner]",
    emoji: null,
    content: (p) => [
      `**Purchaser** — Microsoft Store purchases  \`[Owner Only]\``,
      ``,
      `\`${p}purchase <email:pass> <product_id>\``,
      `Buy items from the Microsoft Store.`,
      ``,
      `\`${p}search <query>\``,
      `Search for products on the Microsoft Store.`,
      ``,
      `Results are always sent to your DMs.`,
    ].join("\n"),
  },
  changer: {
    label: "Changer",
    description: "Change passwords & check accounts [Owner]",
    emoji: null,
    content: (p) => [
      `**Changer** — Account management  \`[Owner Only]\``,
      ``,
      `\`${p}changer <email:pass> <new_password>\``,
      `Change password on Microsoft accounts.`,
      ``,
      `\`${p}checker <email:pass>\` or attach .txt`,
      `Validate account credentials.`,
      ``,
      `Results are always sent to your DMs.`,
    ].join("\n"),
  },
  recovery: {
    label: "Recovery",
    description: "Recover accounts via ACSR",
    emoji: null,
    content: (p) => [
      `**Recovery** — Account recovery via ACSR`,
      ``,
      `\`${p}recover <email(s)> <new_password>\``,
      `Recover account(s) via ACSR.`,
      ``,
      `\`${p}captcha <solution>\``,
      `Submit CAPTCHA solution for active recovery.`,
      ``,
      `Results are always sent to your DMs.`,
    ].join("\n"),
  },
  admin: {
    label: "Admin",
    description: "Authorization, blacklist & settings [Owner]",
    emoji: null,
    content: (p) => [
      `**Admin** — Bot management  \`[Owner Only]\``,
      ``,
      `**WLID Storage**`,
      `\`${p}wlidset <tokens>\` or attach .txt`,
      `Replace all stored WLID tokens.`,
      ``,
      `**Authorization**`,
      `\`${p}auth <@user> <duration>\``,
      `\`${p}deauth <@user>\``,
      `\`${p}authlist\``,
      ``,
      `**Blacklist**`,
      `\`${p}blacklist <@user> [reason]\``,
      `\`${p}unblacklist <@user>\``,
      `\`${p}blacklistshow\``,
      ``,
      `**Admin Tools**`,
      `\`${p}admin\` — Control panel`,
      `\`${p}setwebhook <url>\` — Set webhook`,
      `\`${p}botstats\` — Detailed statistics`,
      `\`${p}stats\` — Bot status`,
    ].join("\n"),
  },
};

function helpOverviewEmbed(prefix) {
  const lines = [
    `Select a category below to view commands.`,
    `All results are sent to your DMs automatically.`,
    ``,
    `**Categories:**`,
    ...Object.entries(HELP_CATEGORIES).map(([key, cat]) =>
      `\u2022 **${cat.label}** — ${cat.description}`
    ),
  ];

  return header()
    .setColor(COLORS.PRIMARY)
    .setTitle("Command Reference")
    .setDescription(lines.join("\n"));
}

function helpCategoryEmbed(categoryKey, prefix) {
  const cat = HELP_CATEGORIES[categoryKey];
  if (!cat) return errorEmbed("Unknown category.");

  return header()
    .setColor(COLORS.PRIMARY)
    .setTitle(`Commands — ${cat.label}`)
    .setDescription(cat.content(prefix));
}

function helpSelectMenu() {
  return new ActionRowBuilder().addComponents(
    new StringSelectMenuBuilder()
      .setCustomId("help_category")
      .setPlaceholder("Select a category...")
      .addOptions(
        Object.entries(HELP_CATEGORIES).map(([key, cat]) => ({
          label: cat.label,
          description: cat.description,
          value: key,
        }))
      )
  );
}

function adminPanelEmbed(stats, authCount, activeOtpSessions, activeProcesses, webhookSet) {
  return header()
    .setColor(COLORS.PRIMARY)
    .setTitle("Admin Control Panel")
    .addFields(
      { name: "Stats", value: `Users: \`${authCount}\`\nOTP Sessions: \`${activeOtpSessions}\`\nActive: \`${activeProcesses}\``, inline: true },
      { name: "Processing", value: `Total: \`${stats.total_processed}\`\nSuccess: \`${stats.total_success}\`\nFailed: \`${stats.total_failed}\``, inline: true },
      { name: "Status", value: `Bot: Online\nWebhook: ${webhookSet ? "Set" : "Not Set"}`, inline: true },
    );
}

function detailedStatsEmbed(stats, topUsers) {
  const rate = stats.total_processed > 0
    ? Math.round((stats.total_success / stats.total_processed) * 100)
    : 0;

  const topText = topUsers.length > 0
    ? topUsers.map(([uid, d]) => `<@${uid}>: ${d.processed} processed (${d.success} success)`).join("\n")
    : "No data";

  return header()
    .setColor(COLORS.PRIMARY)
    .setTitle("Detailed Statistics")
    .addFields(
      { name: "Processing", value: `Processed: \`${stats.total_processed}\`\nSuccess: \`${stats.total_success}\`\nFailed: \`${stats.total_failed}\``, inline: true },
      { name: "Success Rate", value: `\`${rate}%\``, inline: true },
      { name: "Top Users", value: topText, inline: false },
    );
}

/**
 * Create a .txt file attachment from an array of strings.
 */
function textAttachment(lines, filename) {
  const buffer = Buffer.from(lines.join("\n"), "utf-8");
  return new AttachmentBuilder(buffer, { name: filename });
}

function recoverProgressEmbed(email, status) {
  return header()
    .setColor(COLORS.INFO)
    .setTitle("Account Recovery")
    .addFields(
      { name: "Account", value: `\`${email}\``, inline: true },
    )
    .setDescription(status);
}

function recoverResultEmbed(email, success, message) {
  return header()
    .setColor(success ? COLORS.SUCCESS : COLORS.ERROR)
    .setTitle(success ? "Recovery Successful" : "Recovery Failed")
    .addFields(
      { name: "Account", value: `\`${email}\``, inline: true },
    )
    .setDescription(message || (success ? "Password has been reset." : "Recovery failed."));
}

module.exports = {
  progressEmbed,
  checkResultsEmbed,
  claimResultsEmbed,
  pullFetchProgressEmbed,
  pullLiveProgressEmbed,
  pullResultsEmbed,
  purchaseProgressEmbed,
  purchaseResultsEmbed,
  productSearchEmbed,
  changerResultsEmbed,
  accountCheckerResultsEmbed,
  rewardsResultsEmbed,
  errorEmbed,
  successEmbed,
  infoEmbed,
  ownerOnlyEmbed,
  authListEmbed,
  helpOverviewEmbed,
  helpCategoryEmbed,
  helpSelectMenu,
  adminPanelEmbed,
  detailedStatsEmbed,
  textAttachment,
  recoverProgressEmbed,
  recoverResultEmbed,
};
