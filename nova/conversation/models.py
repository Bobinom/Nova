from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConversationTurn:
    role: str
    text: str
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "text": self.text,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ConversationEpisode:
    id: int
    topic: str
    summary: str
    user_text: str
    assistant_text: str
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "topic": self.topic,
            "summary": self.summary,
            "user_text": self.user_text,
            "assistant_text": self.assistant_text,
            "created_at": self.created_at,
        }
