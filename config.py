"""
Central configuration for Spark Baby.
Everything secret comes from environment variables — nothing is hardcoded.
"""
import os
import sys

def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()

def _get_int(name: str, default: int) -> int:
    val = os.environ.get(name, "")
    try:
        return int(val) if val.strip() else default
    except ValueError:
        return default

def _get_ids(name: str) -> set:
    raw = _get(name, "")
    out = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out

# ── Telegram ──
BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN")
BOT_OWNER_IDS = _get_ids("BOT_OWNER_IDS")

# ── AI providers ──
GEMINI_API_KEY = _get("GEMINI_API_KEY")
GROQ_API_KEY = _get("GROQ_API_KEY")
OPENROUTER_API_KEY = _get("OPENROUTER_API_KEY")

# Verify current model IDs at the provider's own docs before relying on these —
# providers deprecate/rotate model IDs without much warning:
#   Gemini      -> https://ai.google.dev/gemini-api/docs/models
#   Groq        -> https://console.groq.com/docs/models
#   OpenRouter  -> https://openrouter.ai/models
GEMINI_MODEL = _get("GEMINI_MODEL", "")
# Gemini 2.0 Flash was shut down by Google (Jun 2026). We try your GEMINI_MODEL first (if set),
# then these in order; a retired ID (404) is skipped automatically.
GEMINI_MODELS = [m for m in [GEMINI_MODEL, "gemini-flash-latest", "gemini-3.5-flash", "gemini-2.5-flash"] if m]
GROQ_MODEL = _get("GROQ_MODEL", "openai/gpt-oss-120b")
# openrouter/free is OpenRouter's own router across all free models (text + vision),
# chosen as the default specifically so this doesn't break when one underlying
# free model gets rotated out.
OPENROUTER_MODEL = _get("OPENROUTER_MODEL", "openrouter/free")

# ── Quiz question bank (JEE / NEET / competitive exams) ──
# Base URL of a folder that holds <exam>.json files (jee.json, neet.json, ssc.json ...), e.g. a GitHub
# raw folder:  https://raw.githubusercontent.com/<user>/<repo>/main/questions
# Format of each file: see data/qbank/README.md. Empty = only the local data/qbank/*.json files are used.
QBANK_BASE_URL = _get("QBANK_BASE_URL", "").rstrip("/")
QBANK_CACHE_HOURS = _get_int("QBANK_CACHE_HOURS", 6)
# AI-made questions get a second, independent "solve it again" check; wrong answer keys are dropped.
# Set QUIZ_VERIFY=0 to turn this off (saves one AI call per quiz).
QUIZ_VERIFY = _get("QUIZ_VERIFY", "1") != "0"
# Hugging Face datasets (via the Dataset Viewer API) as an extra online source for JEE / NEET.
HF_ENABLED = _get("HF_ENABLED", "1") != "0"
HF_TOKEN = _get("HF_TOKEN", "")            # optional; a free read token gives higher rate limits
HF_PAGES = max(1, min(10, _get_int("HF_PAGES", 3)))   # pages of 100 rows sampled per dataset per refresh
# Per-exam dataset override, e.g. HF_DATASETS_NEET=user/dataset1,user/dataset2 (empty value = disable HF for that exam)
HF_DATASETS_OVERRIDE = {e: [x.strip() for x in os.environ[f"HF_DATASETS_{e.upper()}"].split(",") if x.strip()]
                        for e in ("jee", "neet", "ssc", "upsc", "brd", "sch") if f"HF_DATASETS_{e.upper()}" in os.environ}

# ── Storage ──
# Turso (libSQL) is the primary database — a real persistent cloud DB, so
# data survives Render redeploys/restarts (unlike a local SQLite file on
# Render's ephemeral disk). Get these from `turso db show <name> --url`
# and `turso db tokens create <name>`.
#   TURSO_DATABASE_URL looks like: libsql://<db-name>-<org>.turso.io
TURSO_DATABASE_URL = _get("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = _get("TURSO_AUTH_TOKEN")

# Local fallback ONLY used when TURSO_DATABASE_URL is not set — convenient
# for local development without a Turso account. Don't rely on this in
# production; it's a plain local file, ephemeral on Render.
DATABASE_PATH = _get("DATABASE_PATH", "spark_baby.db")

# ── Memory ──
MAX_MEMORY_MESSAGES = max(10, min(20, _get_int("MAX_MEMORY_MESSAGES", 20)))

# ── Free-tier limits (apply equally in DM and groups) ──
FREE_TEXT_DAILY_LIMIT = _get_int("FREE_TEXT_DAILY_LIMIT", 50)
FREE_IMAGE_DAILY_LIMIT = _get_int("FREE_IMAGE_DAILY_LIMIT", 10)
# Group: messages a member sends TO the bot (mention / reply / command). Auto-solve is free.
FREE_GROUP_MEMBER_LIMIT = _get_int("FREE_GROUP_MEMBER_LIMIT", 20)
# Which AI to try first. For faster text replies set on Render:  AI_PROVIDER_ORDER=groq,gemini,openrouter
AI_PROVIDER_ORDER = [x.strip() for x in _get("AI_PROVIDER_ORDER", "gemini,groq,openrouter").split(",") if x.strip()]
# Scheduled jobs (hour in local time, TZ_OFFSET_MINUTES; default India +5:30)
TZ_OFFSET_MINUTES = _get_int("TZ_OFFSET_MINUTES", 330)
GM_HOUR = _get_int("GM_HOUR", 8)      # good-morning message to the owner
GN_HOUR = _get_int("GN_HOUR", 23)     # good-night message to the owner
DQ_HOUR = _get_int("DQ_HOUR", 9)      # daily quiz in groups that enabled it
LIMIT_WINDOW_HOURS = _get_int("LIMIT_WINDOW_HOURS", 18)
LIMIT_WINDOW_SECONDS = LIMIT_WINDOW_HOURS * 3600

# ── Premium plans: key -> (days, stars) ──
# Prices are in Telegram Stars (XTR) — paid via Telegram's native invoice, no
# external payment gateway.
PREMIUM_PLANS = {
    "30d":  {"label": "30 Days",  "days": 30,  "stars": 50},
    "60d":  {"label": "60 Days",  "days": 60,  "stars": 150},
    "180d": {"label": "6 Months", "days": 180, "stars": 300},
    "365d": {"label": "1 Year",   "days": 365, "stars": 700},
}

# ── Misc ──
LOG_LEVEL = _get("LOG_LEVEL", "INFO")
MAX_ANSWER_CHARS = _get_int("MAX_ANSWER_CHARS", 3500)       # Telegram msg cap is 4096
MAX_IMAGE_BYTES = _get_int("MAX_IMAGE_BYTES", 8 * 1024 * 1024)  # 8 MB

def validate_startup():
    """Fail fast with a clear message instead of crashing deep inside aiogram."""
    problems = []
    if not BOT_TOKEN:
        problems.append("TELEGRAM_BOT_TOKEN is not set.")
    if not BOT_OWNER_IDS:
        problems.append("BOT_OWNER_IDS is not set — no one will be able to use owner/admin commands.")
    if not GEMINI_API_KEY and not GROQ_API_KEY and not OPENROUTER_API_KEY:
        problems.append("None of GEMINI_API_KEY / GROQ_API_KEY / OPENROUTER_API_KEY are set — "
                         "the bot will start but every AI reply will fail.")
    if not TURSO_DATABASE_URL:
        problems.append("TURSO_DATABASE_URL is not set — falling back to a local SQLite file "
                         "(DATABASE_PATH). On Render this is WIPED on every redeploy/restart. "
                         "Set TURSO_DATABASE_URL + TURSO_AUTH_TOKEN for real persistence.")
    if problems:
        print("⚠️  Spark Baby config warnings:", file=sys.stderr)
        for p in problems:
            print(f"   - {p}", file=sys.stderr)
    if not BOT_TOKEN:
        # This one really can't continue.
        print("❌ TELEGRAM_BOT_TOKEN missing — cannot start. Set it and restart.", file=sys.stderr)
        sys.exit(1)
