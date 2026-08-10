from __future__ import annotations

import re
from typing import Any, Protocol

from pydantic_ai import Agent, NativeOutput, UsageLimits
from pydantic_ai.exceptions import AgentRunError, UserError
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.ollama import OllamaProvider

from nova.agent.models import AgentPlan
from nova.agent.repository import AgentRunRepository
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
    """Plan and safely advance bounded workflows in Nova's local task list."""

    _CONTROLS = (
        ("agent_status", re.compile(
            r"^(?:agent|plan) status$|^what(?:'s| is) next in my plan\??$",
            re.IGNORECASE,
        )),
        ("agent_start", re.compile(
            r"^(?:start|begin|resume)(?: my| the| agent)? plan$",
            re.IGNORECASE,
        )),
        ("agent_pause", re.compile(
            r"^pause(?: my| the| agent)? plan$", re.IGNORECASE,
        )),
        ("agent_cancel", re.compile(
            r"^cancel(?: my| the| agent)? plan$", re.IGNORECASE,
        )),
        ("agent_step_completed", re.compile(
            r"^(?:complete|finish|done with)(?: the)? current step$",
            re.IGNORECASE,
        )),
    )

    _REQUESTS = (
        re.compile(
            r"^(?:(?:hey\s+)?nova[, ]+)?agent(?:\s+mode)?\s*[:,-]?\s+(.+)$",
            re.IGNORECASE,
        ),
        re.compile(r"^(prepare me for\s+.+)$", re.IGNORECASE),
        re.compile(r"^(?:help me\s+)?plan\s+(.+)$", re.IGNORECASE),
        re.compile(
            r"^(?:break|turn)\s+(.+?)\s+into\s+(?:a\s+)?tasks?$",
            re.IGNORECASE,
        ),
    )

    def __init__(
        self,
        tasks: TaskService,
        planner: PlanGenerator | None = None,
        *,
        runs: AgentRunRepository | None = None,
    ) -> None:
        self.tasks = tasks
        self.planner = planner or PydanticPlanGenerator()
        self.runs = runs or AgentRunRepository(tasks.database_path)

    def status(self) -> dict[str, Any]:
        base = {
            "available": True,
            "provider": "pydantic-ai",
            "model_provider": "ollama",
            "model": "qwen2.5:1.5b",
            "mode": "execution",
            "run_status": "idle",
            "objective": "",
            "progress": "",
            "current_step": "",
        }
        run = self._active_run()
        if run is None:
            return base
        run, tasks = self._reconcile(run)
        completed = sum(task["status"] == "completed" for task in tasks)
        current = next(
            (task for task in tasks if task["status"] == "in_progress"),
            None,
        )
        base.update({
            "run_status": run["status"],
            "objective": run["objective"],
            "progress": f"{completed} of {len(tasks)}",
            "current_step": current["title"] if current else "",
        })
        return base

    def process(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.lower() in {"yes", "begin", "start"}:
            run = self._active_run()
            if run is not None and run["status"] == "planned":
                return self._start()
        for intent, pattern in self._CONTROLS:
            if pattern.fullmatch(cleaned):
                return getattr(self, f"_{intent.removeprefix('agent_')}")()

        match = next(
            (pattern.fullmatch(cleaned) for pattern in self._REQUESTS
             if pattern.fullmatch(cleaned) is not None),
            None,
        )
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
        run = self.runs.create(plan.objective, project)
        numbered = "\n".join(
            f"{index}. {task['title']}"
            for index, task in enumerate(created, start=1)
        )
        return {
            "handled": True,
            "intent": "agent_plan_created",
            "agent_status": "planned",
            "response": (
                f"{plan.summary}\n\nI've added this plan to Tasks:\n{numbered}"
                "\n\nWould you like me to begin?"
            ),
            "plan": plan.model_dump(),
            "tasks": created,
            "run": run,
        }

    def _start(self) -> dict[str, Any]:
        run = self._active_run()
        if run is None:
            return self._no_plan()
        run, tasks = self._reconcile(run)
        current = next(
            (task for task in tasks if task["status"] == "in_progress"),
            None,
        )
        if current is None:
            current = next(
                (task for task in tasks if task["status"] == "open"), None
            )
            if current is None:
                self.runs.set_status(run["id"], "completed")
                return self._result(
                    "agent_completed", "completed",
                    "That plan is already complete.", run=run,
                )
            current = self.tasks.set_status(current["id"], "in_progress")
        run = self.runs.set_status(
            run["id"], "running", current_task_id=current["id"]
        )
        return self._step_result("agent_started", run, current, tasks)

    def _pause(self) -> dict[str, Any]:
        run = self._active_run()
        if run is None:
            return self._no_plan()
        _, tasks = self._reconcile(run)
        current = next(
            (task for task in tasks if task["status"] == "in_progress"), None
        )
        if current is not None:
            self.tasks.set_status(current["id"], "open")
        run = self.runs.set_status(run["id"], "paused")
        return self._result(
            "agent_paused", "paused",
            "I've paused the plan. Say “resume my plan” when you're ready.",
            run=run,
        )

    def _cancel(self) -> dict[str, Any]:
        run = self._active_run()
        if run is None:
            return self._no_plan()
        tasks = self.tasks.list_project(run["project"])
        for task in tasks:
            if task["status"] in {"open", "in_progress"}:
                self.tasks.set_status(task["id"], "cancelled")
        run = self.runs.set_status(run["id"], "cancelled")
        return self._result(
            "agent_cancelled", "cancelled",
            "I've cancelled the remaining steps in that plan.", run=run,
        )

    def _step_completed(self) -> dict[str, Any]:
        run = self._active_run()
        if run is None:
            return self._no_plan()
        run, tasks = self._reconcile(run)
        current = next(
            (task for task in tasks if task["status"] == "in_progress"), None
        )
        if current is None:
            return self._result(
                "agent_not_running", run["status"],
                "No step is running. Say “start my plan” to begin.", run=run,
            )
        self.tasks.set_status(current["id"], "completed")
        remaining = [task for task in tasks if task["status"] == "open"]
        if not remaining:
            run = self.runs.set_status(run["id"], "completed")
            return self._result(
                "agent_completed", "completed",
                "Plan complete. Every step is finished.", run=run,
            )
        following = self.tasks.set_status(remaining[0]["id"], "in_progress")
        run = self.runs.set_status(
            run["id"], "running", current_task_id=following["id"]
        )
        refreshed = self.tasks.list_project(run["project"])
        return self._step_result(
            "agent_step_completed", run, following, refreshed,
            prefix=f"Completed: {current['title']}. ",
        )

    def _status(self) -> dict[str, Any]:
        run = self._active_run()
        if run is None:
            return self._no_plan()
        run, tasks = self._reconcile(run)
        completed = sum(task["status"] == "completed" for task in tasks)
        current = next(
            (task for task in tasks if task["status"] == "in_progress"), None
        )
        if current is not None:
            message = f"Current step: {current['title']}."
        elif run["status"] == "paused":
            message = "The plan is paused."
        else:
            next_task = next(
                (task for task in tasks if task["status"] == "open"), None
            )
            message = (
                f"Next step: {next_task['title']}." if next_task
                else "The plan is complete."
            )
        return self._result(
            "agent_status", run["status"],
            f"{run['objective']}: {completed} of {len(tasks)} steps complete. "
            f"{message}", run=run,
        )

    def _active_run(self) -> dict[str, Any] | None:
        run = self.runs.latest(active_only=True)
        if run is not None:
            return run
        project = self.tasks.latest_project()
        if project is None or self.runs.find_project(project) is not None:
            return None
        return self.runs.create(project.removeprefix("Agent: "), project)

    def _reconcile(
        self, run: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        tasks = self.tasks.list_project(run["project"])
        current = next(
            (task for task in tasks if task["status"] == "in_progress"), None
        )
        open_tasks = any(task["status"] == "open" for task in tasks)
        if current is not None and (
            run["status"] != "running"
            or run["current_task_id"] != current["id"]
        ):
            run = self.runs.set_status(
                run["id"], "running", current_task_id=current["id"]
            )
        elif current is None and not open_tasks:
            run = self.runs.set_status(run["id"], "completed")
        elif current is None and run["status"] == "running":
            run = self.runs.set_status(run["id"], "planned")
        return run, tasks

    def _step_result(
        self,
        intent: str,
        run: dict[str, Any],
        task: dict[str, Any],
        tasks: list[dict[str, Any]],
        *,
        prefix: str = "",
    ) -> dict[str, Any]:
        index = next(
            index for index, item in enumerate(tasks, start=1)
            if item["id"] == task["id"]
        )
        return self._result(
            intent, "running",
            f"{prefix}Step {index} of {len(tasks)}: {task['title']}. "
            "When you're done, say “complete current step.”",
            run=run, task=task,
        )

    @staticmethod
    def _result(
        intent: str,
        status: str,
        response: str,
        *,
        run: dict[str, Any],
        task: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = {
            "handled": True,
            "intent": intent,
            "agent_status": status,
            "response": response,
            "run": run,
        }
        if task is not None:
            result["task"] = task
        return result

    @staticmethod
    def _no_plan() -> dict[str, Any]:
        return {
            "handled": True,
            "intent": "agent_no_plan",
            "agent_status": "idle",
            "response": "There isn't an active plan yet. Tell me a goal first.",
        }

    @staticmethod
    def _failure(response: str) -> dict[str, Any]:
        return {
            "handled": True,
            "intent": "agent_plan_failed",
            "agent_status": "failed",
            "response": response,
        }
