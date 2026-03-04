// ============================================================
//  Xbox Full Capture Checker — Discord Bot
//  Separate bot — port of backup.py
// ============================================================

const {
  Client,
  GatewayIntentBits,
  EmbedBuilder,
  AttachmentBuilder,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
} = require("discord.js");

const config = require("./config");
const { checkAccounts } = require("./utils/xbox-checker");

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
  ],
});

// Track active abort controllers per user
const activeAborts = new Map();

// ── Helpers ──────────────────────────────────────────────────

function isOwner(userId) {
  return userId === config.OWNER_ID;
}

function splitInput(raw) {
  if (!raw) return [];
  return raw
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

async function fetchAttachmentLines(attachment) {
  try {
    const res = await fetch(attachment.url);
    const text = await res.text();
    return text.split(/\r?\n/).filter((l) => l.trim());
  } catch {
    return [];
  }
}

function stopButton(userId) {
  return new ActionRowBuilder().addComponents(
    new ButtonBuilder()
      .setCustomId(`xboxstop_${userId}`)
      .setLabel("⏹ Stop")
      .setStyle(ButtonStyle.Danger)
  );
}

function makeEmbed() {
  return new EmbedBuilder()
    .setColor(config.COLORS.PRIMARY)
    .setFooter({ text: "Xbox Checker" })
    .setTimestamp();
}

function progressBar(current, total, width = 20) {
  const pct = total > 0 ? current / total : 0;
  const filled = Math.round(pct * width);
  return "█".repeat(filled) + "░".repeat(width - filled) + ` ${current}/${total}`;
}

function statsEmbed(stats) {
  return makeEmbed()
    .setTitle("📊 Xbox Check Results")
    .setDescription(
      [
        `**Checked:** ${stats.checked}`,
        `**Hits (Active):** ${stats.hits}`,
        `**Free (Expired):** ${stats.free}`,
        `**Locked (2FA/Ban):** ${stats.locked}`,
        `**Fails:** ${stats.fails}`,
        `**Retries:** ${stats.retries}`,
        `**CPM:** ${stats.cpm}`,
        `**Time:** ${stats.elapsed}`,
      ].join("\n")
    );
}

function textAttachment(lines, filename) {
  const buffer = Buffer.from(lines.join("\n"), "utf-8");
  return new AttachmentBuilder(buffer, { name: filename });
}

// ── Main handler ─────────────────────────────────────────────

async function handleXboxCheck(userId, accountsRaw, accountsFile, threads, respond, sendDM) {
  // Parse accounts
  let accounts = splitInput(accountsRaw).filter((a) => a.includes(":"));
  if (accountsFile) {
    const lines = await fetchAttachmentLines(accountsFile);
    accounts = accounts.concat(lines.filter((l) => l.includes(":")));
  }
  accounts = [...new Set(accounts)];

  if (accounts.length === 0) {
    return respond({
      embeds: [makeEmbed().setDescription("❌ No valid `email:pass` combos provided.")],
    });
  }

  const threadCount = Math.min(Math.max(threads || config.MAX_THREADS, 1), 50);

  // Progress embed
  const progressEmbed = makeEmbed().setDescription(
    `🚀 Starting Xbox check on **${accounts.length}** accounts (${threadCount} threads)...\n\n${progressBar(0, accounts.length)}`
  );
  const msg = await respond({
    embeds: [progressEmbed],
    components: [stopButton(userId)],
    fetchReply: true,
  });

  const abortController = new AbortController();
  activeAborts.set(userId, abortController);

  const startTime = Date.now();
  let lastEdit = 0;

  const results = await checkAccounts(
    accounts,
    threadCount,
    (completed, total) => {
      const now = Date.now();
      if (now - lastEdit < 3000) return; // throttle edits
      lastEdit = now;
      const elapsed = ((now - startTime) / 1000).toFixed(1);
      const cpm = elapsed > 0 ? Math.round((completed / (elapsed / 60))) : 0;
      const embed = makeEmbed().setDescription(
        `⏳ Checking...\n\n${progressBar(completed, total)}\n\nCPM: **${cpm}** | Elapsed: **${elapsed}s**`
      );
      msg.edit({ embeds: [embed], components: [stopButton(userId)] }).catch(() => {});
    },
    abortController.signal
  );

  activeAborts.delete(userId);

  // Tally results
  const stats = { checked: results.length, hits: 0, free: 0, locked: 0, fails: 0, retries: 0 };
  const hitLines = [];
  const freeLines = [];
  const lockedLines = [];

  for (const r of results) {
    if (r.status === "hit") {
      stats.hits++;
      const caps = Object.entries(r.captures || {}).map(([k, v]) => `${k}: ${v}`).join(" | ");
      hitLines.push(`${r.user}:${r.password} | ${caps}`);
    } else if (r.status === "free") {
      stats.free++;
      const caps = Object.entries(r.captures || {}).map(([k, v]) => `${k}: ${v}`).join(" | ");
      freeLines.push(`${r.user}:${r.password} | ${caps}`);
    } else if (r.status === "locked") {
      stats.locked++;
      lockedLines.push(`${r.user}:${r.password} -> ${r.detail}`);
    } else if (r.status === "retry") {
      stats.retries++;
    } else {
      stats.fails++;
    }
  }

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  stats.cpm = elapsed > 0 ? Math.round((stats.checked / (elapsed / 60))) : 0;
  stats.elapsed = `${elapsed}s`;

  // Build result files
  const files = [];
  if (hitLines.length > 0) files.push(textAttachment(hitLines, "Hits.txt"));
  if (freeLines.length > 0) files.push(textAttachment(freeLines, "Free_Hits.txt"));
  if (lockedLines.length > 0) files.push(textAttachment(lockedLines, "Locked.txt"));

  const resultEmbed = statsEmbed(stats);

  // Send results via DM
  if (sendDM) {
    try {
      const dmUser = await client.users.fetch(userId);
      const dmChannel = await dmUser.createDM();
      await dmChannel.send({ embeds: [resultEmbed], files });
      await msg.edit({
        embeds: [makeEmbed().setDescription("✅ Done! Results sent to your DMs.")],
        components: [],
      });
    } catch {
      await msg.edit({ embeds: [resultEmbed], files, components: [] });
    }
  } else {
    await msg.edit({ embeds: [resultEmbed], files, components: [] });
  }
}

// ── Event Handlers ───────────────────────────────────────────

client.on("interactionCreate", async (interaction) => {
  // Stop button
  if (interaction.isButton() && interaction.customId.startsWith("xboxstop_")) {
    const targetUser = interaction.customId.split("_")[1];
    if (interaction.user.id !== targetUser && !isOwner(interaction.user.id)) {
      return interaction.reply({ content: "❌ Not your process.", ephemeral: true });
    }
    const controller = activeAborts.get(targetUser);
    if (controller) {
      controller.abort();
      activeAborts.delete(targetUser);
    }
    return interaction.reply({ content: "⏹ Stopped.", ephemeral: true });
  }

  if (!interaction.isChatInputCommand()) return;

  if (interaction.commandName === "xboxcheck") {
    await interaction.deferReply();
    const accountsRaw = interaction.options.getString("accounts");
    const file = interaction.options.getAttachment("file");
    const threads = interaction.options.getInteger("threads");

    return handleXboxCheck(
      interaction.user.id,
      accountsRaw,
      file,
      threads,
      (opts) => {
        if (opts.fetchReply) return interaction.editReply(opts);
        return interaction.editReply(opts);
      },
      true // always DM results
    );
  }

  if (interaction.commandName === "xboxhelp") {
    const embed = makeEmbed()
      .setTitle("📖 Xbox Checker Help")
      .setDescription(
        [
          "**Commands:**",
          "",
          "`/xboxcheck` — Check Xbox/Microsoft accounts",
          "  • `accounts` — email:pass combos (comma or newline separated)",
          "  • `file` — Upload a `.txt` file with combos",
          "  • `threads` — Thread count (default 15, max 50)",
          "",
          "`.xboxcheck <combos>` — Prefix command version",
          "`.xboxcheck` with a `.txt` attachment",
          "",
          "**Results:**",
          "• **HIT** — Active subscription found",
          "• **FREE** — No/expired subscription",
          "• **LOCKED** — 2FA, Banned, or Custom Lock",
          "• **FAIL** — Invalid credentials",
          "",
          "Results are sent via DM with `.txt` files.",
        ].join("\n")
      );
    return interaction.reply({ embeds: [embed] });
  }
});

// ── Prefix commands ──────────────────────────────────────────

client.on("messageCreate", async (message) => {
  if (message.author.bot) return;
  if (!message.content.startsWith(config.PREFIX)) return;

  const args = message.content.slice(config.PREFIX.length).trim().split(/\s+/);
  const cmd = args.shift()?.toLowerCase();

  if (cmd === "xboxcheck") {
    const accountsRaw = args.join("\n");
    const file = message.attachments.first();
    const threadMatch = args.find((a) => /^\d+$/.test(a));
    const threads = threadMatch ? parseInt(threadMatch) : null;

    return handleXboxCheck(
      message.author.id,
      accountsRaw,
      file,
      threads,
      (opts) => {
        if (opts.fetchReply) return message.reply(opts);
        return message.reply(opts);
      },
      true // always DM
    );
  }

  if (cmd === "xboxhelp") {
    const embed = makeEmbed()
      .setTitle("📖 Xbox Checker Help")
      .setDescription(
        "Use `/xboxcheck` or `.xboxcheck` with email:pass combos.\nAttach a `.txt` file for bulk checks.\nResults sent via DM."
      );
    return message.reply({ embeds: [embed] });
  }
});

// ── Ready ────────────────────────────────────────────────────

client.on("ready", () => {
  console.log(`✅ Xbox Checker Bot logged in as ${client.user.tag}`);
  console.log(`   Guilds: ${client.guilds.cache.size}`);
});

client.login(config.BOT_TOKEN);
