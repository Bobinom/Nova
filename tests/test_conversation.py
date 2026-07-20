import logging
import tempfile
import unittest
from pathlib import Path

from nova.conversation.manager import ConversationManager
from nova.conversation.repository import ConversationRepository
from nova.core.events import EventBus
from nova.memory.engine import MemoryEngine
from nova.memory.repository import MemoryRepository


class ConversationTests(unittest.TestCase):
    def make_manager(self, database: Path):
        events = EventBus(logging.getLogger("test.conversation"))
        memory = MemoryEngine(
            repository=MemoryRepository(database),
            events=events,
            logger=logging.getLogger("test.memory"),
        )
        memory.initialize()

        manager = ConversationManager(
            repository=ConversationRepository(database),
            memory=memory,
            events=events,
            logger=logging.getLogger("test.manager"),
        )
        manager.initialize()
        return manager, memory

    def test_color_paraphrase(self):
        with tempfile.TemporaryDirectory() as directory:
            manager, memory = self.make_manager(Path(directory) / "nova.db")
            manager.handle("My favorite color is Amber")
            result = manager.handle("What color do I like?")

            self.assertEqual(result["response"], "Your favorite color is Amber.")
            manager.close()
            memory.close()

    def test_rich_color_statement(self):
        with tempfile.TemporaryDirectory() as directory:
            manager, memory = self.make_manager(Path(directory) / "nova.db")
            manager.handle(
                "My favorite color is Amber but I do like the color purple as well"
            )
            result = manager.handle("What colors do I like?")

            self.assertIn("Amber", result["response"])
            self.assertIn("Purple", result["response"])
            self.assertEqual(
                memory.recall("user.favorite_color").value,
                "Amber",
            )
            manager.close()
            memory.close()

    def test_follow_up_what_is_it(self):
        with tempfile.TemporaryDirectory() as directory:
            manager, memory = self.make_manager(Path(directory) / "nova.db")
            manager.handle("My name is Eric")
            manager.handle("Actually call me Rick")
            result = manager.handle("What is it?")

            self.assertEqual(result["response"], "Your name is Rick.")
            manager.close()
            memory.close()

    def test_history_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "nova.db"
            manager, memory = self.make_manager(database)
            manager.handle("My name is Eric")
            manager.close()
            memory.close()

            manager2, memory2 = self.make_manager(database)
            history = manager2.history()
            self.assertEqual(history[0]["role"], "user")
            self.assertEqual(history[1]["role"], "assistant")
            manager2.close()
            memory2.close()


if __name__ == "__main__":
    unittest.main()
