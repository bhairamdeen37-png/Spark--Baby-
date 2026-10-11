import time
import unittest

import aiosqlite

from storage import database, repositories as repo


class TestCoupons(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        database._db = await aiosqlite.connect(":memory:")
        database._db.row_factory = aiosqlite.Row
        await database._db.executescript(database._SCHEMA)
        await database._db.commit()

    async def asyncTearDown(self):
        await database._db.close()
        database._db = None

    async def test_create_and_redeem_coupon(self):
        code = await repo.create_coupon(premium_days=30, validity_days=7, max_uses=2, created_by=1)
        ok, reason, days = await repo.redeem_coupon(code, user_id=100)
        self.assertTrue(ok)
        self.assertEqual(days, 30)
        self.assertTrue(await repo.is_premium(100))

    async def test_coupon_cannot_be_redeemed_twice_by_same_user(self):
        code = await repo.create_coupon(premium_days=10, validity_days=7, max_uses=5, created_by=1)
        await repo.redeem_coupon(code, user_id=200)
        ok, reason, _ = await repo.redeem_coupon(code, user_id=200)
        self.assertFalse(ok)
        self.assertEqual(reason, "already_used")

    async def test_coupon_respects_max_uses(self):
        code = await repo.create_coupon(premium_days=10, validity_days=7, max_uses=1, created_by=1)
        ok1, _, _ = await repo.redeem_coupon(code, user_id=300)
        ok2, reason2, _ = await repo.redeem_coupon(code, user_id=301)
        self.assertTrue(ok1)
        self.assertFalse(ok2)
        self.assertEqual(reason2, "exhausted")

    async def test_expired_coupon_rejected(self):
        db = database.get_db()
        await db.execute(
            """INSERT INTO coupons (code, premium_days, expires_at, max_uses, used_count, created_by, created_at)
               VALUES ('OLDCODE123', 30, ?, 5, 0, 1, ?)""",
            (int(time.time()) - 10, int(time.time()) - 100),
        )
        await db.commit()
        ok, reason, _ = await repo.redeem_coupon("OLDCODE123", user_id=400)
        self.assertFalse(ok)
        self.assertEqual(reason, "expired")

    async def test_unknown_coupon_rejected(self):
        ok, reason, _ = await repo.redeem_coupon("DOESNOTEXIST", user_id=500)
        self.assertFalse(ok)
        self.assertEqual(reason, "not_found")

    async def test_grant_premium_stacks_on_existing(self):
        await repo.grant_premium_days(600, 10)
        first_until = await repo.premium_expiry(600)
        await repo.grant_premium_days(600, 5)
        second_until = await repo.premium_expiry(600)
        self.assertGreater(second_until, first_until)
        self.assertAlmostEqual(second_until - first_until, 5 * 86400, delta=5)


if __name__ == "__main__":
    unittest.main()
