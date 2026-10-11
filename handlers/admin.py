"""
Owner-only commands: direct premium grants, coupon generation/management,
and bot-wide stats. Every handler checks BOT_OWNER_IDS itself — this is a
single standalone bot (no clone/factory system), so ownership is global.
"""
import time

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import BOT_OWNER_IDS
from storage import repositories as repo

router = Router(name="admin")


def _is_owner(message: Message) -> bool:
    return message.from_user.id in BOT_OWNER_IDS


async def _deny(message: Message):
    await message.answer("❌ Ye command sirf bot owner use kar sakta hai.")


@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not _is_owner(message):
        return await _deny(message)
    stats = await repo.get_stats()
    await message.answer(
        "**🛠 Owner Panel — Spark Baby**\n\n"
        f"👥 Total users: {stats['total_users']}\n"
        f"🌟 Premium users: {stats['premium_users']}\n"
        f"📚 Active study groups: {stats['active_groups']}\n"
        f"🎟 Active coupons: {stats['active_coupons']}\n\n"
        "**Commands:**\n"
        "`/grantpremium <user_id> <days>`\n"
        "`/revokepremium <user_id>`\n"
        "`/createcoupon <premium_days> <validity_days> <max_uses>`\n"
        "`/listcoupons`\n"
        "`/deletecoupon <code>`\n"
        "`/stats`",
        parse_mode="Markdown",
    )


@router.message(Command("grantpremium"))
async def grant_premium_cmd(message: Message):
    if not _is_owner(message):
        return await _deny(message)
    parts = message.text.split()
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].lstrip("-").isdigit():
        return await message.answer("Usage: `/grantpremium <user_id> <days>`", parse_mode="Markdown")

    target_id, days = int(parts[1]), int(parts[2])
    if days <= 0:
        return await message.answer("Days 0 se zyada hona chahiye.")

    await repo.ensure_user(target_id)  # in case bot has no record of them yet
    new_until = await repo.grant_premium_days(target_id, days)
    days_left = max(0, (new_until - int(time.time())) // 86400)
    await message.answer(
        f"✅ User `{target_id}` ko {days} din ka premium mil gaya.\n"
        f"Total validity ab: ~{days_left} din.", parse_mode="Markdown"
    )


@router.message(Command("revokepremium"))
async def revoke_premium_cmd(message: Message):
    if not _is_owner(message):
        return await _deny(message)
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return await message.answer("Usage: `/revokepremium <user_id>`", parse_mode="Markdown")
    target_id = int(parts[1])
    await repo.revoke_premium(target_id)
    await message.answer(f"✅ User `{target_id}` ka premium hata diya gaya.", parse_mode="Markdown")


@router.message(Command("createcoupon"))
async def create_coupon_cmd(message: Message):
    if not _is_owner(message):
        return await _deny(message)
    parts = message.text.split()
    if len(parts) != 4 or not all(p.isdigit() for p in parts[1:]):
        return await message.answer(
            "Usage: `/createcoupon <premium_days> <validity_days> <max_uses>`\n"
            "Jaise: `/createcoupon 30 7 50` = 30-din premium wala coupon, "
            "khud 7 din tak valid, max 50 log use kar sakte hain.",
            parse_mode="Markdown",
        )
    premium_days, validity_days, max_uses = int(parts[1]), int(parts[2]), int(parts[3])
    if premium_days <= 0 or validity_days <= 0 or max_uses <= 0:
        return await message.answer("Sab values 0 se zyada honi chahiye.")

    code = await repo.create_coupon(premium_days, validity_days, max_uses, message.from_user.id)
    await message.answer(
        f"✅ **Coupon banaya: `{code}`**\n"
        f"Premium: {premium_days} din\n"
        f"Coupon khud {validity_days} din tak valid\n"
        f"Max uses: {max_uses}\n\n"
        f"Users isko `/redeem {code}` se use kar sakte hain.",
        parse_mode="Markdown",
    )


@router.message(Command("listcoupons"))
async def list_coupons_cmd(message: Message):
    if not _is_owner(message):
        return await _deny(message)
    coupons = await repo.list_active_coupons()
    if not coupons:
        return await message.answer("Koi active coupon nahi hai.")

    lines = ["**🎟 Active coupons:**\n"]
    now = int(time.time())
    for c in coupons:
        days_left = max(0, (c["expires_at"] - now) // 86400)
        lines.append(
            f"`{c['code']}` — {c['premium_days']}d premium, "
            f"{c['used_count']}/{c['max_uses']} used, expires in {days_left}d"
        )
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("deletecoupon"))
async def delete_coupon_cmd(message: Message):
    if not _is_owner(message):
        return await _deny(message)
    parts = message.text.split()
    if len(parts) != 2:
        return await message.answer("Usage: `/deletecoupon <code>`", parse_mode="Markdown")
    deleted = await repo.delete_coupon(parts[1])
    await message.answer("✅ Coupon delete ho gaya." if deleted else "❌ Ye coupon mila nahi.")


@router.message(Command("stats"))
async def stats_cmd(message: Message):
    if not _is_owner(message):
        return await _deny(message)
    stats = await repo.get_stats()
    await message.answer(
        f"👥 Total users: {stats['total_users']}\n"
        f"🌟 Premium users: {stats['premium_users']}\n"
        f"📚 Active study groups: {stats['active_groups']}\n"
        f"🎟 Active coupons: {stats['active_coupons']}"
    )
