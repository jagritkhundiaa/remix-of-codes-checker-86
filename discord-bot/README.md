# MS Code Checker & WLID Claimer — Discord Bot

A full-featured Discord bot with slash commands and dot-prefix commands. Same exact checker/claimer logic as the web app.

---

## Setup

### 1. Create a Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** → name it → **Create**
3. Go to **Bot** → click **Reset Token** → copy the token
4. Enable these under **Privileged Gateway Intents**:
   - Message Content Intent
5. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Attach Files`, `Embed Links`, `Read Message History`
6. Copy the generated URL and invite the bot to your server

### 2. Configure

Edit `src/config.js`:

```js
BOT_TOKEN: "paste_your_bot_token_here",
CLIENT_ID: "paste_your_application_id_here",
OWNER_ID: "paste_your_discord_user_id_here",
```

### 3. Install & Run

```bash
cd discord-bot
npm install
node src/deploy-commands.js   # Register slash commands (run once)
node src/index.js             # Start the bot
```

---

## Commands

### Slash Commands

| Command | Description |
|---------|-------------|
| `/check` | Check codes against WLID tokens |
| `/claim` | Claim WLID tokens from accounts |
| `/auth` | Authorize a user (owner only) |
| `/deauth` | Remove authorization (owner only) |
| `/authlist` | List authorized users |
| `/stats` | Bot status |

### Dot Prefix Commands

| Command | Description |
|---------|-------------|
| `.check <wlids>` | Check codes (attach codes.txt) |
| `.claim <accounts>` | Claim WLIDs (or attach accounts.txt) |
| `.auth <@user> <duration>` | Authorize user (e.g. `1h`, `7d`, `forever`) |
| `.deauth <@user>` | Remove authorization |
| `.authlist` | List authorized users |
| `.stats` | Bot status |
| `.help` | Show all commands |

### Auth Duration Format

`30s`, `5m`, `2h`, `1d`, `7d`, `1w`, `1mo`, `forever`

---

## Features

- Exact same checking/claiming logic as the website
- 5 max concurrent users (configurable)
- Auth system with expiration
- Professional embeds, no emojis
- Results sent as .txt file attachments
- Progress bar updates during processing
- Works on both mobile and desktop Discord
