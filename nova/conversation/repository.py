from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import RLock

from nova.conversation.models import ConversationEpisode, ConversationTurn


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
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    user_text TEXT NOT NULL,
                    assistant_text TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversation_episodes_created
                ON conversation_episodes(created_at)
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

    def add_episode(
        self,
        *,
        topic: str,
        summary: str,
        user_text: str,
        assistant_text: str,
    ) -> ConversationEpisode:
        with self._lock:
            connection = self._require_connection()
            cursor = connection.execute(
                """
                INSERT INTO conversation_episodes (
                    topic, summary, user_text, assistant_text
                )
                VALUES (?, ?, ?, ?)
                """,
                (topic, summary, user_text, assistant_text),
            )
            connection.commit()
            row = connection.execute(
                """
                SELECT id, topic, summary, user_text, assistant_text, created_at
                FROM conversation_episodes
                WHERE id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()
            return self._row_to_episode(row)

    def list_episodes(self, limit: int = 20) -> list[ConversationEpisode]:
        with self._lock:
            rows = self._require_connection().execute(
                """
                SELECT id, topic, summary, user_text, assistant_text, created_at
                FROM conversation_episodes
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [self._row_to_episode(row) for row in rows]

    def delete_episode(self, episode_id: int) -> bool:
        with self._lock:
            connection = self._require_connection()
            cursor = connection.execute(
                "DELETE FROM conversation_episodes WHERE id = ?",
                (episode_id,),
            )
            connection.commit()
            return cursor.rowcount > 0

    def clear_episodes(self) -> None:
        with self._lock:
            connection = self._require_connection()
            connection.execute("DELETE FROM conversation_episodes")
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

    @staticmethod
    def _row_to_episode(row: sqlite3.Row) -> ConversationEpisode:
        return ConversationEpisode(
            id=int(row["id"]),
            topic=row["topic"],
            summary=row["summary"],
            user_text=row["user_text"],
            assistant_text=row["assistant_text"],
            created_at=row["created_at"],
        )
