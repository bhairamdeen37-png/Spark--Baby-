"""
Tests the 18hr rolling-window quota logic against a throwaway in-memory
SQLite DB — no network, no live keys.
"""
import time
import unittest

import aiosqlite

from storage import database, repositories as repo


class TestLimits(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        database._db = await aiosqlite.connect(":memory:")
        database._db.row_factory = aiosqlite.Row
        await database._db.executescript(database._SCHEMA)
        await database._db.commit()

    async def asyncTearDown(self):
        await database._db.close()
        database._db = None

    async def test_quota_allows_up_to_limit(self):
        for i in range(5):
            allowed, remaining, _ = await repo.check_and_consume_quota(111, "text", limit=5)
            self.assertTrue(allowed)
        allowed, remaining, reset_in = await repo.check_and_consume_quota(111, "text", limit=5)
        self.assertFalse(allowed)
        self.assertEqual(remaining, 0)
        self.assertGreater(reset_in, 0)

    async def test_quota_isolated_per_user(self):
        for i in range(3):
            await repo.check_and_consume_quota(222, "text", limit=3)
        # user 222 is now exhausted
        allowed, _, _ = await repo.check_and_consume_quota(222, "text", limit=3)
        self.assertFalse(allowed)
        # a different user should be unaffected
        allowed2, _, _ = await repo.check_and_consume_quota(333, "text", limit=3)
        self.assertTrue(allowed2)

    async def test_quota_isolated_per_kind(self):
        for i in range(2):
            await repo.check_and_consume_quota(444, "text", limit=2)
        allowed_text, _, _ = await repo.check_and_consume_quota(444, "text", limit=2)
        self.assertFalse(allowed_text)
        # image quota for the same user should be untouched
        allowed_image, _, _ = await repo.check_and_consume_quota(444, "image", limit=2)
        self.assertTrue(allowed_image)

    async def test_window_resets_after_expiry(self):
        db = database.get_db()
        # simulate a window that started 19 hours ago (window is 18h)
        old_start = int(time.time()) - 19 * 3600
        await db.execute(
            "INSERT INTO usage_windows (user_id, kind, window_start, count) VALUES (?, ?, ?, ?)",
            (555, "text", old_start, 999),
        )
        await db.commit()
        allowed, remaining, _ = await repo.check_and_consume_quota(555, "text", limit=5)
        self.assertTrue(allowed)
        self.assertEqual(remaining, 4)  # fresh window, this request used 1 of 5


if __name__ == "__main__":
    unittest.main()
