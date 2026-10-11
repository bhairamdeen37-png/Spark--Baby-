from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ChatType

from config import BOT_OWNER_IDS
from storage import repositories as repo

router = Router(name="study")


async def _is_authorised(message: Message) -> bool:
    if message.from_user.id in BOT_OWNER_IDS:
        return True
    try:
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


@router.message(Command("study"))
async def study_cmd(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        return await message.answer(
            "❌ `/study` sirf groups me kaam karta hai. DM me AI already available hai."
        )

    args = message.text.split(maxsplit=1)
    arg = args[1].strip().lower() if len(args) > 1 else ""

    if not arg:
        enabled = await repo.get_study_mode(message.chat.id)
        return await message.answer(f"🤖 Study mode is group me: **{'ON' if enabled else 'OFF'}**",
                                     parse_mode="Markdown")

    if arg not in ("on", "off"):
        return await message.answer("Usage: `/study on` / `/study off` / `/study`", parse_mode="Markdown")

    if not await _is_authorised(message):
        return await message.answer("❌ Sirf group admins ya bot owner `/study` change kar sakte hain.")

    await repo.set_study_mode(message.chat.id, arg == "on")
    state = "ENABLED ✅" if arg == "on" else "DISABLED ❌"
    await message.answer(f"**Study mode {state}** is group me.", parse_mode="Markdown")
