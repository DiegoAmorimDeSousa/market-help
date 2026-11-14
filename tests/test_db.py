import sqlite3
import tempfile
import unittest
from pathlib import Path

from market_help.db import Database

OLD_SCHEMA = """
CREATE TABLE watches (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT NOT NULL, max_price REAL,
    exclude TEXT NOT NULL DEFAULT '[]', stores TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE products (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL UNIQUE, title TEXT,
    target_price REAL, last_price REAL, notified_price REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
INSERT INTO watches (query, max_price) VALUES ('air fryer', 300);
INSERT INTO products (url, target_price) VALUES ('https://www.amazon.com.br/dp/B09B8VGCR8', 500);
"""


class TestMultiUser(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "t.db"

    def test_migrates_old_single_user_db(self):
        conn = sqlite3.connect(self.path)
        conn.executescript(OLD_SCHEMA)
        conn.close()

        db = Database(self.path)
        db.assign_orphans("dono")
        [w] = db.list_watches("dono")
        self.assertEqual((w.query, w.max_price, w.chat_id), ("air fryer", 300, "dono"))
        [p] = db.list_products("dono")
        self.assertEqual(p.target_price, 500)
        # depois da migração, duas pessoas podem acompanhar o mesmo link
        db.add_product("esposa", p.url, 450)
        self.assertEqual(len(db.list_products()), 2)

    def test_lists_are_separate(self):
        db = Database(self.path)
        w1 = db.add_watch("dono", "air fryer", 300, [], [])
        db.add_watch("esposa", "livro", 100, [], [])
        self.assertEqual([w.query for w in db.list_watches("esposa")], ["livro"])
        self.assertFalse(db.remove_watch(w1.id, "esposa"))  # não remove alerta do outro
        self.assertTrue(db.remove_watch(w1.id, "dono"))

    def test_access_flow(self):
        db = Database(self.path)
        self.assertIsNone(db.approve_user("123"))  # nunca pediu
        db.request_access("123", "Maria")
        self.assertFalse(db.is_approved("123"))
        self.assertEqual(db.approve_user("123"), "Maria")
        self.assertTrue(db.is_approved("123"))
        db.add_watch("123", "livro", None, [], [])
        self.assertTrue(db.remove_user("123"))
        self.assertFalse(db.is_approved("123"))
        self.assertEqual(db.list_watches("123"), [])


if __name__ == "__main__":
    unittest.main()
