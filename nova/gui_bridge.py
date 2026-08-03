from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from nova.app import NovaApplication


class NovaGUIBridge:
    """Line-delimited JSON bridge for trusted local Nova interfaces."""

    def __init__(self, app: NovaApplication | None = None) -> None:
        self.app = app or NovaApplication()
        self._running = False

    def start(self) -> None:
        if not self._running:
            self.app.start()
            self._running = True

    def stop(self) -> None:
        if self._running:
            self.app.stop()
            self._running = False

    def process(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("id")
        command = request.get("command")
        response: dict[str, Any] = {"id": request_id, "ok": True}

        if command == "message":
            text = str(request.get("text", "")).strip()
            if not text:
                raise ValueError("Message text is required.")
            response["result"] = self.app.handle_message(text)
        elif command == "status":
            response["result"] = self.app.status()
        elif command == "history":
            limit = max(1, min(int(request.get("limit", 30)), 100))
            response["result"] = self.app.conversation.history(limit)
        elif command == "listen":
            response["result"] = self.app.listen_and_respond()
        elif command == "listen_gui":
            transcript = self.app.voice.listen()
            result = self.app.conversation.handle(transcript)
            spoken = str(result.get("spoken_response", result["response"]))
            response["result"] = {
                "transcript": transcript,
                **result,
                "should_speak": bool(
                    self.app.voice.status().get("auto_speak", False)
                ),
                "speech_text": spoken,
            }
        elif command == "speak":
            text = str(request.get("text", "")).strip()
            if not text:
                raise ValueError("Speech text is required.")
            response["result"] = {"spoken": self.app.voice.speak(text)}
        elif command == "dashboard":
            response["result"] = self._dashboard()
        elif command == "set_preference":
            key = str(request.get("key", "")).strip()
            value = bool(request.get("value", False))
            setters = {
                "voice.enabled": self.app.voice.set_enabled,
                "voice.auto_speak": self.app.voice.set_auto_speak,
                "actions.enabled": self.app.actions.set_enabled,
                "live.enabled": self.app.live.set_enabled,
                "memory.episode_auto_save": (
                    self.app.conversation.set_episode_auto_save
                ),
                "memory.confirm_semantic": (
                    self.app.conversation.set_semantic_confirmation
                ),
            }
            setter = setters.get(key)
            if setter is None:
                raise ValueError(f"Unsupported preference: {key}")
            setter(value)
            response["result"] = self._dashboard()
        elif command == "weather":
            location = self.app.memory.recall("user.location")
            if location is None:
                response["result"] = {
                    "available": False,
                    "response": "Tell Nova where you live to show local weather.",
                }
            else:
                result = self.app.live.process(
                    f"What's the weather in {location.value}?"
                )
                response["result"] = {
                    **result,
                    "available": result.get("intent") == "live_weather",
                    "location": str(location.value),
                }
        elif command == "shutdown":
            response["shutdown"] = True
        else:
            raise ValueError(f"Unsupported bridge command: {command}")
        return response

    def _dashboard(self) -> dict[str, Any]:
        return {
            "status": self.app.status(),
            "voice": self.app.voice.status(),
            "actions": self.app.actions.status(),
            "privacy": self.app.conversation.privacy_status(),
            "live_information": self.app.live.status(),
            "ollama_model": "llama3.2",
        }


def run_bridge(
    *,
    app: NovaApplication | None = None,
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
) -> None:
    bridge = NovaGUIBridge(app)
    bridge.start()
    try:
        for line in input_stream:
            if not line.strip():
                continue
            request_id: Any = None
            try:
                request = json.loads(line)
                if not isinstance(request, dict):
                    raise ValueError("Bridge requests must be JSON objects.")
                request_id = request.get("id")
                response = bridge.process(request)
            except (
                json.JSONDecodeError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as exc:
                response = {
                    "id": request_id,
                    "ok": False,
                    "error": str(exc),
                }
            output_stream.write(json.dumps(response, separators=(",", ":")))
            output_stream.write("\n")
            output_stream.flush()
            if response.get("shutdown"):
                break
    finally:
        bridge.stop()


def main() -> None:
    run_bridge()


if __name__ == "__main__":
    main()
