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


if __name__ == "__main__":
    unittest.main()
