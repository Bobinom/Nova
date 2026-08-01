import json
from copy import deepcopy
from threading import RLock

from nova import __version__

DEFAULT_SETTINGS = {
    "application": {"name": "Nova", "version": __version__},
    "privacy": {
        "allow_web_access": False,
        "allow_telemetry": False,
        "episode_auto_save": True,
        "confirm_semantic_memory": False,
        "max_episodes": 200,
        "retention_days": 0,
    },
    "plugins": {"enabled": True}
}

def _merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _merge(base[key], value)
        else:
            base[key] = value
    return base

class SettingsManager:
    def __init__(self, path):
        self.path = path
        self._data = deepcopy(DEFAULT_SETTINGS)
        self._lock = RLock()

    def load(self):
        with self._lock:
            if not self.path.exists():
                self.save()
                return deepcopy(self._data)
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                self._data = _merge(deepcopy(DEFAULT_SETTINGS), loaded)
            except (json.JSONDecodeError, OSError):
                self._data = deepcopy(DEFAULT_SETTINGS)
                self.save()
            return deepcopy(self._data)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(self.path)

    def get(self, dotted_key, default=None):
        current = self._data
        for part in dotted_key.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return deepcopy(current)

    def set(self, dotted_key, value, save=True):
        parts = dotted_key.split(".")
        current = self._data
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = value
        if save:
            self.save()
