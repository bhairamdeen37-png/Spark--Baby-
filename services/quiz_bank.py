"""
Quiz questions: exam/subject/level menu + where the questions come from.

* General Knowledge / History / Geography / Politics / Computers / Science -> ONLINE question bank
  Open Trivia DB (https://opentdb.com, free, no key). No AI needed, so it's instant and costs nothing.
* Exam-style sets (School, Class 11-12 Board, JEE, NEET, SSC, UPSC) -> "bank": questions come from the
  ONLINE question bank first (services/question_bank_online.py: QBANK_BASE_URL + data/qbank/*.json).
  Only if the bank has fewer questions than needed, the AI writes the rest — and those AI questions are
  re-solved by a second model so wrong answer keys are dropped.
* Whatever the source, the correct option is re-placed at a random, balanced position (A/B/C/D), so the
  answer is no longer always A.
"""
import asyncio
import html
import logging
import random

import aiohttp

from config import QUIZ_VERIFY
from services import question_bank_online, quiz_service
from services.quiz_utils import randomize_positions

log = logging.getLogger("spark_baby.quiz_bank")

# exam key -> (label, source, [(subject label, opentdb category id or subject text)])
EXAMS = {
    "gk":   ("🌍 General Knowledge", "web", [("Mixed", None), ("Science", 17), ("History", 23), ("Geography", 22),
                                              ("Politics", 24), ("Sports", 21)]),
    "cs":   ("💻 Computers", "web", [("Computers", 18), ("Maths", 19)]),
    "sch":  ("🏫 School (Class 6-10)", "bank", [("Maths", "Maths"), ("Science", "Science"),
                                              ("Social Science", "Social Science"), ("English", "English"),
                                              ("Mixed", "Mixed subjects")]),
    "brd":  ("📘 Class 11-12 Board", "bank", [("Physics", "Physics"), ("Chemistry", "Chemistry"), ("Maths", "Maths"),
                                            ("Biology", "Biology"), ("English", "English"), ("Mixed", "Mixed subjects")]),
    "jee":  ("⚙️ JEE", "bank", [("Physics", "Physics"), ("Chemistry", "Chemistry"), ("Maths", "Maths"),
                              ("Mixed", "Physics, Chemistry and Maths")]),
    "neet": ("🩺 NEET", "bank", [("Physics", "Physics"), ("Chemistry", "Chemistry"), ("Biology", "Biology"),
                               ("Mixed", "Physics, Chemistry and Biology")]),
    "ssc":  ("🏛 SSC / Railway", "bank", [("Reasoning", "Reasoning"), ("GK", "General Awareness"), ("Maths", "Quantitative Aptitude"),
                                       ("English", "English"), ("Mixed", "Mixed topics")]),
    "upsc": ("📜 UPSC", "bank", [("Polity", "Indian Polity"), ("History", "Indian History"), ("Geography", "Geography"),
                               ("Economy", "Indian Economy"), ("Mixed", "General Studies")]),
}
LEVELS = {"e": ("🟢 Easy", "easy"), "m": ("🟡 Medium", "medium"), "h": ("🔴 Hard", "hard")}
COUNTS = (5, 10)

_EXAM_STYLE = {
    "sch": "NCERT school level (Class 6 to 10)",
    "brd": "Class 11-12 CBSE/State board level (NCERT based)",
    "jee": "JEE Main/Advanced style (conceptual + numerical, single correct answer)",
    "neet": "NEET style (NCERT based, single correct answer)",
    "ssc": "SSC CGL/CHSL/Railway exam style",
    "upsc": "UPSC Prelims style (statement/fact based, single correct answer)",
}


def _clip(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


async def _from_opentdb(category, difficulty, count):
    params = {"amount": count, "type": "multiple", "difficulty": difficulty}
    if category:
        params["category"] = category
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        for attempt in range(2):
            async with s.get("https://opentdb.com/api.php", params=params) as r:
                data = await r.json(content_type=None)
            code = data.get("response_code")
            if code == 0 and data.get("results"):
                return data["results"]
            if code == 5:  # rate limited (1 request / 5s)
                await asyncio.sleep(5.5)
                continue
            if code in (1, 2):  # not enough questions for that filter -> loosen difficulty
                params.pop("difficulty", None)
                continue
            break
    return []


def _convert_web(results):
    out = []
    for item in results:
        q = html.unescape(item["question"])
        correct = html.unescape(item["correct_answer"])
        wrong = [html.unescape(x) for x in item["incorrect_answers"]]
        options = [correct] + wrong
        if len(set(o.strip().lower() for o in options)) < len(options):
            continue
        random.shuffle(options)
        out.append({"question": q, "options": options, "correct_index": options.index(correct),
                    "explanation": f"Sahi jawab: {correct}"})
    return out


def shape_for_poll(questions):
    """Telegram quiz-poll limits: question 300, option 100, explanation 200 characters."""
    out = []
    for q in questions:
        opts = [_clip(o, 100) for o in q["options"]]
        if len(set(opts)) < len(opts):
            continue
        out.append({"question": _clip(q["question"], 270), "options": opts,
                    "correct_index": q["correct_index"], "explanation": _clip(q.get("explanation", ""), 190)})
    return out


async def get_questions(exam: str, subject_idx: int, level: str, count: int):
    """Returns (questions, source_label). Raises on total failure."""
    label, source, subjects = EXAMS[exam]
    sub_label, sub_val = subjects[subject_idx]
    difficulty = LEVELS[level][1]
    questions, parts = [], []
    if source == "web":
        try:
            raw = await _from_opentdb(sub_val, difficulty, count)
            questions = _convert_web(raw)
            if questions:
                parts.append("🌐 Online question bank (Open Trivia DB)")
        except Exception as e:
            log.warning(f"[quiz_bank] opentdb failed: {e}")
        if len(questions) < max(3, count // 2):
            questions, parts = [], []
    elif source == "bank":
        try:
            ask = count + 2 if QUIZ_VERIFY else count
            pool = await question_bank_online.get_questions(exam, sub_label, difficulty, ask)
            trusted = [q for q in pool if q.get("trusted")]
            others = [q for q in pool if not q.get("trusted")]      # Hugging Face rows: re-solve, drop wrong keys
            if others and QUIZ_VERIFY:
                others = await quiz_service.verify_questions(others)
            questions = (trusted + others)[:count]
            if questions:
                parts.append(f"🌐 Online question bank ({len(questions)})")
        except Exception as e:
            log.warning(f"[quiz_bank] online bank failed for {exam}: {e}")
            questions = []
    need = count - len(questions)
    if need > 0:   # bank empty/small, web bank down, or AI-only exam -> AI writes the rest
        topic = sub_val if isinstance(sub_val, str) else (sub_label if sub_label != "Mixed" else label)
        style = _EXAM_STYLE.get(exam, "general knowledge")
        ai_qs = await quiz_service.generate_quiz(f"{topic} ({style})", difficulty, num_questions=need)
        questions = questions + ai_qs
        parts.append("🤖 AI generated" + (" + answer-checked" if QUIZ_VERIFY else ""))
    random.shuffle(questions)
    questions = shape_for_poll(questions)[:count]
    if not questions:
        raise ValueError("no_valid_questions")
    # correct answer at a random, balanced position (never "always A")
    return randomize_positions(questions), " + ".join(parts)


async def get_daily(count: int = 5):
    """Free mixed quiz for the daily auto-post (online bank only, no AI cost)."""
    raw = await _from_opentdb(None, random.choice(["easy", "medium"]), count)
    qs = shape_for_poll(_convert_web(raw))
    if not qs:
        raise ValueError("no_questions")
    return randomize_positions(qs[:count])
