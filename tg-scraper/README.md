# Hijra Scraper — Telegram CC Forwarder

Real-time Telegram group/channel monitor that scrapes CC patterns from source groups and forwards them with branded formatting to a destination group. Lifetime deduplication ensures no duplicates ever.

## Setup

### 1. Get Telegram API Credentials

1. Go to [my.telegram.org](https://my.telegram.org)
2. Log in with your phone number
3. Go to "API development tools"
4. Create a new application → get `API_ID` and `API_HASH`

### 2. Create a Bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow prompts
3. Copy the bot token

### 3. Configure Environment

Create a `.env` file or export environment variables:

```bash
export TG_API_ID="123456"
export TG_API_HASH="abcdef1234567890"
export TG_PHONE="+1234567890"
export SCRAPER_BOT_TOKEN="123:ABC..."
export ADMIN_IDS="123456789"          # comma-separated
export DEST_CHAT_ID="-1001234567890"  # destination group ID
```

### 4. Install & Run

```bash
cd tg-scraper
pip install -r requirements.txt
python main.py
```

On first run, Telethon will ask for your phone verification code.

## Commands

| Command | Description |
|---------|-------------|
| `/addsrc <link>` | Add a source group/channel |
| `/rmsrc <id>` | Remove a source |
| `/sources` | List all sources |
| `/bulk` | Reply to .txt with links for bulk add |
| `/stats` | View analytics |
| `/logs` | Recent forwards |
| `/export` | Export logs as .txt |
| `/pause` / `/resume` | Pause/resume scraper |
| `/setdest <id>` | Change destination group |
| `/addkw <word>` | Add keyword filter |
| `/addregex <pattern>` | Add regex filter |
| `/filters` | List active filters |
| `/status` | Current bot status |

## Architecture

```
main.py          → Entry point, runs both clients
monitor.py       → Telethon userbot, listens to source groups
commands.py      → Bot commands for admin control
filters.py       → CC pattern detection + custom filters
formatter.py     → Hijra Scraper message template
db.py            → SQLite database (dedup, sources, logs, stats)
config.py        → Environment-based configuration
```

## Forwarded Message Format

```
[ϟ] Hijra Scraper [ϟ]

𝗦𝘁𝗮𝘁𝘂𝘀 - Approved ✅
━━━━━━━━━━━━━
[ϟ] 𝗖𝗖 ⌁ 4111111111111111|12|2025|123
[ϟ] 𝗦𝘁𝗮𝘁𝘂𝘀 : Payment method added successfully ✅
[ϟ] 𝗚𝗮𝘁𝗲 - Stripe Auth
━━━━━━━━━━━━━
[ϟ] 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 : United States 🇺🇸
[ϟ] 𝗜𝘀𝘀𝘂𝗲𝗿 : Chase
[ϟ] 𝗧𝘆𝗽𝗲 : VISA CREDIT
━━━━━━━━━━━━━
[ϟ] Proxy : Live ⚡
```

## Deduplication

Content-based SHA256 hashing ensures **lifetime** dedup — the same CC or message is never forwarded twice, even across restarts. The hash DB persists in `data/scraper.db`.

## Deployment (24/7)

### Using systemd (Linux VPS):

```bash
sudo nano /etc/systemd/system/hijra-scraper.service
```

```ini
[Unit]
Description=Hijra Scraper
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/tg-scraper
EnvironmentFile=/path/to/tg-scraper/.env
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable hijra-scraper
sudo systemctl start hijra-scraper
sudo journalctl -u hijra-scraper -f  # view logs
```

### Using screen:

```bash
screen -S scraper
cd tg-scraper && python main.py
# Ctrl+A, D to detach
# screen -r scraper to reattach
```
