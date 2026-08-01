import logging
import sqlite3
import tempfile
import unittest
from pathlib import Path

from nova.conversation.manager import ConversationManager
from nova.conversation.repository import ConversationRepository
from nova.core.events import EventBus
from nova.core.settings import SettingsManager
from nova.memory.engine import MemoryEngine
from nova.memory.repository import MemoryRepository


class RecordingLLM:
    def __init__(self):
        self.calls = []

    def generate(self, system_prompt, history, prompt):
        self.calls.append((system_prompt, history, prompt))
        return "LLM response"


class SequencedLLM(RecordingLLM):
    def __init__(self, responses):
        super().__init__()
        self.responses = iter(responses)

    def generate(self, system_prompt, history, prompt):
        self.calls.append((system_prompt, history, prompt))
        return next(self.responses)


class ConversationTests(unittest.TestCase):
    def make_manager(self, database: Path, llm=None, settings=None):
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
            settings=settings,
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

    def test_episode_auto_save_can_be_disabled_and_manually_overridden(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = RecordingLLM()
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )
            manager.set_episode_auto_save(False)

            manager.handle("Plan a quiet workstation for music production")
            self.assertEqual(manager.episodes(), [])

            result = manager.handle("Remember this conversation")
            self.assertEqual(result["response"], "Conversation remembered.")
            self.assertEqual(len(manager.episodes()), 1)
            manager.close()
            memory.close()

    def test_dont_save_and_forget_last_remove_latest_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = RecordingLLM()
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )
            manager.handle("Plan a quiet workstation for music production")

            result = manager.handle("Don't save this conversation")
            self.assertEqual(
                result["response"],
                "Okay, I won't keep that conversation.",
            )
            self.assertEqual(manager.episodes(), [])

            manager.handle("Compare microphones for recording vocals")
            result = manager.handle("Forget our last conversation")
            self.assertEqual(result["response"], "Last conversation forgotten.")
            self.assertEqual(manager.episodes(), [])
            manager.close()
            memory.close()

    def test_dont_save_removes_hidden_duplicate_group(self):
        with tempfile.TemporaryDirectory() as directory:
            manager, memory = self.make_manager(Path(directory) / "nova.db")
            prompt = "Plan a Ryzen PC upgrade"
            manager.repository.add_episode(
                topic="PC upgrade",
                summary="Failed attempt",
                user_text=prompt,
                assistant_text="I couldn't connect to Ollama.",
            )
            manager.repository.add_episode(
                topic="PC upgrade Ryzen",
                summary="Successful attempt",
                user_text=prompt,
                assistant_text=(
                    "Compare the Ryzen processor, graphics card, motherboard, "
                    "memory, storage, case, cooling, and power supply before "
                    "choosing compatible PC upgrade parts."
                ),
            )

            result = manager.handle("Don't save this conversation")

            self.assertEqual(
                result["response"],
                "Okay, I won't keep that conversation.",
            )
            self.assertEqual(manager.repository.list_episodes(), [])
            manager.close()
            memory.close()

    def test_protected_semantic_memory_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            manager, memory = self.make_manager(Path(directory) / "nova.db")
            manager.set_semantic_confirmation(True)

            pending = manager.handle("My dog is Max")
            self.assertEqual(pending["intent"], "confirm_memory")
            self.assertIsNone(memory.recall("pet.dog"))

            confirmed = manager.handle("yes")
            self.assertEqual(confirmed["intent"], "remember_unique")
            self.assertEqual(memory.recall("pet.dog").value, "Max")

            manager.handle("I work at IKEA")
            cancelled = manager.handle("no")
            self.assertEqual(cancelled["intent"], "memory_confirmation_cancelled")
            self.assertIsNone(memory.recall("work.employer"))
            manager.close()
            memory.close()

    def test_privacy_settings_persist_between_managers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings_path = root / "settings.json"
            settings = SettingsManager(settings_path)
            settings.load()
            manager, memory = self.make_manager(
                root / "nova.db",
                settings=settings,
            )
            manager.set_episode_auto_save(False)
            manager.set_semantic_confirmation(True)
            manager.close()
            memory.close()

            reloaded = SettingsManager(settings_path)
            reloaded.load()
            manager2, memory2 = self.make_manager(
                root / "nova.db",
                settings=reloaded,
            )
            status = manager2.privacy_status()
            self.assertFalse(status["episode_auto_save"])
            self.assertTrue(status["confirm_semantic_memory"])
            manager2.close()
            memory2.close()

    def test_episode_count_retention_prunes_oldest_records(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = RecordingLLM()
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )
            manager.set_episode_retention(max_episodes=2)

            manager.handle("Plan a quiet workstation for music production")
            manager.handle("Compare microphones for recording vocals")
            manager.handle("Choose acoustic panels for the studio walls")

            episodes = manager.episodes()
            self.assertEqual(len(episodes), 2)
            self.assertNotIn("quiet workstation", str(episodes))
            manager.close()
            memory.close()

    def test_episode_age_retention_prunes_expired_records(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "nova.db"
            llm = RecordingLLM()
            manager, memory = self.make_manager(database, llm=llm)
            manager.handle("Plan a quiet workstation for music production")

            connection = sqlite3.connect(database)
            connection.execute(
                """
                UPDATE conversation_episodes
                SET created_at = datetime('now', '-10 days')
                """
            )
            connection.commit()
            connection.close()

            deleted = manager.set_episode_retention(retention_days=7)

            self.assertEqual(deleted, 1)
            self.assertEqual(manager.episodes(), [])
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

    def test_general_conversation_creates_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = RecordingLLM()
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )

            manager.handle("Let's plan a Ryzen PC upgrade")

            episodes = manager.episodes()
            self.assertEqual(len(episodes), 1)
            self.assertIn("Ryzen PC upgrade", episodes[0]["user_text"])
            self.assertEqual(episodes[0]["assistant_text"], "LLM response")
            manager.close()
            memory.close()

    def test_trivial_greeting_does_not_create_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = RecordingLLM()
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )

            manager.handle("Hello")

            self.assertEqual(manager.episodes(), [])
            manager.close()
            memory.close()

    def test_sensitive_request_does_not_create_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = RecordingLLM()
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )

            manager.handle("My password is swordfish, please remember it")

            self.assertEqual(manager.episodes(), [])
            manager.close()
            memory.close()

    def test_episode_recall_is_deterministic_and_skips_llm(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = RecordingLLM()
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )
            manager.handle("Let's plan a Ryzen PC upgrade")
            calls_before_recall = len(llm.calls)

            result = manager.handle(
                "What did we discuss about upgrading my PC?"
            )

            self.assertEqual(result["intent"], "episode_recall")
            self.assertIn("Ryzen PC upgrade", result["response"])
            self.assertEqual(len(llm.calls), calls_before_recall)
            manager.close()
            memory.close()

    def test_episode_recall_supports_today_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = RecordingLLM()
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )
            manager.handle("Let's plan the Nova plugin architecture")

            result = manager.handle("What did we discuss today?")

            self.assertIn("Nova plugin architecture", result["response"])
            manager.close()
            memory.close()

    def test_episode_persists_and_is_injected_when_relevant(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "nova.db"
            first_llm = RecordingLLM()
            manager, memory = self.make_manager(database, llm=first_llm)
            manager.handle("Let's plan a Ryzen PC upgrade")
            manager.close()
            memory.close()

            second_llm = RecordingLLM()
            manager2, memory2 = self.make_manager(database, llm=second_llm)
            manager2.handle("Which GPU suits the PC upgrade?")

            system_prompt, _, _ = second_llm.calls[-1]
            self.assertIn("Relevant past conversations", system_prompt)
            self.assertIn("Ryzen PC upgrade", system_prompt)
            manager2.close()
            memory2.close()

    def test_continue_episode_uses_llm_with_past_context(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = RecordingLLM()
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )
            manager.handle("Let's plan a Ryzen PC upgrade")

            result = manager.handle("Continue our PC upgrade discussion")

            self.assertEqual(result["intent"], "episode_continue")
            system_prompt, _, _ = llm.calls[-1]
            self.assertIn("Relevant past conversations", system_prompt)
            self.assertIn("Ryzen PC upgrade", system_prompt)
            manager.close()
            memory.close()

    def test_episode_inspect_delete_and_clear(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = RecordingLLM()
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )
            manager.handle("Plan the Nova memory architecture")
            manager.handle("Compare options for a gaming monitor")
            episodes = manager.episodes()

            self.assertTrue(manager.delete_episode(episodes[0]["id"]))
            self.assertEqual(len(manager.episodes()), 1)
            manager.clear_episodes()
            self.assertEqual(manager.episodes(), [])
            manager.close()
            memory.close()

    def test_ollama_failure_is_not_saved_as_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = SequencedLLM([
                "I couldn't connect to Ollama. "
                "Make sure Ollama is running on this computer.",
            ])
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )

            manager.handle(
                "Let's plan a PC upgrade using a Ryzen processor"
            )

            self.assertEqual(manager.episodes(), [])
            manager.close()
            memory.close()

    def test_duplicate_episode_is_updated_with_newest_success(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = SequencedLLM(["First answer", "Improved answer"])
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )
            prompt = (
                "Let's plan a PC upgrade using a Ryzen processor "
                "and an RTX graphics card."
            )

            manager.handle(prompt)
            original_id = manager.episodes()[0]["id"]
            manager.handle(prompt)

            episodes = manager.episodes()
            self.assertEqual(len(episodes), 1)
            self.assertEqual(episodes[0]["id"], original_id)
            self.assertEqual(episodes[0]["assistant_text"], "Improved answer")
            self.assertEqual(episodes[0]["topic"], "PC upgrade Ryzen RTX")
            manager.close()
            memory.close()

    def test_existing_failed_and_duplicate_episodes_are_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = RecordingLLM()
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )
            prompt = "Let's plan a Ryzen PC upgrade"
            manager.repository.add_episode(
                topic="pc upgrade",
                summary="Failed attempt",
                user_text=prompt,
                assistant_text="I couldn't connect to Ollama.",
            )
            manager.repository.add_episode(
                topic="pc upgrade",
                summary="Older successful attempt",
                user_text=prompt,
                assistant_text="Older answer",
            )
            manager.repository.add_episode(
                topic="pc upgrade",
                summary="Newest successful attempt",
                user_text=prompt,
                assistant_text="Newest answer",
            )

            episodes = manager.episodes()
            result = manager.handle(
                "What did we discuss about upgrading my PC?"
            )

            self.assertEqual(len(episodes), 1)
            self.assertEqual(episodes[0]["assistant_text"], "Newest answer")
            self.assertEqual(episodes[0]["topic"], "Ryzen PC upgrade")
            self.assertEqual(result["response"].count("\n- "), 1)
            self.assertNotIn("Failed attempt", result["response"])
            self.assertNotIn("Older successful attempt", result["response"])
            manager.close()
            memory.close()

    def test_paraphrased_pc_discussions_merge_by_response_similarity(self):
        with tempfile.TemporaryDirectory() as directory:
            first_response = (
                "Let's plan a PC upgrade using a Ryzen processor and an RTX "
                "graphics card. We should start by choosing a budget, then "
                "compare the Ryzen 5 and Ryzen 7 options before selecting a "
                "compatible motherboard, power supply, memory, and graphics card."
            )
            second_response = (
                "Let's plan a PC upgrade using a Ryzen processor and an RTX "
                "graphics card. We previously discussed general guidelines, "
                "so start by choosing a budget, compare Ryzen 5 and Ryzen 7, "
                "then select a compatible motherboard, power supply, memory, "
                "and graphics card."
            )
            llm = SequencedLLM([first_response, second_response])
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )
            detailed_prompt = (
                "Let's plan a PC upgrade using a Ryzen processor and an RTX "
                "graphics card."
            )

            manager.handle(detailed_prompt)
            original_id = manager.episodes()[0]["id"]
            manager.handle("Lets buid a pc")

            episodes = manager.episodes()
            self.assertEqual(len(episodes), 1)
            self.assertEqual(episodes[0]["id"], original_id)
            self.assertEqual(episodes[0]["assistant_text"], second_response)
            self.assertEqual(episodes[0]["topic"], "PC upgrade Ryzen RTX")
            manager.close()
            memory.close()

    def test_short_generic_responses_do_not_merge_unrelated_topics(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = RecordingLLM()
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )

            manager.handle("Plan the Nova memory architecture")
            manager.handle("Compare options for a gaming monitor")

            self.assertEqual(len(manager.episodes()), 2)
            manager.close()
            memory.close()

    def test_live_pc_episode_paraphrases_collapse(self):
        with tempfile.TemporaryDirectory() as directory:
            manager, memory = self.make_manager(Path(directory) / "nova.db")
            detailed_prompt = (
                "Let's plan a PC upgrade using a Ryzen processor and an RTX "
                "graphics card."
            )
            first_response = (
                "Since we're starting from scratch, let's consider some general "
                "guidelines. For a Ryzen processor, how much budget are you "
                "willing to spend? A higher-end Ryzen 9 or 7 series might be "
                "out of your reach, but there are more affordable options like "
                "the Ryzen 5 series. Which one do you think suits your needs? "
                "Also, what is the approximate power consumption of the RTX "
                "graphics card you're interested in?"
            )
            second_response = (
                "Let's plan a PC upgrade using a Ryzen processor and an RTX "
                "graphics card. We previously discussed some general guidelines, "
                "but since we're starting from scratch, let's begin again. For a "
                "Ryzen processor, how much budget are you willing to spend? A "
                "higher-end Ryzen 9 or 7 series might be out of your reach, but "
                "there are more affordable options like the Ryzen 5 series."
            )
            manager.repository.add_episode(
                topic="an card graphic graphics",
                summary="Older PC discussion",
                user_text=detailed_prompt,
                assistant_text=first_response,
            )
            manager.repository.add_episode(
                topic="Lets buid pc",
                summary="Newer PC discussion",
                user_text="Lets buid a pc",
                assistant_text=second_response,
            )

            episodes = manager.episodes()

            self.assertEqual(len(episodes), 1)
            self.assertEqual(episodes[0]["assistant_text"], second_response)
            self.assertEqual(episodes[0]["topic"], "PC upgrade Ryzen RTX")
            manager.close()
            memory.close()

    def test_meaningful_turns_consolidate_into_one_session(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = RecordingLLM()
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )

            manager.handle("Plan a Ryzen workstation for software development")
            manager.handle("Compare microphones for recording vocals")

            sessions = manager.sessions()
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0]["episode_count"], 2)
            self.assertIn("Ryzen workstation software development", sessions[0]["topic"])
            self.assertIn("microphones recording vocals", sessions[0]["topic"])
            self.assertIn("Plan a Ryzen workstation", sessions[0]["summary"])
            self.assertIn("Compare microphones", sessions[0]["summary"])
            manager.close()
            memory.close()

    def test_trivial_and_semantic_turns_do_not_create_session(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = RecordingLLM()
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )

            manager.handle("Hello")
            manager.handle("My dog is Max")

            self.assertEqual(manager.sessions(), [])
            manager.close()
            memory.close()

    def test_current_session_recall_skips_llm(self):
        with tempfile.TemporaryDirectory() as directory:
            llm = RecordingLLM()
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=llm,
            )
            manager.handle("Plan a Ryzen workstation for software development")
            calls_before = len(llm.calls)

            result = manager.handle("What did we discuss this session?")

            self.assertEqual(result["intent"], "session_recall")
            self.assertIn("Ryzen workstation", result["response"])
            self.assertEqual(len(llm.calls), calls_before)
            manager.close()
            memory.close()

    def test_closed_session_persists_and_new_run_starts_new_session(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "nova.db"
            first_llm = RecordingLLM()
            manager, memory = self.make_manager(database, llm=first_llm)
            manager.handle("Plan a Ryzen workstation for software development")
            first_id = manager.sessions()[0]["id"]
            manager.close()
            memory.close()

            second_llm = RecordingLLM()
            manager2, memory2 = self.make_manager(database, llm=second_llm)
            self.assertIsNotNone(manager2.sessions()[0]["ended_at"])
            manager2.handle("Compare microphones for recording vocals")

            sessions = manager2.sessions()
            self.assertEqual(len(sessions), 2)
            self.assertNotEqual(sessions[0]["id"], first_id)
            manager2.close()
            memory2.close()

    def test_relevant_prior_session_is_injected_into_llm(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "nova.db"
            manager, memory = self.make_manager(database, llm=RecordingLLM())
            manager.handle("Plan a Ryzen workstation for software development")
            manager.close()
            memory.close()

            llm = RecordingLLM()
            manager2, memory2 = self.make_manager(database, llm=llm)
            manager2.handle("Which Ryzen CPU suits that workstation?")

            system_prompt, _, _ = llm.calls[-1]
            self.assertIn("Relevant conversation sessions", system_prompt)
            self.assertIn("Ryzen workstation", system_prompt)
            manager2.close()
            memory2.close()

    def test_session_inspect_delete_and_clear(self):
        with tempfile.TemporaryDirectory() as directory:
            manager, memory = self.make_manager(
                Path(directory) / "nova.db",
                llm=RecordingLLM(),
            )
            manager.handle("Plan a Ryzen workstation for software development")
            session_id = manager.sessions()[0]["id"]

            self.assertTrue(manager.delete_session(session_id))
            self.assertEqual(manager.sessions(), [])
            manager.handle("Compare microphones for recording vocals")
            manager.clear_sessions()
            self.assertEqual(manager.sessions(), [])
            manager.close()
            memory.close()


if __name__ == "__main__":
    unittest.main()
