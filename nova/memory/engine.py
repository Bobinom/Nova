from __future__ import annotations

from logging import Logger
from typing import Any

from nova.memory.models import MemoryRecord
from nova.memory.parser import extract_fact, recall_key
from nova.memory.repository import MemoryRepository


class MemoryEngine:
    """Structured, deterministic memory for user facts."""

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
