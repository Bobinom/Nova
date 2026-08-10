from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class AgentRunRepository:
    """Persist supervisor plan state in Nova's existing SQLite database."""

    ACTIVE_STATUSES = ("planned", "running", "paused")
    VALID_STATUSES = {*ACTIVE_STATUSES, "completed", "cancelled"}

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def create(self, objective: str, project: str) -> dict[str, Any]:
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """INSERT INTO agent_runs(objective, project)
                VALUES (?, ?)""",
                (objective.strip(), project.strip()),
            )
            run_id = int(cursor.lastrowid)
        return self.get(run_id)

    def get(self, run_id: int) -> dict[str, Any]:
        return self._one("SELECT * FROM agent_runs WHERE id = ?", (run_id,))

    def find_project(self, project: str) -> dict[str, Any] | None:
        return self._optional(
            "SELECT * FROM agent_runs WHERE project = ? ORDER BY id DESC LIMIT 1",
            (project,),
        )

    def latest(self, *, active_only: bool = False) -> dict[str, Any] | None:
        where = (
            "WHERE status IN ('planned', 'running', 'paused')"
            if active_only else ""
        )
        return self._optional(
            f"SELECT * FROM agent_runs {where} ORDER BY id DESC LIMIT 1"
        )

    def set_status(
        self,
        run_id: int,
        status: str,
        *,
        current_task_id: int | None = None,
    ) -> dict[str, Any]:
        cleaned = status.strip().lower()
        if cleaned not in self.VALID_STATUSES:
            raise ValueError(f"Unsupported agent status: {status}")
        finished = "CURRENT_TIMESTAMP" if cleaned == "completed" else "NULL"
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                f"""UPDATE agent_runs SET status = ?, current_task_id = ?,
                updated_at = CURRENT_TIMESTAMP, completed_at = {finished}
                WHERE id = ?""",
                (cleaned, current_task_id, int(run_id)),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Agent run {run_id} was not found.")
        return self.get(run_id)

    def _one(
        self,
        query: str,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any]:
        result = self._optional(query, parameters)
        if result is None:
            raise ValueError("Agent run was not found.")
        return result

    def _optional(
        self,
        query: str,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(query, parameters).fetchone()
        return dict(row) if row is not None else None
