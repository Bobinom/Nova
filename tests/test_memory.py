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

    def test_event_path_updates_and_forgets_matching_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory) / "nova.db")
            engine.process_text("I work at Espresso House")
            engine.process_text("Actually, I work at IKEA now")

            self.assertEqual(engine.recall("work.employer").value, "IKEA")

            result = engine.process_text("I no longer work at IKEA")

            self.assertTrue(result["deleted"])
            self.assertIsNone(engine.recall("work.employer"))
            engine.close()

    def test_natural_location_forget(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory) / "nova.db")
            engine.process_text("I live in Malmö")

            result = engine.process_text("Forget where I live")

            self.assertTrue(result["deleted"])
            self.assertIsNone(engine.recall("user.location"))
            engine.close()

    def test_repeated_pet_and_preference_facts_remain_unique(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory) / "nova.db")
            engine.process_text("My dog is Max")
            engine.process_text("My dog is Rex")
            engine.process_text("My dog is Max")
            engine.process_text("I prefer dark interfaces")
            engine.process_text("I prefer concise answers")

            self.assertEqual(engine.recall("pet.dog").value, ["Max", "Rex"])
            self.assertEqual(
                engine.recall("user.preference").value,
                ["dark interfaces", "concise answers"],
            )
            engine.close()

    def test_unique_memory_consolidates_case_and_whitespace_variants(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory) / "nova.db")

            engine.remember_unique("user.preference", "Dark interfaces")
            engine.remember_unique("user.preference", "  dark   interfaces ")

            self.assertEqual(
                engine.recall("user.preference").value,
                "Dark interfaces",
            )
            engine.close()

    def test_search_explains_scores_and_filters_weak_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory) / "nova.db")
            engine.remember(
                "project.current",
                "Nova voice assistant",
                category="project",
            )
            engine.remember(
                "work.employer",
                "Voice Coffee",
                category="work",
            )

            explanation = engine.explain_search("current voice project")

            self.assertEqual(
                explanation["matches"][0]["memory"]["key"],
                "project.current",
            )
            self.assertIn(
                "key terms: current, project",
                explanation["matches"][0]["reasons"],
            )
            self.assertEqual(
                engine.search("voice volume settings"),
                [],
            )
            engine.close()

    def test_exact_key_search_stays_deterministic_in_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory) / "nova.db")
            engine.remember("user.location", "Malmö", category="identity")

            explanation = engine.explain_search("user.location")

            self.assertEqual(len(explanation["matches"]), 1)
            self.assertEqual(explanation["matches"][0]["score"], 100)
            self.assertEqual(
                explanation["matches"][0]["reasons"],
                ["exact key match"],
            )
            engine.close()

    def test_maintenance_archives_low_confidence_and_restores_it(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory) / "nova.db")
            engine.remember(
                "inference.favorite_drink",
                "Coffee",
                confidence=0.25,
                source="inferred",
            )

            result = engine.maintain(0.5)

            self.assertEqual(result["archived"], ["inference.favorite_drink"])
            self.assertIsNone(engine.recall("inference.favorite_drink"))
            self.assertEqual(
                engine.archived_memories()[0]["key"],
                "inference.favorite_drink",
            )
            self.assertTrue(engine.restore_archived("inference.favorite_drink"))
            self.assertEqual(
                engine.recall("inference.favorite_drink").value,
                "Coffee",
            )
            self.assertEqual(engine.archived_memories(), [])
            engine.close()

    def test_forget_permanently_removes_an_archived_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory) / "nova.db")
            engine.remember("inference.snack", "Popcorn", confidence=0.1)
            engine.maintain()

            self.assertTrue(engine.forget_matching("inference.snack", "Popcorn"))
            self.assertEqual(engine.archived_memories(), [])
            self.assertFalse(engine.restore_archived("inference.snack"))
            engine.close()

    def test_natural_category_forget_removes_archived_memories(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory) / "nova.db")
            engine.remember("pet.dog", "Max", category="pet", confidence=0.1)
            engine.maintain()

            result = engine.process_text("Forget what you know about my pets")

            self.assertTrue(result["deleted"])
            self.assertEqual(engine.archived_memories(), [])
            engine.close()

    def test_relearning_an_archived_key_replaces_the_archived_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory) / "nova.db")
            engine.remember("inference.snack", "Popcorn", confidence=0.1)
            engine.maintain()

            engine.remember("inference.snack", "Fruit", confidence=1.0)

            self.assertEqual(engine.recall("inference.snack").value, "Fruit")
            self.assertEqual(engine.archived_memories(), [])
            engine.close()

    def test_maintenance_normalizes_existing_list_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make_engine(Path(directory) / "nova.db")
            engine.remember(
                "user.preference",
                ["Concise answers", "concise  answers", "Dark UI"],
                category="preference",
            )

            result = engine.maintain()

            self.assertEqual(result["normalized"], ["user.preference"])
            self.assertEqual(
                engine.recall("user.preference").value,
                ["Concise answers", "Dark UI"],
            )
            engine.close()


if __name__ == "__main__":
    unittest.main()
