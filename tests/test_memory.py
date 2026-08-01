import logging
import tempfile
import unittest
from pathlib import Path

from nova.core.events import EventBus
from nova.memory.engine import MemoryEngine
from nova.memory.repository import MemoryRepository


class MemoryEngineTests(unittest.TestCase):
    def make_engine(self, path: Path) -> MemoryEngine:
        engine = MemoryEngine(
            repository=MemoryRepository(path),
            events=EventBus(logging.getLogger("test.memory")),
            logger=logging.getLogger("test.memory.engine"),
        )
        engine.initialize()
        return engine

    def test_name_learning_and_recall(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory) / "nova.db")
            learned = engine.process_text("My name is Eric")
            recalled = engine.process_text("What's my name?")

            self.assertTrue(learned["handled"])
            self.assertEqual(recalled["response"], "Your name is Eric.")
            engine.close()

    def test_name_replaces_old_name(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory) / "nova.db")
            engine.process_text("My name is Eric")
            engine.process_text("Call me Rick")

            recalled = engine.process_text("What is my name?")
            self.assertEqual(recalled["response"], "Your name is Rick.")
            self.assertEqual(len(engine.list_memories("identity")), 1)
            engine.close()

    def test_memory_persists_between_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "nova.db"

            first = self.make_engine(database)
            first.process_text("My favorite color is amber")
            first.close()

            second = self.make_engine(database)
            recalled = second.process_text("What's my favorite color?")
            self.assertEqual(
                recalled["response"],
                "Your favorite color is amber.",
            )
            second.close()

    def test_missing_name_does_not_return_nova(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory) / "nova.db")
            recalled = engine.process_text("What's my name?")

            self.assertEqual(recalled["response"], "I don't know your name yet.")
            self.assertNotIn("Nova", recalled["response"])
            engine.close()

    def test_search_finds_memory_from_natural_language(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory) / "nova.db")
            engine.remember(
                "relationship.girlfriend",
                "Dunja",
                category="relationship",
            )

            results = engine.search("What is my partner's name?")

            self.assertEqual([record.key for record in results], [
                "relationship.girlfriend",
            ])
            self.assertEqual(results[0].value, "Dunja")
            engine.close()

    def test_search_ranks_key_matches_and_respects_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory) / "nova.db")
            engine.remember(
                "user.favorite_color",
                "Amber",
                category="preference",
            )
            engine.remember(
                "user.liked_colors",
                ["Purple"],
                category="preference",
            )
            engine.remember("user.location", "Malmö", category="identity")

            results = engine.search("What is my favorite colour?", limit=1)

            self.assertEqual([record.key for record in results], [
                "user.favorite_color",
            ])
            engine.close()

    def test_search_preserves_exact_key_recall(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory) / "nova.db")
            stored = engine.remember(
                "user.location",
                "Malmö",
                category="identity",
            )

            self.assertEqual(engine.recall("user.location"), stored)
            self.assertEqual(engine.search("user.location"), [stored])
            engine.close()

    def test_extracts_semantic_memories(self):
        cases = [
            (
                "My girlfriend's name is Dunja",
                "relationship.girlfriend",
                "Dunja",
            ),
            ("My dog is Max", "pet.dog", "Max"),
            ("I work at Espresso House", "work.employer", "Espresso House"),
            ("I'm working on Nova", "project.current", "Nova"),
            ("My goal is to build Jarvis", "goal.primary", "build Jarvis"),
            ("I prefer dark interfaces", "user.preference", "dark interfaces"),
        ]

        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory) / "nova.db")

            for text, key, value in cases:
                result = engine.process_text(text)
                self.assertTrue(result["handled"], text)
                self.assertEqual(engine.recall(key).value, value)

            engine.close()

    def test_does_not_learn_questions_or_uncertain_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory) / "nova.db")

            question = engine.process_text("My dog is Max?")
            uncertainty = engine.process_text("My dog is maybe Max")
            third_person = engine.process_text("Dunja's dog is Max")

            self.assertFalse(question["handled"])
            self.assertFalse(uncertainty["handled"])
            self.assertFalse(third_person["handled"])
            self.assertEqual(engine.list_memories(), [])
            engine.close()


if __name__ == "__main__":
    unittest.main()
