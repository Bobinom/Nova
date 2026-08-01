from __future__ import annotations

import json
import re
from logging import Logger
from typing import Any

from nova.memory.models import MemoryRecord
from nova.memory.parser import extract_fact, recall_key
from nova.memory.repository import MemoryRepository


class MemoryEngine:
    """Structured, deterministic memory for user facts."""

    _TERM_ALIASES = {
        "colour": {"color"},
        "colours": {"color", "colors"},
        "favorite": {"preference", "preferred", "like"},
        "favourite": {"favorite", "preference", "preferred", "like"},
        "home": {"location", "live"},
        "live": {"home", "location"},
        "partner": {"girlfriend", "boyfriend", "relationship", "spouse"},
        "girlfriend": {"partner", "relationship"},
        "boyfriend": {"partner", "relationship"},
        "spouse": {"partner", "relationship"},
        "work": {"job", "career", "employer"},
        "job": {"work", "career", "employer"},
        "project": {"goal", "building"},
        "birthday": {"born", "birth"},
    }

    _IGNORED_TERMS = {
        "a", "about", "am", "an", "and", "are", "do", "for", "i",
        "in", "is", "me", "my", "of", "on", "please", "tell", "that",
        "the", "to", "what", "where", "which", "who", "you",
    }

    def __init__(self, repository: MemoryRepository, events: Any, logger: Logger) -> None:
        self.repository = repository
        self.events = events
        self.logger = logger

    def initialize(self) -> None:
        self.repository.initialize()
        self.events.subscribe("user.message", self._on_user_message)

    def close(self) -> None:
        self.events.unsubscribe("user.message", self._on_user_message)
        self.repository.close()

    def remember(
        self,
        key: str,
        value: Any,
        *,
        category: str = "general",
        confidence: float = 1.0,
        source: str = "user",
    ) -> MemoryRecord:
        record = self.repository.upsert(
            key=key,
            category=category,
            value=value,
            confidence=confidence,
            source=source,
        )
        self.events.emit("memory.changed", {"memory": record.as_dict()})
        return record

    def recall(self, key: str) -> MemoryRecord | None:
        return self.repository.get(key)

    def search(self, query: str, limit: int = 5) -> list[MemoryRecord]:
        """Return memories ranked by deterministic natural-language relevance."""
        if limit <= 0:
            return []

        normalized_query = query.strip().lower()
        if not normalized_query:
            return []

        exact = self.recall(normalized_query)
        if exact is not None:
            return [exact]

        query_terms = self._expanded_terms(normalized_query)
        if not query_terms:
            return []

        ranked: list[tuple[int, str, MemoryRecord]] = []
        for record in self.list_memories():
            key_terms = self._expanded_terms(record.key.replace(".", " "))
            category_terms = self._expanded_terms(record.category)
            value_text = json.dumps(record.value, ensure_ascii=False, default=str)
            value_terms = self._expanded_terms(value_text)

            score = (
                5 * len(query_terms & key_terms)
                + 3 * len(query_terms & category_terms)
                + 2 * len(query_terms & value_terms)
            )
            if score:
                ranked.append((score, record.key, record))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [record for _, _, record in ranked[:limit]]

    def forget(self, key: str) -> bool:
        deleted = self.repository.delete(key)
        if deleted:
            self.events.emit("memory.deleted", {"key": key})
        return deleted

    def list_memories(self, category: str | None = None) -> list[MemoryRecord]:
        return self.repository.list_all(category)

    def process_text(self, text: str) -> dict[str, Any]:
        fact = extract_fact(text)
        if fact is not None:
            record = self.remember(
                fact.key,
                fact.value,
                category=fact.category,
                confidence=1.0,
                source="user",
            )
            return {
                "handled": True,
                "action": "remembered",
                "memory": record.as_dict(),
                "response": self._confirmation(record),
            }

        key = recall_key(text)
        if key is not None:
            record = self.recall(key)
            return {
                "handled": True,
                "action": "recalled",
                "memory": record.as_dict() if record else None,
                "response": self._recall_response(key, record),
            }

        return {"handled": False}

    def _on_user_message(self, event: Any) -> None:
        text = str(event.payload.get("text", "")).strip()
        if not text:
            return

        result = self.process_text(text)
        if result.get("handled"):
            self.events.emit("assistant.response", result)

    @classmethod
    def _expanded_terms(cls, text: str) -> set[str]:
        terms = {
            term
            for term in re.findall(r"[\w]+", text.lower())
            if term not in cls._IGNORED_TERMS
        }
        expanded = set(terms)
        for term in terms:
            expanded.update(cls._TERM_ALIASES.get(term, set()))
        return expanded

    @staticmethod
    def _confirmation(record: MemoryRecord) -> str:
        if record.key == "user.name":
            return f"Understood. I'll remember that your name is {record.value}."
        if record.key == "user.favorite_color":
            return f"I'll remember that your favorite color is {record.value}."
        if record.key == "user.location":
            return f"I'll remember that you live in {record.value}."
        if record.key == "user.birthday":
            return f"I'll remember that your birthday is {record.value}."
        if record.key.startswith("relationship."):
            role = record.key.split(".", maxsplit=1)[1]
            return f"I'll remember that your {role} is {record.value}."
        if record.key.startswith("pet."):
            pet = record.key.split(".", maxsplit=1)[1]
            return f"I'll remember that your {pet} is {record.value}."
        if record.key == "work.employer":
            return f"I'll remember that you work at {record.value}."
        if record.key == "project.current":
            return f"I'll remember that your current project is {record.value}."
        if record.key == "goal.primary":
            return f"I'll remember that your goal is to {record.value}."
        if record.key == "user.preference":
            return f"I'll remember that you prefer {record.value}."
        return "I've saved that."

    @staticmethod
    def _recall_response(key: str, record: MemoryRecord | None) -> str:
        if record is None:
            missing = {
                "user.name": "I don't know your name yet.",
                "user.favorite_color": "I don't know your favorite color yet.",
                "user.location": "I don't know where you live yet.",
                "user.birthday": "I don't know your birthday yet.",
            }
            return missing.get(key, "I don't have that information yet.")

        responses = {
            "user.name": f"Your name is {record.value}.",
            "user.favorite_color": f"Your favorite color is {record.value}.",
            "user.location": f"You live in {record.value}.",
            "user.birthday": f"Your birthday is {record.value}.",
        }
        return responses.get(key, str(record.value))
