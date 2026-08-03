from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Protocol


class ConversationVoice(Protocol):
    def listen(self) -> str: ...
    def speak(self, text: str, *, force: bool = False) -> bool: ...
    def status(self) -> dict[str, Any]: ...


class HandsFreeConversation:
    STOP_PHRASES = {
        "nova stop",
        "stop nova",
        "stop listening",
        "end conversation",
        "exit conversation",
    }

    def __init__(
        self,
        voice: ConversationVoice,
        handle_message: Callable[[str], dict[str, Any]],
    ) -> None:
        self.voice = voice
        self.handle_message = handle_message

    @classmethod
    def is_stop_phrase(cls, transcript: str) -> bool:
        normalized = re.sub(r"[^a-z0-9]+", " ", transcript.lower()).strip()
        return normalized in cls.STOP_PHRASES

    def run(
        self,
        *,
        on_listening: Callable[[], None],
        on_transcript: Callable[[str], None],
        on_response: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> str:
        while True:
            on_listening()
            try:
                transcript = self.voice.listen()
            except KeyboardInterrupt:
                return "interrupted"
            except (OSError, RuntimeError, ValueError) as exc:
                on_error(str(exc))
                continue

            on_transcript(transcript)
            if self.is_stop_phrase(transcript):
                try:
                    self.voice.speak(
                        "Hands-free conversation stopped.",
                        force=True,
                    )
                except (OSError, RuntimeError, ValueError) as exc:
                    on_error(f"Speech output failed: {exc}")
                return "spoken_stop"

            try:
                result = self.handle_message(transcript)
                response = str(result["response"])
            except (OSError, RuntimeError, ValueError, KeyError) as exc:
                on_error(str(exc))
                continue

            on_response(response)
            if not bool(self.voice.status()["auto_speak"]):
                try:
                    self.voice.speak(response, force=True)
                except (OSError, RuntimeError, ValueError) as exc:
                    on_error(f"Speech output failed: {exc}")
