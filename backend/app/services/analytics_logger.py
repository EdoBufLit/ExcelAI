from __future__ import annotations

import hashlib
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_transformation_type(plan: dict[str, Any]) -> str:
    operations = plan.get("operations")
    if not isinstance(operations, list) or not operations:
        return "other"

    op_types = {
        str(operation.get("type", "")).strip().lower()
        for operation in operations
        if isinstance(operation, dict)
    }
    op_types.discard("")
    if not op_types:
        return "other"

    if any(tag in op_type for op_type in op_types for tag in ("merge", "join")):
        return "merge"

    if any(tag in op_type for op_type in op_types for tag in ("group", "aggregate")):
        return "group"

    clean_ops = {
        "rename_column",
        "drop_columns",
        "fill_null",
        "cast_type",
        "trim_whitespace",
        "change_case",
    }
    if op_types.issubset(clean_ops):
        return "clean"

    if "derive_numeric" in op_types:
        return "group"

    if op_types.intersection({"filter_rows", "sort_rows"}):
        return "clean"

    return "mixed"


class AnalyticsLogger:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analytics_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    event_name TEXT NOT NULL,
                    user_id_hash TEXT NOT NULL,
                    plan_tier TEXT NOT NULL,
                    transformation_type TEXT NOT NULL,
                    operation_count INTEGER NOT NULL,
                    file_size_bytes INTEGER,
                    processing_ms INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error_code TEXT,
                    output_format TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_analytics_events_created_at ON analytics_events(created_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_analytics_events_status ON analytics_events(status)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_analytics_events_type ON analytics_events(transformation_type)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_analytics_events_tier ON analytics_events(plan_tier)"
            )
            connection.commit()

    @staticmethod
    def _hash_user_id(user_id: str) -> str:
        clean = user_id.strip().lower().encode("utf-8")
        return hashlib.sha256(clean).hexdigest()[:16]

    @staticmethod
    def _operation_count(plan: dict[str, Any]) -> int:
        operations = plan.get("operations")
        if not isinstance(operations, list):
            return 0
        return sum(1 for operation in operations if isinstance(operation, dict))

    def log_transform_event(
        self,
        *,
        user_id: str,
        plan: dict[str, Any],
        file_size_bytes: int | None,
        processing_ms: int,
        status: str,
        error_code: str | None,
        plan_tier: str,
        output_format: str | None,
    ) -> None:
        try:
            with self._lock:
                with sqlite3.connect(self.db_path, timeout=2.0) as connection:
                    connection.execute(
                        """
                        INSERT INTO analytics_events (
                            created_at,
                            event_name,
                            user_id_hash,
                            plan_tier,
                            transformation_type,
                            operation_count,
                            file_size_bytes,
                            processing_ms,
                            status,
                            error_code,
                            output_format
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            _utcnow_iso(),
                            "transform_job",
                            self._hash_user_id(user_id),
                            plan_tier,
                            classify_transformation_type(plan),
                            self._operation_count(plan),
                            file_size_bytes,
                            processing_ms,
                            status,
                            error_code,
                            output_format,
                        ),
                    )
                    connection.commit()
        except Exception:
            # Analytics must never block the core product flow.
            return
