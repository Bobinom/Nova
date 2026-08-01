import logging
import tempfile
import unittest
from pathlib import Path

from nova.conversation.manager import ConversationManager
from nova.conversation.repository import ConversationRepository
from nova.core.events import EventBus
from nova.memory.engine import MemoryEngine
from nova.memory.repository import MemoryRepository


class RecordingLLM:
    def __init__(self):
        self.calls = []

    def generate(self, system_prompt, history, prompt):
        self.calls.append((system_prompt, history, prompt))
        return "LLM response"


class ConversationTests(unittest.TestCase):
    def make_manager(self, database: Path, llm=None):
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
            llm=llm,
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

    def test_llm_receives_previous_turns_without_current_user_turn(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = RecordingLLM()
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )

            manager.handle("First general question")
            manager.handle("Follow-up general question")

            _, history, prompt = llm.calls[-1]
            self.assertEqual(
                history,
                [
                    {"role": "user", "content": "First general question"},
                    {"role": "assistant", "content": "LLM response"},
                ],
            )
            self.assertEqual(prompt, "Follow-up general question")
            self.assertNotIn(
                {"role": "user", "content": "Follow-up general question"},
                history,
            )
            manager.close()
            memory.close()

    def test_llm_receives_only_relevant_memory_context(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = RecordingLLM()
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )
            memory.remember(
                "relationship.girlfriend",
                "Dunja",
                category="relationship",
            )
            memory.remember("user.location", "Malmö", category="identity")

            manager.handle("What is my partner's name?")

            system_prompt, _, _ = llm.calls[-1]
            self.assertIn("relationship.girlfriend: Dunja", system_prompt)
            self.assertNotIn("user.location: Malmö", system_prompt)
            manager.close()
            memory.close()

    def test_conversation_learns_semantic_fact_before_llm(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = RecordingLLM()
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )

            result = manager.handle("My girlfriend's name is Dunja")

            self.assertEqual(result["intent"], "remember")
            self.assertEqual(
                result["response"],
                "I'll remember that your girlfriend is Dunja.",
            )
            self.assertEqual(
                memory.recall("relationship.girlfriend").value,
                "Dunja",
            )
            self.assertEqual(llm.calls, [])
            manager.close()
            memory.close()

    def test_correction_updates_existing_semantic_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            manager, memory = self.make_manager(Path(directory) / "nova.db")
            manager.handle("I work at Espresso House")

            result = manager.handle("Actually, I work at IKEA now")

            self.assertEqual(result["intent"], "remember")
            self.assertEqual(memory.recall("work.employer").value, "IKEA")
            self.assertEqual(len(memory.list_memories("work")), 1)
            manager.close()
            memory.close()

    def test_no_longer_forgets_only_matching_relationship(self):
        with tempfile.TemporaryDirectory() as directory:
            manager, memory = self.make_manager(Path(directory) / "nova.db")
            manager.handle("My girlfriend is Dunja")

            mismatch = manager.handle("Anna is no longer my girlfriend")
            self.assertEqual(mismatch["response"], "I couldn't find that memory.")
            self.assertIsNotNone(memory.recall("relationship.girlfriend"))

            result = manager.handle("Dunja is no longer my girlfriend")
            self.assertEqual(result["response"], "Forgotten.")
            self.assertIsNone(memory.recall("relationship.girlfriend"))
            manager.close()
            memory.close()

    def test_explicit_category_forget_removes_all_pets(self):
        with tempfile.TemporaryDirectory() as directory:
            manager, memory = self.make_manager(Path(directory) / "nova.db")
            manager.handle("My dog is Max")
            manager.handle("My cat is Luna")

            result = manager.handle("Forget what you know about my pets")

            self.assertEqual(result["response"], "Forgotten.")
            self.assertEqual(memory.list_memories("pet"), [])
            manager.close()
            memory.close()

    def test_searchable_recall_is_answered_without_llm(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = RecordingLLM()
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )
            manager.handle("I'm working on Nova")

            result = manager.handle("What do you remember about my projects?")

            self.assertEqual(result["intent"], "search_memory")
            self.assertIn("project.current: Nova", result["response"])
            self.assertEqual(llm.calls, [])
            manager.close()
            memory.close()


if __name__ == "__main__":
    unittest.main()
