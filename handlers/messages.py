"""
Core question-handling flow: DM auto-handles any text/photo; groups only
respond when study mode is ON and the message is a mention, a reply to the
bot, or an explicit /ask /solve /explain command.
"""
import asyncio
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ChatType, ChatAction

from config import MAX_ANSWER_CHARS, MAX_IMAGE_BYTES, BOT_OWNER_IDS
from storage import repositories as repo
from services import access_service, memory_service, bot_state
from services.ai_router import generate_answer, AllProvidersFailedError

log = logging.getLogger("spark_baby.messages")
router = Router(name="messages")

_user_locks: dict = {}


def _lock_for(user_id: int) -> asyncio.Lock:
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]


def _is_bot_mentioned(text: str) -> bool:
    if not text or not bot_state.username:
        return False
    return f"@{bot_state.username.lower()}" in text.lower()


async def _is_reply_to_bot(message: Message) -> bool:
    return bool(
        message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.id == bot_state.user_id
    )


def _chunk(text: str, size: int) -> list:
    return [text[i:i + size] for i in range(0, len(text), size)] or [text]


async def process_question(message: Message, question_text: str, image_bytes: bytes = None,
                            image_mime: str = "image/jpeg"):
    user_id = message.from_user.id
    chat_id = message.chat.id
    is_group = message.chat.type != ChatType.PRIVATE
    kind = "image" if image_bytes is not None else "text"

    await repo.ensure_user(user_id, message.from_user.username, message.from_user.first_name)

    async with _lock_for(user_id):
        access = await access_service.check_access(user_id, kind)
        if not access["allowed"]:
            wait = access_service.format_reset_time(access["reset_in_seconds"])
            kind_label = "images" if kind == "image" else "messages"
            return await message.reply(
                f"⏳ **Aaj ke {kind_label} khatam ho gaye.**\n"
                f"Reset hoga ~{wait} me, ya /premium se abhi unlimited karo."
                , parse_mode="Markdown"
            )

        detailed_mode = await access_service.can_use_detailed_mode(user_id) and await repo.get_detailed_mode(user_id)
        is_owner = user_id in BOT_OWNER_IDS
        speaker = message.from_user.first_name or message.from_user.username or ""
        system_prompt = memory_service.build_system_prompt(detailed_mode, is_group, is_owner, speaker)
        history = await memory_service.get_history(chat_id)

        await message.bot.send_chat_action(chat_id, ChatAction.TYPING)

        shown_q = question_text or "(image question, see attached image)"
        if is_group:  # group history is shared, so tag who said what
            shown_q = f"[{speaker or 'user'}]: {shown_q}"
        api_messages = history + [{"role": "user", "content": shown_q}]

        try:
            answer = await generate_answer(api_messages, system_prompt,
                                            image_bytes=image_bytes, image_mime=image_mime)
        except AllProvidersFailedError as e:
            log.error(f"[AI] all providers failed for user {user_id}: {e.details}")
            return await message.reply(
                "😔 Abhi AI service available nahi hai (sab providers fail ho gaye). "
                "Thodi der me phir try karna."
            )
        except Exception as e:
            log.error(f"[AI] unexpected error for user {user_id}: {e}")
            return await message.reply("😔 Kuch gadbad ho gayi, thodi der me phir try karna.")

        await memory_service.remember_turn(chat_id, "user", shown_q if is_group else (question_text or "[image]"))
        await memory_service.remember_turn(chat_id, "assistant", answer)

        for chunk in _chunk(answer, MAX_ANSWER_CHARS):
            try:
                await message.reply(chunk, parse_mode="Markdown")
            except Exception:
                await message.reply(chunk)  # markdown parse failure fallback -> plain text


async def _group_eligible(message: Message, explicit_command: bool) -> bool:
    if explicit_command:
        return True
    if not await repo.get_study_mode(message.chat.id):
        return False
    text = message.text or message.caption or ""
    if _is_bot_mentioned(text):
        return True
    if await _is_reply_to_bot(message):
        return True
    return False


# ── explicit commands (work in DM always; in groups, always eligible) ──

@router.message(Command("ask", "solve", "explain"))
async def explicit_ask_cmd(message: Message):
    if message.from_user.is_bot:
        return
    parts = message.text.split(maxsplit=1)
    question = parts[1].strip() if len(parts) > 1 else ""
    if not question:
        return await message.reply("Command ke baad apna question likho. Jaise:\n`/ask 2+2 kitna hota hai?`",
                                    parse_mode="Markdown")
    await process_question(message, question)


# ── plain text messages (no command) ──

@router.message(F.text & ~F.text.startswith("/"))
async def plain_text_handler(message: Message):
    if message.from_user.is_bot:
        return
    is_group = message.chat.type != ChatType.PRIVATE
    if is_group:
        if not await _group_eligible(message, explicit_command=False):
            return
    await process_question(message, message.text)


# ── photos (image questions) ──

@router.message(F.photo)
async def photo_handler(message: Message):
    if message.from_user.is_bot:
        return
    is_group = message.chat.type != ChatType.PRIVATE
    if is_group:
        if not await _group_eligible(message, explicit_command=False):
            return

    photo = message.photo[-1]  # highest resolution
    if photo.file_size and photo.file_size > MAX_IMAGE_BYTES:
        return await message.reply("❌ Image bahut badi hai. Chhoti/compressed photo bhejo.")

    file = await message.bot.get_file(photo.file_id)
    buf = await message.bot.download_file(file.file_path)
    image_bytes = buf.read()

    caption = message.caption or "Is image me jo question hai usko solve karo."
    await process_question(message, caption, image_bytes=image_bytes, image_mime="image/jpeg")
