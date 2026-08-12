from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from nova.skills.models import SkillManifest
from nova.skills.repository import SkillRunRepository


class SkillService:
    """Discover declarative, guidance-only skills and record their outcomes."""

    def __init__(self, database_path: Path, user_skills_dir: Path) -> None:
        self.runs = SkillRunRepository(database_path)
        self.user_skills_dir = user_skills_dir
        self.builtin_skills_dir = Path(__file__).with_name("builtin")
        self._skills: dict[str, SkillManifest] = {}
        self.errors: list[str] = []

    def discover(self) -> None:
        self.user_skills_dir.mkdir(parents=True, exist_ok=True)
        self._skills = {}
        self.errors = []
        self._load_directory(self.builtin_skills_dir, source="builtin")
        self._load_directory(self.user_skills_dir, source="user")

    def list(self) -> list[dict[str, Any]]:
        return [skill.as_dict() for skill in self._skills.values()]

    def get(self, skill_id: str) -> SkillManifest | None:
        return self._skills.get(skill_id.strip().lower())

    def prepare(self, skill_id: str, request: str) -> dict[str, Any]:
        skill = self.get(skill_id)
        if skill is None:
            return self._result(
                "skill_not_found",
                f"I couldn't find the skill '{skill_id}'. Say “skills” to list them.",
            )
        cleaned = request.strip()
        if not cleaned:
            return self._result(
                "skill_request_required",
                f"Tell me what you want the {skill.name} skill to help with.",
            )
        run = self.runs.create(skill.skill_id, skill.version, cleaned)
        steps = "\n".join(
            f"{index}. {instruction}"
            for index, instruction in enumerate(skill.instructions, start=1)
        )
        return {
            "handled": True,
            "intent": "skill_prepared",
            "skill": skill.as_dict(),
            "skill_run": run,
            "response": (
                f"Using {skill.name} for: {cleaned}\n\n{steps}\n\n"
                f"Skill run {run['id']} is prepared. This Skills v1 workflow "
                "provides guidance only and cannot execute computer actions."
            ),
        }

    def process(self, text: str) -> dict[str, Any]:
        cleaned = re.sub(r"\s+", " ", text.strip())
        if cleaned.lower() in {"skills", "list skills", "show skills"}:
            skills = self.list()
            if not skills:
                response = "No valid skills are installed."
            else:
                response = "Available skills:\n" + "\n".join(
                    f"- {skill['id']}: {skill['description']}"
                    for skill in skills
                )
            return {"handled": True, "intent": "skill_list", "response": response, "skills": skills}
        detail = re.fullmatch(r"skill ([a-z0-9-]+)", cleaned, re.I)
        if detail:
            skill = self.get(detail.group(1))
            if skill is None:
                return self._result("skill_not_found", "That skill is not installed.")
            return {
                "handled": True,
                "intent": "skill_detail",
                "response": f"{skill.name} {skill.version}: {skill.description}",
                "skill": skill.as_dict(),
            }
        use = re.fullmatch(
            r"(?:use|run) skill ([a-z0-9-]+)(?: (?:for|to) (.+))?",
            cleaned,
            re.I,
        )
        if use:
            return self.prepare(use.group(1), use.group(2) or "")
        outcome = re.fullmatch(
            r"(finish|complete|fail|cancel) skill run (\d+)"
            r"(?: rating ([1-5]))?(?: feedback (.+))?",
            cleaned,
            re.I,
        )
        if outcome:
            verb, run_id, rating, feedback = outcome.groups()
            status = {
                "finish": "completed",
                "complete": "completed",
                "fail": "failed",
                "cancel": "cancelled",
            }[verb.lower()]
            try:
                run = self.runs.finish(
                    int(run_id), status,
                    feedback=feedback or "",
                    rating=int(rating) if rating else None,
                )
            except ValueError as exc:
                return self._result("skill_run_error", str(exc))
            return {
                "handled": True,
                "intent": "skill_run_updated",
                "skill_run": run,
                "response": (
                    f"Skill run {run_id} marked {status}. "
                    "I saved that outcome for future skill improvement."
                ),
            }
        return {"handled": False}

    def _load_directory(self, root: Path, *, source: str) -> None:
        if not root.exists():
            return
        for manifest_path in sorted(root.glob("*/manifest.json")):
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                skill = SkillManifest.from_dict(payload, source=source)
                if skill.skill_id in self._skills:
                    raise ValueError(f"Duplicate skill id: {skill.skill_id}")
                self._skills[skill.skill_id] = skill
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self.errors.append(f"{manifest_path}: {exc}")

    @staticmethod
    def _result(intent: str, response: str) -> dict[str, Any]:
        return {"handled": True, "intent": intent, "response": response}
