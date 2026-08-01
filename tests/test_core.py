import logging, tempfile, unittest
from pathlib import Path

from nova import __version__
from nova.app import NovaStatus
from nova.core.events import EventBus
from nova.core.settings import SettingsManager
from nova.core.state import StateStore

class CoreTests(unittest.TestCase):
    def test_release_version(self):
        self.assertEqual(__version__, "5.1.0")

    def test_status_uses_release_version(self):
        status = NovaStatus(
            version=__version__,
            running=True,
            loaded_plugins=0,
            memories=3,
            conversation_turns=4,
            conversation_episodes=2,
        ).as_dict()

        self.assertEqual(status["version"], "5.1.0")
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

    def test_memory_privacy_defaults_and_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = SettingsManager(path)
            settings.load()

            self.assertTrue(settings.get("privacy.episode_auto_save"))
            self.assertFalse(settings.get("privacy.confirm_semantic_memory"))
            self.assertEqual(settings.get("privacy.max_episodes"), 200)
            self.assertEqual(settings.get("privacy.retention_days"), 0)
            self.assertEqual(settings.get("application.version"), __version__)

            settings.set("privacy.episode_auto_save", False)
            reloaded = SettingsManager(path)
            reloaded.load()
            self.assertFalse(reloaded.get("privacy.episode_auto_save"))

    def test_state_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            store = StateStore(Path(d) / "state.db")
            store.initialize()
            store.set("profile", {"name": "Eric"})
            self.assertEqual(store.get("profile"), {"name": "Eric"})
            store.close()

if __name__ == "__main__":
    unittest.main()
