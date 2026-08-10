import tempfile
import unittest
from pathlib import Path

from nova.agent.models import AgentPlan, PlanStep
from nova.agent.service import SupervisorAgent
from nova.app import NovaApplication
from nova.tasks.service import TaskService


class RecordingPlanner:
    def __init__(self, plan: AgentPlan | None = None, error: Exception | None = None):
        self.plan = plan
        self.error = error
        self.goals: list[str] = []

    def create_plan(self, goal: str) -> AgentPlan:
        self.goals.append(goal)
        if self.error is not None:
            raise self.error
        assert self.plan is not None
        return self.plan


class SupervisorAgentTests(unittest.TestCase):
    def make_plan(self) -> AgentPlan:
        return AgentPlan(
            objective="Prepare for tomorrow",
            summary="Here is a focused preparation plan.",
            steps=[
                PlanStep(title="Review tomorrow's calendar", priority=2),
                PlanStep(
                    title="Pack required items",
                    details="Use the calendar review to make the list.",
                ),
            ],
        )

    def test_explicit_agent_request_creates_validated_persistent_tasks(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "nova.db"
            app = NovaApplication(base_dir=Path(directory))
            app.start()
            planner = RecordingPlanner(self.make_plan())
            app.agent.planner = planner

            result = app.handle_message("Agent: prepare me for tomorrow")

            self.assertEqual(result["intent"], "agent_plan_created")
            self.assertEqual(planner.goals, ["prepare me for tomorrow"])
            self.assertEqual(len(result["tasks"]), 2)
            self.assertEqual(len(app.tasks.list()), 2)
            self.assertIn("added this plan to Tasks", result["response"])
            app.stop()

            tasks = TaskService(database).list()
            self.assertEqual(tasks[0]["project"], "Agent: Prepare for tomorrow")

    def test_model_numbering_is_removed_before_tasks_are_saved_or_spoken(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NovaApplication(base_dir=Path(directory))
            app.start()
            plan = AgentPlan(
                objective="Prepare tomorrow",
                summary="A short plan.",
                steps=[
                    PlanStep(title="1. Review the schedule"),
                    PlanStep(title="Step 2: Pack required items"),
                ],
            )
            app.agent.planner = RecordingPlanner(plan)

            result = app.handle_message("Prepare me for tomorrow")

            self.assertIn("1. Review the schedule", result["response"])
            self.assertNotIn("1. 1.", result["response"])
            self.assertNotIn("2. Step 2", result["response"])
            self.assertEqual(
                [task["title"] for task in app.tasks.list()],
                ["Review the schedule", "Pack required items"],
            )
            app.stop()

    def test_agent_does_not_intercept_normal_conversation(self):
        with tempfile.TemporaryDirectory() as directory:
            tasks = TaskService(Path(directory) / "nova.db")
            planner = RecordingPlanner(self.make_plan())
            agent = SupervisorAgent(tasks, planner)

            result = agent.process("Help me prepare for tomorrow")

            self.assertEqual(result, {"handled": False})
            self.assertEqual(planner.goals, [])

    def test_natural_prepare_request_activates_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NovaApplication(base_dir=Path(directory))
            app.start()
            planner = RecordingPlanner(self.make_plan())
            app.agent.planner = planner

            result = app.handle_message(
                "Prepare me for a productive day tomorrow"
            )

            self.assertEqual(result["intent"], "agent_plan_created")
            self.assertEqual(
                planner.goals,
                ["Prepare me for a productive day tomorrow"],
            )
            app.stop()

    def test_agent_planning_failure_creates_no_tasks(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NovaApplication(base_dir=Path(directory))
            app.start()
            planner = RecordingPlanner(error=RuntimeError("offline"))
            agent = SupervisorAgent(app.tasks, planner)

            result = agent.process("Agent plan tomorrow")

            self.assertEqual(result["agent_status"], "failed")
            self.assertEqual(app.tasks.list(), [])
            self.assertIn("Ollama", result["response"])
            app.stop()


if __name__ == "__main__":
    unittest.main()
