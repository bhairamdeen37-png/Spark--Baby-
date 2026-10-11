import unittest

import aiosqlite

from storage import database, repositories as repo


class TestMemory(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        database._db = await aiosqlite.connect(":memory:")
        database._db.row_factory = aiosqlite.Row
        await database._db.executescript(database._SCHEMA)
        await database._db.commit()

    async def asyncTearDown(self):
        await database._db.close()
        database._db = None

    async def test_memory_isolated_per_chat(self):
        await repo.remember("chat_A", "user", "hello from A")
        await repo.remember("chat_B", "user", "hello from B")
        mem_a = await repo.get_memory("chat_A")
        mem_b = await repo.get_memory("chat_B")
        self.assertEqual(len(mem_a), 1)
        self.assertEqual(len(mem_b), 1)
        self.assertIn("A", mem_a[0]["content"])
        self.assertIn("B", mem_b[0]["content"])

    async def test_memory_trims_to_limit(self):
        from config import MAX_MEMORY_MESSAGES
        for i in range(MAX_MEMORY_MESSAGES + 10):
            await repo.remember("chat_C", "user", f"msg {i}")
        mem = await repo.get_memory("chat_C")
        self.assertEqual(len(mem), MAX_MEMORY_MESSAGES)
        # the oldest messages should have been dropped, newest kept
        self.assertIn("msg " + str(MAX_MEMORY_MESSAGES + 9), mem[-1]["content"])

    async def test_clear_memory(self):
        await repo.remember("chat_D", "user", "hi")
        await repo.clear_memory("chat_D")
        self.assertEqual(await repo.get_memory("chat_D"), [])


if __name__ == "__main__":
    unittest.main()
