from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DataManager:
    REQUIRED_TABLES = {
        "app_state",
        "conversation_episodes",
        "conversation_turns",
        "memories",
    }

    def __init__(self, database_path: Path, data_dir: Path) -> None:
        self.database_path = database_path
        self.data_dir = data_dir

    def export_json(
        self,
        payload: dict[str, Any],
        destination: Path | None = None,
    ) -> Path:
        generated = destination is None
        destination = destination or (
            self.data_dir / "exports" / f"nova-memory-{self._timestamp()}.json"
        )
        destination = destination.expanduser().resolve()
        destination = self._available_path(destination) if generated else destination
        if destination.exists():
            raise FileExistsError(f"Export already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, destination)
        return destination

    def backup(self, destination: Path | None = None) -> Path:
        generated = destination is None
        destination = destination or (
            self.data_dir / "backups" / f"nova-{self._timestamp()}.db"
        )
        destination = destination.expanduser().resolve()
        destination = self._available_path(destination) if generated else destination
        if destination == self.database_path.expanduser().resolve():
            raise ValueError("Backup destination must differ from Nova's database.")
        if destination.exists():
            raise FileExistsError(f"Backup already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect(self.database_path)
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        self.validate_backup(destination)
        return destination

    def restore(self, backup_path: Path) -> Path:
        backup_path = backup_path.expanduser().resolve()
        self.validate_backup(backup_path)
        recovery = self._available_path(
            self.data_dir
            / "backups"
            / f"pre-restore-{self._timestamp()}.db"
        )
        if self.database_path.exists():
            self.backup(recovery)

        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=self.database_path.parent,
            prefix=".nova-restore.",
            suffix=".db",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        source = sqlite3.connect(backup_path)
        target = sqlite3.connect(temporary_path)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        self.validate_backup(temporary_path)
        os.replace(temporary_path, self.database_path)
        return recovery

    def validate_backup(self, backup_path: Path) -> None:
        backup_path = backup_path.expanduser().resolve()
        if not backup_path.is_file():
            raise ValueError(f"Backup not found: {backup_path}")
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        except sqlite3.Error as exc:
            raise ValueError("Backup is not a readable SQLite database.") from exc
        finally:
            if connection is not None:
                connection.close()
        if integrity != "ok":
            raise ValueError(f"Backup integrity check failed: {integrity}")
        missing = self.REQUIRED_TABLES - tables
        if missing:
            raise ValueError(
                "Backup is missing Nova tables: " + ", ".join(sorted(missing)),
            )

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

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
