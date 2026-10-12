"""
Generates MCQ quizzes through the AI router and tracks per-user quiz state.
AI-generated answer keys are NOT blindly trusted as ground truth for scoring —
we store the model's own stated correct_index/explanation pair together, so
scoring is at least internally consistent, and we validate the JSON shape
strictly before using it (deterministic check instead of trusting raw text).
"""
import json
import re

from services import ai_router
from services.math_format import plain_math
from storage import repositories as repo

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
    "option; the 3 wrong options must be clearly wrong; all 4 options must be different."
)


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


async def generate_quiz(topic: str, difficulty: str, num_questions: int = 5) -> list:
    user_prompt = (
        f"Generate {num_questions} multiple-choice questions on the topic "
        f"\"{topic}\" at {difficulty} difficulty. Remember: JSON only."
    )
    # 5 questions + explanations need far more than the default 600 tokens (that cut the JSON
    # off and made every quiz fail); thinking-type models also spend tokens before answering.
    raw = await ai_router.generate_answer(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=QUIZ_SYSTEM_PROMPT,
        max_tokens=4000,
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
                and isinstance(ci, int) and 0 <= ci <= 3):
            opts = [plain_math(str(o)) for o in opts]
            if len(set(o.strip().lower() for o in opts)) < 4:
                continue  # duplicate options -> unusable question
            questions.append({"question": plain_math(q), "options": opts, "correct_index": ci,
                              "explanation": plain_math(exp) if isinstance(exp, str) else ""})
    if not questions:
        raise ValueError(f"quiz_generation_produced_no_valid_questions; raw_start={raw[:200]!r}")
    return questions


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
