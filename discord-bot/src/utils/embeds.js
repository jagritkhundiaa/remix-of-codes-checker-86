// ============================================================
//  Embed builders — clean, professional, no emojis
// ============================================================

const { EmbedBuilder, AttachmentBuilder } = require("discord.js");
const { COLORS } = require("../config");

function header() {
  return new EmbedBuilder()
    .setAuthor({ name: "MS Code Checker" })
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

  const embed = header()
    .setColor(COLORS.PRIMARY)
    .setTitle("Check Results")
    .addFields(
      { name: "Valid", value: `\`${valid.length}\``, inline: true },
      { name: "Used", value: `\`${used.length}\``, inline: true },
      { name: "Expired", value: `\`${expired.length}\``, inline: true },
      { name: "Invalid", value: `\`${invalid.length}\``, inline: true },
      { name: "Total", value: `\`${results.length}\``, inline: true }
    );

  return embed;
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

function errorEmbed(message) {
  return header().setColor(COLORS.ERROR).setTitle("Error").setDescription(message);
}

function successEmbed(message) {
  return header().setColor(COLORS.SUCCESS).setTitle("Success").setDescription(message);
}

function infoEmbed(title, description) {
  return header().setColor(COLORS.INFO).setTitle(title).setDescription(description);
}

function authListEmbed(entries) {
  if (entries.length === 0) {
    return header().setColor(COLORS.MUTED).setTitle("Authorized Users").setDescription("No authorized users.");
  }

  const lines = entries.map((e, i) => {
    const expiry = e.expiresAt === "Infinity" ? "Permanent" : `<t:${Math.floor(e.expiresAt / 1000)}:R>`;
    return `\`${i + 1}.\` <@${e.userId}> — Expires: ${expiry}`;
  });

  return header()
    .setColor(COLORS.INFO)
    .setTitle("Authorized Users")
    .setDescription(lines.join("\n"));
}

/**
 * Create a .txt file attachment from an array of strings.
 */
function textAttachment(lines, filename) {
  const buffer = Buffer.from(lines.join("\n"), "utf-8");
  return new AttachmentBuilder(buffer, { name: filename });
}

module.exports = {
  progressEmbed,
  checkResultsEmbed,
  claimResultsEmbed,
  errorEmbed,
  successEmbed,
  infoEmbed,
  authListEmbed,
  textAttachment,
};
