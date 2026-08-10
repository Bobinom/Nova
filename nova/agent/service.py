from __future__ import annotations

import re
from typing import Any, Protocol

from pydantic_ai import Agent, NativeOutput, UsageLimits
from pydantic_ai.exceptions import AgentRunError, UserError
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.ollama import OllamaProvider

from nova.agent.models import AgentPlan
from nova.tasks.service import TaskService


class PlanGenerator(Protocol):
    def create_plan(self, goal: str) -> AgentPlan: ...


class PydanticPlanGenerator:
    """Create validated plans with Pydantic AI and Nova's local Ollama model."""

    INSTRUCTIONS = """
You are Nova's local planning supervisor. Turn the user's goal into a short,
practical plan. Produce between two and six concrete steps in execution order.
Each title must describe one observable action. Keep details brief. Use priority
0 for optional work, 1 for normal work, 2 for important work, and 3 only for an
urgent blocker. Do not claim that a step has already been completed. Do not add
steps involving purchases, messages, account changes, deletion, printing, or
computer control without stating that Nova must request user confirmation first.
""".strip()

    def __init__(
        self,
        *,
        model: str = "qwen2.5:1.5b",
        base_url: str = "http://localhost:11434/v1",
    ) -> None:
        ollama_model = OpenAIChatModel(
            model,
            provider=OllamaProvider(base_url=base_url),
        )
        self._agent = Agent(
            ollama_model,
            output_type=NativeOutput(AgentPlan),
            instructions=self.INSTRUCTIONS,
            model_settings=OpenAIChatModelSettings(
                temperature=0.2,
                max_tokens=900,
                timeout=60,
            ),
            retries=1,
        )

    def create_plan(self, goal: str) -> AgentPlan:
        result = self._agent.run_sync(
            goal,
            usage_limits=UsageLimits(
                request_limit=2,
                output_tokens_limit=1200,
                tool_calls_limit=0,
            ),
        )
        return result.output


class SupervisorAgent:
    """A bounded agent that plans explicit goals into Nova's local task list."""

    _REQUEST = re.compile(
        r"^(?:(?:hey\s+)?nova[, ]+)?agent(?:\s+mode)?\s*[:,-]?\s+(.+)$",
        re.IGNORECASE,
    )

    def __init__(
        self,
        tasks: TaskService,
        planner: PlanGenerator | None = None,
    ) -> None:
        self.tasks = tasks
        self.planner = planner or PydanticPlanGenerator()

    def status(self) -> dict[str, Any]:
        return {
            "available": True,
            "provider": "pydantic-ai",
            "model_provider": "ollama",
            "model": "qwen2.5:1.5b",
            "mode": "planning",
        }

    def process(self, text: str) -> dict[str, Any]:
        match = self._REQUEST.fullmatch(text.strip())
        if match is None:
            return {"handled": False}

        goal = match.group(1).strip()
        if not goal:
            return self._failure("Tell me what goal you want me to plan.")

        try:
            plan = self.planner.create_plan(goal)
        except (AgentRunError, UserError, OSError, RuntimeError, ValueError) as exc:
            return self._failure(
                "I couldn't create the agent plan. Make sure Ollama is running "
                f"and try again. ({exc})"
            )

        project = f"Agent: {plan.objective}"[:120]
        created = [
            self.tasks.create(
                step.title,
                details=step.details,
                project=project,
                priority=step.priority,
            )
            for step in plan.steps
        ]
        numbered = "\n".join(
            f"{index}. {task['title']}"
            for index, task in enumerate(created, start=1)
        )
        return {
            "handled": True,
            "intent": "agent_plan_created",
            "agent_status": "completed",
            "response": f"{plan.summary}\n\nI've added this plan to Tasks:\n{numbered}",
            "plan": plan.model_dump(),
            "tasks": created,
        }

    @staticmethod
    def _failure(response: str) -> dict[str, Any]:
        return {
            "handled": True,
            "intent": "agent_plan_failed",
            "agent_status": "failed",
            "response": response,
        }
