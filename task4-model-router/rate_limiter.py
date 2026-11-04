# sliding window token limiter stored in sqlite

import sqlite3
import time

WINDOW_SECONDS = 60


class RateLimiter:
    def __init__(self, db_path="ratelimit.db", limit=50_000):
        self.db_path = db_path
        self.limit = limit
        with self.connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS usage (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_key TEXT,
                    ts      REAL,
                    tokens  INTEGER
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_key_ts ON usage (api_key, ts)")

    def connect(self):
        return sqlite3.connect(self.db_path, timeout=10, isolation_level=None)

    def try_reserve(self, api_key, tokens):
        now = time.time()
        window_start = now - WINDOW_SECONDS
        db = self.connect()
        try:
            # lock before reading so two requests can't both get in
            db.execute("BEGIN IMMEDIATE")

            # remove old rows
            db.execute("DELETE FROM usage WHERE api_key = ? AND ts <= ?", (api_key, window_start))

            used = db.execute(
                "SELECT COALESCE(SUM(tokens), 0) FROM usage WHERE api_key = ?", (api_key,)
            ).fetchone()[0]

            if used + tokens > self.limit:
                db.execute("COMMIT")
                return None

            cursor = db.execute(
                "INSERT INTO usage (api_key, ts, tokens) VALUES (?, ?, ?)", (api_key, now, tokens)
            )
            db.execute("COMMIT")
            return cursor.lastrowid
        except Exception:
            db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def set_actual_tokens(self, row_id, tokens):
        with self.connect() as db:
            db.execute("UPDATE usage SET tokens = ? WHERE id = ?", (tokens, row_id))

    def cancel(self, row_id):
        with self.connect() as db:
            db.execute("DELETE FROM usage WHERE id = ?", (row_id,))

    def used(self, api_key):
        with self.connect() as db:
            return db.execute(
                "SELECT COALESCE(SUM(tokens), 0) FROM usage WHERE api_key = ? AND ts > ?",
                (api_key, time.time() - WINDOW_SECONDS),
            ).fetchone()[0]
