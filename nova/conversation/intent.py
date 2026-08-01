from __future__ import annotations

import re
from dataclasses import dataclass

from nova.memory.parser import (
    extract_fact,
    extract_forget_request,
    extract_search_query,
)


@dataclass(frozen=True)
class Intent:
    name: str
    memory_key: str | None = None
    value: str | list[str] | None = None
    category: str | None = None
    confidence: float = 1.0


def classify(text: str, last_topic: str | None = None) -> Intent:
    raw = text.strip()
    normalized = _normalize(raw)

    episode_continue = re.match(
        r"^(?:continue|resume)\s+(?:our|the)\s+(.+?)(?:\s+discussion)?$",
        normalized,
        re.I,
    )
    if episode_continue:
        return Intent("episode_continue", value=episode_continue.group(1))

    episode_recall = re.match(
        r"^(?:what did we (?:discuss|talk about|decide)(?: about)?|"
        r"what were we talking about)(.*)$",
        normalized,
        re.I,
    )
    if episode_recall:
        query = episode_recall.group(1).strip() or normalized
        return Intent("episode_recall", value=query)

    forget = extract_forget_request(raw)
    if forget is not None:
        return Intent(
            "forget",
            forget.key,
            forget.expected_value,
            forget.category,
        )

    search_query = extract_search_query(raw)
    if search_query is not None:
        return Intent("search_memory", value=search_query)

    incomplete = {
        "my name": "name",
        "my favorite color": "favorite_color",
        "my favourite colour": "favorite_color",
        "i live": "location",
        "my birthday": "birthday",
    }
    if normalized in incomplete:
        return Intent("incomplete", value=incomplete[normalized])

    name_match = re.match(
        r"^(?:my name is|i am called|call me|actually call me|actually my name is)\s+(.+)$",
        raw,
        re.I,
    )
    if name_match:
        value = _clean_value(name_match.group(1))
        return Intent("remember", "user.name", value, "identity")

    color_match = re.match(
        r"^my favorite colou?r is\s+(.+)$",
        raw,
        re.I,
    )
    if color_match:
        full = _clean_value(color_match.group(1))
        split = re.split(
            r"\s+(?:but|and)\s+(?:i\s+)?(?:also\s+)?(?:do\s+)?like\s+",
            full,
            maxsplit=1,
            flags=re.I,
        )
        favorite = _normalize_color_value(split[0])
        if len(split) == 2:
            liked = [_normalize_color_value(split[1])]
            return Intent(
                "remember_color_bundle",
                "user.favorite_color",
                [favorite, *liked],
                "preference",
            )
        return Intent("remember", "user.favorite_color", favorite, "preference")

    like_match = re.match(
        r"^i (?:also )?like (?:the colou?r )?(.+)$",
        raw,
        re.I,
    )
    if like_match:
        return Intent(
            "append_list",
            "user.liked_colors",
            _normalize_color_value(like_match.group(1)),
            "preference",
        )

    fact = extract_fact(raw)
    if fact is not None:
        action = (
            "remember_unique"
            if fact.key.startswith("pet.") or fact.key == "user.preference"
            else "remember"
        )
        return Intent(
            action,
            fact.key,
            fact.value,
            fact.category,
        )

    recall_map = {
        "user.name": {
            "whats my name",
            "what is my name",
            "do you know my name",
            "who am i",
        },
        "user.favorite_color": {
            "whats my favorite color",
            "what is my favorite color",
            "whats my favourite colour",
            "what is my favourite colour",
            "which color is my favorite",
            "which colour is my favourite",
        },
        "user.color_preferences": {
            "what color do i like",
            "what colors do i like",
            "which color do i like",
            "which colors do i like",
            "what colour do i like",
            "what colours do i like",
            "list the colors i like",
            "list the colours i like",
        },
        "user.location": {
            "where do i live",
            "whats my location",
            "what is my location",
        },
        "user.birthday": {
            "whens my birthday",
            "when is my birthday",
            "whats my birthday",
            "what is my birthday",
        },
    }

    for key, phrases in recall_map.items():
        if normalized in phrases:
            return Intent("recall", key)

    if normalized in {"what is it", "whats it", "what was it"} and last_topic:
        return Intent("recall", last_topic)

    return Intent("general")


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_value(value: str) -> str:
    return value.strip(" \t\r\n.!?")


def _normalize_color_value(value: str) -> str:
    value = _clean_value(value)
    value = re.sub(r"^(?:the\s+)?colou?r\s+", "", value, flags=re.I)
    value = re.sub(r"\s+as\s+well$", "", value, flags=re.I)
    value = re.sub(r"\s+", " ", value).strip()
    return value.capitalize()
