from __future__ import annotations

import re

from pydantic import BaseModel, Field
from pydantic import field_validator


class PlanStep(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    details: str = Field(default="", max_length=500)
    priority: int = Field(default=1, ge=0, le=3)

    @field_validator("title", mode="before")
    @classmethod
    def remove_list_prefix(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return re.sub(
            r"^\s*(?:(?:step\s*)?\d+\s*[.):-]\s*|[-*•]\s+)",
            "",
            value,
            flags=re.IGNORECASE,
        ).strip()


class AgentPlan(BaseModel):
    objective: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=500)
    steps: list[PlanStep] = Field(min_length=1, max_length=8)
