"""
Liya's private diary about the OWNER (only filled from private chats with the owner, only shown
to the AI when the owner is the one talking — never revealed to anyone else).
"""
import asyncio
import json
import logging
import re

from storage import repositories as repo
from services import ai_router, memory_service

log = logging.getLogger("spark_baby.diary")

MAX_FACTS = 40
EVERY_N_MESSAGES = 6
_counter = 0
_lock = asyncio.Lock()
_tasks = set()

_EXTRACT_SYSTEM = (
    "You maintain a private diary of facts about ONE person: the bot owner (the girlfriend's boyfriend). "
    "You get the current diary and the latest chat. Return ONLY a JSON list of strings: the UPDATED diary. "
    "Keep useful long-term facts: likes/dislikes, birthday, family and friends' names, exams and goals, "
    "daily routine, favourite food/songs/shows, important dates, promises, mood patterns, nicknames. "
    f"Max {MAX_FACTS} short facts (each under 120 characters, same language style as the chat). "
    "Merge duplicates, drop outdated ones, keep old facts unless contradicted. "
    "NEVER store passwords, OTPs, card/bank numbers, IDs, addresses, or anything secret. "
    "Do not store facts about other people except their names/relation. No commentary, JSON only."
)

_SECRET_RE = re.compile(r"(password|passcode|otp|pin\b|cvv|card|account number|aadhaar|aadhar|pan\b|\b\d{9,}\b)", re.I)


async def prompt_block() -> str:
    facts = await repo.diary_all()
    if not facts:
        return ""
    return ("\n\nYOUR PRIVATE DIARY ABOUT HIM (use naturally when it fits, e.g. remembering his exam, "
            "favourite food or mood; never dump the list, never show it to anyone else):\n- "
            + "\n- ".join(facts))


def note_owner_dm_message(chat_id: int):
    """Call after each owner DM turn; every Nth message updates the diary in the background."""
    global _counter
    _counter += 1
    if _counter % EVERY_N_MESSAGES:
        return
    t = asyncio.create_task(_extract(chat_id))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


def _parse(raw: str):
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    i, j = raw.find("["), raw.rfind("]")
    if i == -1 or j == -1:
        return None
    try:
        data = json.loads(raw[i:j + 1])
    except ValueError:
        return None
    out = []
    for f in data:
        if isinstance(f, str):
            f = " ".join(f.split())[:120]
            if f and not _SECRET_RE.search(f) and f not in out:
                out.append(f)
    return out[:MAX_FACTS]


async def _extract(chat_id: int):
    if _lock.locked():
        return
    async with _lock:
        try:
            history = await memory_service.get_history(chat_id)
            if not history:
                return
            chat = "\n".join(f"{'OWNER' if m['role'] == 'user' else 'LIYA'}: {m['content'][:300]}"
                             for m in history[-14:])
            current = await repo.diary_all()
            prompt = ("CURRENT DIARY:\n" + json.dumps(current, ensure_ascii=False) +
                      "\n\nLATEST CHAT:\n" + chat + "\n\nReturn the updated diary JSON list now.")
            raw = await ai_router.generate_answer(
                messages=[{"role": "user", "content": prompt}], system_prompt=_EXTRACT_SYSTEM, max_tokens=1500)
            facts = _parse(raw)
            if facts is not None and (facts or not current):
                await repo.diary_replace(facts)
                log.info(f"[diary] updated, {len(facts)} facts")
        except Exception as e:
            log.warning(f"[diary] extract failed: {e}")
