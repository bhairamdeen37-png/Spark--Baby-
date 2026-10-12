from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import BOT_OWNER_IDS

router = Router(name="help")

HELP_TEXT = """╭━━━━━━━━━━━━━━━━━━━━━━╮
     💖 *SPARK BABY*
      📚 *HELP CENTER*
╰━━━━━━━━━━━━━━━━━━━━━━╯

Hiii! 🥰 Welcome to Spark Baby Help Center!
Yahan tumhe available commands ki information milegi. ✨

━━━━━━━━━━━━━━━━━━━━━━━━
📚 *STUDY & LEARNING*
━━━━━━━━━━━━━━━━━━━━━━━━

🧠 `/ask <question>`
Question seedha AI se poocho. Normal text ya photo bhi bhej sakte ho.

🧮 `/solve <question>`
Apne question ka solution pao.

💡 `/explain <topic>`
Difficult concepts ko simple language mein samjho.

📝 `/notes <topic>`
Notes aur chapter summaries generate karo.

🎯 `/quiz`
Buttons se exam, subject, level aur sawal chuno. Group me sab log jawab de sakte hain!

🏆 `/top` • 📊 `/mystats` • 🛑 `/quizstop`
Leaderboard, apna score aur streak, quiz rokna.

📅 `/dailyquiz on` _(Admins only)_
Roz subah 9 baje group me daily quiz.

━━━━━━━━━━━━━━━━━━━━━━━━
⚙️ *PERSONAL SETTINGS*
━━━━━━━━━━━━━━━━━━━━━━━━

📖 `/mode`
Step-by-step ya detailed mode set karo (Premium only).

🌍 `/language`
Apni preferred reply language set karo.

🧹 `/clear`
Is chat ki AI memory clear karo.

📊 `/status`
Apna plan aur daily usage check karo.

━━━━━━━━━━━━━━━━━━━━━━━━
👥 *GROUP STUDY* _(Admins only)_
━━━━━━━━━━━━━━━━━━━━━━━━

✅ `/study on`
Group mein AI study mode ON karo.

🔕 `/study off`
Group mein AI study mode OFF karo.

📊 `/study`
Group ka current study mode status dekho.

━━━━━━━━━━━━━━━━━━━━━━━━
💎 *PREMIUM & REWARDS*
━━━━━━━━━━━━━━━━━━━━━━━━

🌟 `/premium`
Available plans dekho aur Telegram Stars se purchase karo.

🎟 `/redeem <code>`
Apna coupon code redeem karo.

━━━━━━━━━━━━━━━━━━━━━━━━

💗 _Happy learning with Spark Baby!_
✨ _Keep learning, keep growing._ 🎓
"""

OWNER_HELP = """
━━━━━━━━━━━━━━━━━━━━━━━━
🛠 *OWNER CONTROL PANEL*
━━━━━━━━━━━━━━━━━━━━━━━━

👑 `/admin`
Owner panel open karo.

💎 `/grantpremium <user_id> <days>`
Kisi user ko Premium access do.

🔒 `/revokepremium <user_id>`
User ka Premium access hatao.

🎟 `/createcoupon <days> <validity_days> <max_uses>`
Naya coupon create karo.

📋 `/listcoupons`
Active coupons ki list dekho.

🗑 `/deletecoupon <code>`
Coupon delete karo.

📊 `/stats`
Bot ke statistics dekho.

━━━━━━━━━━━━━━━━━━━━━━━━
👑 _Spark Baby — Owner Controls_
"""

@router.message(Command("help"))
async def help_cmd(message: Message):
    text = HELP_TEXT
    if message.from_user.id in BOT_OWNER_IDS:
        text += OWNER_HELP
    await message.answer(text, parse_mode="Markdown")
