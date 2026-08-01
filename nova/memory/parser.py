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

_SEMANTIC_PATTERNS: list[
    tuple[re.Pattern[str], str, str]
] = [
    (
        re.compile(
            r"^\s*my\s+(girlfriend|boyfriend|partner|spouse)"
            r"(?:'s name)?\s+is\s+(.+?)\s*[.!]?\s*$",
            re.I,
        ),
        "relationship",
        "relationship",
    ),
    (
        re.compile(
            r"^\s*my\s+(dog|cat|pet)(?:'s name)?"
            r"\s+is\s+(.+?)\s*[.!]?\s*$",
            re.I,
        ),
        "pet",
        "pet",
    ),
    (
        re.compile(r"^\s*i work (?:at|for)\s+(.+?)\s*[.!]?\s*$", re.I),
        "work",
        "work.employer",
    ),
    (
        re.compile(
            r"^\s*(?:my current project is|i(?:'m| am) working on)"
            r"\s+(.+?)\s*[.!]?\s*$",
            re.I,
        ),
        "project",
        "project.current",
    ),
    (
        re.compile(
            r"^\s*(?:my (?:main )?goal is(?: to)?|i want to)"
            r"\s+(.+?)\s*[.!]?\s*$",
            re.I,
        ),
        "goal",
        "goal.primary",
    ),
    (
        re.compile(r"^\s*i prefer\s+(.+?)\s*[.!]?\s*$", re.I),
        "preference",
        "user.preference",
    ),
]

_UNSAFE_VALUE_PREFIXES = ("maybe ", "not ", "probably ", "possibly ")


def extract_fact(text: str) -> LearnedFact | None:
    if text.rstrip().endswith("?"):
        return None

    for pattern, key, category in _PATTERNS:
        match = pattern.match(text)
        if match:
            value = _safe_value(match.group(1))
            if value is not None:
                return LearnedFact(key=key, category=category, value=value)

    for pattern, category, key in _SEMANTIC_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue

        if key in {"relationship", "pet"}:
            subject = match.group(1).lower()
            value_group = match.group(2)
            memory_key = f"{key}.{subject}"
        else:
            value_group = match.group(1)
            memory_key = key

        value = _safe_value(value_group)
        if value is not None:
            return LearnedFact(
                key=memory_key,
                category=category,
                value=value,
            )
    return None


def _safe_value(value: str) -> str | None:
    cleaned = value.strip(" \t\r\n.!?")
    if not cleaned or cleaned.lower().startswith(_UNSAFE_VALUE_PREFIXES):
        return None
    return cleaned


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
