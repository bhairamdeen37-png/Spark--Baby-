# Spark Baby — StudyZone AI Study Tutor

A standalone Telegram bot (built with **Aiogram 3.x**) that helps students with
any academic subject — text questions, image-based questions, notes,
quizzes — in both private DMs and Telegram groups. Uses **Gemini → Groq →
OpenRouter** with sequential fallback, SQLite storage, and a Telegram
**Stars**-based premium system with owner-managed coupons.

This is a **brand-new, standalone project**. It does not depend on, import,
or reuse any previous userbot/clone-factory project. No clones are created —
this is a single bot, one deployment, one owner panel.

---

## 1. Project structure

```
spark-baby/
├── main.py                  # entrypoint: bot + health server + router registration
├── config.py                 # all settings, read from environment variables
├── requirements.txt
├── .env.example
├── .gitignore
├── render.yaml
├── README.md
├── AI_SETUP.md
│
├── handlers/                 # one file per command group
│   ├── start.py               /start
│   ├── help.py                /help
│   ├── messages.py            core text/photo question flow (DM + groups)
│   ├── study.py                /study on/off (group mode)
│   ├── quiz.py                 /quiz + answer buttons
│   ├── notes.py                 /notes
│   ├── settings.py             /mode /language /clear /status
│   ├── payment.py               /premium, Stars checkout, /redeem
│   └── admin.py                owner panel, coupons, grants
│
├── services/                 # business logic, no Telegram-specific code
│   ├── ai_router.py            Gemini -> Groq -> OpenRouter fallback
│   ├── gemini_provider.py
│   ├── groq_provider.py
│   ├── openrouter_provider.py
│   ├── access_service.py       premium + quota decisions
│   ├── memory_service.py       conversation memory + system prompt builder
│   ├── quiz_service.py
│   ├── notes_service.py
│   └── bot_state.py             caches bot's own username/id for mention checks
│
├── storage/
│   ├── database.py              Turso (primary) + local SQLite fallback, same interface
│   └── repositories.py          all DB reads/writes
│
├── prompts/
│   └── study_tutor.txt          the actual system prompt sent to the AI
│
└── tests/                    # run with: python -m unittest discover tests
    ├── test_ai_router.py        fallback order, image-vs-text routing
    ├── test_limits.py           18hr rolling quota logic
    ├── test_coupons.py          coupon create/redeem/expiry/max-uses
    ├── test_memory.py           per-chat memory isolation + trimming
    ├── test_group_settings.py   per-group study-mode isolation
    └── test_commands.py         config + pure-logic sanity checks
```

## 2. What it does

- **DM**: any text message or photo is automatically answered — no `/ask`
  required (though `/ask`, `/solve`, `/explain` work too).
- **Groups**: silent by default. An owner/admin turns it on with `/study on`.
  Once on, the bot answers when it's **@mentioned**, when a message is a
  **reply to one of its own messages**, or when `/ask` / `/solve` / `/explain`
  is used explicitly — it does not answer every message in the group.
- **Images**: sent straight to a vision-capable provider (Gemini or
  OpenRouter) — never silently downgraded to a text-only guess.
- **Quizzes** (`/quiz <topic> [easy|medium|hard]`): AI generates 5 MCQs as
  strict JSON, bot asks them one at a time with inline buttons, tracks score.
- **Notes** (`/notes <topic> [short|detailed|formula_sheet|flashcards]`).
- **Memory**: last 10–20 messages (configurable), isolated per DM/per group,
  cleared with `/clear`.
- **Free vs Premium** — see AI_SETUP.md for the exact numbers and how to
  change them.
- **Premium purchase**: `/premium` shows plans with inline buttons; tapping
  one sends a native **Telegram Stars** invoice (no external payment
  gateway/Razorpay/UPI integration — Stars only).
- **Owner panel** (`/admin`): grant/revoke premium for any user id directly,
  create/list/delete coupon codes, see bot-wide stats.

## 3. Local setup

```bash
cd spark-baby
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then fill in your real values
```

Load `.env` however you prefer locally (e.g. `export $(cat .env | xargs)` on
Linux/Mac, or add `python-dotenv` yourself if you want it auto-loaded — not
included by default since Render doesn't need it).

Run it:
```bash
python main.py
```

## 4. BotFather setup

1. Talk to **@BotFather** on Telegram → `/newbot` → name it, get your
   `TELEGRAM_BOT_TOKEN`.
2. `/setprivacy` → choose your bot → **Disable** if you want the bot to see
   all group messages (needed for mention/reply detection to work reliably
   in groups). If left **Enabled**, the bot only receives messages that
   explicitly mention it or reply to it anyway — which happens to match this
   bot's group behavior, so either setting works here.
3. `/setcommands` → paste:
   ```
   start - Start the bot
   help - Show all commands
   ask - Ask a question
   solve - Solve a question
   explain - Explain a topic
   notes - Generate study notes
   quiz - Start a practice quiz
   mode - Toggle detailed mode (premium)
   language - Set reply language
   clear - Clear this chat's AI memory
   status - Check your plan and usage
   study - Group study mode on/off
   premium - View premium plans
   redeem - Redeem a coupon code
   ```

## 5. Render deployment

See **AI_SETUP.md** for the full environment-variable list, the AI-provider
fallback details, image-solving notes, storage/persistence caveats, and the
honest testing summary (what was and wasn't actually run).

Quick version:
1. Push this folder to a GitHub repo.
2. Render → New → Web Service → connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `python main.py`
5. Set the environment variables listed in AI_SETUP.md.
6. Deploy.

## 6. Known limitations (stated honestly, not guessed around)

- **Database is Turso (libSQL)** — set `TURSO_DATABASE_URL` +
  `TURSO_AUTH_TOKEN` (see AI_SETUP.md) and everything persists across
  Render redeploys/restarts. If you skip Turso, the bot falls back to a
  local SQLite file, which **is wiped on every redeploy/restart** on
  Render's default disk — that fallback is for local dev only.
- Image solving only works through Gemini or OpenRouter (Groq's configured
  model has no vision support) — if both of those fail/are unconfigured,
  image questions get a clear error, never a text-only guess.
- Free OpenRouter models rotate; the default `openrouter/free` router model
  is used specifically to survive that, but verify at openrouter.ai/models
  if something stops working.
