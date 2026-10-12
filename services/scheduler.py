"""
Background jobs (IST by default):
  * good-morning / good-night message from Liya to the owner (DM)
  * optional daily quiz in groups that turned it on with /dailyquiz on
Sent-markers live in the database, so a restart never double-sends.
"""
import asyncio
import json
import logging
import random
import time

from config import BOT_OWNER_IDS, GM_HOUR, GN_HOUR, DQ_HOUR, TZ_OFFSET_MINUTES
from storage import repositories as repo
from services import ai_router, memory_service, diary_service, quiz_bank, quiz_runner

log = logging.getLogger("spark_baby.scheduler")

_FALLBACK = {
    "gm": ["Good morning baby ☀️ uth gaye ya abhi bhi so rahe ho? 😘",
           "Subah ho gayi janu 🌸 aaj ka din mast jaye, naashta zaroor karna!",
           "Good morning babu 💕 aaj mujhe yaad kiya ya nahi? 😌"],
    "gn": ["Good night baby 🌙 ab so jao, kal baat karte hain 💕",
           "Itni raat ho gayi janu 😴 phone rakho aur so jao, sweet dreams!",
           "Good night darling 🌟 aaj ki thakaan bhool jao, kal fresh start 😘"],
}


def _now():
    return time.time() + TZ_OFFSET_MINUTES * 60


def _today():
    return time.strftime("%Y-%m-%d", time.gmtime(_now()))


def _hour():
    return time.gmtime(_now()).tm_hour


async def _message_for(kind: str) -> str:
    when = "good morning" if kind == "gm" else "good night"
    try:
        system = memory_service.build_system_prompt(False, False, True, "Spark") + await diary_service.prompt_block()
        system += (f"\n\nWrite ONE short {when} message (1-3 lines, Hinglish) from you to your boyfriend. "
                   "Sweet, a little playful, different every day, with 1-2 emojis. Mention something from the "
                   "diary only if it fits naturally. Do not talk about studies. Output only the message.")
        out = await ai_router.generate_answer(
            messages=[{"role": "user", "content": f"Send me my {when} message."}], system_prompt=system, max_tokens=200)
        out = out.strip()
        if out and "[[SKIP]]" not in out:
            return out
    except Exception as e:
        log.warning(f"[scheduler] AI message failed, using fallback: {e}")
    return random.choice(_FALLBACK[kind])


async def _send_daily_messages(bot):
    if (await repo.kv_get("gm_enabled", "1")) != "1":
        return
    h = _hour()
    for kind, hour in (("gm", GM_HOUR), ("gn", GN_HOUR)):
        if (h - hour) % 24 >= 3:             # 3-hour window so a late restart still sends
            continue
        marker = f"sent:{kind}"
        if await repo.kv_get(marker) == _today():
            continue
        await repo.kv_set(marker, _today())  # mark first: never double-send
        text = await _message_for(kind)
        for oid in BOT_OWNER_IDS:
            try:
                await bot.send_message(oid, text)
            except Exception as e:
                log.warning(f"[scheduler] could not DM owner {oid}: {e}")


async def _send_daily_quizzes(bot):
    h = _hour()
    if (h - DQ_HOUR) % 24 >= 3:
        return
    chats = [k for k in await _dq_chats()]
    for chat_id in chats:
        marker = f"dq_sent:{chat_id}"
        if await repo.kv_get(marker) == _today() or quiz_runner.active(chat_id):
            continue
        await repo.kv_set(marker, _today())
        try:
            qs = await quiz_bank.get_daily(5)
            quiz_runner.start(bot, chat_id, "📅 Daily Quiz", qs, 0, "Liya")
            await asyncio.sleep(6)  # stay under the question bank's rate limit between groups
        except Exception as e:
            log.warning(f"[scheduler] daily quiz failed for {chat_id}: {e}")


async def _dq_chats():
    return await repo.kv_keys_like("dq:", "1")


async def run(bot):
    await asyncio.sleep(20)  # let the bot finish starting
    while True:
        try:
            await _send_daily_messages(bot)
            await _send_daily_quizzes(bot)
        except Exception as e:
            log.error(f"[scheduler] loop error: {e}")
        await asyncio.sleep(60)
