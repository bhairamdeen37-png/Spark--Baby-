"""
Handles taps on the inline main-menu buttons shown after /start.
Reuses the same logic the slash-commands use, just triggered via callback.
"""
from aiogram import Router
from aiogram.types import CallbackQuery

from handlers.help import HELP_TEXT, OWNER_HELP
from handlers.payment import _plans_keyboard
from services import access_service
from storage import repositories as repo
from config import BOT_OWNER_IDS

router = Router(name="menu")


@router.callback_query(lambda c: c.data and c.data.startswith("menu:"))
async def menu_cb(callback: CallbackQuery):
    action = callback.data.split(":", 1)[1]
    await callback.answer()

    if action == "ask":
        await callback.message.answer(
            "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
            "      💖 *LET'S TALK* 💖\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            "Hii! 👋 Main yahan tumhari help ke liye hoon. 💕\n\n"
            "📝 *Apna question seedha type karo*\n"
            "Kisi command ki zarurat nahi hai.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📚 *Available Commands*\n\n"
            "• `/ask <question>`\n"
            "• `/solve <question>`\n"
            "• `/explain <topic>`\n\n"
            "📸 *Photo se question solve karna hai?*\n"
            "Seedha photo bhej do. Caption likhna optional hai.\n\n"
            "✨ _Chalo, milkar question solve karte hain!_ 💗",
            parse_mode="Markdown",
        )

    elif action == "quiz":
        await callback.message.answer(
            "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
            "       🎯 *QUIZ TIME* 🎯\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            "Ready ho apni knowledge test karne ke liye? 📚✨\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🎓 *Quiz Command*\n\n"
            "`/quiz <topic> [easy|medium|hard]`\n\n"
            "📝 *Example:*\n"
            "`/quiz Photosynthesis medium`\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🌱 Easy  •  ⭐ Medium  •  🔥 Hard\n\n"
            "_Apna topic aur difficulty choose karo aur practice shuru karo!_ 💖",
            parse_mode="Markdown",
        )

    elif action == "notes":
        await callback.message.answer(
            "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
            "       📝 *SMART NOTES* 📝\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            "Apni padhai ko organized banao! 📚✨\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📖 *Notes Command*\n\n"
            "`/notes <topic> [short|detailed|formula_sheet|flashcards]`\n\n"
            "📝 *Example:*\n"
            "`/notes Thermodynamics short`\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 Short Notes\n"
            "📚 Detailed Notes\n"
            "🧮 Formula Sheet\n"
            "🎴 Flashcards\n\n"
            "_Apne topic ke liye suitable format choose karo._ 💗",
            parse_mode="Markdown",
        )

    elif action == "status":
        await repo.ensure_user(callback.from_user.id, callback.from_user.username,
                                callback.from_user.first_name)
        text = await access_service.status_text(callback.from_user.id)
        await callback.message.answer(text, parse_mode="Markdown")

    elif action == "premium":
        is_premium = await repo.is_premium(callback.from_user.id)
        prefix = (
            "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
            "     🌟 *PREMIUM ACTIVE* 🌟\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            "Tumhara Premium already active hai! 💎✨\n"
            "Kya tum apna plan extend karna chahte ho?\n\n"
            if is_premium else ""
        )
        await callback.message.answer(
            f"{prefix}"
            "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
            "       💎 *SPARK BABY PREMIUM*\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            "✨ *Premium Benefits*\n\n"
            "✅ Unlimited text + image questions (DM aur groups dono mein)\n"
            "✅ Detailed aur step-by-step answer mode\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👇 *Apna plan choose karo*\n\n"
            "Payment Telegram Stars ke through hota hai. ⭐\n\n"
            "_Choose your plan and continue your learning journey!_ 💖",
            reply_markup=_plans_keyboard(),
            parse_mode="Markdown",
        )

    elif action == "help":
        text = HELP_TEXT
        if callback.from_user.id in BOT_OWNER_IDS:
            text += OWNER_HELP
        await callback.message.answer(text, parse_mode="Markdown")

    elif action == "admin":
        if callback.from_user.id not in BOT_OWNER_IDS:
            return await callback.message.answer(
                "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
                "       🔒 *ACCESS DENIED*\n"
                "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                "❌ Ye sirf bot owner ke liye hai.",
                parse_mode="Markdown",
            )
        stats = await repo.get_stats()
        await callback.message.answer(
            "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
            "      🛠 *OWNER PANEL*\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            "📊 *Bot Statistics*\n\n"
            f"👥 Total users: {stats['total_users']}\n"
            f"🌟 Premium users: {stats['premium_users']}\n"
            f"📚 Active study groups: {stats['active_groups']}\n"
            f"🎟 Active coupons: {stats['active_coupons']}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚙️ *Owner Commands*\n\n"
            "💎 *Grant Premium*\n"
            "`/grantpremium <user_id> <days>`\n\n"
            "🔒 *Revoke Premium*\n"
            "`/revokepremium <user_id>`\n\n"
            "🎟 *Create Coupon*\n"
            "`/createcoupon <premium_days> <validity_days> <max_uses>`\n\n"
            "📋 *List Coupons*\n"
            "`/listcoupons`\n\n"
            "🗑 *Delete Coupon*\n"
            "`/deletecoupon <code>`\n\n"
            "📈 *View Statistics*\n"
            "`/stats`",
            parse_mode="Markdown",
        )
