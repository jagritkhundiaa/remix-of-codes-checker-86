const { REST, Routes, SlashCommandBuilder } = require("discord.js");
const config = require("./config");

const commands = [
  new SlashCommandBuilder()
    .setName("xboxcheck")
    .setDescription("Check Xbox/Microsoft accounts for subscriptions & captures")
    .addStringOption((o) =>
      o.setName("accounts").setDescription("email:pass combos (one per line, or comma-separated)").setRequired(false)
    )
    .addAttachmentOption((o) =>
      o.setName("file").setDescription("Upload a .txt file with email:pass combos").setRequired(false)
    )
    .addIntegerOption((o) =>
      o.setName("threads").setDescription("Number of threads (default 15, max 50)").setRequired(false)
    ),

  new SlashCommandBuilder()
    .setName("xboxhelp")
    .setDescription("Show Xbox checker help"),
].map((c) => c.toJSON());

const rest = new REST({ version: "10" }).setToken(config.BOT_TOKEN);

(async () => {
  try {
    console.log("Registering slash commands...");
    await rest.put(Routes.applicationCommands(config.CLIENT_ID), { body: commands });
    console.log("✅ Commands registered successfully!");
  } catch (err) {
    console.error("Failed to register commands:", err);
  }
})();
