import json
import sqlite3
from pathlib import Path

from .models import Product, Watch

SCHEMA = """
CREATE TABLE IF NOT EXISTS watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    max_price REAL,
    exclude TEXT NOT NULL DEFAULT '[]',
    stores TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    chat_id TEXT
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    title TEXT,
    target_price REAL,
    last_price REAL,
    notified_price REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    chat_id TEXT,
    UNIQUE (chat_id, url)
);
CREATE TABLE IF NOT EXISTS sent (
    watch_id INTEGER NOT NULL,
    deal_key TEXT NOT NULL,
    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (watch_id, deal_key)
);
CREATE TABLE IF NOT EXISTS users (
    chat_id TEXT PRIMARY KEY,
    name TEXT,
    approved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


class Database:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()

    def _columns(self, table: str) -> set[str]:
        return {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}

    def _migrate(self) -> None:
        """Atualiza bancos criados pela versão de um usuário só (sem chat_id)."""
        with self.conn:
            if "chat_id" not in self._columns("watches"):
                self.conn.execute("ALTER TABLE watches ADD COLUMN chat_id TEXT")
            if "chat_id" not in self._columns("products"):
                # A restrição UNIQUE(url) precisa virar UNIQUE(chat_id, url): recria a tabela.
                self.conn.executescript("""
                    ALTER TABLE products RENAME TO products_old;
                    CREATE TABLE products (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url TEXT NOT NULL,
                        title TEXT,
                        target_price REAL,
                        last_price REAL,
                        notified_price REAL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        chat_id TEXT,
                        UNIQUE (chat_id, url)
                    );
                    INSERT INTO products (id, url, title, target_price, last_price, notified_price, created_at)
                        SELECT id, url, title, target_price, last_price, notified_price, created_at FROM products_old;
                    DROP TABLE products_old;
                """)

    def assign_orphans(self, chat_id: str) -> None:
        """Alertas sem dono (da versão antiga) passam a ser do dono do bot."""
        with self.conn:
            self.conn.execute("UPDATE watches SET chat_id = ? WHERE chat_id IS NULL", (chat_id,))
            self.conn.execute("UPDATE products SET chat_id = ? WHERE chat_id IS NULL", (chat_id,))

    # --- meta (ex.: chat do dono do bot) ---
    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    # --- usuários liberados pelo dono ---
    def request_access(self, chat_id: str, name: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO users (chat_id, name) VALUES (?, ?) ON CONFLICT(chat_id) DO UPDATE SET name = excluded.name",
                (chat_id, name),
            )

    def approve_user(self, chat_id: str) -> str | None:
        """Libera o usuário. Devolve o nome dele, ou None se ele nunca mandou /start."""
        with self.conn:
            cur = self.conn.execute("UPDATE users SET approved = 1 WHERE chat_id = ?", (chat_id,))
        if cur.rowcount == 0:
            return None
        return self.conn.execute("SELECT name FROM users WHERE chat_id = ?", (chat_id,)).fetchone()["name"]

    def is_approved(self, chat_id: str) -> bool:
        row = self.conn.execute("SELECT approved FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
        return bool(row and row["approved"])

    def list_users(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM users ORDER BY approved DESC, created_at").fetchall()

    def remove_user(self, chat_id: str) -> bool:
        """Remove o acesso e apaga os alertas da pessoa."""
        with self.conn:
            cur = self.conn.execute("DELETE FROM users WHERE chat_id = ?", (chat_id,))
            self.conn.execute(
                "DELETE FROM sent WHERE watch_id IN (SELECT id FROM watches WHERE chat_id = ?)", (chat_id,)
            )
            self.conn.execute("DELETE FROM watches WHERE chat_id = ?", (chat_id,))
            self.conn.execute("DELETE FROM products WHERE chat_id = ?", (chat_id,))
        return cur.rowcount > 0

    # --- lista de monitoramento ---
    def add_watch(
        self, chat_id: str, query: str, max_price: float | None, exclude: list[str], stores: list[str]
    ) -> Watch:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO watches (chat_id, query, max_price, exclude, stores) VALUES (?, ?, ?, ?, ?)",
                (chat_id, query, max_price, json.dumps(exclude), json.dumps(stores)),
            )
        return Watch(cur.lastrowid, query, max_price, exclude, stores, chat_id)

    def list_watches(self, chat_id: str | None = None) -> list[Watch]:
        """Alertas de uma pessoa, ou de todo mundo se chat_id for None."""
        if chat_id is None:
            rows = self.conn.execute("SELECT * FROM watches ORDER BY id").fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM watches WHERE chat_id = ? ORDER BY id", (chat_id,)).fetchall()
        return [
            Watch(r["id"], r["query"], r["max_price"], json.loads(r["exclude"]), json.loads(r["stores"]), r["chat_id"])
            for r in rows
        ]

    def remove_watch(self, watch_id: int, chat_id: str) -> bool:
        with self.conn:
            cur = self.conn.execute("DELETE FROM watches WHERE id = ? AND chat_id = ?", (watch_id, chat_id))
            if cur.rowcount:
                self.conn.execute("DELETE FROM sent WHERE watch_id = ?", (watch_id,))
        return cur.rowcount > 0

    # --- controle de notificações já enviadas ---
    def was_sent(self, watch_id: int, deal_key: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sent WHERE watch_id = ? AND deal_key = ?", (watch_id, deal_key)
        ).fetchone()
        return row is not None

    def mark_sent(self, watch_id: int, deal_key: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO sent (watch_id, deal_key) VALUES (?, ?)", (watch_id, deal_key)
            )

    def cleanup_sent(self, days: int = 30) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM sent WHERE sent_at < datetime('now', ?)", (f"-{days} days",))

    # --- produtos acompanhados por link ---
    def add_product(self, chat_id: str, url: str, target_price: float | None) -> Product:
        with self.conn:
            self.conn.execute(
                "INSERT INTO products (chat_id, url, target_price) VALUES (?, ?, ?) "
                "ON CONFLICT(chat_id, url) DO UPDATE SET target_price = excluded.target_price, notified_price = NULL",
                (chat_id, url, target_price),
            )
        row = self.conn.execute("SELECT * FROM products WHERE chat_id = ? AND url = ?", (chat_id, url)).fetchone()
        return self._product(row)

    def list_products(self, chat_id: str | None = None) -> list[Product]:
        if chat_id is None:
            rows = self.conn.execute("SELECT * FROM products ORDER BY id")
        else:
            rows = self.conn.execute("SELECT * FROM products WHERE chat_id = ? ORDER BY id", (chat_id,))
        return [self._product(r) for r in rows]

    def update_product(self, product: Product) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE products SET title = ?, last_price = ?, notified_price = ? WHERE id = ?",
                (product.title, product.last_price, product.notified_price, product.id),
            )

    def remove_product(self, product_id: int, chat_id: str) -> bool:
        with self.conn:
            cur = self.conn.execute("DELETE FROM products WHERE id = ? AND chat_id = ?", (product_id, chat_id))
        return cur.rowcount > 0

    @staticmethod
    def _product(r: sqlite3.Row) -> Product:
        return Product(
            r["id"], r["url"], r["title"], r["target_price"], r["last_price"], r["notified_price"], r["chat_id"]
        )
