from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class UsageLimiter:
    def __init__(self, db_path: Path, max_uses: int) -> None:
        self.db_path = db_path
        self.max_uses = max_uses
        self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS usage (
                    user_id TEXT PRIMARY KEY,
                    usage_count INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.commit()

    @staticmethod
    def _clean_user_id(user_id: str) -> str:
        return user_id.strip().lower()

    def get_usage(self, user_id: str) -> int:
        clean = self._clean_user_id(user_id)
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT usage_count FROM usage WHERE user_id = ?",
                (clean,),
            ).fetchone()
        return int(row[0]) if row else 0

    def get_remaining(self, user_id: str) -> int:
        return max(0, self.max_uses - self.get_usage(user_id))

    def can_consume(self, user_id: str) -> bool:
        return self.get_usage(user_id) < self.max_uses

    def consume(self, user_id: str) -> tuple[int, int]:
        clean = self._clean_user_id(user_id)
        with self._lock:
            with sqlite3.connect(self.db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT usage_count FROM usage WHERE user_id = ?",
                    (clean,),
                ).fetchone()
                usage_count = int(row[0]) if row else 0
                if usage_count >= self.max_uses:
                    connection.rollback()
                    return usage_count, 0

                new_usage = usage_count + 1
                if row:
                    connection.execute(
                        "UPDATE usage SET usage_count = ?, updated_at = ? WHERE user_id = ?",
                        (new_usage, _utcnow_iso(), clean),
                    )
                else:
                    connection.execute(
                        "INSERT INTO usage (user_id, usage_count, updated_at) VALUES (?, ?, ?)",
                        (clean, new_usage, _utcnow_iso()),
                    )
                connection.commit()
                return new_usage, max(0, self.max_uses - new_usage)
