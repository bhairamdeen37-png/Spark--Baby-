"""
Storage layer. Turso (libSQL) is the primary backend — a real persistent
cloud database, so data survives Render redeploys/restarts. If
TURSO_DATABASE_URL isn't set, falls back to a local SQLite file via
aiosqlite (handy for local dev without a Turso account, but ephemeral on
Render — see AI_SETUP.md).

Both backends are wrapped to expose the SAME interface (execute/executescript/
commit/close, with async fetchone()/fetchall() on the cursor and sqlite3.Row-
style access via both string and integer keys) so repositories.py never has
to know which one is actually in use.
"""
import re
import time

import aiosqlite

from config import DATABASE_PATH, TURSO_DATABASE_URL, TURSO_AUTH_TOKEN

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id         INTEGER PRIMARY KEY,
    username        TEXT,
    first_name      TEXT,
    premium_until   INTEGER DEFAULT 0,     -- unix ts; 0 or past = not premium
    detailed_mode   INTEGER DEFAULT 0,     -- 1 = step-by-step mode (premium only, enforced in code)
    language        TEXT DEFAULT 'auto',
    created_at      INTEGER
);

CREATE TABLE IF NOT EXISTS usage_windows (
    user_id         INTEGER,
    kind            TEXT,                  -- 'text' or 'image'
    window_start    INTEGER,
    count           INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, kind)
);

CREATE TABLE IF NOT EXISTS memory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_key        TEXT,                  -- str(chat_id), isolates DM vs each group
    role            TEXT,                  -- 'user' or 'assistant'
    content         TEXT,
    ts              INTEGER
);
CREATE INDEX IF NOT EXISTS idx_memory_chat ON memory(chat_key);

CREATE TABLE IF NOT EXISTS group_settings (
    chat_id         INTEGER PRIMARY KEY,
    study_mode      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS coupons (
    code            TEXT PRIMARY KEY,
    premium_days    INTEGER,
    expires_at      INTEGER,               -- unix ts after which coupon can't be redeemed
    max_uses        INTEGER,
    used_count      INTEGER DEFAULT 0,
    created_by      INTEGER,
    created_at      INTEGER
);

CREATE TABLE IF NOT EXISTS coupon_redemptions (
    code            TEXT,
    user_id         INTEGER,
    redeemed_at     INTEGER,
    PRIMARY KEY (code, user_id)
);

CREATE TABLE IF NOT EXISTS payments (
    payment_charge_id  TEXT PRIMARY KEY,
    user_id            INTEGER,
    plan_key           TEXT,
    stars              INTEGER,
    days               INTEGER,
    ts                 INTEGER
);

CREATE TABLE IF NOT EXISTS kv (
    key             TEXT PRIMARY KEY,
    value           TEXT
);

CREATE TABLE IF NOT EXISTS diary (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fact            TEXT UNIQUE,
    ts              INTEGER
);

CREATE TABLE IF NOT EXISTS quiz_stats (
    chat_id         INTEGER,
    user_id         INTEGER,
    name            TEXT,
    points          INTEGER DEFAULT 0,
    correct         INTEGER DEFAULT 0,
    answered        INTEGER DEFAULT 0,
    streak          INTEGER DEFAULT 0,
    best_streak     INTEGER DEFAULT 0,
    last_day        TEXT,
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS quiz_sessions (
    user_id         INTEGER PRIMARY KEY,
    data            TEXT,                  -- JSON blob: topic, questions, current index, score
    updated_at      INTEGER
);
"""


class _Row(dict):
    """dict that also supports integer-index access, like sqlite3.Row —
    so repositories.py can keep doing row["col"] regardless of backend."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return dict.__getitem__(self, key)


class _TursoCursor:
    def __init__(self, result_set):
        columns = list(result_set.columns)
        self._rows = [_Row(zip(columns, row)) for row in result_set.rows]
        self._pos = 0
        self.rowcount = getattr(result_set, "rows_affected", -1)
        self.lastrowid = getattr(result_set, "last_insert_rowid", None)

    async def fetchone(self):
        if self._pos < len(self._rows):
            row = self._rows[self._pos]
            self._pos += 1
            return row
        return None

    async def fetchall(self):
        rows = self._rows[self._pos:]
        self._pos = len(self._rows)
        return rows


class TursoBackend:
    """Thin adapter so Turso (libsql_client) looks like our aiosqlite usage."""

    def __init__(self, client):
        self._client = client

    async def execute(self, sql, params=None):
        rs = await self._client.execute(sql, list(params) if params else [])
        return _TursoCursor(rs)

    async def executescript(self, script: str):
        # libsql_client doesn't batch arbitrary DDL scripts in one call the
        # way aiosqlite does — split on ';' and run each statement. Fine
        # for our schema (no literal semicolons inside string values here).
        # Strip "-- comments" FIRST: a comment containing ';' (e.g. "-- unix ts; 0 or
        # past") used to split a CREATE TABLE in half -> Turso syntax error ->
        # libsql_client crashed with KeyError: 'result'.
        script = re.sub(r"--[^\n]*", "", script)
        for stmt in script.split(";"):
            stmt = stmt.strip()
            if stmt:
                await self._client.execute(stmt)

    async def commit(self):
        # Turso/libSQL auto-commits each statement outside an explicit
        # interactive transaction — nothing to do, kept for interface parity.
        pass

    async def close(self):
        await self._client.close()


_db = None  # aiosqlite.Connection OR TursoBackend — repositories.py treats both the same


def _to_http_url(url: str) -> str:
    """
    libsql:// forces libsql_client onto the WebSocket (Hrana/wss) transport,
    which fails with a 400 handshake error behind some hosts' proxies
    (this happens on Render). The plain HTTPS Hrana-over-HTTP transport
    works the same for everything this bot does, so we force it here
    regardless of which scheme was put in the env var.
    """
    if url.startswith("libsql://"):
        return "https://" + url[len("libsql://"):]
    return url


async def init_db():
    global _db
    if TURSO_DATABASE_URL:
        import libsql_client
        client = libsql_client.create_client(
            url=_to_http_url(TURSO_DATABASE_URL),
            auth_token=TURSO_AUTH_TOKEN or None,
        )
        backend = TursoBackend(client)
        await backend.executescript(_SCHEMA)
        _db = backend
    else:
        conn = await aiosqlite.connect(DATABASE_PATH)
        conn.row_factory = aiosqlite.Row
        await conn.executescript(_SCHEMA)
        await conn.commit()
        _db = conn
    return _db


def get_db():
    if _db is None:
        raise RuntimeError("Database not initialized — call init_db() at startup first.")
    return _db


async def close_db():
    global _db
    if _db is not None:
        await _db.close()
        _db = None


def now_ts() -> int:
    return int(time.time())
