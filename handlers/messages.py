"""
Core question-handling flow: DM auto-handles any text/photo; groups only
respond when study mode is ON and the message is a mention, a reply to the
bot, or an explicit /ask /solve /explain command.
"""
import asyncio
import logging
import re

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


SKIP_TAG = "[[SKIP]]"


def _strip_mention(text: str) -> str:
    if text and bot_state.username:
        text = re.sub(rf"@{re.escape(bot_state.username)}\b", "", text, flags=re.I).strip()
    return text


async def process_question(message: Message, question_text: str, image_bytes: bytes = None,
                            image_mime: str = "image/jpeg", auto: bool = False):
    user_id = message.from_user.id
    chat_id = message.chat.id
    is_group = message.chat.type != ChatType.PRIVATE
    kind = "image" if image_bytes is not None else "text"

    await repo.ensure_user(user_id, message.from_user.username, message.from_user.first_name)

    async with _lock_for(user_id):
        scope = "auto" if auto else ("group" if is_group else "dm")
        access = await access_service.check_access(user_id, kind, scope)
        if not access["allowed"]:
            wait = access_service.format_reset_time(access["reset_in_seconds"])
            kind_label = "images" if kind == "image" else "messages"
            if is_group:
                return await message.reply(
                    f"⏳ Group ke aaj ke messages khatam ho gaye. Reset hoga ~{wait} me, "
                    "ya /premium se unlimited karo. (Group me jo question khud solve hote hain wo free hain 😊)")
            return await message.reply(
                f"⏳ **Aaj ke {kind_label} khatam ho gaye.**\n"
                f"Reset hoga ~{wait} me, ya /premium se abhi unlimited karo."
                , parse_mode="Markdown"
            )

        detailed_mode = await access_service.can_use_detailed_mode(user_id) and await repo.get_detailed_mode(user_id)
        is_owner = user_id in BOT_OWNER_IDS
        speaker = message.from_user.first_name or message.from_user.username or ""
        system_prompt = memory_service.build_system_prompt(detailed_mode, is_group, is_owner, speaker)
        if auto:
            system_prompt += ("\n\nAUTO-SOLVE: nobody asked you directly. Only answer if the message is a genuine "
                              "academic/study question (maths, science, concepts, homework, MCQ etc). If it is just "
                              f"chatting, a meme, a greeting or not a question, reply with exactly {SKIP_TAG} and nothing else.")
        history = await memory_service.get_history(chat_id)

        await message.bot.send_chat_action(chat_id, ChatAction.TYPING)

        shown_q = question_text or "(image question, see attached image)"
        if is_group:  # group history is shared, so tag who said what
            shown_q = f"[{speaker or 'user'}]: {shown_q}"
        api_messages = history + [{"role": "user", "content": shown_q}]

        async def _typing():
            while True:
                await asyncio.sleep(4)
                try:
                    await message.bot.send_chat_action(chat_id, ChatAction.TYPING)
                except Exception:
                    return
        typing_task = asyncio.create_task(_typing())
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
        finally:
            typing_task.cancel()

        if auto and SKIP_TAG in answer:
            return  # not a study question -> stay silent (nothing saved to memory)

        await memory_service.remember_turn(chat_id, "user", shown_q if is_group else (question_text or "[image]"))
        await memory_service.remember_turn(chat_id, "assistant", answer)

        for chunk in _chunk(answer, MAX_ANSWER_CHARS):
            try:
                await message.reply(chunk, parse_mode="Markdown")
            except Exception:
                await message.reply(chunk)  # markdown parse failure fallback -> plain text


_Q_WORDS = ("kya", "kaise", "kyu", "kyun", "kaun", "kab", "kitna", "kitne", "kitni", "kahan", "konsa", "kaunsa",
            "what", "how", "why", "when", "which", "who", "solve", "find", "calculate", "explain", "define",
            "prove", "derive", "difference", "meaning", "batao", "bataiye", "samjhao", "nikalo", "hal karo")
_MATH_RE = re.compile(r"\d\s*[-+*/^=x×÷]\s*\d|\b(sin|cos|tan|log|sqrt)\b|[∫√∑π]")


def _looks_like_question(text: str) -> bool:
    t = (text or "").strip().lower()
    if len(t) < 6 or re.search(r"\b(kaise ho|kaisi ho|kya haal|kya kar rah|kha(a)?na kha|what'?s up|how are you)", t):
        return False
    if "?" in t or _MATH_RE.search(t):
        return True
    words = set(re.findall(r"[a-z\u0900-\u097f]+", t))
    return any(w in words for w in _Q_WORDS)


async def _auto_eligible(message: Message) -> bool:
    """Group study mode ON: pick up questions without needing a command/mention."""
    if not await repo.get_study_mode(message.chat.id):
        return False
    text = message.text or message.caption or ""
    if message.photo:
        return (not text) or _looks_like_question(text)
    return _looks_like_question(text)


async def _group_eligible(message: Message, explicit_command: bool) -> bool:
    # Direct address (@botusername or reply to the bot) is answered in EVERY group,
    # whether study mode is on or off.
    if explicit_command:
        return True
    text = message.text or message.caption or ""
    if _is_bot_mentioned(text):
        return True
    if await _is_reply_to_bot(message):
        return True
    return False


# ── explicit commands (work in DM always; in groups, always eligible) ──

async def _download_photo(message: Message, photo):
    if photo.file_size and photo.file_size > MAX_IMAGE_BYTES:
        return None
    file = await message.bot.get_file(photo.file_id)
    buf = await message.bot.download_file(file.file_path)
    return buf.read()


async def _run_command(message: Message, arg: str):
    """/ask /solve /explain — works with text, with a photo + caption command,
    or as a reply to someone's photo/text."""
    src = message.reply_to_message
    photo = None
    if message.photo:
        photo = message.photo[-1]
    elif src and src.photo:
        photo = src.photo[-1]
    replied_text = (src.text or src.caption or "") if src else ""

    if photo is not None:
        data = await _download_photo(message, photo)
        if data is None:
            return await message.reply("❌ Image bahut badi hai. Chhoti/compressed photo bhejo.")
        q = arg or replied_text or "Is image me jo question hai usko solve karo."
        return await process_question(message, q, image_bytes=data, image_mime="image/jpeg")
    if not arg and replied_text:
        arg = replied_text
    if not arg:
        return await message.reply("Command ke baad apna question likho, ya kisi question/photo ko reply karke "
                                    "/solve likho. Jaise:\n`/ask 2+2 kitna hota hai?`", parse_mode="Markdown")
    await process_question(message, arg)


@router.message(Command("ask", "solve", "explain"))
async def explicit_ask_cmd(message: Message):
    if message.from_user.is_bot:
        return
    parts = (message.text or "").split(maxsplit=1)
    await _run_command(message, parts[1].strip() if len(parts) > 1 else "")


# photo sent WITH a caption like "/solve" or "/explain 3rd question"
@router.message(F.photo & F.caption.regexp(r"^/(ask|solve|explain)(@\w+)?(\s|$)"))
async def photo_caption_cmd(message: Message):
    if message.from_user.is_bot:
        return
    parts = (message.caption or "").split(maxsplit=1)
    await _run_command(message, parts[1].strip() if len(parts) > 1 else "")


# ── plain text messages (no command) ──

@router.message(F.text & ~F.text.startswith("/"))
async def plain_text_handler(message: Message):
    if message.from_user.is_bot:
        return
    is_group = message.chat.type != ChatType.PRIVATE
    auto = False
    if is_group:
        if not await _group_eligible(message, explicit_command=False):
            if not await _auto_eligible(message):
                return
            auto = True
    await process_question(message, _strip_mention(message.text) or "hello", auto=auto)


# ── photos (image questions) ──

@router.message(F.photo)
async def photo_handler(message: Message):
    if message.from_user.is_bot:
        return
    is_group = message.chat.type != ChatType.PRIVATE
    auto = False
    if is_group:
        if not await _group_eligible(message, explicit_command=False):
            if not await _auto_eligible(message):
                return
            auto = True

    photo = message.photo[-1]  # highest resolution
    if photo.file_size and photo.file_size > MAX_IMAGE_BYTES:
        return await message.reply("❌ Image bahut badi hai. Chhoti/compressed photo bhejo.")

    file = await message.bot.get_file(photo.file_id)
    buf = await message.bot.download_file(file.file_path)
    image_bytes = buf.read()

    caption = _strip_mention(message.caption) or "Is image me jo question hai usko solve karo."
    await process_question(message, caption, image_bytes=image_bytes, image_mime="image/jpeg", auto=auto)
