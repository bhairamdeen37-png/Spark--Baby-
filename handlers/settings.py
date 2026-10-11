from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from storage import repositories as repo
from services import memory_service, access_service

router = Router(name="settings")


@router.message(Command("mode"))
async def mode_cmd(message: Message):
    user_id = message.from_user.id
    is_premium = await repo.is_premium(user_id)
    if not is_premium:
        return await message.answer(
            "🔒 **Detailed/step-by-step mode sirf Premium users ke liye hai.**\n"
            "Free plan me normal (concise) answers milte hain.\n"
            "Upgrade karne ke liye /premium bhejo.",
            parse_mode="Markdown",
        )

    current = await repo.get_detailed_mode(user_id)
    new_val = not current
    await repo.set_detailed_mode(user_id, new_val)
    state = "ON — detailed, step-by-step answers" if new_val else "OFF — normal concise answers"
    await message.answer(f"✅ **Answer mode set to: {state}**", parse_mode="Markdown")


@router.message(Command("language"))
async def language_cmd(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.answer(
            "Usage: `/language hindi` ya `/language english` ya `/language hinglish` ya "
            "`/language auto` (auto = jis language me tum likho usi me reply)",
            parse_mode="Markdown",
        )
    lang = args[1].strip().lower()
    if lang not in ("hindi", "english", "hinglish", "auto"):
        return await message.answer("Valid options: hindi, english, hinglish, auto")
    await repo.set_language(message.from_user.id, lang)
    await message.answer(f"✅ **Language set to: {lang}**", parse_mode="Markdown")


@router.message(Command("clear"))
async def clear_cmd(message: Message):
    await memory_service.clear(message.chat.id)
    await message.answer("🧹 **Is chat ki AI memory clear kar di gayi.**", parse_mode="Markdown")


@router.message(Command("status"))
async def status_cmd(message: Message):
    await repo.ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    text = await access_service.status_text(message.from_user.id)
    await message.answer(text, parse_mode="Markdown")
