from __future__ import annotations

import json
import sys
import threading
from collections.abc import Callable
from typing import Any, TextIO

from nova.app import NovaApplication
from nova.voice.wake import WakePhraseSession


class NovaGUIBridge:
    """Line-delimited JSON bridge for trusted local Nova interfaces."""

    def __init__(
        self,
        app: NovaApplication | None = None,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.app = app or NovaApplication()
        self.event_sink = event_sink or (lambda event: None)
        self._running = False
        self._wake_lock = threading.Lock()
        self._wake_generation = 0
        self._wake_thread: threading.Thread | None = None
        self._wake_gate: threading.Event | None = None
        self._wake_armed = False
        self._wake_awaiting_confirmation = False

    def start(self) -> None:
        if not self._running:
            self.app.start()
            self._running = True

    def stop(self) -> None:
        self._stop_wake_listener()
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
        elif command == "voice_setup":
            response["result"] = self.app.voice.setup_input()
        elif command == "wake_listen_start":
            response["result"] = self._start_wake_listener()
        elif command == "wake_listen_stop":
            self._stop_wake_listener()
            response["result"] = {"listening": False}
        elif command == "wake_message":
            text = str(request.get("text", "")).strip()
            if not text:
                raise ValueError("Wake request text is required.")
            result = self.app.conversation.handle(text)
            self._wake_awaiting_confirmation = (
                result.get("action_status") == "pending_confirmation"
            )
            spoken = str(result.get("spoken_response", result["response"]))
            response["result"] = {
                **result,
                "should_speak": True,
                "speech_text": spoken,
            }
        elif command == "configure_elevenlabs":
            voice_id = str(request.get("voice_id", "")).strip()
            api_key = str(request.get("api_key", "")).strip()
            self.app.voice.configure_elevenlabs(voice_id, api_key)
            response["result"] = self._dashboard()
        elif command == "set_voice_provider":
            provider = str(request.get("provider", "")).strip()
            self.app.voice.set_output_provider(provider)
            response["result"] = self._dashboard()
        elif command == "test_voice":
            response["result"] = self.app.voice.test_output()
        elif command == "dashboard":
            response["result"] = self._dashboard()
        elif command == "set_preference":
            key = str(request.get("key", "")).strip()
            value = bool(request.get("value", False))
            setters = {
                "voice.enabled": self.app.voice.set_enabled,
                "voice.auto_speak": self.app.voice.set_auto_speak,
                "voice.wake_enabled": self.app.voice.set_wake_enabled,
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

    def _start_wake_listener(self) -> dict[str, Any]:
        if not self.app.voice.status().get("wake_enabled", False):
            return {"listening": False}
        with self._wake_lock:
            if self._wake_thread is not None and self._wake_thread.is_alive():
                return {"listening": True}
            self._wake_generation += 1
            generation = self._wake_generation
            gate = threading.Event()
            self._wake_gate = gate
        thread = threading.Thread(
            target=self._wake_worker,
            args=(generation, gate),
            name="nova-wake-listener",
            daemon=True,
        )
        with self._wake_lock:
            self._wake_thread = thread
        thread.start()
        return {"listening": True}

    def release_wake_listener(self) -> None:
        with self._wake_lock:
            gate = self._wake_gate
        if gate is not None:
            gate.set()

    def _wake_worker(
        self,
        generation: int,
        gate: threading.Event,
    ) -> None:
        try:
            if not gate.wait(timeout=2):
                return
            self._listen_for_wake(generation)
        finally:
            with self._wake_lock:
                if self._wake_thread is threading.current_thread():
                    self._wake_thread = None
                    self._wake_gate = None

    def _stop_wake_listener(self) -> None:
        with self._wake_lock:
            self._wake_generation += 1
        self._wake_armed = False
        self._wake_awaiting_confirmation = False

    def _listen_for_wake(self, generation: int) -> None:
        try:
            transcript = self.app.voice.listen()
        except (OSError, RuntimeError, ValueError) as exc:
            if not WakePhraseSession.is_silence_error(str(exc)):
                self._emit_wake(generation, "error", error=str(exc))
            else:
                self._emit_wake(generation, "silence")
            return
        phrase = str(self.app.voice.status().get("wake_phrase", "Nova"))
        session = WakePhraseSession(
            self.app.voice,
            self.app.conversation.handle,
            phrase,
        )
        if session.is_sleep_phrase(transcript):
            self.app.voice.set_wake_enabled(False)
            self._emit_wake(generation, "sleep", transcript=transcript)
            return
        if self._wake_armed or self._wake_awaiting_confirmation:
            request = transcript.strip()
            self._wake_armed = False
            self._wake_awaiting_confirmation = False
        else:
            request = session.request_after_wake_phrase(transcript)
            if request is None:
                self._emit_wake(generation, "ignored")
                return
            if not request:
                self._wake_armed = True
                self._emit_wake(
                    generation,
                    "activation",
                    transcript=transcript,
                    request="",
                )
                return
        self._emit_wake(
            generation,
            "request",
            transcript=transcript,
            request=request,
        )

    def _emit_wake(
        self,
        generation: int,
        kind: str,
        **values: Any,
    ) -> None:
        with self._wake_lock:
            if generation != self._wake_generation:
                return
        self.event_sink({"event": "wake", "kind": kind, **values})

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
    output_lock = threading.Lock()

    def write(payload: dict[str, Any]) -> None:
        with output_lock:
            output_stream.write(json.dumps(payload, separators=(",", ":")))
            output_stream.write("\n")
            output_stream.flush()

    bridge = NovaGUIBridge(app, event_sink=write)
    bridge.start()
    try:
        for line in input_stream:
            if not line.strip():
                continue
            request_id: Any = None
            command: Any = None
            try:
                request = json.loads(line)
                if not isinstance(request, dict):
                    raise ValueError("Bridge requests must be JSON objects.")
                request_id = request.get("id")
                command = request.get("command")
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
            write(response)
            if command == "wake_listen_start":
                bridge.release_wake_listener()
            if response.get("shutdown"):
                break
    finally:
        bridge.stop()


def main() -> None:
    run_bridge()


if __name__ == "__main__":
    main()
