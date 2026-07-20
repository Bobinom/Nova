from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LearnedFact:
    key: str
    category: str
    value: str


_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"^\s*(?:my name is|i am called|call me)\s+(.+?)\s*[.!]?\s*$", re.I),
        "user.name",
        "identity",
    ),
    (
        re.compile(r"^\s*my favorite colou?r is\s+(.+?)\s*[.!]?\s*$", re.I),
        "user.favorite_color",
        "preference",
    ),
    (
        re.compile(r"^\s*i live in\s+(.+?)\s*[.!]?\s*$", re.I),
        "user.location",
        "identity",
    ),
    (
        re.compile(r"^\s*my birthday is\s+(.+?)\s*[.!]?\s*$", re.I),
        "user.birthday",
        "identity",
    ),
]


def extract_fact(text: str) -> LearnedFact | None:
    for pattern, key, category in _PATTERNS:
        match = pattern.match(text)
        if match:
            value = match.group(1).strip(" \t\r\n.!?")
            if value:
                return LearnedFact(key=key, category=category, value=value)
    return None


def recall_key(text: str) -> str | None:
    normalized = re.sub(r"[^\w\s]", "", text.lower()).strip()

    if normalized in {
        "whats my name",
        "what is my name",
        "do you know my name",
        "who am i",
    }:
        return "user.name"

    if normalized in {
        "whats my favorite color",
        "what is my favorite color",
        "whats my favourite colour",
        "what is my favourite colour",
    }:
        return "user.favorite_color"

    if normalized in {
        "where do i live",
        "whats my location",
        "what is my location",
    }:
        return "user.location"

    if normalized in {
        "whens my birthday",
        "when is my birthday",
        "whats my birthday",
        "what is my birthday",
    }:
        return "user.birthday"

    return None
