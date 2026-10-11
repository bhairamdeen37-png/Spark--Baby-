"""
Decides whether a given user is allowed to make a text/image request right
now, and whether they're allowed detailed/step-by-step mode. Single place
that encodes the free-vs-premium rules so handlers don't duplicate logic.
"""
from storage import repositories as repo
from config import (FREE_TEXT_DAILY_LIMIT, FREE_IMAGE_DAILY_LIMIT, FREE_GROUP_MEMBER_LIMIT,
                    LIMIT_WINDOW_HOURS, BOT_OWNER_IDS)


async def check_access(user_id: int, kind: str, scope: str = "dm") -> dict:
    """
    kind: 'text' or 'image'
    Returns a dict:
      allowed (bool)
      is_premium (bool)
      remaining (int or None)   -- None means unlimited (premium)
      reset_in_seconds (int or None)
    Premium users bypass the quota entirely (truly unlimited, DM + group).

    scope: 'dm'    -> normal daily text/image limits
           'group' -> member talks to the bot in a group: FREE_GROUP_MEMBER_LIMIT per window
           'auto'  -> bot auto-solved a group question: free, never counted
    Owners and premium users are never limited.
    """
    if scope == "auto" or user_id in BOT_OWNER_IDS:
        return {"allowed": True, "is_premium": True, "remaining": None, "reset_in_seconds": None}
    premium = await repo.is_premium(user_id)
    if premium:
        return {"allowed": True, "is_premium": True, "remaining": None, "reset_in_seconds": None}

    if scope == "group":
        kind, limit = "group", FREE_GROUP_MEMBER_LIMIT
    else:
        limit = FREE_TEXT_DAILY_LIMIT if kind == "text" else FREE_IMAGE_DAILY_LIMIT
    allowed, remaining, reset_in = await repo.check_and_consume_quota(user_id, kind, limit)
    return {
        "allowed": allowed,
        "is_premium": False,
        "remaining": remaining,
        "reset_in_seconds": reset_in,
    }


def format_reset_time(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


async def can_use_detailed_mode(user_id: int) -> bool:
    return await repo.is_premium(user_id)


async def status_text(user_id: int) -> str:
    premium = await repo.is_premium(user_id)
    lines = []
    if premium:
        until = await repo.premium_expiry(user_id)
        import time
        days_left = max(0, (until - int(time.time())) // 86400)
        lines.append("🌟 **Premium active** — unlimited text + image, detailed mode unlocked.")
        lines.append(f"Expires in ~{days_left} day(s).")
    else:
        text_remaining, text_reset = await repo.get_quota_status(user_id, "text", FREE_TEXT_DAILY_LIMIT)
        img_remaining, img_reset = await repo.get_quota_status(user_id, "image", FREE_IMAGE_DAILY_LIMIT)
        lines.append("🆓 **Free plan**")
        lines.append(f"Text: {text_remaining}/{FREE_TEXT_DAILY_LIMIT} left "
                      f"(resets in {format_reset_time(text_reset)})" if text_reset else
                      f"Text: {FREE_TEXT_DAILY_LIMIT}/{FREE_TEXT_DAILY_LIMIT} left")
        lines.append(f"Image: {img_remaining}/{FREE_IMAGE_DAILY_LIMIT} left "
                      f"(resets in {format_reset_time(img_reset)})" if img_reset else
                      f"Image: {FREE_IMAGE_DAILY_LIMIT}/{FREE_IMAGE_DAILY_LIMIT} left")
        lines.append(f"(Limits reset {LIMIT_WINDOW_HOURS}h after your first use in the current window)")
        lines.append("Use /premium to remove limits and unlock detailed mode.")
    return "\n".join(lines)
