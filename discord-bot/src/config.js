// ============================================================
//  CONFIGURATION — Fill these in before running
// ============================================================

module.exports = {
  // Discord Bot Token  (Developer Portal → Bot → Token)
  BOT_TOKEN: "YOUR_BOT_TOKEN_HERE",

  // Application / Client ID  (Developer Portal → General Information)
  CLIENT_ID: "YOUR_CLIENT_ID_HERE",

  // Bot owner Discord user ID (right-click yourself → Copy User ID)
  OWNER_ID: "YOUR_OWNER_ID_HERE",

  // Command prefix for message-based commands
  PREFIX: ".",

  // Max concurrent users allowed to run commands simultaneously
  MAX_CONCURRENT_USERS: 5,

  // Discord webhook for logging valid codes / tokens (optional, leave "" to disable)
  DISCORD_WEBHOOK: "",

  // ── Proxy Settings ──────────────────────────────────────────
  // Set to true to route requests through proxies loaded from proxies.txt
  // Set to false for direct connections
  USE_PROXIES: false,

  // Embed color palette — monochrome
  COLORS: {
    PRIMARY:  0xffffff,   // white
    SUCCESS:  0xd4d4d4,   // neutral-300
    ERROR:    0x737373,   // neutral-500
    WARNING:  0xa3a3a3,   // neutral-400
    EXPIRED:  0x525252,   // neutral-600
    INFO:     0xe5e5e5,   // neutral-200
    MUTED:    0x404040,   // neutral-700
  },
};
