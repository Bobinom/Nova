from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import RLock

from nova.conversation.models import ConversationTurn


class ConversationRepository:
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
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._connection.commit()

    def add(self, role: str, text: str) -> ConversationTurn:
        with self._lock:
            connection = self._require_connection()
            cursor = connection.execute(
                """
                INSERT INTO conversation_turns (role, text)
                VALUES (?, ?)
                """,
                (role, text),
            )
            connection.commit()
            row = connection.execute(
                """
                SELECT role, text, created_at
                FROM conversation_turns
                WHERE id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()
            return ConversationTurn(
                role=row["role"],
                text=row["text"],
                created_at=row["created_at"],
            )

    def recent(self, limit: int = 20) -> list[ConversationTurn]:
        with self._lock:
            rows = self._require_connection().execute(
                """
                SELECT role, text, created_at
                FROM conversation_turns
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            rows = list(reversed(rows))
            return [
                ConversationTurn(
                    role=row["role"],
                    text=row["text"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    def clear(self) -> None:
        with self._lock:
            connection = self._require_connection()
            connection.execute("DELETE FROM conversation_turns")
            connection.commit()

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("ConversationRepository has not been initialized.")
        return self._connection
