"""
Online question bank for JEE / NEET / SSC / UPSC / Board / School.

Why: AI-written exam questions are often wrong. A curated bank (real, checked questions) is far more
reliable, so quiz_bank tries THIS first and only uses the AI for whatever is missing.

Where questions come from (merged together):
  1. ONLINE  -> {QBANK_BASE_URL}/{exam}.json   (e.g. a GitHub raw folder you control; cached in memory)
  2. LOCAL   -> data/qbank/{exam}.json         (ships with the bot, works even if online is down)
  3. HUGGING FACE datasets (services/hf_dataset_source.py) -> JEE / NEET, answer-checked by AI before use
exam = jee, neet, ssc, upsc, brd, sch. File format is described in data/qbank/README.md.
"""
import json
import logging
import random
import time
from pathlib import Path

import aiohttp

from config import QBANK_BASE_URL, QBANK_CACHE_HOURS
from services import hf_dataset_source

log = logging.getLogger("spark_baby.qbank")

LOCAL_DIR = Path(__file__).resolve().parent.parent / "data" / "qbank"
_cache = {}   # exam -> (fetched_at, [normalised questions])
_LEVELS = ("easy", "medium", "hard")


def is_configured(exam=None) -> bool:
    return (bool(QBANK_BASE_URL) or (LOCAL_DIR.exists() and any(LOCAL_DIR.glob("*.json")))
            or (hf_dataset_source.enabled_for(exam) if exam else False))


def _answer_index(item, options):
    """Accepts correct_index (0-3), answer as a letter 'A'-'D', or answer as the option text."""
    ci = item.get("correct_index")
    if isinstance(ci, int) and not isinstance(ci, bool) and 0 <= ci < len(options):
        return ci
    ans = item.get("answer", item.get("correct"))
    if isinstance(ans, str):
        a = ans.strip()
        if len(a) == 1 and a.upper() in "ABCD":
            return "ABCD".index(a.upper())
        for i, o in enumerate(options):
            if o.strip().lower() == a.lower():
                return i
    return None


def normalize(item, default_subject=""):
    """One raw JSON item -> clean question dict, or None if it is unusable."""
    if not isinstance(item, dict):
        return None
    q = item.get("question") or item.get("q")
    opts = item.get("options")
    if isinstance(opts, dict):   # {"A": "...", "B": "..."}
        opts = [opts[k] for k in sorted(opts)]
    if not isinstance(q, str) or not q.strip() or not isinstance(opts, list) or len(opts) != 4:
        return None
    opts = [str(o).strip() for o in opts]
    if any(not o for o in opts) or len(set(o.lower() for o in opts)) < 4:
        return None
    ci = _answer_index(item, opts)
    if ci is None:
        return None
    level = str(item.get("level", item.get("difficulty", ""))).strip().lower()
    return {
        "question": q.strip(), "options": opts, "correct_index": ci,
        "explanation": str(item.get("explanation", "") or ""),
        "subject": str(item.get("subject", default_subject) or "").strip().lower(),
        "level": level if level in _LEVELS else "",
        "trusted": True,   # your own online/local bank; Hugging Face rows are trusted=False (re-checked by AI)
    }


def _items_from(data):
    if isinstance(data, dict):
        data = data.get("questions", [])
    return data if isinstance(data, list) else []


async def _fetch_online(exam):
    if not QBANK_BASE_URL:
        return []
    url = f"{QBANK_BASE_URL}/{exam}.json"
    timeout = aiohttp.ClientTimeout(total=12)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(url) as r:
                if r.status != 200:
                    log.warning(f"[qbank] {url} -> HTTP {r.status}")
                    return []
                data = await r.json(content_type=None)
        return _items_from(data)
    except Exception as e:
        log.warning(f"[qbank] online fetch failed for {exam}: {e}")
        return []


def _read_local(exam):
    path = LOCAL_DIR / f"{exam}.json"
    if not path.exists():
        return []
    try:
        return _items_from(json.loads(path.read_text(encoding="utf-8")))
    except Exception as e:
        log.warning(f"[qbank] bad local file {path}: {e}")
        return []


async def load(exam):
    """All usable questions for an exam (online + local), cached for QBANK_CACHE_HOURS."""
    hit = _cache.get(exam)
    if hit and time.time() - hit[0] < QBANK_CACHE_HOURS * 3600:
        return hit[1]
    raw = (await _fetch_online(exam)) + _read_local(exam)
    normalised = [normalize(item) for item in raw]
    try:
        normalised += await hf_dataset_source.load(exam)    # curated bank first, HF datasets after
    except Exception as e:
        log.warning(f"[qbank] HF source failed for {exam}: {e}")
    pool, seen = [], set()
    for n in normalised:
        if n and n["question"].lower() not in seen:
            seen.add(n["question"].lower())
            pool.append(n)
    _cache[exam] = (time.time(), pool)
    log.info(f"[qbank] {exam}: {len(pool)} questions loaded")
    return pool


async def get_questions(exam, subject_label, difficulty, count):
    """
    Up to `count` random questions for exam + subject (+ preferred level).
    Fewer than `count` (or none) is normal when the bank is small — the caller tops up with AI.
    """
    pool = await load(exam)
    sub = (subject_label or "").strip().lower()
    if sub and not sub.startswith("mix"):
        pool = [q for q in pool if q["subject"] == sub]
    random.shuffle(pool)
    # your own checked questions first, then preferred level; HF rows / other levels only to fill up
    pool.sort(key=lambda q: (0 if q["trusted"] else 1, 0 if q["level"] == difficulty else 1))
    return [{k: q[k] for k in ("question", "options", "correct_index", "explanation", "trusted")} for q in pool[:count]]
