from __future__ import annotations

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    details: str = Field(default="", max_length=500)
    priority: int = Field(default=1, ge=0, le=3)


class AgentPlan(BaseModel):
    objective: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=500)
    steps: list[PlanStep] = Field(min_length=1, max_length=8)
