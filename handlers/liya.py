"""Owner-only extras for Liya: diary, good-morning/good-night switch."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ChatType

from config import BOT_OWNER_IDS, GM_HOUR, GN_HOUR
from storage import repositories as repo

router = Router(name="liya")


def _owner_dm(message: Message) -> bool:
    return message.from_user.id in BOT_OWNER_IDS and message.chat.type == ChatType.PRIVATE


@router.message(Command("diary"))
async def diary_cmd(message: Message):
    if not _owner_dm(message):
        return  # silently ignore: the diary is private
    facts = await repo.diary_all()
    if not facts:
        return await message.answer("📔 Meri diary abhi khali hai. Baat karte raho, main yaad rakhungi 💕")
    text = "📔 Tumhare baare me jo mujhe yaad hai:\n\n" + "\n".join(f"{i + 1}. {f}" for i, f in enumerate(facts))
    await message.answer(text[:4000] + "\n\n(Sab mitane ke liye: /diaryclear)")


@router.message(Command("diaryclear"))
async def diary_clear_cmd(message: Message):
    if not _owner_dm(message):
        return
    await repo.diary_replace([])
    await message.answer("🧹 Meri diary saaf kar di. Ab sab nayi shuru se yaad rakhungi.")


@router.message(Command("gm"))
async def gm_cmd(message: Message):
    if not _owner_dm(message):
        return
    arg = (message.text or "").split(maxsplit=1)
    arg = arg[1].strip().lower() if len(arg) > 1 else ""
    if arg in ("on", "off"):
        await repo.kv_set("gm_enabled", "1" if arg == "on" else "0")
    on = (await repo.kv_get("gm_enabled", "1")) == "1"
    await message.answer(
        f"🌅 Good morning ({GM_HOUR}:00) / 🌙 good night ({GN_HOUR}:00) messages: {'ON ✅' if on else 'OFF ❌'}\n"
        "Badalne ke liye: /gm on  ya  /gm off")
