import json
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatAction

from storage import repositories as repo
from services import access_service, quiz_service

log = logging.getLogger("spark_baby.quiz")
router = Router(name="quiz")

LETTERS = ["A", "B", "C", "D"]


def _question_keyboard(options: list) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"{LETTERS[i]}. {opt}"[:64], callback_data=f"quizans:{i}")]
        for i, opt in enumerate(options)
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _send_question(message_or_cb, questions: list, index: int):
    q = questions[index]
    text = f"**Q{index + 1}/{len(questions)}.** {q['question']}"
    target = message_or_cb.message if isinstance(message_or_cb, CallbackQuery) else message_or_cb
    await target.answer(text, reply_markup=_question_keyboard(q["options"]), parse_mode="Markdown")


@router.message(Command("quiz"))
async def quiz_cmd(message: Message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    arg_text = args[1].strip() if len(args) > 1 else ""

    if arg_text.lower() == "cancel":
        await quiz_service.cancel_session(user_id)
        return await message.reply("🛑 Quiz cancel kar diya.")

    if not arg_text:
        return await message.reply(
            "Usage: `/quiz <topic> [easy|medium|hard]`\n"
            "Jaise: `/quiz Photosynthesis medium`", parse_mode="Markdown"
        )

    difficulty = "medium"
    for d in ("easy", "medium", "hard"):
        if arg_text.lower().endswith(d):
            difficulty = d
            arg_text = arg_text[: -len(d)].strip()
            break
    topic = arg_text

    access = await access_service.check_access(user_id, "text")
    if not access["allowed"]:
        wait = access_service.format_reset_time(access["reset_in_seconds"])
        return await message.reply(
            f"⏳ Aaj ka limit khatam ho gaya. Reset hoga ~{wait} me, ya /premium lo."
        )

    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    try:
        questions = await quiz_service.generate_quiz(topic, difficulty, num_questions=5)
    except Exception as e:
        log.error(f"[quiz] generation failed for '{topic}': {e}")
        return await message.reply(
            "😔 Quiz generate nahi ho paya abhi. Topic thoda specific likh kar dobara try karo."
        )

    await quiz_service.start_session(user_id, topic, difficulty, questions)
    await message.reply(f"🎯 **Quiz: {topic} ({difficulty})** — {len(questions)} questions. Good luck!",
                         parse_mode="Markdown")
    await _send_question(message, questions, 0)


@router.callback_query(lambda c: c.data and c.data.startswith("quizans:"))
async def quiz_answer_cb(callback: CallbackQuery):
    user_id = callback.from_user.id
    selected = int(callback.data.split(":")[1])

    session = await quiz_service.get_session(user_id)
    if session is None:
        return await callback.answer("Ye quiz ab active nahi hai. /quiz <topic> se naya shuru karo.",
                                      show_alert=True)

    result = await quiz_service.answer_current(user_id, selected)
    if "error" in result:
        return await callback.answer("Ye quiz ab active nahi hai.", show_alert=True)

    mark = "✅ Correct!" if result["correct"] else f"❌ Wrong — correct: {LETTERS[result['correct_index']]}"
    feedback = f"{mark}\n{result['explanation']}" if result["explanation"] else mark

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(feedback)
    await callback.answer()

    if result["finished"]:
        pct = round(100 * result["score"] / result["total"]) if result["total"] else 0
        await callback.message.answer(
            f"🏁 **Quiz khatam!** Score: {result['score']}/{result['total']} ({pct}%)\n"
            f"Naya quiz: `/quiz <topic>`", parse_mode="Markdown"
        )
    else:
        session = await quiz_service.get_session(user_id)
        await _send_question(callback, session["questions"], session["current"])
