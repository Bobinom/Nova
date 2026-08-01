from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DatabaseManager:
    CURRENT_SCHEMA_VERSION = 3
    EXPECTED_TABLES = {
        "app_state", "conversation_episodes", "conversation_sessions",
        "conversation_turns", "memories", "memory_archive", "nova_schema",
    }
    MIGRATIONS = {
        1: (
        """CREATE TABLE IF NOT EXISTS nova_schema (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            version INTEGER NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS app_state (
            key TEXT PRIMARY KEY, value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS memories (
            memory_key TEXT PRIMARY KEY, category TEXT NOT NULL,
            value_json TEXT NOT NULL, confidence REAL NOT NULL,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS conversation_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS conversation_episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL,
            summary TEXT NOT NULL, user_text TEXT NOT NULL,
            assistant_text TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
        ),
        2: ("""CREATE TABLE IF NOT EXISTS conversation_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL, summary TEXT NOT NULL,
            episode_count INTEGER NOT NULL DEFAULT 1,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ended_at TEXT
        )""",),
        3: ("""CREATE TABLE IF NOT EXISTS memory_archive (
            memory_key TEXT PRIMARY KEY, category TEXT NOT NULL,
            value_json TEXT NOT NULL, confidence REAL NOT NULL,
            source TEXT NOT NULL, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            archived_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            archive_reason TEXT NOT NULL
        )""",),
    }

    def __init__(self, database_path: Path, data_dir: Path) -> None:
        self.database_path = database_path
        self.data_dir = data_dir
        self.last_recovery: Path | None = None

    def prepare(self) -> dict[str, Any]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        if self.database_path.exists() and self.database_path.stat().st_size:
            integrity, error = self._integrity_check()
            if integrity == "error" and not self._looks_corrupt(error):
                raise RuntimeError(
                    f"Could not verify Nova's database safely: {error}"
                )
            if integrity != "ok":
                self.last_recovery = self._quarantine_database()
        self._apply_migrations()
        return self.health()

    def health(self) -> dict[str, Any]:
        integrity, error = self._integrity_check()
        tables: set[str] = set()
        schema_version = 0
        if integrity == "ok":
            connection = sqlite3.connect(self.database_path)
            try:
                tables = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )}
                if "nova_schema" in tables:
                    row = connection.execute(
                        "SELECT version FROM nova_schema WHERE singleton = 1"
                    ).fetchone()
                    schema_version = int(row[0]) if row else 0
            finally:
                connection.close()
        missing = sorted(self.EXPECTED_TABLES - tables)
        healthy = (
            integrity == "ok"
            and not missing
            and schema_version == self.CURRENT_SCHEMA_VERSION
        )
        return {
            "status": "healthy" if healthy else "degraded",
            "integrity": integrity,
            "error": error,
            "schema_version": schema_version,
            "expected_schema_version": self.CURRENT_SCHEMA_VERSION,
            "missing_tables": missing,
            "database_bytes": self.database_path.stat().st_size,
            "last_recovery": str(self.last_recovery) if self.last_recovery else None,
        }

    def recoveries(self) -> list[Path]:
        recovery_dir = self.data_dir / "recoveries"
        return (
            sorted(recovery_dir.glob("nova-corrupt-*.db"), reverse=True)
            if recovery_dir.exists() else []
        )

    def _apply_migrations(self) -> None:
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(self.MIGRATIONS[1][0])
            row = connection.execute(
                "SELECT version FROM nova_schema WHERE singleton = 1"
            ).fetchone()
            version = int(row[0]) if row else 0
            if version > self.CURRENT_SCHEMA_VERSION:
                raise RuntimeError(
                    "Database schema is newer than this Nova version: "
                    f"{version} > {self.CURRENT_SCHEMA_VERSION}"
                )
            for target in range(version + 1, self.CURRENT_SCHEMA_VERSION + 1):
                for statement in self.MIGRATIONS[target]:
                    connection.execute(statement)
                connection.execute(
                    """INSERT INTO nova_schema(singleton, version, updated_at)
                    VALUES (1, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(singleton) DO UPDATE SET
                    version = excluded.version, updated_at = CURRENT_TIMESTAMP""",
                    (target,),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _integrity_check(self) -> tuple[str, str | None]:
        if not self.database_path.exists():
            return "missing", None
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                f"file:{self.database_path}?mode=ro", uri=True
            )
            return str(connection.execute("PRAGMA integrity_check").fetchone()[0]), None
        except sqlite3.Error as exc:
            return "error", str(exc)
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _looks_corrupt(error: str | None) -> bool:
        normalized = (error or "").lower()
        return any(
            marker in normalized
            for marker in (
                "database disk image is malformed",
                "file is encrypted",
                "file is not a database",
                "malformed",
                "not a database",
            )
        )

    def _quarantine_database(self) -> Path:
        recovery_dir = self.data_dir / "recoveries"
        recovery_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        recovery = self._available_path(recovery_dir / f"nova-corrupt-{stamp}.db")
        os.replace(self.database_path, recovery)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{self.database_path}{suffix}")
            if sidecar.exists():
                os.replace(sidecar, Path(f"{recovery}{suffix}"))
        return recovery

    @staticmethod
    def _available_path(path: Path) -> Path:
        if not path.exists():
            return path
        counter = 1
        while True:
            candidate = path.with_name(f"{path.stem}-{counter}{path.suffix}")
            if not candidate.exists():
                return candidate
            counter += 1
