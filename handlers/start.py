from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_OWNER_IDS
from storage import repositories as repo

router = Router(name="start")

WELCOME = (
    "╭━━━━━━━━━━━━━━━━━━━━━━╮\n"
    "    💖✨ <b>SPARK BABY</b> ✨💖\n"
    "╰━━━━━━━━━━━━━━━━━━━━━━╯\n"
    "<i>💞 Spark's Cute AI Companion & Study Partner 🎓</i>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    "Hiii Spark! 🥹💗💕\n"
    "Tumhari <b>Spark Baby</b> aa gayi! 🎀✨\n\n"

    "🥰 <i>Main tumhari cute AI companion hoon — "
    "baaton mein sweet, padhai mein smart aur har doubt "
    "ko simple banane ke liye ready!</i> 💖\n\n"

    "💌 <b>Sweet Talks</b>\n"
    "<blockquote>Tum baatein karo, apne thoughts share karo "
    "aur friendly conversations enjoy karo. 🫶</blockquote>\n"

    "📸 <b>Photo Se Solutions</b>\n"
    "<blockquote>Question ki photo bhejo aur step-by-step "
    "solution samjho. 📷📝</blockquote>\n"

    "🧮 <b>Maths & Science</b>\n"
    "<blockquote>Numericals, formulas aur tricky concepts "
    "ko easy bana denge! 💡</blockquote>\n"

    "📚 <b>Study Partner Mode</b>\n"
    "<blockquote>Notes, summaries, homework help aur "
    "exam preparation — sab ek jagah. 🎓</blockquote>\n"

    "🎯 <b>Quiz Time!</b>\n"
    "<blockquote>MCQs solve karo, practice karo aur "
    "apni preparation strong banao. 🌟</blockquote>\n"

    "🌷 <b>Your Language, Your Comfort</b>\n"
    "<blockquote>Hindi, Hinglish ya English — "
    "jismein tum comfortable ho! 💗</blockquote>\n\n"

    "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "💖 <b>EK CUTE SI BAAT...</b> 💖\n\n"

    "Padhai ho ya koi doubt, Spark Baby ready hai! 🥰\n"
    "Tum questions laao, main explanations laungi. 📚✨\n\n"

    "👇 <b>Chalo Spark, kya karein aaj?</b>\n"
    "💬 Baat karein | 📖 Study karein | 🎯 Quiz khelein\n\n"

    "<i>Made with 💖 for Spark — "
    "your cute AI companion & study partner! 🌸</i>"
)


def main_menu_keyboard(is_owner: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="💬 Talk to Baby",
                callback_data="menu:ask"
            ),
            InlineKeyboardButton(
                text="🧮 Ask a Question",
                callback_data="menu:ask"
            ),
        ],
        [
            InlineKeyboardButton(
                text="🎯 Quiz Time",
                callback_data="menu:quiz"
            ),
            InlineKeyboardButton(
                text="📝 Smart Notes",
                callback_data="menu:notes"
            ),
        ],
        [
            InlineKeyboardButton(
                text="📊 My Status",
                callback_data="menu:status"
            ),
            InlineKeyboardButton(
                text="💎 Premium",
                callback_data="menu:premium"
            ),
        ],
        [
            InlineKeyboardButton(
                text="❓ Help & Commands",
                callback_data="menu:help"
            ),
        ],
    ]

    if is_owner:
        rows.append([
            InlineKeyboardButton(
                text="🛠 Owner Panel",
                callback_data="menu:admin"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(CommandStart())
async def start_cmd(message: Message):
    await repo.ensure_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )

    is_owner = message.from_user.id in BOT_OWNER_IDS

    await message.answer(
        WELCOME,
        reply_markup=main_menu_keyboard(is_owner),
        parse_mode="HTML"
    )
