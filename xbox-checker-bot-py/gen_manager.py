import os
import json
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "gen")
STOCK_DIR = os.path.join(DATA_DIR, "stock")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

def _ensure():
    os.makedirs(STOCK_DIR, exist_ok=True)

def _load(path, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default

def _save(path, data):
    _ensure()
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


class GenManager:
    def __init__(self):
        _ensure()
        self.users = _load(USERS_FILE, {})
        self.config = _load(CONFIG_FILE, {
            "free_limit": 20, "premium_limit": 50,
            "categories": [], "premium_users": {},
        })
        self.config.setdefault("categories", [])
        self.config.setdefault("premium_users", {})
        self.config.setdefault("free_limit", 20)
        self.config.setdefault("premium_limit", 50)

    def save(self):
        _save(USERS_FILE, self.users)
        _save(CONFIG_FILE, self.config)

    # categories

    def get_categories(self):
        return list(self.config["categories"])

    def add_category(self, name):
        key = name.lower().strip()
        if key in self.config["categories"]:
            return False
        self.config["categories"].append(key)
        p = os.path.join(STOCK_DIR, f"{key}.txt")
        if not os.path.exists(p):
            open(p, "w").close()
        self.save()
        return True

    def remove_category(self, name):
        key = name.lower().strip()
        if key not in self.config["categories"]:
            return False
        self.config["categories"].remove(key)
        p = os.path.join(STOCK_DIR, f"{key}.txt")
        if os.path.exists(p):
            os.remove(p)
        self.save()
        return True

    def category_exists(self, name):
        return name.lower().strip() in self.config["categories"]

    # stock

    def get_stock(self, cat):
        p = os.path.join(STOCK_DIR, f"{cat.lower().strip()}.txt")
        if not os.path.exists(p):
            return []
        with open(p, "r") as f:
            return [l.strip() for l in f if l.strip()]

    def stock_count(self, cat):
        return len(self.get_stock(cat))

    def all_stock_counts(self):
        return {c: self.stock_count(c) for c in self.config["categories"]}

    def add_stock(self, cat, lines):
        key = cat.lower().strip()
        if not self.category_exists(key):
            return 0
        p = os.path.join(STOCK_DIR, f"{key}.txt")
        existing = self.get_stock(key)
        clean = [l.strip() for l in lines if l.strip()]
        with open(p, "w") as f:
            f.write("\n".join(existing + clean))
        return len(clean)

    def pull_one(self, cat):
        key = cat.lower().strip()
        lines = self.get_stock(key)
        if not lines:
            return None
        item = lines.pop(0)
        p = os.path.join(STOCK_DIR, f"{key}.txt")
        with open(p, "w") as f:
            f.write("\n".join(lines))
        return item

    def clear_stock(self, cat):
        p = os.path.join(STOCK_DIR, f"{cat.lower().strip()}.txt")
        if os.path.exists(p):
            open(p, "w").close()

    # premium

    def is_premium(self, uid):
        return str(uid) in self.config["premium_users"]

    def add_premium(self, uid):
        self.config["premium_users"][str(uid)] = {"added": int(datetime.now().timestamp())}
        self.save()

    def remove_premium(self, uid):
        self.config["premium_users"].pop(str(uid), None)
        self.save()

    def premium_list(self):
        return list(self.config["premium_users"].keys())

    # limits

    @property
    def free_limit(self):
        return self.config["free_limit"]

    @property
    def premium_limit(self):
        return self.config["premium_limit"]

    def set_free_limit(self, n):
        self.config["free_limit"] = n
        self.save()

    def set_premium_limit(self, n):
        self.config["premium_limit"] = n
        self.save()

    def daily_limit(self, uid):
        return self.premium_limit if self.is_premium(uid) else self.free_limit

    # user tracking

    def _today(self):
        return datetime.utcnow().strftime("%Y-%m-%d")

    def _user(self, uid):
        uid = str(uid)
        if uid not in self.users:
            self.users[uid] = {"total": 0, "daily": 0, "reset": self._today(), "history": {}}
        u = self.users[uid]
        if u["reset"] != self._today():
            u["daily"] = 0
            u["reset"] = self._today()
        return u

    def can_gen(self, uid):
        return self._user(uid)["daily"] < self.daily_limit(uid)

    def remaining(self, uid):
        u = self._user(uid)
        return max(0, self.daily_limit(uid) - u["daily"])

    def record(self, uid, cat):
        u = self._user(uid)
        u["total"] += 1
        u["daily"] += 1
        u["history"][cat] = u["history"].get(cat, 0) + 1
        self.save()

    def stats(self, uid):
        u = self._user(uid)
        return {
            "total": u["total"], "today": u["daily"],
            "remaining": self.remaining(uid),
            "limit": self.daily_limit(uid),
            "premium": self.is_premium(uid),
            "history": dict(u["history"]),
        }

    def generate(self, uid, cat):
        if not self.category_exists(cat):
            return {"error": "not_found"}
        if not self.can_gen(uid):
            return {"error": "limit"}
        item = self.pull_one(cat)
        if not item:
            return {"error": "empty"}
        self.record(uid, cat)
        return {"ok": True, "item": item, "left": self.remaining(uid)}