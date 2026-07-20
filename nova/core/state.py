import json, sqlite3
from threading import RLock

class StateStore:
    def __init__(self, path):
        self.path = path
        self._connection = None
        self._lock = RLock()

    def initialize(self):
        with self._lock:
            self._connection = sqlite3.connect(self.path)
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS app_state ("
                "key TEXT PRIMARY KEY, value_json TEXT NOT NULL, "
                "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            self._connection.commit()

    def set(self, key, value):
        with self._lock:
            connection = self._require()
            connection.execute(
                "INSERT INTO app_state(key,value_json,updated_at) VALUES(?,?,CURRENT_TIMESTAMP) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, "
                "updated_at=CURRENT_TIMESTAMP",
                (key, json.dumps(value))
            )
            connection.commit()

    def get(self, key, default=None):
        with self._lock:
            row = self._require().execute(
                "SELECT value_json FROM app_state WHERE key=?", (key,)
            ).fetchone()
            return default if row is None else json.loads(row[0])

    def close(self):
        with self._lock:
            if self._connection:
                self._connection.close()
                self._connection = None

    def _require(self):
        if self._connection is None:
            raise RuntimeError("StateStore has not been initialized.")
        return self._connection
