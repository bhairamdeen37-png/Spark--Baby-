import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ChatAction

from config import MAX_ANSWER_CHARS
from services import access_service, notes_service

log = logging.getLogger("spark_baby.notes")
router = Router(name="notes")

VALID_STYLES = ("short", "detailed", "formula_sheet", "flashcards")


def _chunk(text: str, size: int) -> list:
    return [text[i:i + size] for i in range(0, len(text), size)] or [text]


@router.message(Command("notes"))
async def notes_cmd(message: Message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    arg_text = args[1].strip() if len(args) > 1 else ""

    if not arg_text:
        return await message.reply(
            "Usage: `/notes <topic> [short|detailed|formula_sheet|flashcards]`\n"
            "Jaise: `/notes Photosynthesis short`", parse_mode="Markdown"
        )

    style = "detailed"
    for s in VALID_STYLES:
        if arg_text.lower().endswith(s):
            style = s
            arg_text = arg_text[: -len(s)].strip()
            break
    topic = arg_text

    access = await access_service.check_access(user_id, "text")
    if not access["allowed"]:
        wait = access_service.format_reset_time(access["reset_in_seconds"])
        return await message.reply(f"⏳ Aaj ka limit khatam ho gaya. Reset hoga ~{wait} me, ya /premium lo.")

    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    try:
        notes = await notes_service.generate_notes(topic, style)
    except Exception as e:
        log.error(f"[notes] generation failed for '{topic}': {e}")
        return await message.reply("😔 Notes generate nahi ho paye abhi, thodi der me try karo.")

    for chunk in _chunk(notes, MAX_ANSWER_CHARS):
        await message.reply(chunk, parse_mode="Markdown")
