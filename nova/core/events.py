from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

@dataclass(frozen=True)
class Event:
    name: str
    payload: dict
    event_id: str
    created_at: str

class EventBus:
    def __init__(self, logger):
        self._logger = logger
        self._subscribers = {}
        self._lock = RLock()

    def subscribe(self, event_name, handler):
        with self._lock:
            handlers = self._subscribers.setdefault(event_name, [])
            if handler not in handlers:
                handlers.append(handler)

    def unsubscribe(self, event_name, handler):
        with self._lock:
            handlers = self._subscribers.get(event_name, [])
            if handler in handlers:
                handlers.remove(handler)

    def emit(self, event_name, payload=None):
        event = Event(event_name, payload or {}, str(uuid4()),
                      datetime.now(timezone.utc).isoformat())
        with self._lock:
            handlers = list(self._subscribers.get(event_name, []))
            handlers += list(self._subscribers.get("*", []))
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                self._logger.exception("Handler failed for %s", event_name)
        return event
