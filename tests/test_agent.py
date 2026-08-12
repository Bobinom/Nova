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

    def test_plan_can_start_advance_and_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NovaApplication(base_dir=Path(directory))
            app.start()
            app.agent.planner = RecordingPlanner(self.make_plan())
            planned = app.handle_message("Agent: prepare me for tomorrow")

            started = app.handle_message("start my plan")
            first, second = planned["tasks"]
            self.assertEqual(started["intent"], "agent_started")
            self.assertEqual(app.tasks.get(first["id"])["status"], "in_progress")

            advanced = app.handle_message("complete current step")
            self.assertEqual(advanced["intent"], "agent_step_completed")
            self.assertEqual(app.tasks.get(first["id"])["status"], "completed")
            self.assertEqual(app.tasks.get(second["id"])["status"], "in_progress")

            completed = app.handle_message("finish the current step")
            self.assertEqual(completed["intent"], "agent_completed")
            self.assertEqual(app.agent.status()["run_status"], "idle")
            app.stop()

    def test_yes_starts_a_plan_after_nova_offers_to_begin(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NovaApplication(base_dir=Path(directory))
            app.start()
            app.agent.planner = RecordingPlanner(self.make_plan())
            app.handle_message("Agent: prepare me for tomorrow")

            result = app.handle_message("yes")

            self.assertEqual(result["intent"], "agent_started")
            self.assertEqual(result["agent_status"], "running")
            app.stop()

    def test_plan_pause_and_resume_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            app = NovaApplication(base_dir=base)
            app.start()
            app.agent.planner = RecordingPlanner(self.make_plan())
            app.handle_message("Plan prepare for tomorrow")
            app.handle_message("begin the plan")

            paused = app.handle_message("pause my plan")
            self.assertEqual(paused["agent_status"], "paused")
            app.stop()

            restarted = NovaApplication(base_dir=base)
            restarted.start()
            status = restarted.handle_message("agent status")
            self.assertEqual(status["agent_status"], "paused")
            resumed = restarted.handle_message("resume my plan")
            self.assertEqual(resumed["agent_status"], "running")
            self.assertEqual(restarted.agent.status()["current_step"], "Review tomorrow's calendar")
            restarted.stop()

    def test_cancel_marks_every_remaining_plan_task_cancelled(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NovaApplication(base_dir=Path(directory))
            app.start()
            app.agent.planner = RecordingPlanner(self.make_plan())
            planned = app.handle_message("Agent: prepare me for tomorrow")
            app.handle_message("start my plan")

            result = app.handle_message("cancel the plan")

            self.assertEqual(result["intent"], "agent_cancelled")
            statuses = [app.tasks.get(task["id"])["status"] for task in planned["tasks"]]
            self.assertEqual(statuses, ["cancelled", "cancelled"])
            app.stop()

    def test_execution_control_without_a_plan_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NovaApplication(base_dir=Path(directory))
            app.start()
            planner = RecordingPlanner(self.make_plan())
            app.agent.planner = planner

            result = app.handle_message("start my plan")

            self.assertEqual(result["intent"], "agent_no_plan")
            self.assertEqual(planner.goals, [])
            app.stop()


if __name__ == "__main__":
    unittest.main()
