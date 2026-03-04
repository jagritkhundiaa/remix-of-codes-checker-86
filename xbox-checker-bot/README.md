# Xbox Full Capture Checker — Discord Bot

Port of the Python `backup.py` Xbox checker script to a standalone Node.js Discord bot.

## Features
- **Exact same logic** as the original Python script
- Login via `login.live.com` OAuth flow
- Captures: Payment info (CC, balance, address), subscriptions (active/expired), Bing rewards points
- Results categorized as **HIT** (active sub), **FREE** (expired/no sub), **LOCKED** (2FA/ban), **FAIL** (invalid)
- Results sent via DM with `.txt` file attachments
- Stop button to cancel mid-check
- Supports both `/xboxcheck` slash and `.xboxcheck` prefix commands

## Setup

1. **Create a Discord App** at [discord.com/developers](https://discord.com/developers/applications)
   - Create a Bot, copy the token
   - Enable **Message Content Intent** under Privileged Gateway Intents
   - Generate an OAuth2 URL with `bot` + `applications.commands` scopes

2. **Configure** `src/config.js`:
   ```js
   BOT_TOKEN: "your-bot-token",
   CLIENT_ID: "your-client-id",
   OWNER_ID: "your-discord-user-id",
   ```

3. **Install & Run**:
   ```bash
   cd xbox-checker-bot
   npm install
   node src/deploy-commands.js   # Register slash commands (once)
   node src/index.js             # Start the bot
   ```

## Commands

| Command | Description |
|---------|-------------|
| `/xboxcheck` | Check accounts (paste combos or attach .txt) |
| `.xboxcheck` | Prefix version |
| `/xboxhelp` | Show help |
