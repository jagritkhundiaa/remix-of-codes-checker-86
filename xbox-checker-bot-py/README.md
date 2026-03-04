# Xbox Checker + Gen Bot (Python)

## Setup

```
pip install -r requirements.txt
```

Edit `config.py` with your bot token, client ID, and owner ID.

## Run

```
python bot.py
```

## Commands

**Gen:** `.gen <category>`, `.gen`, `.stock`, `.stats [@user]`

**Admin:** `.addcategory`, `.removecategory`, `.restock <cat> + .txt`, `.clearstock`, `.addpremium`, `.removepremium`, `.premiumlist`, `.setfree <n>`, `.setpremium <n>`

**Xbox:** `.xboxcheck` (attach .txt), `.xboxhelp`, `.stop`

**Info:** `.help`

Free: 20/day, Premium: 50/day (configurable). Resets midnight UTC.