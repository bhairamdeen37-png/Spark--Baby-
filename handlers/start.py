from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from storage import repositories as repo

router = Router(name="start")

WELCOME = (
    "Hey! 👋 Main Spark Baby hoon — StudyZone ka AI Study Tutor!\n\n"
    "Main tumhari padhai mein help karne ke liye yahan hoon. 📚\n\n"
    "✨ Tum mujhse kar sakte ho:\n\n"
    "📸 Question ki photo bhejkar solution samajhna.\n"
    "🧮 Maths aur Science numericals solve karna.\n"
    "📖 Kisi bhi academic subject par help lena.\n"
    "📝 Notes aur chapter summaries banana (/notes).\n"
    "🎯 MCQs aur practice quizzes karna (/quiz).\n"
    "💡 Difficult concepts ko simple language mein samajhna.\n"
    "🌍 Hindi, Hinglish aur English mein baat karna.\n\n"
    "Apna question bhejo aur chalo padhai shuru karte hain! 🚀\n\n"
    "Kisi bhi waqt /help bhejo saare commands dekhne ke liye."
)


@router.message(CommandStart())
async def start_cmd(message: Message):
    await repo.ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.answer(WELCOME)
