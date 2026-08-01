from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

from nova.conversation.intent import Intent, classify
from nova.conversation.models import ConversationEpisode
from nova.conversation.repository import ConversationRepository
from nova.llm.prompts import NOVA_SYSTEM_PROMPT
from nova.llm.service import LLMService
from nova.memory.engine import MemoryEngine


class ConversationManager:
    _EPISODE_STOP_WORDS = {
        "a", "about", "and", "are", "continue", "did", "discuss",
        "discussion", "do", "for", "i", "in", "is", "it", "last",
        "me", "my", "of", "on", "our", "resume", "talk", "the",
        "this", "to", "today", "we", "week", "what", "yesterday",
        "you",
    }

    _TOPIC_STOP_WORDS = _EPISODE_STOP_WORDS | {
        "an", "card", "graphic", "graphics", "interested", "let", "plan",
        "lets", "processor", "s", "using", "want", "would",
    }

    _OLLAMA_FAILURE_PREFIXES = (
        "i couldn't connect to ollama",
        "ollama error:",
        "ollama request failed:",
        "ollama returned an empty response",
        "ollama returned an invalid response",
        "ollama took too long to respond",
    )

    _TRIVIAL_EPISODE_TEXT = {
        "good morning", "good night", "hello", "hey", "hi", "thanks",
        "thank you",
    }

    _SENSITIVE_EPISODE_TERMS = {
        "api key", "bank account", "credit card", "password", "passcode",
        "private key", "secret key", "security number", "social security",
    }

    def __init__(
        self,
        *,
        repository: ConversationRepository,
        memory: MemoryEngine,
        events: Any,
        logger: Any,
        llm: LLMService | None = None,
    ) -> None:
        self.repository = repository
        self.memory = memory
        self.events = events
        self.logger = logger
        self.llm = llm
        self.last_topic: str | None = None

    def initialize(self) -> None:
        self.repository.initialize()

    def close(self) -> None:
        self.repository.close()

    def handle(self, text: str) -> dict[str, Any]:
        text = text.strip()

        if not text:
            return {
                "handled": True,
                "response": "Please say something.",
            }

        self.repository.add("user", text)

        intent = classify(text, self.last_topic)
        result = self._execute(intent, text)

        record_episode = bool(result.pop("_record_episode", False))

        response = str(result["response"])
        self.repository.add("assistant", response)
        if record_episode:
            self._record_episode(text, response)
        self.events.emit("assistant.response", result)

        return result

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        return [
            turn.as_dict()
            for turn in self.repository.recent(limit)
        ]

    def clear_history(self) -> None:
        self.repository.clear()
        self.last_topic = None

    def episodes(self, limit: int = 20) -> list[dict[str, Any]]:
        return [
            episode.as_dict()
            for episode in self._quality_episodes(
                self.repository.list_episodes(200),
            )[:limit]
        ]

    def delete_episode(self, episode_id: int) -> bool:
        return self.repository.delete_episode(episode_id)

    def clear_episodes(self) -> None:
        self.repository.clear_episodes()

    def _execute(
        self,
        intent: Intent,
        text: str,
    ) -> dict[str, Any]:
        if intent.name == "incomplete":
            prompts = {
                "name": "What would you like me to know about your name?",
                "favorite_color": "What is your favorite color?",
                "location": "Where do you live?",
                "birthday": "What is your birthday?",
            }

            return {
                "handled": True,
                "intent": intent.name,
                "response": prompts.get(
                    str(intent.value),
                    "Could you finish that thought?",
                ),
            }

        if intent.name == "remember":
            record = self.memory.remember(
                intent.memory_key,
                intent.value,
                category=intent.category or "general",
            )

            self.last_topic = intent.memory_key

            return {
                "handled": True,
                "intent": intent.name,
                "response": self._remember_response(
                    record.key,
                    record.value,
                ),
            }

        if intent.name == "remember_unique":
            record = self.memory.remember_unique(
                intent.memory_key,
                intent.value,
                category=intent.category or "general",
            )
            self.last_topic = intent.memory_key
            return {
                "handled": True,
                "intent": intent.name,
                "response": self._remember_response(record.key, intent.value),
            }

        if intent.name == "forget":
            deleted = self._forget_memory(intent)
            return {
                "handled": True,
                "intent": intent.name,
                "response": (
                    "Forgotten."
                    if deleted
                    else "I couldn't find that memory."
                ),
            }

        if intent.name == "search_memory":
            records = self.memory.search(str(intent.value))
            return {
                "handled": True,
                "intent": intent.name,
                "response": self.memory.search_response(records),
            }

        if intent.name == "episode_recall":
            episodes = self._search_episodes(str(intent.value))
            return {
                "handled": True,
                "intent": intent.name,
                "response": self._episode_recall_response(episodes),
            }

        if intent.name == "episode_continue":
            episodes = self._search_episodes(str(intent.value))
            if not episodes:
                return {
                    "handled": True,
                    "intent": intent.name,
                    "response": "I couldn't find a related past discussion.",
                }
            if self.llm is None:
                return {
                    "handled": True,
                    "intent": intent.name,
                    "response": self._episode_recall_response(episodes),
                }
            return {
                "handled": True,
                "intent": intent.name,
                "response": self._generate_llm_response(
                    text,
                    episode_context=self._episode_context(episodes),
                ),
                "_record_episode": True,
            }

        if intent.name == "remember_color_bundle":
            values = list(intent.value or [])
            favorite = values[0]
            liked = values[1:]

            self.memory.remember(
                "user.favorite_color",
                favorite,
                category="preference",
            )

            if liked:
                self.memory.remember(
                    "user.liked_colors",
                    liked,
                    category="preference",
                )

            self.last_topic = "user.color_preferences"

            extra = (
                f" You also like {', '.join(liked)}."
                if liked
                else ""
            )

            return {
                "handled": True,
                "intent": intent.name,
                "response": (
                    f"I'll remember that your favorite color is {favorite}.{extra}"
                ),
            }

        if intent.name == "append_list":
            existing = self.memory.recall(intent.memory_key)

            values = (
                list(existing.value)
                if existing and isinstance(existing.value, list)
                else []
            )

            if intent.value not in values:
                values.append(intent.value)

            self.memory.remember(
                intent.memory_key,
                values,
                category=intent.category or "preference",
            )

            self.last_topic = "user.color_preferences"

            return {
                "handled": True,
                "intent": intent.name,
                "response": (
                    f"I'll remember that you also like {intent.value}."
                ),
            }

        if intent.name == "recall":
            self.last_topic = intent.memory_key

            return {
                "handled": True,
                "intent": intent.name,
                "response": self._recall_response(
                    intent.memory_key,
                ),
            }

        if self.llm is not None:
            return {
                "handled": True,
                "intent": "general",
                "response": self._generate_llm_response(text),
                "_record_episode": True,
            }

        return {
            "handled": False,
            "intent": "general",
            "response": (
                "I understand this is a general request, "
                "but no language model is configured yet."
            ),
        }

    def _forget_memory(self, intent: Intent) -> bool:
        if intent.category:
            records = self.memory.list_memories(intent.category)
            for record in records:
                self.memory.forget(record.key)
            return bool(records)

        record = self.memory.recall(intent.memory_key)
        if record is None:
            return False
        if intent.value is not None and not self.memory.matches_value(
            record.value,
            str(intent.value),
        ):
            return False
        return self.memory.forget(intent.memory_key)

    def _memory_context(self, query: str) -> str:
        memories = self.memory.search(query)

        if not memories:
            return ""

        lines = [
            f"- {record.key}: {record.value}"
            for record in memories
        ]

        return (
            "\n\nKnown user memories:\n"
            + "\n".join(lines)
            + "\nUse these memories only when relevant."
        )

    def _generate_llm_response(
        self,
        text: str,
        *,
        episode_context: str | None = None,
    ) -> str:
        turns = self.repository.recent(11)
        if turns and turns[-1].role == "user" and turns[-1].text == text:
            turns = turns[:-1]
        history = [
            {"role": turn.role, "content": turn.text}
            for turn in turns[-10:]
        ]
        context = episode_context
        if context is None:
            context = self._episode_context(self._search_episodes(text))
        return self.llm.generate(
            system_prompt=(
                NOVA_SYSTEM_PROMPT
                + self._memory_context(text)
                + context
            ),
            history=history,
            prompt=text,
        )

    def _record_episode(self, user_text: str, assistant_text: str) -> None:
        normalized = re.sub(r"[^\w\s]", "", user_text.lower()).strip()
        if normalized in self._TRIVIAL_EPISODE_TEXT:
            return
        if any(term in normalized for term in self._SENSITIVE_EPISODE_TERMS):
            return
        if self._is_failed_response(assistant_text):
            return
        terms = self._episode_terms(user_text)
        if len(normalized.split()) < 3 or not terms:
            return
        topic = self._episode_topic(user_text)
        user_summary = self._truncate(user_text, 220)
        assistant_summary = self._truncate(assistant_text, 280)
        episode_data = {
            "topic": topic,
            "summary": f"User: {user_summary} Nova: {assistant_summary}",
            "user_text": user_text,
            "assistant_text": assistant_text,
        }
        duplicate = self._find_duplicate_episode(user_text, assistant_text)
        if duplicate is not None:
            episode_data["topic"] = self._better_topic(
                duplicate.topic,
                topic,
            )
            self.repository.update_episode(duplicate.id, **episode_data)
        else:
            self.repository.add_episode(**episode_data)

    def _search_episodes(
        self,
        query: str,
        limit: int = 5,
    ) -> list[ConversationEpisode]:
        terms = self._episode_terms(query)
        ranked: list[tuple[int, int, ConversationEpisode]] = []
        for episode in self._quality_episodes(
            self.repository.list_episodes(200),
        ):
            if not self._episode_time_matches(query, episode.created_at):
                continue
            topic_terms = self._episode_terms(episode.topic)
            user_terms = self._episode_terms(episode.user_text)
            summary_terms = self._episode_terms(episode.summary)
            score = (
                5 * len(terms & topic_terms)
                + 3 * len(terms & user_terms)
                + 2 * len(terms & summary_terms)
            )
            if score or not terms:
                ranked.append((score, episode.id, episode))
        ranked.sort(key=lambda item: (-item[0], -item[1]))
        return [episode for _, _, episode in ranked[:limit]]

    def _find_duplicate_episode(
        self,
        user_text: str,
        assistant_text: str,
    ) -> ConversationEpisode | None:
        for episode in self._quality_episodes(
            self.repository.list_episodes(50),
        ):
            if self._episodes_are_duplicates(
                user_text,
                assistant_text,
                episode.user_text,
                episode.assistant_text,
            ):
                return episode
        return None

    def _quality_episodes(
        self,
        episodes: list[ConversationEpisode],
    ) -> list[ConversationEpisode]:
        quality: list[ConversationEpisode] = []
        for episode in episodes:
            if self._is_failed_response(episode.assistant_text):
                continue
            cleaned = replace(
                episode,
                topic=self._better_topic(
                    episode.topic,
                    self._episode_topic(episode.user_text),
                ),
            )
            duplicate_index = next(
                (
                    index
                    for index, kept in enumerate(quality)
                    if self._episodes_are_duplicates(
                        cleaned.user_text,
                        cleaned.assistant_text,
                        kept.user_text,
                        kept.assistant_text,
                    )
                ),
                None,
            )
            if duplicate_index is not None:
                kept = quality[duplicate_index]
                quality[duplicate_index] = replace(
                    kept,
                    topic=self._better_topic(kept.topic, cleaned.topic),
                )
                continue
            quality.append(cleaned)
        return quality

    @classmethod
    def _episode_topic(cls, text: str) -> str:
        topic_terms: list[str] = []
        seen: set[str] = set()
        for term in re.findall(r"[\w]+", text):
            normalized = term.lower()
            if normalized in cls._TOPIC_STOP_WORDS or normalized in seen:
                continue
            seen.add(normalized)
            topic_terms.append(term)
        return " ".join(topic_terms[:5]) or "conversation"

    @classmethod
    def _episode_similarity(cls, first: str, second: str) -> float:
        first_terms = cls._episode_terms(first)
        second_terms = cls._episode_terms(second)
        if not first_terms or not second_terms:
            return 0.0
        return len(first_terms & second_terms) / len(first_terms | second_terms)

    @classmethod
    def _episodes_are_duplicates(
        cls,
        first_user: str,
        first_assistant: str,
        second_user: str,
        second_assistant: str,
    ) -> bool:
        if cls._episode_similarity(first_user, second_user) >= 0.85:
            return True
        first_response_terms = cls._episode_terms(first_assistant)
        second_response_terms = cls._episode_terms(second_assistant)
        if len(first_response_terms) < 12 or len(second_response_terms) < 12:
            return False
        return cls._episode_similarity(first_assistant, second_assistant) >= 0.64

    @classmethod
    def _better_topic(cls, first: str, second: str) -> str:
        first_score = cls._topic_score(first)
        second_score = cls._topic_score(second)
        if second_score > first_score:
            return second
        if first_score > second_score:
            return first
        return second if len(second.split()) < len(first.split()) else first

    @classmethod
    def _topic_score(cls, topic: str) -> int:
        return len({
            term.lower()
            for term in re.findall(r"[\w]+", topic)
            if term.lower() not in cls._TOPIC_STOP_WORDS
        })

    @classmethod
    def _is_failed_response(cls, response: str) -> bool:
        normalized = response.strip().lower()
        return normalized.startswith(cls._OLLAMA_FAILURE_PREFIXES)

    @classmethod
    def _episode_terms(cls, text: str) -> set[str]:
        terms: set[str] = set()
        for raw_term in re.findall(r"[\w]+", text.lower()):
            if raw_term in cls._EPISODE_STOP_WORDS:
                continue
            terms.add(raw_term)
            if len(raw_term) > 4 and raw_term.endswith("ing"):
                stem = raw_term[:-3]
                terms.add(stem)
                terms.add(stem + "e")
            elif len(raw_term) > 3 and raw_term.endswith("s"):
                terms.add(raw_term[:-1])
        return terms

    @staticmethod
    def _episode_time_matches(query: str, created_at: str) -> bool:
        lowered = query.lower()
        if not any(word in lowered for word in ("today", "yesterday", "last week")):
            return True
        created = datetime.fromisoformat(created_at).date()
        today = datetime.now(timezone.utc).date()
        if "yesterday" in lowered:
            return created == today - timedelta(days=1)
        if "today" in lowered:
            return created == today
        return today - timedelta(days=7) <= created <= today

    @staticmethod
    def _episode_context(episodes: list[ConversationEpisode]) -> str:
        if not episodes:
            return ""
        lines = [
            f"- [{episode.created_at}] {episode.summary}"
            for episode in episodes[:3]
        ]
        return (
            "\n\nRelevant past conversations:\n"
            + "\n".join(lines)
            + "\nUse these only when relevant; do not invent missing details."
        )

    @staticmethod
    def _episode_recall_response(episodes: list[ConversationEpisode]) -> str:
        if not episodes:
            return "I couldn't find a related past discussion."
        details = "\n".join(
            f"- {episode.created_at}: {episode.summary}"
            for episode in episodes[:3]
        )
        return f"I found these past discussions:\n{details}"

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: limit - 1].rstrip() + "…"

    def _recall_response(self, key: str) -> str:
        if key == "user.color_preferences":
            favorite = self.memory.recall(
                "user.favorite_color"
            )
            liked = self.memory.recall(
                "user.liked_colors"
            )

            if not favorite and not liked:
                return "I don't know which colors you like yet."

            sentences: list[str] = []

            if favorite:
                sentences.append(
                    f"Your favorite color is {favorite.value}."
                )

            if (
                liked
                and isinstance(liked.value, list)
                and liked.value
            ):
                sentences.append(
                    f"You also like {', '.join(liked.value)}."
                )

            return " ".join(sentences)

        record = self.memory.recall(key)

        if record is None:
            missing = {
                "user.name": "I don't know your name yet.",
                "user.favorite_color": (
                    "I don't know your favorite color yet."
                ),
                "user.location": "I don't know where you live yet.",
                "user.birthday": "I don't know your birthday yet.",
            }

            return missing.get(
                key,
                "I don't have that information yet.",
            )

        responses = {
            "user.name": f"Your name is {record.value}.",
            "user.favorite_color": (
                f"Your favorite color is {record.value}."
            ),
            "user.location": f"You live in {record.value}.",
            "user.birthday": f"Your birthday is {record.value}.",
        }

        return responses.get(
            key,
            str(record.value),
        )

    @staticmethod
    def _remember_response(
        key: str,
        value: Any,
    ) -> str:
        if key == "user.name":
            return f"I'll remember that your name is {value}."

        if key == "user.favorite_color":
            return (
                f"I'll remember that your favorite color is {value}."
            )

        if key == "user.location":
            return f"I'll remember that you live in {value}."

        if key == "user.birthday":
            return f"I'll remember that your birthday is {value}."

        if key.startswith("relationship."):
            role = key.split(".", maxsplit=1)[1]
            return f"I'll remember that your {role} is {value}."

        if key.startswith("pet."):
            pet = key.split(".", maxsplit=1)[1]
            return f"I'll remember that your {pet} is {value}."

        if key == "work.employer":
            return f"I'll remember that you work at {value}."

        if key == "project.current":
            return f"I'll remember that your current project is {value}."

        if key == "goal.primary":
            return f"I'll remember that your goal is to {value}."

        if key == "user.preference":
            return f"I'll remember that you prefer {value}."

        return "I've saved that."
