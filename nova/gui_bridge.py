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
        elif command == "shutdown":
            response["shutdown"] = True
        else:
            raise ValueError(f"Unsupported bridge command: {command}")
        return response


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
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
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
