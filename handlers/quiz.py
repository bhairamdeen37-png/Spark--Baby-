"""
/quiz  -> ONE setup message with buttons (exam -> subject -> level -> number of questions),
then the quiz runs as native Telegram quiz polls that EVERY member of the chat can answer.
"""
import logging
import secrets

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (Message, CallbackQuery, PollAnswer, InlineKeyboardMarkup,
                           InlineKeyboardButton as Btn)
from aiogram.enums import ChatType

from config import BOT_OWNER_IDS
from storage import repositories as repo
from services import access_service, quiz_bank, quiz_runner

log = logging.getLogger("spark_baby.quiz")
router = Router(name="quiz")

_menu_owner = {}   # (chat_id, message_id) -> user_id who opened the menu
_custom = {}       # token -> custom topic text


def _kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _chunk(btns, n):
    return [btns[i:i + n] for i in range(0, len(btns), n)]


def _exam_menu():
    btns = [Btn(text=lbl, callback_data=f"qz|{key}") for key, (lbl, _, _) in quiz_bank.EXAMS.items()]
    rows = _chunk(btns, 2)
    rows.append([Btn(text="❌ Cancel", callback_data="qz|x")])
    return "🎯 <b>QUIZ SETUP</b>\n\nPehle <b>exam / category</b> chuno 👇", _kb(rows)


def _subject_menu(exam):
    label, _, subjects = quiz_bank.EXAMS[exam]
    btns = [Btn(text=name, callback_data=f"qz|{exam}|{i}") for i, (name, _) in enumerate(subjects)]
    rows = _chunk(btns, 3)
    rows.append([Btn(text="🔙 Back", callback_data="qz|"), Btn(text="❌ Cancel", callback_data="qz|x")])
    return f"🎯 <b>{label}</b>\n\nAb <b>subject</b> chuno 👇", _kb(rows)


def _level_menu(prefix, back, title):
    btns = [Btn(text=lbl, callback_data=f"{prefix}|{k}") for k, (lbl, _) in quiz_bank.LEVELS.items()]
    rows = [btns, [Btn(text="🔙 Back", callback_data=back), Btn(text="❌ Cancel", callback_data="qz|x")]]
    return f"🎯 <b>{title}</b>\n\n<b>Level</b> chuno 👇", _kb(rows)


def _count_menu(prefix, back, title):
    btns = [Btn(text=f"{c} sawal", callback_data=f"{prefix}|{c}") for c in quiz_bank.COUNTS]
    rows = [btns, [Btn(text="🔙 Back", callback_data=back), Btn(text="❌ Cancel", callback_data="qz|x")]]
    return f"🎯 <b>{title}</b>\n\nKitne <b>sawal</b> chahiye? 👇", _kb(rows)


async def _is_admin(bot, chat_id, user_id):
    if user_id in BOT_OWNER_IDS:
        return True
    try:
        m = await bot.get_chat_member(chat_id, user_id)
        return m.status in ("administrator", "creator")
    except Exception:
        return False


@router.message(Command("quiz"))
async def quiz_cmd(message: Message):
    arg = (message.text or "").split(maxsplit=1)
    arg = arg[1].strip() if len(arg) > 1 else ""
    if arg.lower() in ("stop", "cancel"):
        return await _stop(message)
    if quiz_runner.active(message.chat.id):
        return await message.reply("⏳ Is chat me abhi quiz chal raha hai. Rokne ke liye /quizstop")
    if arg:
        tok = secrets.token_hex(3)
        if len(_custom) > 300:
            _custom.clear()
        _custom[tok] = arg[:80]
        text, kb = _level_menu(f"qc|{tok}", "qz|x", f"Topic: {arg[:60]}")
    else:
        text, kb = _exam_menu()
    sent = await message.reply(text, reply_markup=kb, parse_mode="HTML")
    _menu_owner[(sent.chat.id, sent.message_id)] = message.from_user.id


@router.message(Command("quizstop"))
async def quizstop_cmd(message: Message):
    await _stop(message)


async def _stop(message: Message):
    run = quiz_runner.active(message.chat.id)
    if not run:
        return await message.reply("Abhi koi quiz nahi chal raha.")
    uid = message.from_user.id
    if uid != run.starter_id and not await _is_admin(message.bot, message.chat.id, uid):
        return await message.reply("❌ Quiz sirf shuru karne wala ya admin rok sakta hai.")
    quiz_runner.stop(message.chat.id)
    await message.reply("🛑 Quiz rok diya.")


@router.callback_query(F.data.startswith("qz|") | F.data.startswith("qc|"))
async def quiz_menu_cb(cb: CallbackQuery):
    msg = cb.message
    key = (msg.chat.id, msg.message_id)
    owner = _menu_owner.get(key)
    if owner is not None and cb.from_user.id != owner and not await _is_admin(cb.bot, msg.chat.id, cb.from_user.id):
        return await cb.answer("Ye menu /quiz chalane wale ka hai. Apna quiz /quiz se shuru karo 🙂", show_alert=True)
    parts = cb.data.split("|")
    try:
        if parts[0] == "qz":
            if parts[1:] == ["x"]:
                _menu_owner.pop(key, None)
                await msg.delete()
                return await cb.answer("Cancel kar diya")
            if len(parts) == 2 and parts[1] == "":
                text, kb = _exam_menu()
            elif len(parts) == 2:
                text, kb = _subject_menu(parts[1])
            elif len(parts) == 3:
                exam, si = parts[1], int(parts[2])
                label, _, subs = quiz_bank.EXAMS[exam]
                text, kb = _level_menu(f"qz|{exam}|{si}", f"qz|{exam}", f"{label} • {subs[si][0]}")
            elif len(parts) == 4:
                exam, si, lv = parts[1], int(parts[2]), parts[3]
                label, _, subs = quiz_bank.EXAMS[exam]
                text, kb = _count_menu(f"qz|{exam}|{si}|{lv}", f"qz|{exam}|{si}",
                                       f"{label} • {subs[si][0]} • {quiz_bank.LEVELS[lv][0]}")
            else:
                exam, si, lv, cnt = parts[1], int(parts[2]), parts[3], int(parts[4])
                return await _launch(cb, key, exam=exam, si=si, lv=lv, cnt=cnt)
        else:  # custom topic
            tok = parts[1]
            topic = _custom.get(tok)
            if not topic:
                return await cb.answer("Ye menu purana ho gaya. /quiz se phir shuru karo.", show_alert=True)
            if len(parts) == 3:
                text, kb = _count_menu(f"qc|{tok}|{parts[2]}", f"qc|{tok}", f"Topic: {topic[:50]} • {quiz_bank.LEVELS[parts[2]][0]}")
            elif len(parts) == 2:
                text, kb = _level_menu(f"qc|{tok}", "qz|x", f"Topic: {topic[:60]}")
            else:
                return await _launch(cb, key, topic=topic, lv=parts[2], cnt=int(parts[3]))
        await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await cb.answer()
    except Exception as e:
        log.warning(f"[quiz] menu callback error {cb.data}: {e}")
        await cb.answer("Kuch gadbad hui, /quiz se phir try karo.", show_alert=True)


async def _launch(cb: CallbackQuery, key, exam=None, si=0, lv="m", cnt=5, topic=None):
    msg, user = cb.message, cb.from_user
    chat_id = msg.chat.id
    if quiz_runner.active(chat_id):
        await cb.answer("Is chat me quiz chal raha hai.", show_alert=True)
        return
    uses_ai = topic is not None or quiz_bank.EXAMS[exam][1] == "ai"
    if uses_ai and user.id not in BOT_OWNER_IDS:
        scope = "dm" if msg.chat.type == ChatType.PRIVATE else "group"
        access = await access_service.check_access(user.id, "text", scope)
        if not access["allowed"]:
            wait = access_service.format_reset_time(access["reset_in_seconds"])
            await cb.answer(f"Aaj ka limit khatam. ~{wait} me reset hoga, ya /premium lo.", show_alert=True)
            return
    await cb.answer()
    await msg.edit_text("⏳ Sawal taiyaar ho rahe hain...", parse_mode="HTML")
    try:
        if topic is not None:
            from services import quiz_service
            qs = quiz_bank.shape_for_poll(await quiz_service.generate_quiz(topic, quiz_bank.LEVELS[lv][1], cnt))[:cnt]
            title, src = f"{topic} • {quiz_bank.LEVELS[lv][0]}", "🤖 AI generated"
        else:
            qs, src = await quiz_bank.get_questions(exam, si, lv, cnt)
            label, _, subs = quiz_bank.EXAMS[exam]
            title = f"{label} • {subs[si][0]} • {quiz_bank.LEVELS[lv][0]}"
        if not qs:
            raise ValueError("empty")
    except Exception as e:
        log.error(f"[quiz] question fetch failed: {e}")
        await msg.edit_text("😔 Sawal nahi ban paye abhi. Thodi der baad /quiz phir try karo.")
        return
    _menu_owner.pop(key, None)
    try:
        await msg.delete()
    except Exception:
        pass
    run = quiz_runner.start(cb.bot, chat_id, title, qs, user.id, user.full_name)
    if run is None:
        await cb.bot.send_message(chat_id, "Is chat me quiz pehle se chal raha hai.")
    else:
        await cb.bot.send_message(chat_id, f"📚 Source: {src}")


@router.poll_answer()
async def poll_answer_handler(pa: PollAnswer):
    if pa.user:
        quiz_runner.record_answer(pa.poll_id, pa.user.id, pa.user.full_name, pa.option_ids)


@router.message(Command("top", "leaderboard"))
async def top_cmd(message: Message):
    await message.reply(await quiz_runner.leaderboard_text(message.chat.id), parse_mode="HTML")


@router.message(Command("mystats"))
async def mystats_cmd(message: Message):
    st = await repo.quiz_user(message.chat.id, message.from_user.id)
    if not st:
        return await message.reply("Abhi tumne is chat me koi quiz nahi khela. /quiz se shuru karo 🎯")
    acc = round(100 * st["correct"] / st["answered"]) if st["answered"] else 0
    await message.reply(
        f"📊 <b>Tumhara score</b>\n⭐ Points: {st['points']}\n✅ Sahi: {st['correct']}/{st['answered']} ({acc}%)\n"
        f"🔥 Streak: {st['streak']} din (best {st['best_streak']})", parse_mode="HTML")


@router.message(Command("dailyquiz"))
async def dailyquiz_cmd(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        return await message.reply("❌ /dailyquiz sirf groups me kaam karta hai.")
    arg = (message.text or "").split(maxsplit=1)
    arg = arg[1].strip().lower() if len(arg) > 1 else ""
    if arg not in ("on", "off"):
        on = (await repo.kv_get(f"dq:{message.chat.id}")) == "1"
        return await message.reply(f"📅 Daily quiz is group me: <b>{'ON' if on else 'OFF'}</b>\n"
                                   "Badalne ke liye: /dailyquiz on  ya  /dailyquiz off", parse_mode="HTML")
    if not await _is_admin(message.bot, message.chat.id, message.from_user.id):
        return await message.reply("❌ Sirf group admin ya bot owner ye badal sakte hain.")
    await repo.kv_set(f"dq:{message.chat.id}", "1" if arg == "on" else "0")
    await message.reply("✅ Roz subah 9 baje 5 sawal ka daily quiz aayega!" if arg == "on" else "🔕 Daily quiz band.")
