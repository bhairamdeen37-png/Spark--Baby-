"""
Group-friendly quizzes using Telegram's native QUIZ POLLS.
Everybody in the chat can answer (not only the person who started it), answers are scored,
points go to a per-chat leaderboard, and day-streaks are tracked.
"""
import asyncio
import logging
import time

from storage import repositories as repo

log = logging.getLogger("spark_baby.quiz_runner")

POLL_SECONDS = 25         # time each question stays open
POINTS_CORRECT = 10
SPEED_BONUS_MAX = 5       # extra points for fast correct answers
MEDALS = ["🥇", "🥈", "🥉"]

_runs = {}   # chat_id -> Run
_polls = {}  # poll_id -> (Run, question_index)
_tasks = set()


class Run:
    def __init__(self, chat_id, title, questions, starter_id, starter_name):
        self.chat_id, self.title, self.questions = chat_id, title, questions
        self.starter_id, self.starter_name = starter_id, starter_name
        self.stop = asyncio.Event()
        self.scores = {}      # uid -> {"name","points","correct","answered"}
        self.seen = set()     # (poll_id, uid) already counted
        self.sent_at = {}     # poll_id -> timestamp


def active(chat_id):
    return _runs.get(chat_id)


def _today_pair(tz_minutes=330):
    now = time.time() + tz_minutes * 60
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    yday = time.strftime("%Y-%m-%d", time.gmtime(now - 86400))
    return day, yday


def start(bot, chat_id, title, questions, starter_id, starter_name):
    """Starts a quiz in the background. Returns the Run, or None if one is already running here."""
    if chat_id in _runs:
        return None
    run = Run(chat_id, title, questions, starter_id, starter_name)
    _runs[chat_id] = run
    t = asyncio.create_task(_run(bot, run))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return run


def stop(chat_id):
    run = _runs.get(chat_id)
    if run:
        run.stop.set()
    return run


async def _run(bot, run: Run):
    try:
        n = len(run.questions)
        await bot.send_message(
            run.chat_id,
            f"🎯 <b>{_h(run.title)}</b>\n{n} sawal • har sawal {POLL_SECONDS} sec • sab log jawab de sakte hain!\n"
            f"Jitna jaldi sahi jawab, utne zyada points ⚡",
            parse_mode="HTML",
        )
        await asyncio.sleep(2)
        for i, q in enumerate(run.questions):
            if run.stop.is_set():
                break
            msg = await bot.send_poll(
                run.chat_id,
                question=f"Q{i + 1}/{n}. {q['question']}"[:300],
                options=q["options"],
                type="quiz",
                correct_option_id=q["correct_index"],
                explanation=(q.get("explanation") or None),
                is_anonymous=False,
                open_period=POLL_SECONDS,
            )
            pid = msg.poll.id
            _polls[pid] = (run, i)
            run.sent_at[pid] = time.time()
            try:
                await asyncio.wait_for(run.stop.wait(), timeout=POLL_SECONDS + 3)
            except asyncio.TimeoutError:
                pass
        await _finish(bot, run)
    except Exception as e:  # never leave a chat stuck with a dead quiz
        log.error(f"[quiz_runner] run crashed in chat {run.chat_id}: {e}")
        try:
            await bot.send_message(run.chat_id, "😔 Quiz beech me ruk gaya. Phir se /quiz try karo.")
        except Exception:
            pass
    finally:
        _runs.pop(run.chat_id, None)
        for pid in [p for p, (r, _) in _polls.items() if r is run]:
            _polls.pop(pid, None)


async def _finish(bot, run: Run):
    n = len(run.questions)
    ranked = sorted(run.scores.items(), key=lambda kv: (-kv[1]["points"], -kv[1]["correct"]))
    today, yday = _today_pair()
    streaks = {}
    for uid, sc in ranked:
        try:
            streaks[uid] = await repo.add_quiz_result(run.chat_id, uid, sc["name"], sc["points"],
                                                      sc["correct"], sc["answered"], today, yday)
        except Exception as e:
            log.error(f"[quiz_runner] stats save failed: {e}")
    if not ranked:
        await bot.send_message(run.chat_id, "🏁 Quiz khatam! Kisi ne jawab nahi diya 😅  Phir try karo: /quiz")
        return
    lines = [f"🏁 <b>QUIZ KHATAM — {_h(run.title)}</b>", ""]
    for pos, (uid, sc) in enumerate(ranked[:10]):
        medal = MEDALS[pos] if pos < 3 else f"{pos + 1}."
        fire = f" 🔥{streaks[uid]}" if streaks.get(uid, 0) >= 2 else ""
        lines.append(f"{medal} <b>{_h(sc['name'])}</b> — {sc['points']} pts ({sc['correct']}/{n} sahi){fire}")
    lines += ["", "📊 Overall leaderboard: /top   •   Apna score: /mystats"]
    await bot.send_message(run.chat_id, "\n".join(lines), parse_mode="HTML")


def record_answer(poll_id, user_id, user_name, option_ids):
    """Called for every poll_answer update. Returns True if it was counted."""
    hit = _polls.get(poll_id)
    if not hit or not option_ids:
        return False
    run, qi = hit
    if (poll_id, user_id) in run.seen:
        return False
    run.seen.add((poll_id, user_id))
    q = run.questions[qi]
    sc = run.scores.setdefault(user_id, {"name": user_name, "points": 0, "correct": 0, "answered": 0})
    sc["name"] = user_name
    sc["answered"] += 1
    if option_ids[0] == q["correct_index"]:
        elapsed = max(0.0, time.time() - run.sent_at.get(poll_id, time.time()))
        bonus = int(round(SPEED_BONUS_MAX * max(0.0, 1 - elapsed / POLL_SECONDS)))
        sc["points"] += POINTS_CORRECT + bonus
        sc["correct"] += 1
    return True


def _h(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def leaderboard_text(chat_id):
    rows = await repo.quiz_top(chat_id, 10)
    if not rows:
        return "📊 Abhi koi score nahi hai. Pehle ek quiz khelo: /quiz"
    lines = ["🏆 <b>LEADERBOARD</b>", ""]
    for pos, r in enumerate(rows):
        medal = MEDALS[pos] if pos < 3 else f"{pos + 1}."
        fire = f" 🔥{r['streak']}" if r["streak"] >= 2 else ""
        lines.append(f"{medal} <b>{_h(r['name'])}</b> — {r['points']} pts ({r['correct']}/{r['answered']}){fire}")
    return "\n".join(lines)
