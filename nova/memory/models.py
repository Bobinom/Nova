from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MemoryRecord:
    key: str
    category: str
    value: Any
    confidence: float
    source: str
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "category": self.category,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class MemorySearchMatch:
    record: MemoryRecord
    score: int
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "memory": self.record.as_dict(),
            "score": self.score,
            "reasons": list(self.reasons),
        }
