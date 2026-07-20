from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

from nova.memory.models import MemoryRecord


class MemoryRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._connection: sqlite3.Connection | None = None
        self._lock = RLock()

    def initialize(self) -> None:
        with self._lock:
            self._connection = sqlite3.connect(self.database_path)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    memory_key TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memories_category
                ON memories(category)
                """
            )
            self._connection.commit()

    def upsert(
        self,
        *,
        key: str,
        category: str,
        value: Any,
        confidence: float = 1.0,
        source: str = "user",
    ) -> MemoryRecord:
        with self._lock:
            connection = self._require_connection()
            connection.execute(
                """
                INSERT INTO memories (
                    memory_key, category, value_json, confidence, source
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(memory_key) DO UPDATE SET
                    category = excluded.category,
                    value_json = excluded.value_json,
                    confidence = excluded.confidence,
                    source = excluded.source,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    key,
                    category,
                    json.dumps(value, ensure_ascii=False),
                    confidence,
                    source,
                ),
            )
            connection.commit()
            record = self.get(key)
            if record is None:
                raise RuntimeError(f"Failed to persist memory: {key}")
            return record

    def get(self, key: str) -> MemoryRecord | None:
        with self._lock:
            row = self._require_connection().execute(
                """
                SELECT memory_key, category, value_json, confidence, source,
                       created_at, updated_at
                FROM memories
                WHERE memory_key = ?
                """,
                (key,),
            ).fetchone()
            return self._row_to_record(row) if row else None

    def list_all(self, category: str | None = None) -> list[MemoryRecord]:
        with self._lock:
            connection = self._require_connection()
            if category:
                rows = connection.execute(
                    """
                    SELECT memory_key, category, value_json, confidence, source,
                           created_at, updated_at
                    FROM memories
                    WHERE category = ?
                    ORDER BY memory_key
                    """,
                    (category,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT memory_key, category, value_json, confidence, source,
                           created_at, updated_at
                    FROM memories
                    ORDER BY category, memory_key
                    """
                ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def delete(self, key: str) -> bool:
        with self._lock:
            connection = self._require_connection()
            cursor = connection.execute(
                "DELETE FROM memories WHERE memory_key = ?",
                (key,),
            )
            connection.commit()
            return cursor.rowcount > 0

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("MemoryRepository has not been initialized.")
        return self._connection

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            key=row["memory_key"],
            category=row["category"],
            value=json.loads(row["value_json"]),
            confidence=float(row["confidence"]),
            source=row["source"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
