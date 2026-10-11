import unittest

import aiosqlite

from storage import database, repositories as repo


class TestGroupSettings(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        database._db = await aiosqlite.connect(":memory:")
        database._db.row_factory = aiosqlite.Row
        await database._db.executescript(database._SCHEMA)
        await database._db.commit()

    async def asyncTearDown(self):
        await database._db.close()
        database._db = None

    async def test_study_mode_default_off(self):
        self.assertFalse(await repo.get_study_mode(-1001))

    async def test_study_mode_independent_per_group(self):
        await repo.set_study_mode(-1001, True)
        self.assertTrue(await repo.get_study_mode(-1001))
        self.assertFalse(await repo.get_study_mode(-1002))

    async def test_study_mode_can_be_toggled_off(self):
        await repo.set_study_mode(-1003, True)
        await repo.set_study_mode(-1003, False)
        self.assertFalse(await repo.get_study_mode(-1003))


if __name__ == "__main__":
    unittest.main()
