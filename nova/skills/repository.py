from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class SkillRunRepository:
    VALID_STATUSES = {"prepared", "completed", "failed", "cancelled"}

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def create(self, skill_id: str, skill_version: str, request: str) -> dict[str, Any]:
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """INSERT INTO skill_runs(skill_id, skill_version, request)
                VALUES (?, ?, ?)""",
                (skill_id, skill_version, request.strip()),
            )
            run_id = int(cursor.lastrowid)
        return self.get(run_id)

    def get(self, run_id: int) -> dict[str, Any]:
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM skill_runs WHERE id = ?", (int(run_id),)
            ).fetchone()
        if row is None:
            raise ValueError(f"Skill run {run_id} was not found.")
        return dict(row)

    def list(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM skill_runs ORDER BY id DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_for_skill(self, skill_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """SELECT * FROM skill_runs WHERE skill_id = ?
                ORDER BY id DESC LIMIT ?""",
                (skill_id.strip().lower(), max(1, min(int(limit), 500))),
            ).fetchall()
        return [dict(row) for row in rows]

    def finish(
        self,
        run_id: int,
        status: str,
        *,
        feedback: str = "",
        rating: int | None = None,
    ) -> dict[str, Any]:
        normalized = status.strip().lower()
        if normalized not in self.VALID_STATUSES - {"prepared"}:
            raise ValueError(f"Unsupported skill-run status: {status}")
        if rating is not None and rating not in range(1, 6):
            raise ValueError("Skill rating must be between 1 and 5.")
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """UPDATE skill_runs SET status = ?, feedback = ?, rating = ?,
                completed_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (normalized, feedback.strip(), rating, int(run_id)),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Skill run {run_id} was not found.")
        return self.get(run_id)


class SkillProposalRepository:
    VALID_STATUSES = {"pending", "approved", "rejected"}

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def create(
        self,
        skill_id: str,
        base_version: str,
        proposed_version: str,
        rationale: str,
        manifest: dict[str, Any],
        test_summary: str,
    ) -> dict[str, Any]:
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """INSERT INTO skill_proposals(
                    skill_id, base_version, proposed_version, rationale,
                    manifest_json, test_summary
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    skill_id,
                    base_version,
                    proposed_version,
                    rationale,
                    json.dumps(manifest, sort_keys=True),
                    test_summary,
                ),
            )
            proposal_id = int(cursor.lastrowid)
        return self.get(proposal_id)

    def get(self, proposal_id: int) -> dict[str, Any]:
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM skill_proposals WHERE id = ?", (int(proposal_id),)
            ).fetchone()
        if row is None:
            raise ValueError(f"Skill proposal {proposal_id} was not found.")
        result = dict(row)
        result["manifest"] = json.loads(result.pop("manifest_json"))
        return result

    def list(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM skill_proposals ORDER BY id DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        results = []
        for row in rows:
            result = dict(row)
            result["manifest"] = json.loads(result.pop("manifest_json"))
            results.append(result)
        return results

    def decide(self, proposal_id: int, status: str) -> dict[str, Any]:
        normalized = status.strip().lower()
        if normalized not in self.VALID_STATUSES - {"pending"}:
            raise ValueError(f"Unsupported proposal status: {status}")
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """UPDATE skill_proposals SET status = ?,
                decided_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'pending'""",
                (normalized, int(proposal_id)),
            )
            if cursor.rowcount == 0:
                current = self.get(proposal_id)
                raise ValueError(
                    f"Skill proposal {proposal_id} is already {current['status']}."
                )
        return self.get(proposal_id)
