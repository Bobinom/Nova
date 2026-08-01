from __future__ import annotations

import json
import re
from logging import Logger
from typing import Any

from nova.memory.models import MemoryRecord, MemorySearchMatch
from nova.memory.parser import (
    ForgetRequest,
    extract_fact,
    extract_forget_request,
    extract_search_query,
    recall_key,
)
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

    def remember_unique(
        self,
        key: str,
        value: Any,
        *,
        category: str = "general",
    ) -> MemoryRecord:
        existing = self.recall(key)
        if existing is None:
            combined = value
        elif isinstance(existing.value, list):
            combined = self._unique_values([*existing.value, value])
        elif self._same_value(existing.value, value):
            combined = existing.value
        else:
            combined = [existing.value, value]
        return self.remember(key, combined, category=category)

    def search(self, query: str, limit: int = 5) -> list[MemoryRecord]:
        """Return memories ranked by deterministic natural-language relevance."""
        return [match.record for match in self.search_with_scores(query, limit)]

    def search_with_scores(
        self,
        query: str,
        limit: int = 5,
    ) -> list[MemorySearchMatch]:
        """Return explainable matches while keeping exact recall deterministic."""
        if limit <= 0:
            return []

        normalized_query = query.strip().lower()
        if not normalized_query:
            return []

        exact = self.recall(normalized_query)
        if exact is not None:
            return [MemorySearchMatch(exact, 100, ("exact key match",))]

        query_terms = self._expanded_terms(normalized_query)
        query_base_terms = set(self._base_terms(normalized_query))
        if not query_terms:
            return []

        ranked: list[MemorySearchMatch] = []
        for record in self.list_memories():
            key_terms = self._expanded_terms(record.key.replace(".", " "))
            category_terms = self._expanded_terms(record.category)
            value_text = json.dumps(record.value, ensure_ascii=False, default=str)
            value_terms = self._expanded_terms(value_text)

            key_overlap = query_terms & key_terms
            category_overlap = query_terms & category_terms
            value_overlap = query_terms & value_terms
            score = (
                6 * len(key_overlap)
                + 4 * len(category_overlap)
                + 2 * len(value_overlap)
            )
            reasons: list[str] = []
            explained_key = query_base_terms & key_terms
            explained_category = query_base_terms & category_terms
            explained_value = query_base_terms & value_terms
            if key_overlap:
                displayed = explained_key or key_overlap
                reasons.append(f"key terms: {', '.join(sorted(displayed))}")
            if category_overlap:
                displayed = explained_category or category_overlap
                reasons.append(
                    f"category terms: {', '.join(sorted(displayed))}"
                )
            if value_overlap:
                displayed = explained_value or value_overlap
                reasons.append(f"value terms: {', '.join(sorted(displayed))}")

            compact_query = " ".join(self._base_terms(normalized_query))
            compact_value = " ".join(self._base_terms(value_text))
            if compact_query and compact_query in compact_value:
                score += 3
                reasons.append("matching phrase in value")

            # A lone value word is too weak; it previously caused unrelated
            # memories to leak into prompts. Key/category matches remain strong.
            if score >= 3:
                ranked.append(MemorySearchMatch(record, score, tuple(reasons)))

        ranked.sort(
            key=lambda match: (
                -match.score,
                -match.record.confidence,
                match.record.key,
            )
        )
        return ranked[:limit]

    def explain_search(self, query: str, limit: int = 5) -> dict[str, Any]:
        matches = self.search_with_scores(query, limit)
        return {
            "query": query,
            "query_terms": sorted(self._expanded_terms(query)),
            "matches": [match.as_dict() for match in matches],
        }

    def maintain(self, minimum_confidence: float = 0.5) -> dict[str, Any]:
        """Consolidate lists and safely archive weak memories."""
        threshold = min(1.0, max(0.0, minimum_confidence))
        normalized: list[str] = []
        archived: list[str] = []
        for record in self.list_memories():
            if record.confidence < threshold:
                if self.repository.archive(
                    record.key,
                    f"confidence {record.confidence:.2f} below {threshold:.2f}",
                ):
                    archived.append(record.key)
                continue
            if isinstance(record.value, list):
                unique = self._unique_values(record.value)
                if unique != record.value:
                    self.remember(
                        record.key,
                        unique,
                        category=record.category,
                        confidence=record.confidence,
                        source=record.source,
                    )
                    normalized.append(record.key)
        return {
            "minimum_confidence": threshold,
            "normalized": normalized,
            "archived": archived,
        }

    def archived_memories(self) -> list[dict[str, Any]]:
        return self.repository.list_archived()

    def restore_archived(self, key: str) -> bool:
        restored = self.repository.restore_archived(key)
        if restored:
            self.events.emit("memory.changed", {"restored_key": key})
        return restored

    def forget(self, key: str) -> bool:
        deleted = self.repository.delete(key)
        if deleted:
            self.events.emit("memory.deleted", {"key": key})
        return deleted

    def forget_matching(self, key: str, expected_value: str | None = None) -> bool:
        record = self.recall(key)
        stored_value = record.value if record is not None else None
        if record is None:
            archived = next(
                (
                    memory
                    for memory in self.archived_memories()
                    if memory["key"] == key
                ),
                None,
            )
            if archived is None:
                return False
            stored_value = archived["value"]
        if expected_value is not None and not self.matches_value(
            stored_value,
            expected_value,
        ):
            return False
        return self.forget(key)

    def forget_category(self, category: str) -> int:
        keys = {record.key for record in self.list_memories(category)}
        keys.update(
            memory["key"]
            for memory in self.archived_memories()
            if memory["category"] == category
        )
        return sum(self.forget(key) for key in sorted(keys))

    def list_memories(self, category: str | None = None) -> list[MemoryRecord]:
        return self.repository.list_all(category)

    def process_text(self, text: str) -> dict[str, Any]:
        forget = extract_forget_request(text)
        if forget is not None:
            return self._process_forget(forget)

        search_query = extract_search_query(text)
        if search_query is not None:
            records = self.search(search_query)
            return {
                "handled": True,
                "action": "searched",
                "memories": [record.as_dict() for record in records],
                "response": self.search_response(records),
            }

        fact = extract_fact(text)
        if fact is not None:
            if fact.key.startswith("pet.") or fact.key == "user.preference":
                record = self.remember_unique(
                    fact.key,
                    fact.value,
                    category=fact.category,
                )
            else:
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
                "response": self._confirmation(record, fact.value),
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

    def _process_forget(self, request: ForgetRequest) -> dict[str, Any]:
        if request.category:
            deleted = self.forget_category(request.category) > 0
        else:
            deleted = self.forget_matching(
                request.key,
                request.expected_value,
            )

        return {
            "handled": True,
            "action": "forgotten",
            "deleted": deleted,
            "response": "Forgotten." if deleted else "I couldn't find that memory.",
        }

    @staticmethod
    def matches_value(stored: Any, expected: str) -> bool:
        values = stored if isinstance(stored, list) else [stored]
        return any(str(value).casefold() == expected.casefold() for value in values)

    @staticmethod
    def search_response(records: list[MemoryRecord]) -> str:
        if not records:
            return "I don't have any relevant memories yet."
        details = "; ".join(
            f"{record.key}: {record.value}"
            for record in records
        )
        return f"I remember: {details}."

    def _on_user_message(self, event: Any) -> None:
        text = str(event.payload.get("text", "")).strip()
        if not text:
            return

        result = self.process_text(text)
        if result.get("handled"):
            self.events.emit("assistant.response", result)

    @classmethod
    def _expanded_terms(cls, text: str) -> set[str]:
        terms = set(cls._base_terms(text))
        expanded = set(terms)
        for term in terms:
            expanded.update(cls._TERM_ALIASES.get(term, set()))
            if len(term) > 3 and term.endswith("s"):
                expanded.add(term[:-1])
        return expanded

    @classmethod
    def _base_terms(cls, text: str) -> list[str]:
        return [
            term
            for term in re.findall(r"[\w]+", text.lower())
            if term not in cls._IGNORED_TERMS
        ]

    @classmethod
    def _unique_values(cls, values: list[Any]) -> list[Any]:
        unique: list[Any] = []
        for value in values:
            if not any(cls._same_value(value, existing) for existing in unique):
                unique.append(value)
        return unique

    @staticmethod
    def _same_value(left: Any, right: Any) -> bool:
        if isinstance(left, str) and isinstance(right, str):
            normalize = lambda value: " ".join(value.casefold().split())
            return normalize(left) == normalize(right)
        return left == right

    @staticmethod
    def _confirmation(record: MemoryRecord, learned_value: Any | None = None) -> str:
        value = record.value if learned_value is None else learned_value
        if record.key == "user.name":
            return f"Understood. I'll remember that your name is {value}."
        if record.key == "user.favorite_color":
            return f"I'll remember that your favorite color is {value}."
        if record.key == "user.location":
            return f"I'll remember that you live in {value}."
        if record.key == "user.birthday":
            return f"I'll remember that your birthday is {value}."
        if record.key.startswith("relationship."):
            role = record.key.split(".", maxsplit=1)[1]
            return f"I'll remember that your {role} is {value}."
        if record.key.startswith("pet."):
            pet = record.key.split(".", maxsplit=1)[1]
            return f"I'll remember that your {pet} is {value}."
        if record.key == "work.employer":
            return f"I'll remember that you work at {value}."
        if record.key == "project.current":
            return f"I'll remember that your current project is {value}."
        if record.key == "goal.primary":
            return f"I'll remember that your goal is to {value}."
        if record.key == "user.preference":
            return f"I'll remember that you prefer {value}."
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
