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
from storage import repositories as repo

QUIZ_SYSTEM_PROMPT = (
    "You are a quiz generator for a study app. Output ONLY valid JSON — no "
    "markdown fences, no commentary before or after. The JSON must be a list "
    "of objects, each with exactly these keys: "
    '"question" (string), "options" (list of exactly 4 strings), '
    '"correct_index" (integer 0-3), "explanation" (short string). '
    "Do not invent fake facts — keep questions factually sound for the given "
    "topic and difficulty."
)


def _extract_json(text: str) -> str:
    text = text.strip()
    # strip markdown fences if the model added them anyway
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def generate_quiz(topic: str, difficulty: str, num_questions: int = 5) -> list:
    user_prompt = (
        f"Generate {num_questions} multiple-choice questions on the topic "
        f"\"{topic}\" at {difficulty} difficulty. Remember: JSON only."
    )
    raw = await ai_router.generate_answer(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=QUIZ_SYSTEM_PROMPT,
    )
    cleaned = _extract_json(raw)
    data = json.loads(cleaned)  # let it raise — caller handles ValueError/JSONDecodeError

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
            questions.append({"question": q, "options": opts, "correct_index": ci, "explanation": exp})
    if not questions:
        raise ValueError("quiz_generation_produced_no_valid_questions")
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
