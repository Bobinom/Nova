import logging
import tempfile
import unittest
from pathlib import Path

from nova.conversation.manager import ConversationManager
from nova.conversation.repository import ConversationRepository
from nova.core.events import EventBus
from nova.memory.engine import MemoryEngine
from nova.memory.repository import MemoryRepository


class ConversationPolishTests(unittest.TestCase):
    def make_manager(self, database: Path):
        events = EventBus(logging.getLogger("test.polish"))
        memory = MemoryEngine(
            repository=MemoryRepository(database),
            events=events,
            logger=logging.getLogger("test.polish.memory"),
        )
        memory.initialize()
        manager = ConversationManager(
            repository=ConversationRepository(database),
            memory=memory,
            events=events,
            logger=logging.getLogger("test.polish.manager"),
        )
        manager.initialize()
        return manager, memory

    def test_incomplete_name_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            manager, memory = self.make_manager(Path(directory) / "nova.db")
            result = manager.handle("My name")
            self.assertEqual(
                result["response"],
                "What would you like me to know about your name?",
            )
            manager.close()
            memory.close()

    def test_color_normalization(self):
        with tempfile.TemporaryDirectory() as directory:
            manager, memory = self.make_manager(Path(directory) / "nova.db")
            manager.handle(
                "My favorite color is Amber but I do like the color purple as well"
            )
            self.assertEqual(memory.recall("user.favorite_color").value, "Amber")
            self.assertEqual(memory.recall("user.liked_colors").value, ["Purple"])
            manager.close()
            memory.close()

    def test_color_response_capitalization(self):
        with tempfile.TemporaryDirectory() as directory:
            manager, memory = self.make_manager(Path(directory) / "nova.db")
            manager.handle(
                "My favorite color is Amber but I do like the color purple as well"
            )
            result = manager.handle("What color do I like?")
            self.assertEqual(
                result["response"],
                "Your favorite color is Amber. You also like Purple.",
            )
            manager.close()
            memory.close()


if __name__ == "__main__":
    unittest.main()
