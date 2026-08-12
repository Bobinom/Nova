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


if __name__ == "__main__":
    unittest.main()
