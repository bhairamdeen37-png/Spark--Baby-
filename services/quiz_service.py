"""
Generates MCQ quizzes through the AI router and tracks per-user quiz state.
AI-generated answer keys are NOT blindly trusted as ground truth for scoring —
we store the model's own stated correct_index/explanation pair together, so
scoring is at least internally consistent, and we validate the JSON shape
strictly before using it (deterministic check instead of trusting raw text).
"""
import json
import logging
import re

from config import AI_PROVIDER_ORDER, QUIZ_VERIFY
from services import ai_router
from services.math_format import plain_math
from services.quiz_utils import has_positional_option, randomize_positions
from storage import repositories as repo

log = logging.getLogger("spark_baby.quiz_service")

QUIZ_SYSTEM_PROMPT = (
    "You are a quiz generator for a study app. Output ONLY valid JSON — no "
    "markdown fences, no commentary before or after. The JSON must be a list "
    "of objects, each with exactly these keys: "
    '"question" (string), "options" (list of exactly 4 strings), '
    '"correct_index" (integer 0-3), "explanation" (short string). '
    "Do not invent fake facts — keep questions factually sound for the given "
    "topic and difficulty. Write ALL maths in plain Unicode text, NEVER LaTeX "
    "(use x², √2, 1/2, 45°, θ, π, log₁₀ x, sin 30° — not \\frac, \\sqrt, $...$). "
    "Solve each question yourself first and make sure correct_index points to the truly correct "
    "option; the 3 wrong options must be clearly wrong; all 4 options must be different. "
    "Every question must have exactly ONE unambiguous correct answer. Numerical answers must be exact "
    "(re-check the arithmetic and units). Do NOT use options like 'All of the above', 'None of these' or "
    "'Both A and B'. Spread the correct answer over different positions (do not always use index 0)."
)

VERIFY_SYSTEM_PROMPT = (
    "You are a strict answer-key checker for JEE / NEET / competitive exam MCQs. For EACH question, "
    "solve it yourself from scratch (do not guess) and choose the one correct option. "
    "If no option is correct, more than one is correct, or the question is ambiguous or factually wrong, "
    "answer -1. Output ONLY valid JSON, no markdown, no commentary: a list like "
    '[{"id": 0, "answer": 2}, {"id": 1, "answer": -1}] where "answer" is the option index 0-3 (or -1).'
)
VERIFY_EXTRA = 2          # ask the AI for a couple of extra questions, so dropping bad ones still leaves enough


def _extract_json(text: str) -> str:
    text = text.strip()
    # strip markdown fences if the model added them anyway
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_questions(raw: str) -> list:
    """Tolerant parser: handles extra text around the JSON and a reply that got cut off
    half-way (keeps every complete question object found)."""
    cleaned = _extract_json(raw)
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            data = data.get("questions") or data.get("quiz") or [data]
        return data
    except ValueError:
        pass
    dec, items, i = json.JSONDecoder(), [], 0
    while True:
        i = cleaned.find("{", i)
        if i == -1:
            break
        try:
            obj, end = dec.raw_decode(cleaned, i)
            if isinstance(obj, dict) and "question" in obj:
                items.append(obj)
            i = end
        except ValueError:
            i += 1
    return items


def _parse_answers(raw: str) -> dict:
    """Parses the checker's reply into {question_id: answer_index}. Tolerant of extra text."""
    cleaned = _extract_json(raw)
    items = []
    try:
        data = json.loads(cleaned)
        items = data if isinstance(data, list) else data.get("answers", []) if isinstance(data, dict) else []
    except ValueError:
        dec, i = json.JSONDecoder(), 0
        while True:
            i = cleaned.find("{", i)
            if i == -1:
                break
            try:
                obj, i = dec.raw_decode(cleaned, i)
                items.append(obj)
            except ValueError:
                i += 1
    out = {}
    for it in items:
        if isinstance(it, dict) and isinstance(it.get("id"), int) and isinstance(it.get("answer"), int):
            out[it["id"]] = it["answer"]
    return out


async def verify_questions(questions: list) -> list:
    """
    Second, independent opinion on every answer key: another model solves each question WITHOUT seeing
    the key, and only questions where both agree are kept. This is what makes AI-written JEE/NEET
    questions trustworthy enough to score. If the checker itself fails we keep the questions (and log it)
    rather than leave the user with no quiz.
    """
    if not questions:
        return questions
    payload = [{"id": i, "question": q["question"], "options": q["options"]} for i, q in enumerate(questions)]
    try:
        raw = await ai_router.generate_answer(
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            system_prompt=VERIFY_SYSTEM_PROMPT,
            max_tokens=3000,
            provider_order=list(reversed(AI_PROVIDER_ORDER)),   # prefer a different model than the writer
        )
        answers = _parse_answers(raw)
    except Exception as e:
        log.warning(f"[quiz] answer check failed, keeping unverified questions: {e}")
        return questions
    if len(answers) < max(1, len(questions) // 2):
        log.warning("[quiz] answer check returned too little, keeping unverified questions")
        return questions
    kept = [q for i, q in enumerate(questions) if answers.get(i) == q["correct_index"]]
    log.info(f"[quiz] answer check: kept {len(kept)}/{len(questions)}")
    if not kept:
        log.warning("[quiz] checker disagreed with every key — keeping originals (checker may be unreliable)")
        return questions
    return kept


async def generate_quiz(topic: str, difficulty: str, num_questions: int = 5, verify: bool = None) -> list:
    """
    AI-written MCQs, with two safety nets:
      1. option positions are re-randomised in code (AI always put the right answer at A before);
      2. (optional) a second model re-solves every question and wrong keys are dropped.
    """
    verify = QUIZ_VERIFY if verify is None else verify
    ask_for = min(num_questions + VERIFY_EXTRA, 12) if verify else num_questions
    user_prompt = (
        f"Generate {ask_for} multiple-choice questions on the topic "
        f"\"{topic}\" at {difficulty} difficulty. Remember: JSON only."
    )
    # 5 questions + explanations need far more than the default 600 tokens (that cut the JSON
    # off and made every quiz fail); thinking-type models also spend tokens before answering.
    raw = await ai_router.generate_answer(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=QUIZ_SYSTEM_PROMPT,
        max_tokens=4000 if not verify else 5000,
    )
    data = _parse_questions(raw)

    questions = []
    for item in data:
        if not isinstance(item, dict):
            continue
        q = item.get("question")
        opts = item.get("options")
        ci = item.get("correct_index")
        exp = item.get("explanation", "")
        if (isinstance(q, str) and isinstance(opts, list) and len(opts) == 4
                and isinstance(ci, int) and not isinstance(ci, bool) and 0 <= ci <= 3):
            opts = [plain_math(str(o)) for o in opts]
            if len(set(o.strip().lower() for o in opts)) < 4:
                continue  # duplicate options -> unusable question
            if has_positional_option(opts):
                continue  # "All of the above" etc. can't be shuffled safely
            questions.append({"question": plain_math(q), "options": opts, "correct_index": ci,
                              "explanation": plain_math(exp) if isinstance(exp, str) else ""})
    if not questions:
        raise ValueError(f"quiz_generation_produced_no_valid_questions; raw_start={raw[:200]!r}")

    # shuffle BEFORE checking, so the checker never sees the writer's "always A" layout
    questions = randomize_positions(questions)
    if verify:
        questions = await verify_questions(questions)
    questions = questions[:num_questions]
    return randomize_positions(questions)   # final balanced placement for the questions we keep


async def start_session(user_id: int, topic: str, difficulty: str, questions: list):
    await repo.save_quiz_session(user_id, {
        "topic": topic, "difficulty": difficulty,
        "questions": questions, "current": 0, "score": 0,
    })


async def get_session(user_id: int):
    return await repo.get_quiz_session(user_id)


async def answer_current(user_id: int, selected_index: int) -> dict:
    """Returns {correct, explanation, correct_index, finished, score, total}."""
    session = await repo.get_quiz_session(user_id)
    if session is None:
        return {"error": "no_active_quiz"}

    idx = session["current"]
    questions = session["questions"]
    if idx >= len(questions):
        return {"error": "no_active_quiz"}

    q = questions[idx]
    correct = selected_index == q["correct_index"]
    if correct:
        session["score"] += 1
    session["current"] += 1
    finished = session["current"] >= len(questions)

    await repo.save_quiz_session(user_id, session)
    if finished:
        await repo.clear_quiz_session(user_id)

    return {
        "correct": correct,
        "explanation": q.get("explanation", ""),
        "correct_index": q["correct_index"],
        "finished": finished,
        "score": session["score"],
        "total": len(questions),
    }


async def cancel_session(user_id: int):
    await repo.clear_quiz_session(user_id)
