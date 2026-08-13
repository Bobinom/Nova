import json
import tempfile
import unittest
from pathlib import Path

from nova.app import NovaApplication
from nova.skills.service import SkillService


class SkillServiceTests(unittest.TestCase):
    def test_builtin_skills_are_discovered(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NovaApplication(base_dir=Path(directory))
            app.start()

            skill_ids = [skill["id"] for skill in app.skills.list()]

            self.assertEqual(skill_ids, ["project-planning", "research"])
            app.stop()

    def test_skill_request_is_routed_before_general_conversation(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NovaApplication(base_dir=Path(directory))
            app.start()

            result = app.handle_message(
                "Use skill research for compare two laptop options"
            )

            self.assertEqual(result["intent"], "skill_prepared")
            self.assertEqual(result["skill"]["id"], "research")
            self.assertIn("guidance only", result["response"])
            self.assertEqual(len(app.skills.runs.list()), 1)
            app.stop()

    def test_research_comparison_returns_structured_popup_data(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NovaApplication(base_dir=Path(directory))
            app.start()

            result = app.handle_message(
                "Use skill research for MacBook Air vs Dell XPS 13"
            )

            comparison = result["comparison"]
            self.assertEqual(comparison["first_option"], "Macbook Air")
            self.assertEqual(comparison["second_option"], "Dell Xps 13")
            self.assertIn("Performance", comparison["criteria"])
            app.stop()

    def test_user_skill_manifest_is_loaded_without_executable_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "nova.db"
            app = NovaApplication(base_dir=root)
            app.start()
            skill_dir = app.paths.skills_dir / "writing"
            skill_dir.mkdir()
            (skill_dir / "manifest.json").write_text(json.dumps({
                "id": "writing",
                "name": "Writing",
                "version": "1.0.0",
                "description": "Prepare polished writing.",
                "triggers": ["write"],
                "instructions": ["Clarify the audience.", "Draft and revise."],
                "permissions": ["none"],
            }), encoding="utf-8")

            service = SkillService(database, app.paths.skills_dir)
            service.discover()

            self.assertIsNotNone(service.get("writing"))
            self.assertEqual(service.errors, [])
            app.stop()

    def test_unsafe_skill_permission_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = NovaApplication(base_dir=root)
            app.start()
            skill_dir = app.paths.skills_dir / "unsafe"
            skill_dir.mkdir()
            (skill_dir / "manifest.json").write_text(json.dumps({
                "id": "unsafe",
                "name": "Unsafe",
                "version": "1.0.0",
                "description": "Should not load.",
                "triggers": ["unsafe"],
                "instructions": ["Run a command."],
                "permissions": ["shell"],
            }), encoding="utf-8")

            app.skills.discover()

            self.assertIsNone(app.skills.get("unsafe"))
            self.assertTrue(app.skills.errors)
            app.stop()

    def test_skill_run_feedback_is_persistent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = NovaApplication(base_dir=root)
            app.start()
            prepared = app.skills.prepare("project-planning", "launch a website")
            run_id = prepared["skill_run"]["id"]

            completed = app.skills.runs.finish(
                run_id, "completed", feedback="Useful sequence", rating=5
            )

            self.assertEqual(completed["rating"], 5)
            self.assertEqual(completed["feedback"], "Useful sequence")
            app.stop()

    def test_natural_skill_completion_records_rating_and_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NovaApplication(base_dir=Path(directory))
            app.start()
            prepared = app.skills.prepare("research", "compare two laptops")
            run_id = prepared["skill_run"]["id"]

            result = app.handle_message(
                f"Complete skill run {run_id} rating 4 feedback Needed prices"
            )

            self.assertEqual(result["intent"], "skill_run_updated")
            self.assertEqual(result["skill_run"]["status"], "completed")
            self.assertEqual(result["skill_run"]["rating"], 4)
            self.assertEqual(result["skill_run"]["feedback"], "Needed prices")
            app.stop()

    def test_improvement_requires_feedback_from_two_finished_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NovaApplication(base_dir=Path(directory))
            app.start()
            prepared = app.skills.prepare("research", "compare laptops")
            app.skills.runs.finish(
                prepared["skill_run"]["id"], "completed",
                feedback="Needed current prices", rating=3,
            )

            result = app.handle_message("Improve skill research")

            self.assertEqual(result["intent"], "skill_feedback_required")
            self.assertEqual(app.skills.proposals.list(), [])
            app.stop()

    def test_improvement_proposal_shows_exact_change_without_activating(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NovaApplication(base_dir=Path(directory))
            app.start()
            for request in ("compare laptops", "compare desktops"):
                prepared = app.skills.prepare("research", request)
                app.skills.runs.finish(
                    prepared["skill_run"]["id"], "completed",
                    feedback="Needed current prices and budget", rating=3,
                )

            result = app.handle_message("Improve skill research")

            self.assertEqual(result["intent"], "skill_improvement_proposed")
            self.assertEqual(result["proposal"]["status"], "pending")
            self.assertEqual(result["proposal"]["proposed_version"], "1.0.1")
            self.assertIn("Exact change:", result["response"])
            self.assertIn("Verify current prices", result["response"])
            self.assertEqual(app.skills.get("research").version, "1.0.0")
            app.stop()

    def test_approved_proposal_activates_and_can_be_rolled_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = NovaApplication(base_dir=root)
            app.start()
            for request in ("compare laptops", "compare tablets"):
                prepared = app.skills.prepare("research", request)
                app.skills.runs.finish(
                    prepared["skill_run"]["id"], "completed",
                    feedback="Please cite sources", rating=4,
                )
            proposal = app.handle_message("Improve skill research")["proposal"]

            approved = app.handle_message(
                f"Approve skill proposal {proposal['id']}"
            )

            self.assertEqual(approved["intent"], "skill_proposal_approved")
            self.assertEqual(app.skills.get("research").version, "1.0.1")
            self.assertTrue(
                any(
                    instruction.startswith("Cite reliable primary sources")
                    for instruction in app.skills.get("research").instructions
                )
            )
            archive = app.paths.skills_dir / "research" / "versions" / "1.0.0.json"
            self.assertTrue(archive.exists())

            restarted = SkillService(app.paths.database_file, app.paths.skills_dir)
            restarted.discover()
            self.assertEqual(restarted.get("research").version, "1.0.1")

            rolled_back = app.handle_message("Rollback skill research to 1.0.0")
            self.assertEqual(rolled_back["intent"], "skill_rolled_back")
            self.assertEqual(app.skills.get("research").version, "1.0.0")
            app.stop()

    def test_rejected_proposal_does_not_change_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NovaApplication(base_dir=Path(directory))
            app.start()
            for request in ("plan launch", "plan release"):
                prepared = app.skills.prepare("project-planning", request)
                app.skills.runs.finish(
                    prepared["skill_run"]["id"], "completed",
                    feedback="Make it more concise", rating=4,
                )
            proposal = app.handle_message(
                "Improve skill project-planning"
            )["proposal"]

            rejected = app.handle_message(
                f"Reject skill proposal {proposal['id']}"
            )

            self.assertEqual(rejected["intent"], "skill_proposal_rejected")
            self.assertEqual(app.skills.get("project-planning").version, "1.0.0")
            self.assertEqual(
                app.skills.proposals.get(proposal["id"])["status"], "rejected"
            )
            app.stop()


if __name__ == "__main__":
    unittest.main()
