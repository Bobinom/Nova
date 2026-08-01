from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LearnedFact:
    key: str
    category: str
    value: str


@dataclass(frozen=True)
class ForgetRequest:
    key: str | None = None
    category: str | None = None
    expected_value: str | None = None


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
        re.compile(
            r"^\s*i (?:now )?work (?:at|for)\s+(.+?)"
            r"(?:\s+now)?\s*[.!]?\s*$",
            re.I,
        ),
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

_FORGET_KEYS = {
    "birthday": "user.birthday",
    "boyfriend": "relationship.boyfriend",
    "cat": "pet.cat",
    "dog": "pet.dog",
    "employer": "work.employer",
    "favorite color": "user.favorite_color",
    "favourite colour": "user.favorite_color",
    "girlfriend": "relationship.girlfriend",
    "goal": "goal.primary",
    "location": "user.location",
    "name": "user.name",
    "partner": "relationship.partner",
    "preference": "user.preference",
    "project": "project.current",
    "spouse": "relationship.spouse",
}

_FORGET_CATEGORIES = {
    "goals": "goal",
    "pets": "pet",
    "preferences": "preference",
    "projects": "project",
    "relationships": "relationship",
    "work": "work",
}


def extract_fact(text: str) -> LearnedFact | None:
    if text.rstrip().endswith("?"):
        return None

    normalized_text = re.sub(r"^\s*actually[,]?\s+", "", text, flags=re.I)

    for pattern, key, category in _PATTERNS:
        match = pattern.match(normalized_text)
        if match:
            value = _safe_value(match.group(1))
            if value is not None:
                return LearnedFact(key=key, category=category, value=value)

    for pattern, category, key in _SEMANTIC_PATTERNS:
        match = pattern.match(normalized_text)
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


def extract_forget_request(text: str) -> ForgetRequest | None:
    normalized = text.strip(" \t\r\n.!?")

    category_match = re.fullmatch(
        r"forget what you know about my\s+"
        r"(goals|pets|preferences|projects|relationships|work)",
        normalized,
        re.I,
    )
    if category_match:
        return ForgetRequest(
            category=_FORGET_CATEGORIES[category_match.group(1).lower()],
        )

    if re.fullmatch(r"forget where i work", normalized, re.I):
        return ForgetRequest(key="work.employer")

    if re.fullmatch(r"forget where i live", normalized, re.I):
        return ForgetRequest(key="user.location")

    key_match = re.fullmatch(
        r"forget (?:my|where i live|what my)\s+(.+)",
        normalized,
        re.I,
    )
    if key_match:
        key = _FORGET_KEYS.get(key_match.group(1).lower())
        if key:
            return ForgetRequest(key=key)

    relationship_match = re.fullmatch(
        r"(.+?)\s+is no longer my\s+"
        r"(girlfriend|boyfriend|partner|spouse)",
        normalized,
        re.I,
    )
    if relationship_match:
        return ForgetRequest(
            key=f"relationship.{relationship_match.group(2).lower()}",
            expected_value=relationship_match.group(1).strip(),
        )

    work_match = re.fullmatch(
        r"i no longer work (?:at|for)\s+(.+)",
        normalized,
        re.I,
    )
    if work_match:
        return ForgetRequest(
            key="work.employer",
            expected_value=work_match.group(1).strip(),
        )

    return None


def extract_search_query(text: str) -> str | None:
    match = re.fullmatch(
        r"what do you (?:remember|know) about\s+(.+?)\s*[?]?",
        text.strip(),
        re.I,
    )
    if not match:
        return None
    return re.sub(r"^my\s+", "", match.group(1), flags=re.I).strip()


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
