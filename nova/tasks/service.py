from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any


class TaskService:
    """Persistent, deterministic assistant tasks stored in Nova's database."""

    VALID_STATUSES = {"open", "in_progress", "completed", "cancelled"}

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def create(
        self,
        title: str,
        *,
        details: str = "",
        project: str = "Inbox",
        priority: int = 0,
    ) -> dict[str, Any]:
        clean_title = self._clean_title(title)
        clean_project = project.strip() or "Inbox"
        bounded_priority = max(0, min(int(priority), 3))
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """INSERT INTO assistant_tasks(
                    title, details, project, status, priority
                ) VALUES (?, ?, ?, 'open', ?)""",
                (clean_title, details.strip(), clean_project, bounded_priority),
            )
            task_id = int(cursor.lastrowid)
        return self.get(task_id)

    def get(self, task_id: int) -> dict[str, Any]:
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM assistant_tasks WHERE id = ?",
                (int(task_id),),
            ).fetchone()
        if row is None:
            raise ValueError(f"Task {task_id} was not found.")
        return dict(row)

    def list(
        self,
        *,
        include_finished: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        where = "" if include_finished else "WHERE status IN ('open', 'in_progress')"
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f"""SELECT * FROM assistant_tasks {where}
                ORDER BY CASE status WHEN 'in_progress' THEN 0 ELSE 1 END,
                priority DESC, created_at ASC LIMIT ?""",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_project(
        self,
        project: str,
        *,
        include_finished: bool = True,
    ) -> list[dict[str, Any]]:
        finished = "" if include_finished else (
            "AND status IN ('open', 'in_progress')"
        )
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f"""SELECT * FROM assistant_tasks WHERE project = ? {finished}
                ORDER BY id ASC""",
                (project,),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_project(self, prefix: str = "Agent:") -> str | None:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                """SELECT project FROM assistant_tasks
                WHERE project LIKE ? ORDER BY id DESC LIMIT 1""",
                (f"{prefix}%",),
            ).fetchone()
        return str(row[0]) if row is not None else None

    def set_status(self, task_id: int, status: str) -> dict[str, Any]:
        clean_status = status.strip().lower()
        if clean_status not in self.VALID_STATUSES:
            raise ValueError(f"Unsupported task status: {status}")
        completed = "CURRENT_TIMESTAMP" if clean_status == "completed" else "NULL"
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                f"""UPDATE assistant_tasks SET status = ?,
                completed_at = {completed}, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
                (clean_status, int(task_id)),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Task {task_id} was not found.")
        return self.get(task_id)

    def delete(self, task_id: int) -> bool:
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                "DELETE FROM assistant_tasks WHERE id = ?",
                (int(task_id),),
            )
        return cursor.rowcount > 0

    def process(self, text: str) -> dict[str, Any]:
        normalized = re.sub(r"\s+", " ", text.strip())
        add = re.match(r"^(?:add|create) (?:a )?task(?: to)? (.+)$", normalized, re.I)
        if add:
            task = self.create(add.group(1))
            return self._result("task_created", f"Task {task['id']} added: {task['title']}", task)

        if normalized.lower() in {"tasks", "list tasks", "show tasks", "show my tasks", "what are my tasks"}:
            tasks = self.list()
            if not tasks:
                response = "You have no open tasks."
            else:
                lines = [f"{task['id']}. {task['title']} ({task['status'].replace('_', ' ')})" for task in tasks]
                response = "Your tasks:\n" + "\n".join(lines)
            return {"handled": True, "intent": "task_list", "response": response, "tasks": tasks}

        update = re.match(
            r"^(complete|finish|start|cancel|delete) task (\d+)$",
            normalized,
            re.I,
        )
        if update:
            verb, task_id_text = update.groups()
            task_id = int(task_id_text)
            if verb.lower() == "delete":
                deleted = self.delete(task_id)
                return self._result(
                    "task_deleted",
                    f"Task {task_id} deleted." if deleted else f"Task {task_id} was not found.",
                )
            status = {
                "complete": "completed",
                "finish": "completed",
                "start": "in_progress",
                "cancel": "cancelled",
            }[verb.lower()]
            try:
                task = self.set_status(task_id, status)
            except ValueError:
                return self._result("task_not_found", f"Task {task_id} was not found.")
            return self._result(
                "task_updated",
                f"Task {task_id} marked {status.replace('_', ' ')}.",
                task,
            )
        return {"handled": False}

    @staticmethod
    def _result(intent: str, response: str, task: dict[str, Any] | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {"handled": True, "intent": intent, "response": response}
        if task is not None:
            result["task"] = task
        return result

    @staticmethod
    def _clean_title(title: str) -> str:
        cleaned = title.strip(" \t\r\n.!?")
        if not cleaned:
            raise ValueError("Task title is required.")
        if len(cleaned) > 240:
            raise ValueError("Task title must be 240 characters or fewer.")
        return cleaned
