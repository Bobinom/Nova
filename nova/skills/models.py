from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class SkillManifest:
    skill_id: str
    name: str
    version: str
    description: str
    triggers: tuple[str, ...]
    instructions: tuple[str, ...]
    permissions: tuple[str, ...] = ()
    source: str = "user"

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, source: str) -> "SkillManifest":
        skill_id = str(payload.get("id", "")).strip().lower()
        name = str(payload.get("name", "")).strip()
        version = str(payload.get("version", "")).strip()
        description = str(payload.get("description", "")).strip()
        triggers = cls._strings(payload.get("triggers"), "triggers")
        instructions = cls._strings(payload.get("instructions"), "instructions")
        permissions = cls._strings(
            payload.get("permissions", []), "permissions", allow_empty=True
        )
        if not _IDENTIFIER.fullmatch(skill_id):
            raise ValueError("Skill id must use lowercase words separated by hyphens.")
        if not name or not version or not description:
            raise ValueError("Skill name, version, and description are required.")
        if any(permission != "none" for permission in permissions):
            raise ValueError(
                "Skills v1 is guidance-only; the only allowed permission is 'none'."
            )
        return cls(
            skill_id=skill_id,
            name=name,
            version=version,
            description=description,
            triggers=triggers,
            instructions=instructions,
            permissions=permissions,
            source=source,
        )

    @staticmethod
    def _strings(value: Any, field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f"Skill {field} must be a list of text values.")
        cleaned = tuple(item.strip() for item in value if item.strip())
        if not cleaned and not allow_empty:
            raise ValueError(f"Skill {field} cannot be empty.")
        return cleaned

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.skill_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "triggers": list(self.triggers),
            "instructions": list(self.instructions),
            "permissions": list(self.permissions),
            "source": self.source,
        }
