import logging, tempfile, unittest
from pathlib import Path

from nova import __version__
from nova.app import NovaStatus
from nova.core.events import EventBus
from nova.core.settings import SettingsManager
from nova.core.state import StateStore

class CoreTests(unittest.TestCase):
    def test_release_version(self):
        self.assertEqual(__version__, "5.0.0")

    def test_status_uses_release_version(self):
        status = NovaStatus(
            version=__version__,
            running=True,
            loaded_plugins=0,
            memories=3,
            conversation_turns=4,
            conversation_episodes=2,
        ).as_dict()

        self.assertEqual(status["version"], "5.0.0")
        self.assertEqual(status["conversation_episodes"], 2)

    def test_event_delivery(self):
        bus = EventBus(logging.getLogger("test"))
        received = []
        bus.subscribe("x", received.append)
        bus.emit("x", {"value": 42})
        self.assertEqual(received[0].payload["value"], 42)

    def test_settings_persist(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "settings.json"
            s = SettingsManager(p)
            s.load()
            s.set("privacy.allow_web_access", True)
            r = SettingsManager(p)
            r.load()
            self.assertTrue(r.get("privacy.allow_web_access"))

    def test_state_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            store = StateStore(Path(d) / "state.db")
            store.initialize()
            store.set("profile", {"name": "Eric"})
            self.assertEqual(store.get("profile"), {"name": "Eric"})
            store.close()

if __name__ == "__main__":
    unittest.main()
