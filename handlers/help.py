from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import BOT_OWNER_IDS

router = Router(name="help")

HELP_TEXT = """**📚 Spark Baby — Commands**

**Study**
`/ask <question>` — seedha AI se poocho (ya bina command ke bhi, normal text/photo bhejo)
`/solve <question>` — question solve karo
`/explain <topic>` — concept explain karo
`/notes <topic>` — notes/summary generate karo
`/quiz <topic>` — practice quiz shuru karo

**Settings**
`/mode` — step-by-step/detailed mode (premium only)
`/language` — reply language set karo
`/clear` — is chat ki AI memory clear karo
`/status` — apna plan aur daily usage dekho

**Group (admins only)**
`/study on` / `/study off` — is group me AI ON/OFF
`/study` — is group ka status

**Premium**
`/premium` — plans dekho, Telegram Stars se kharido
`/redeem <code>` — coupon code redeem karo
"""

OWNER_HELP = """
**Owner panel**
`/admin` — owner panel menu
`/grantpremium <user_id> <days>` — kisi ko bhi premium do
`/revokepremium <user_id>` — premium hatao
`/createcoupon <days> <validity_days> <max_uses>` — naya coupon banao
`/listcoupons` — active coupons dekho
`/deletecoupon <code>` — coupon delete karo
`/stats` — bot ke stats
"""


@router.message(Command("help"))
async def help_cmd(message: Message):
    text = HELP_TEXT
    if message.from_user.id in BOT_OWNER_IDS:
        text += OWNER_HELP
    await message.answer(text, parse_mode="Markdown")
