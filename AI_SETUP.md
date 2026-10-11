# AI_SETUP.md — Spark Baby

## 1. Environment variables

### Required

| Variable | Notes |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From @BotFather. Bot won't start at all without this. |
| `BOT_OWNER_IDS` | Comma-separated Telegram numeric user IDs. These are the only people who can use `/admin`, `/grantpremium`, `/createcoupon`, etc. |

### AI providers (at least one needed; all three recommended)

| Variable | Notes |
|---|---|
| `GEMINI_API_KEY` | Primary provider. Supports text + images. |
| `GROQ_API_KEY` | Secondary. **Text only** — never receives image requests. |
| `OPENROUTER_API_KEY` | Third. Default model (`openrouter/free`) supports text + images. |

If a key is missing, that provider is skipped immediately (not retried) and
the next one in the chain is tried. If **all three** are missing, the bot
still starts (so you can at least test `/start`, `/premium`, owner commands)
but every question will get "AI service unavailable right now."

### Optional model overrides

| Variable | Default | Where to verify current IDs |
|---|---|---|
| `GEMINI_MODEL` | `gemini-2.0-flash` | ai.google.dev/gemini-api/docs/models |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | console.groq.com/docs/models |
| `OPENROUTER_MODEL` | `openrouter/free` | openrouter.ai/models |

`openrouter/free` is OpenRouter's **own router** across whichever free
models are currently available — it was chosen as the default specifically
because individual free models get rotated out by providers without much
warning (this exact thing already happened once with Groq's
`llama-3.3-70b-versatile`, which Groq permanently retired on 16 Aug 2026 —
that's why the Groq default above is NOT that model).

### Database (Turso — primary)

| Variable | Notes |
|---|---|
| `TURSO_DATABASE_URL` | e.g. `libsql://spark-baby-yourorg.turso.io`. Get it with `turso db show <name> --url` |
| `TURSO_AUTH_TOKEN` | Get it with `turso db tokens create <name>` |

If both are set, **every** read/write (users, premium, memory, coupons,
quiz sessions, payments) goes to Turso — a real persistent cloud database,
so a Render redeploy/restart doesn't wipe anything.

If `TURSO_DATABASE_URL` is **not set**, the bot falls back to a local
SQLite file (`DATABASE_PATH`, default `spark_baby.db`) — convenient for
local development without a Turso account, but on Render's free/standard
disk this file is **wiped on every redeploy/restart**. Use this fallback
only for local testing, not production.

### Optional tuning

| Variable | Default |
|---|---|
| `DATABASE_PATH` | `spark_baby.db` (only used when Turso isn't configured) |
| `MAX_MEMORY_MESSAGES` | `15` (clamped to 10–20) |
| `FREE_TEXT_DAILY_LIMIT` | `50` |
| `FREE_IMAGE_DAILY_LIMIT` | `10` |
| `LIMIT_WINDOW_HOURS` | `18` |
| `LOG_LEVEL` | `INFO` |
| `MAX_ANSWER_CHARS` | `3500` |
| `MAX_IMAGE_BYTES` | `8388608` (8 MB) |

## 2. Free vs Premium — exact rules implemented

| | Free | Premium |
|---|---|---|
| Text questions | 50/day | Unlimited |
| Image questions | 10/day | Unlimited |
| Reset | **Per-user rolling 18h window** — counted from that user's own first request in the current window, not a fixed clock time | n/a |
| Detailed/step-by-step mode (`/mode`) | ❌ locked | ✅ |
| Scope | DM and groups both count against the same two counters | DM and groups both fully unlimited |

Premium is checked **before** the quota is touched at all — a premium user
never consumes or trips any counter.

## 3. Premium plans (Telegram Stars)

| Plan key | Duration | Price |
|---|---|---|
| `30d` | 30 days | 50 ⭐ |
| `60d` | 60 days | 150 ⭐ |
| `180d` | 6 months | 300 ⭐ |
| `365d` | 1 year | 700 ⭐ |

Edit `PREMIUM_PLANS` in `config.py` to change pricing/duration — nothing
else needs to change, `/premium`'s buttons and the invoice flow read from
that dict directly.

Payment uses Telegram's **native Stars invoice** (`currency="XTR"`,
`provider_token=""`) — no Razorpay/UPI/external gateway. Flow:
1. `/premium` → inline buttons per plan.
2. Tap a plan → bot calls `send_invoice` → Telegram shows its own native
   payment sheet (Stars balance / buy more Stars).
3. Telegram sends a `pre_checkout_query` → bot auto-approves (`ok=True`,
   no inventory to check).
4. On success, Telegram sends a `successful_payment` message → bot grants
   premium (**stacks** on top of any remaining premium time) and logs the
   payment (`payments` table) for your own records.

## 4. Coupons + owner-granted premium

- `/createcoupon <premium_days> <validity_days> <max_uses>` — e.g.
  `/createcoupon 30 7 50` makes a code that:
  - grants **30 days** of premium to whoever redeems it,
  - the **code itself** stops working after **7 days**,
  - can be redeemed by up to **50 different users** (one redemption per
    user — the same person can't reuse it to stack days).
- `/listcoupons`, `/deletecoupon <code>` — manage active coupons.
- `/grantpremium <user_id> <days>` / `/revokepremium <user_id>` — owner can
  hand premium to (or take it from) **any** Telegram user ID directly,
  without that user doing anything. Also stacks on existing premium time.
- Everything above is owner-only (`BOT_OWNER_IDS`); anyone else gets a
  plain "owner-only command" reply.

## 5. Image-solving behavior

- Only providers with actual vision support receive image bytes:
  Gemini and OpenRouter. Groq's configured model is text-only and is
  **skipped entirely** for image requests — never silently sent the image
  as a text-only guess (this was an explicit requirement).
- If neither vision-capable provider is configured/working, the user gets
  a clear "AI service unavailable" message — not a fabricated answer.
- Images over `MAX_IMAGE_BYTES` (default 8 MB) are rejected with a message
  asking for a smaller/compressed photo, before any API call is made.

## 6. Storage & persistence — Turso setup

**Turso (libSQL)** is the database — a real persistent cloud DB, so none of
this resets on a Render redeploy/restart.

1. Install the Turso CLI and sign up (free tier is generous for a bot this
   size): https://docs.turso.tech/quickstart
2. ```bash
   turso db create spark-baby
   turso db show spark-baby --url        # -> TURSO_DATABASE_URL
   turso db tokens create spark-baby     # -> TURSO_AUTH_TOKEN
   ```
3. Put both values into Render's Environment tab (or `.env` locally).
4. That's it — `main.py` calls `init_db()` on startup, which creates all
   tables on Turso automatically if they don't exist yet (`CREATE TABLE IF
   NOT EXISTS`, safe to run every boot).

If you genuinely don't want to use Turso, leaving `TURSO_DATABASE_URL`
empty makes the bot fall back to a local SQLite file (`DATABASE_PATH`) —
but on Render's default disk that file is wiped on every redeploy/restart,
so only use that fallback for local development, never production.

The database layer (`storage/database.py`) wraps both backends behind the
identical interface `repositories.py` uses, so nothing else in the project
needed to change to support Turso.

## 7. Testing performed

No live Telegram bot token, no live Gemini/Groq/OpenRouter API keys, and
**no network access** were available in the environment this was built in
(pip install itself failed — DNS resolution blocked). So:

**Actually run:**
- ✅ `python3 -m py_compile` on every single `.py` file in the project —
  all pass, zero syntax errors.
- ✅ Manual trace-through of every handler against the acceptance checklist
  (sequential fallback order, group on/off isolation, memory isolation,
  quota isolation per user/per kind, coupon max-uses/expiry/one-per-user
  logic, premium stacking math).

**Written but NOT executed (needs `pip install -r requirements.txt`, which
needs network access this environment didn't have):**
- `tests/test_ai_router.py` — asserts Gemini-success skips Groq/OpenRouter,
  a non-retryable Gemini failure falls through to Groq, all-providers-fail
  raises `AllProvidersFailedError`, and an image request never reaches the
  text-only Groq provider. Fully mocked — no live keys needed even when run.
- `tests/test_limits.py` — 18h rolling window: allows exactly up to the
  limit then blocks, isolated per user, isolated per kind (text vs image),
  and a window older than 18h resets correctly. Uses an in-memory SQLite DB.
- `tests/test_coupons.py` — create/redeem, double-redemption blocked,
  max-uses enforced, expired coupon rejected, unknown code rejected,
  premium-days stacking math. In-memory SQLite.
- `tests/test_memory.py` — per-chat isolation, trimming to
  `MAX_MEMORY_MESSAGES`, `/clear` behavior. In-memory SQLite.
- `tests/test_group_settings.py` — study mode defaults off, is independent
  per group, can be toggled back off. In-memory SQLite.
- `tests/test_commands.py` — config sanity (plan shape, positive limits)
  and the quiz JSON-fence-stripping helper.

**Not testable at all without a live deployment (explicitly not claimed):**
- An actual Telegram bot token receiving real updates.
- A real Gemini/Groq/OpenRouter API call succeeding end-to-end.
- A real Telegram Stars payment completing (`pre_checkout_query` →
  `successful_payment`) — the code follows Telegram's documented Stars
  flow, but this was not exercised against Telegram's servers.
- Render's actual disk persistence behavior on your specific plan.

**Before going live:** run `pip install -r requirements.txt && python -m
unittest discover tests` locally to confirm the written tests pass in a
real environment, then do one real end-to-end pass — `/start`, ask a text
question, send an image, run `/quiz`, buy the cheapest premium plan with
real Stars, and check `/admin` stats — before treating it as production-ready.
