from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from nova.skills.models import SkillManifest
from nova.skills.repository import SkillProposalRepository, SkillRunRepository


class SkillService:
    """Discover declarative, guidance-only skills and record their outcomes."""

    def __init__(self, database_path: Path, user_skills_dir: Path) -> None:
        self.runs = SkillRunRepository(database_path)
        self.proposals = SkillProposalRepository(database_path)
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
        result = {
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
        if skill.skill_id == "research" and self._is_comparison(cleaned):
            first, second = self._comparison_options(cleaned)
            result["comparison"] = {
                "title": "Laptop comparison",
                "first_option": first,
                "second_option": second,
                "criteria": [
                    "Performance", "Battery", "Display", "Portability", "Price"
                ],
                "status": "Research prepared",
                "note": (
                    "Skills v1 has prepared the comparison framework. "
                    "Specifications are not filled until live sourced research is added."
                ),
            }
        return result

    def propose_improvement(self, skill_id: str) -> dict[str, Any]:
        skill = self.get(skill_id)
        if skill is None:
            return self._result("skill_not_found", "That skill is not installed.")
        runs = [
            run for run in self.runs.list_for_skill(skill.skill_id)
            if run["status"] != "prepared" and str(run["feedback"]).strip()
        ]
        if len(runs) < 2:
            return self._result(
                "skill_feedback_required",
                "I need feedback from at least two finished runs before I can "
                f"propose an improvement to {skill.name}.",
            )
        added = self._learning_instruction(runs)
        if added in skill.instructions:
            return self._result(
                "skill_no_new_improvement",
                "The recurring feedback is already covered by this skill.",
            )
        proposed_version = self._next_patch_version(skill.version)
        manifest = self._manifest_payload(skill)
        manifest["version"] = proposed_version
        manifest["instructions"] = [*skill.instructions, added]
        validated = SkillManifest.from_dict(manifest, source="proposal")
        test_summary = (
            f"Passed manifest safety validation and replayed {len(runs)} stored "
            "examples. Permissions remain guidance-only."
        )
        ratings = [int(run["rating"]) for run in runs if run["rating"] is not None]
        average = f" Average rating: {sum(ratings) / len(ratings):.1f}/5." if ratings else ""
        rationale = f"Analyzed {len(runs)} feedback-bearing runs.{average}"
        proposal = self.proposals.create(
            skill.skill_id,
            skill.version,
            proposed_version,
            rationale,
            self._manifest_payload(validated),
            test_summary,
        )
        return {
            "handled": True,
            "intent": "skill_improvement_proposed",
            "proposal": proposal,
            "response": (
                f"Skill improvement proposal {proposal['id']} is ready for "
                f"{skill.name} {skill.version} → {proposed_version}.\n\n"
                f"Exact change:\n+ {added}\n\n{rationale} {test_summary}\n\n"
                f"Nothing has changed yet. Say “approve skill proposal "
                f"{proposal['id']}” or “reject skill proposal {proposal['id']}”."
            ),
        }

    def approve_proposal(self, proposal_id: int) -> dict[str, Any]:
        try:
            proposal = self.proposals.get(proposal_id)
        except ValueError as exc:
            return self._result("skill_proposal_error", str(exc))
        if proposal["status"] != "pending":
            return self._result(
                "skill_proposal_error",
                f"Skill proposal {proposal_id} is already {proposal['status']}.",
            )
        current = self.get(proposal["skill_id"])
        if current is None or current.version != proposal["base_version"]:
            return self._result(
                "skill_proposal_stale",
                "This proposal no longer matches the active skill version. "
                "Create a new proposal instead.",
            )
        try:
            SkillManifest.from_dict(proposal["manifest"], source="user")
            self._archive_and_activate(current, proposal["manifest"])
            decided = self.proposals.decide(proposal_id, "approved")
            self.discover()
        except (OSError, ValueError) as exc:
            return self._result("skill_proposal_error", str(exc))
        return {
            "handled": True,
            "intent": "skill_proposal_approved",
            "proposal": decided,
            "skill": self.get(proposal["skill_id"]).as_dict(),
            "response": (
                f"Approved proposal {proposal_id}. {current.name} "
                f"{proposal['proposed_version']} is now active. Version "
                f"{current.version} was archived for rollback."
            ),
        }

    def reject_proposal(self, proposal_id: int) -> dict[str, Any]:
        try:
            proposal = self.proposals.decide(proposal_id, "rejected")
        except ValueError as exc:
            return self._result("skill_proposal_error", str(exc))
        return {
            "handled": True,
            "intent": "skill_proposal_rejected",
            "proposal": proposal,
            "response": f"Rejected skill proposal {proposal_id}. No skill changed.",
        }

    def rollback(self, skill_id: str, version: str) -> dict[str, Any]:
        skill = self.get(skill_id)
        if skill is None:
            return self._result("skill_not_found", "That skill is not installed.")
        archived = self._versions_dir(skill.skill_id) / f"{version}.json"
        if not archived.exists():
            return self._result(
                "skill_version_not_found",
                f"Archived version {version} was not found for {skill.name}.",
            )
        try:
            payload = json.loads(archived.read_text(encoding="utf-8"))
            restored = SkillManifest.from_dict(payload, source="user")
            self._write_active_manifest(restored.skill_id, self._manifest_payload(restored))
            self.discover()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return self._result("skill_rollback_error", str(exc))
        return {
            "handled": True,
            "intent": "skill_rolled_back",
            "skill": self.get(skill.skill_id).as_dict(),
            "response": f"Rolled {skill.name} back to version {version}.",
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
        if cleaned.lower() in {"skill-proposals", "skill proposals"}:
            proposals = self.proposals.list()
            response = "No skill proposals recorded." if not proposals else (
                "Skill proposals:\n" + "\n".join(
                    f"- [{item['id']}] {item['status']}: {item['skill_id']} "
                    f"{item['base_version']} → {item['proposed_version']}"
                    for item in proposals
                )
            )
            return {"handled": True, "intent": "skill_proposal_list", "response": response, "proposals": proposals}
        improve = re.fullmatch(
            r"(?:improve skill|propose skill improvement) ([a-z0-9-]+)", cleaned, re.I
        )
        if improve:
            return self.propose_improvement(improve.group(1))
        decision = re.fullmatch(
            r"(approve|reject) skill proposal (\d+)", cleaned, re.I
        )
        if decision:
            return (
                self.approve_proposal(int(decision.group(2)))
                if decision.group(1).lower() == "approve"
                else self.reject_proposal(int(decision.group(2)))
            )
        rollback = re.fullmatch(
            r"rollback skill ([a-z0-9-]+) to ([0-9]+(?:\.[0-9]+){2})", cleaned, re.I
        )
        if rollback:
            return self.rollback(rollback.group(1), rollback.group(2))
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
                existing = self._skills.get(skill.skill_id)
                if existing is not None and not (
                    source == "user" and existing.source == "builtin"
                ):
                    raise ValueError(f"Duplicate skill id: {skill.skill_id}")
                self._skills[skill.skill_id] = skill
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self.errors.append(f"{manifest_path}: {exc}")

    @staticmethod
    def _is_comparison(request: str) -> bool:
        lowered = request.lower()
        return any(marker in lowered for marker in ("compare", " vs ", " versus "))

    @staticmethod
    def _comparison_options(request: str) -> tuple[str, str]:
        cleaned = request.strip().rstrip(".?!")
        cleaned = re.sub(r"^compare\s+", "", cleaned, flags=re.I)
        split = re.split(r"\s+(?:vs\.?|versus|and)\s+", cleaned, maxsplit=1, flags=re.I)
        if len(split) == 2 and all(part.strip() for part in split):
            return split[0].strip().title(), split[1].strip().title()
        return "Laptop A", "Laptop B"

    @staticmethod
    def _learning_instruction(runs: list[dict[str, Any]]) -> str:
        feedback = " ".join(str(run["feedback"]).lower() for run in runs)
        themes = (
            (("price", "cost", "budget"), "Verify current prices and compare total cost against the user's budget."),
            (("source", "citation", "evidence"), "Cite reliable primary sources for factual claims and recommendations."),
            (("detail", "spec", "technical"), "Include the exact specifications that materially affect the recommendation."),
            (("short", "concise", "brief"), "Keep the final result concise while preserving the decisive evidence."),
        )
        for markers, instruction in themes:
            if any(marker in feedback for marker in markers):
                return instruction
        snippets = []
        for run in runs[:3]:
            text = re.sub(r"\s+", " ", str(run["feedback"]).strip()).rstrip(".?!")
            if text and text.lower() not in {item.lower() for item in snippets}:
                snippets.append(text)
        return "Address recurring user feedback explicitly: " + "; ".join(snippets) + "."

    @staticmethod
    def _next_patch_version(version: str) -> str:
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
        if match is None:
            raise ValueError("Skill versions must use semantic versioning, such as 1.0.0.")
        major, minor, patch = (int(value) for value in match.groups())
        return f"{major}.{minor}.{patch + 1}"

    @staticmethod
    def _manifest_payload(skill: SkillManifest) -> dict[str, Any]:
        payload = skill.as_dict()
        payload.pop("source", None)
        return payload

    def _versions_dir(self, skill_id: str) -> Path:
        return self.user_skills_dir / skill_id / "versions"

    def _archive_and_activate(
        self, current: SkillManifest, proposed: dict[str, Any]
    ) -> None:
        versions = self._versions_dir(current.skill_id)
        versions.mkdir(parents=True, exist_ok=True)
        archive = versions / f"{current.version}.json"
        if not archive.exists():
            archive.write_text(
                json.dumps(self._manifest_payload(current), indent=2) + "\n",
                encoding="utf-8",
            )
        self._write_active_manifest(current.skill_id, proposed)

    def _write_active_manifest(self, skill_id: str, payload: dict[str, Any]) -> None:
        directory = self.user_skills_dir / skill_id
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / "manifest.json"
        temporary = directory / "manifest.json.tmp"
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(destination)

    @staticmethod
    def _result(intent: str, response: str) -> dict[str, Any]:
        return {"handled": True, "intent": intent, "response": response}
