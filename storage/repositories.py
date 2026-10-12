"""
All database reads/writes live here. Handlers and services call these
functions instead of writing raw SQL inline.
"""
import json
import secrets
import string

from storage.database import get_db, now_ts
from config import MAX_MEMORY_MESSAGES, LIMIT_WINDOW_SECONDS


# ═══════════════ USERS ═══════════════

async def ensure_user(user_id: int, username: str = None, first_name: str = None):
    db = get_db()
    await db.execute(
        """INSERT INTO users (user_id, username, first_name, created_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
             username = COALESCE(excluded.username, users.username),
             first_name = COALESCE(excluded.first_name, users.first_name)""",
        (user_id, username, first_name, now_ts()),
    )
    await db.commit()


async def get_user(user_id: int):
    db = get_db()
    cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return await cur.fetchone()


async def is_premium(user_id: int) -> bool:
    row = await get_user(user_id)
    return bool(row and row["premium_until"] and row["premium_until"] > now_ts())


async def premium_expiry(user_id: int):
    row = await get_user(user_id)
    return row["premium_until"] if row else 0


async def grant_premium_days(user_id: int, days: int):
    """Stacks on top of existing premium if the user already has time left."""
    db = get_db()
    row = await get_user(user_id)
    base = max(now_ts(), row["premium_until"] if row and row["premium_until"] else 0)
    new_until = base + days * 86400
    await db.execute(
        "UPDATE users SET premium_until = ? WHERE user_id = ?", (new_until, user_id)
    )
    await db.commit()
    return new_until


async def revoke_premium(user_id: int):
    db = get_db()
    await db.execute("UPDATE users SET premium_until = 0 WHERE user_id = ?", (user_id,))
    await db.commit()


async def set_detailed_mode(user_id: int, enabled: bool):
    db = get_db()
    await db.execute(
        "UPDATE users SET detailed_mode = ? WHERE user_id = ?", (1 if enabled else 0, user_id)
    )
    await db.commit()


async def get_detailed_mode(user_id: int) -> bool:
    row = await get_user(user_id)
    return bool(row and row["detailed_mode"])


async def set_language(user_id: int, language: str):
    db = get_db()
    await db.execute("UPDATE users SET language = ? WHERE user_id = ?", (language, user_id))
    await db.commit()


# ═══════════════ RATE LIMITS (18hr rolling window, per user, per kind) ═══════════════

async def check_and_consume_quota(user_id: int, kind: str, limit: int) -> tuple:
    """
    Returns (allowed: bool, remaining: int, reset_in_seconds: int).
    Premium bypass is the CALLER's responsibility (check is_premium() first) —
    this function always enforces the given limit.
    """
    db = get_db()
    ts = now_ts()
    cur = await db.execute(
        "SELECT window_start, count FROM usage_windows WHERE user_id = ? AND kind = ?",
        (user_id, kind),
    )
    row = await cur.fetchone()

    if row is None or (ts - row["window_start"]) >= LIMIT_WINDOW_SECONDS:
        # fresh window — either first ever request, or old window expired
        window_start = ts
        count = 0
    else:
        window_start = row["window_start"]
        count = row["count"]

    if count >= limit:
        reset_in = LIMIT_WINDOW_SECONDS - (ts - window_start)
        return False, 0, max(0, reset_in)

    count += 1
    await db.execute(
        """INSERT INTO usage_windows (user_id, kind, window_start, count)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id, kind) DO UPDATE SET window_start = ?, count = ?""",
        (user_id, kind, window_start, count, window_start, count),
    )
    await db.commit()
    remaining = limit - count
    reset_in = LIMIT_WINDOW_SECONDS - (ts - window_start)
    return True, remaining, max(0, reset_in)


async def get_quota_status(user_id: int, kind: str, limit: int) -> tuple:
    """Read-only peek, used by /status — does not consume quota."""
    db = get_db()
    ts = now_ts()
    cur = await db.execute(
        "SELECT window_start, count FROM usage_windows WHERE user_id = ? AND kind = ?",
        (user_id, kind),
    )
    row = await cur.fetchone()
    if row is None or (ts - row["window_start"]) >= LIMIT_WINDOW_SECONDS:
        return limit, 0
    remaining = max(0, limit - row["count"])
    reset_in = LIMIT_WINDOW_SECONDS - (ts - row["window_start"])
    return remaining, reset_in


# ═══════════════ MEMORY (per chat_key = str(chat_id), isolates DM vs each group) ═══════════════

async def remember(chat_key: str, role: str, content: str):
    db = get_db()
    await db.execute(
        "INSERT INTO memory (chat_key, role, content, ts) VALUES (?, ?, ?, ?)",
        (chat_key, role, content[:2000], now_ts()),
    )
    # trim to last MAX_MEMORY_MESSAGES for this chat
    await db.execute(
        """DELETE FROM memory WHERE chat_key = ? AND id NOT IN (
               SELECT id FROM memory WHERE chat_key = ? ORDER BY id DESC LIMIT ?
           )""",
        (chat_key, chat_key, MAX_MEMORY_MESSAGES),
    )
    await db.commit()


async def get_memory(chat_key: str) -> list:
    db = get_db()
    cur = await db.execute(
        "SELECT role, content FROM memory WHERE chat_key = ? ORDER BY id ASC", (chat_key,)
    )
    rows = await cur.fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


async def clear_memory(chat_key: str):
    db = get_db()
    await db.execute("DELETE FROM memory WHERE chat_key = ?", (chat_key,))
    await db.commit()


# ═══════════════ GROUP SETTINGS ═══════════════

async def set_study_mode(chat_id: int, enabled: bool):
    db = get_db()
    await db.execute(
        """INSERT INTO group_settings (chat_id, study_mode) VALUES (?, ?)
           ON CONFLICT(chat_id) DO UPDATE SET study_mode = ?""",
        (chat_id, 1 if enabled else 0, 1 if enabled else 0),
    )
    await db.commit()


async def get_study_mode(chat_id: int) -> bool:
    db = get_db()
    cur = await db.execute("SELECT study_mode FROM group_settings WHERE chat_id = ?", (chat_id,))
    row = await cur.fetchone()
    return bool(row and row["study_mode"])


# ═══════════════ COUPONS ═══════════════

def _generate_code(length: int = 10) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def create_coupon(premium_days: int, validity_days: int, max_uses: int, created_by: int) -> str:
    db = get_db()
    code = _generate_code()
    ts = now_ts()
    expires_at = ts + validity_days * 86400
    await db.execute(
        """INSERT INTO coupons (code, premium_days, expires_at, max_uses, used_count, created_by, created_at)
           VALUES (?, ?, ?, ?, 0, ?, ?)""",
        (code, premium_days, expires_at, max_uses, created_by, ts),
    )
    await db.commit()
    return code


async def get_coupon(code: str):
    db = get_db()
    cur = await db.execute("SELECT * FROM coupons WHERE code = ?", (code.strip().upper(),))
    return await cur.fetchone()


async def list_active_coupons():
    db = get_db()
    cur = await db.execute(
        "SELECT * FROM coupons WHERE expires_at > ? AND used_count < max_uses ORDER BY created_at DESC",
        (now_ts(),),
    )
    return await cur.fetchall()


async def delete_coupon(code: str) -> bool:
    db = get_db()
    cur = await db.execute("DELETE FROM coupons WHERE code = ?", (code.strip().upper(),))
    await db.commit()
    return cur.rowcount > 0


async def redeem_coupon(code: str, user_id: int) -> tuple:
    """Returns (ok: bool, message_key: str, premium_days: int)."""
    db = get_db()
    coupon = await get_coupon(code)
    if coupon is None:
        return False, "not_found", 0
    if coupon["expires_at"] <= now_ts():
        return False, "expired", 0
    if coupon["used_count"] >= coupon["max_uses"]:
        return False, "exhausted", 0

    cur = await db.execute(
        "SELECT 1 FROM coupon_redemptions WHERE code = ? AND user_id = ?",
        (coupon["code"], user_id),
    )
    if await cur.fetchone() is not None:
        return False, "already_used", 0

    await db.execute(
        "INSERT INTO coupon_redemptions (code, user_id, redeemed_at) VALUES (?, ?, ?)",
        (coupon["code"], user_id, now_ts()),
    )
    await db.execute(
        "UPDATE coupons SET used_count = used_count + 1 WHERE code = ?", (coupon["code"],)
    )
    await db.commit()
    return True, "ok", coupon["premium_days"]


# ═══════════════ PAYMENTS (Telegram Stars) ═══════════════

async def record_payment(payment_charge_id: str, user_id: int, plan_key: str, stars: int, days: int):
    db = get_db()
    await db.execute(
        """INSERT OR IGNORE INTO payments (payment_charge_id, user_id, plan_key, stars, days, ts)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (payment_charge_id, user_id, plan_key, stars, days, now_ts()),
    )
    await db.commit()


# ═══════════════ QUIZ SESSIONS ═══════════════

async def save_quiz_session(user_id: int, data: dict):
    db = get_db()
    await db.execute(
        """INSERT INTO quiz_sessions (user_id, data, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET data = ?, updated_at = ?""",
        (user_id, json.dumps(data), now_ts(), json.dumps(data), now_ts()),
    )
    await db.commit()


async def get_quiz_session(user_id: int):
    db = get_db()
    cur = await db.execute("SELECT data FROM quiz_sessions WHERE user_id = ?", (user_id,))
    row = await cur.fetchone()
    return json.loads(row["data"]) if row else None


async def clear_quiz_session(user_id: int):
    db = get_db()
    await db.execute("DELETE FROM quiz_sessions WHERE user_id = ?", (user_id,))
    await db.commit()


# ═══════════════ STATS (owner panel) ═══════════════

async def get_stats() -> dict:
    db = get_db()
    cur = await db.execute("SELECT COUNT(*) c FROM users")
    total_users = (await cur.fetchone())["c"]
    cur = await db.execute("SELECT COUNT(*) c FROM users WHERE premium_until > ?", (now_ts(),))
    premium_users = (await cur.fetchone())["c"]
    cur = await db.execute("SELECT COUNT(*) c FROM group_settings WHERE study_mode = 1")
    active_groups = (await cur.fetchone())["c"]
    cur = await db.execute("SELECT COUNT(*) c FROM coupons WHERE expires_at > ?", (now_ts(),))
    active_coupons = (await cur.fetchone())["c"]
    return {
        "total_users": total_users,
        "premium_users": premium_users,
        "active_groups": active_groups,
        "active_coupons": active_coupons,
    }


# ═══════════════ KEY/VALUE (settings, scheduler markers) ═══════════════

async def kv_get(key: str, default=None):
    db = get_db()
    cur = await db.execute("SELECT value FROM kv WHERE key = ?", (key,))
    row = await cur.fetchone()
    return row["value"] if row else default


async def kv_set(key: str, value):
    db = get_db()
    await db.execute(
        "INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
        (key, str(value), str(value)),
    )
    await db.commit()


# ═══════════════ DIARY (owner-only long-term memory) ═══════════════

async def diary_all() -> list:
    db = get_db()
    cur = await db.execute("SELECT fact FROM diary ORDER BY id ASC")
    return [r["fact"] for r in await cur.fetchall()]


async def diary_replace(facts: list):
    db = get_db()
    await db.execute("DELETE FROM diary")
    ts = now_ts()
    for f in facts:
        await db.execute("INSERT OR IGNORE INTO diary (fact, ts) VALUES (?, ?)", (f, ts))
    await db.commit()


# ═══════════════ QUIZ LEADERBOARD / STREAKS ═══════════════

async def add_quiz_result(chat_id: int, user_id: int, name: str, points: int, correct: int,
                          answered: int, today: str, yesterday: str):
    """Adds one finished quiz to a user's totals and updates the day-streak."""
    db = get_db()
    cur = await db.execute(
        "SELECT points, correct, answered, streak, best_streak, last_day FROM quiz_stats "
        "WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    row = await cur.fetchone()
    if row is None:
        streak = 1
        await db.execute(
            "INSERT INTO quiz_stats (chat_id, user_id, name, points, correct, answered, streak, best_streak, last_day) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (chat_id, user_id, name, points, correct, answered, streak, streak, today))
    else:
        if row["last_day"] == today:
            streak = row["streak"]
        elif row["last_day"] == yesterday:
            streak = row["streak"] + 1
        else:
            streak = 1
        best = max(row["best_streak"], streak)
        await db.execute(
            "UPDATE quiz_stats SET name = ?, points = ?, correct = ?, answered = ?, streak = ?, best_streak = ?, "
            "last_day = ? WHERE chat_id = ? AND user_id = ?",
            (name, row["points"] + points, row["correct"] + correct, row["answered"] + answered,
             streak, best, today, chat_id, user_id))
    await db.commit()
    return streak


async def quiz_top(chat_id: int, limit: int = 10) -> list:
    db = get_db()
    cur = await db.execute(
        "SELECT user_id, name, points, correct, answered, streak FROM quiz_stats WHERE chat_id = ? "
        "ORDER BY points DESC, correct DESC LIMIT ?", (chat_id, limit))
    return [dict(r) for r in await cur.fetchall()]


async def quiz_user(chat_id: int, user_id: int):
    db = get_db()
    cur = await db.execute(
        "SELECT name, points, correct, answered, streak, best_streak FROM quiz_stats "
        "WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    row = await cur.fetchone()
    return dict(row) if row else None


async def kv_keys_like(prefix: str, value: str) -> list:
    """Returns the integer id after 'prefix' for every kv row whose key starts with prefix and value matches."""
    db = get_db()
    cur = await db.execute("SELECT key FROM kv WHERE key LIKE ? AND value = ?", (prefix + "%", value))
    out = []
    for r in await cur.fetchall():
        try:
            out.append(int(r["key"][len(prefix):]))
        except ValueError:
            pass
    return out
