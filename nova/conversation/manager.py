from __future__ import annotations

from typing import Any

from nova.conversation.intent import Intent, classify
from nova.conversation.repository import ConversationRepository
from nova.llm.prompts import NOVA_SYSTEM_PROMPT
from nova.llm.service import LLMService
from nova.memory.engine import MemoryEngine


class ConversationManager:
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

        response = str(result["response"])
        self.repository.add("assistant", response)
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
            turns = self.repository.recent(11)

            if (
                turns
                and turns[-1].role == "user"
                and turns[-1].text == text
            ):
                turns = turns[:-1]

            turns = turns[-10:]

            history = [
                {
                    "role": turn.role,
                    "content": turn.text,
                }
                for turn in turns
            ]

            system_prompt = (
                NOVA_SYSTEM_PROMPT
                + self._memory_context(text)
            )

            return {
                "handled": True,
                "intent": "general",
                "response": self.llm.generate(
                    system_prompt=system_prompt,
                    history=history,
                    prompt=text,
                ),
            }

        return {
            "handled": False,
            "intent": "general",
            "response": (
                "I understand this is a general request, "
                "but no language model is configured yet."
            ),
        }

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

        return "I've saved that."
