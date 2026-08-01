import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from nova.app import NovaApplication
from nova.core.data import DataManager


class DataManagerTests(unittest.TestCase):
    def make_database(self, path: Path, marker: str) -> None:
        connection = sqlite3.connect(path)
        connection.executescript(
            """
            CREATE TABLE app_state (key TEXT PRIMARY KEY, value_json TEXT);
            CREATE TABLE memories (memory_key TEXT PRIMARY KEY, value_json TEXT);
            CREATE TABLE conversation_turns (
                id INTEGER PRIMARY KEY, role TEXT, text TEXT
            );
            CREATE TABLE conversation_episodes (
                id INTEGER PRIMARY KEY, topic TEXT, summary TEXT,
                user_text TEXT, assistant_text TEXT
            );
            CREATE TABLE marker (value TEXT);
            """
        )
        connection.execute("INSERT INTO marker(value) VALUES (?)", (marker,))
        connection.commit()
        connection.close()

    def read_marker(self, path: Path) -> str:
        connection = sqlite3.connect(path)
        marker = connection.execute("SELECT value FROM marker").fetchone()[0]
        connection.close()
        return marker

    def test_json_export_is_readable_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "nova.db"
            self.make_database(database, "current")
            manager = DataManager(database, root)
            destination = root / "memory.json"
            payload = {"format": "nova-memory-export", "memories": ["Malmö"]}

            exported = manager.export_json(payload, destination)

            self.assertEqual(
                json.loads(exported.read_text(encoding="utf-8")),
                payload,
            )
            with self.assertRaises(FileExistsError):
                manager.export_json(payload, destination)

    def test_backup_is_verified_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "nova.db"
            self.make_database(database, "current")
            manager = DataManager(database, root)
            destination = root / "backup.db"

            backup = manager.backup(destination)

            manager.validate_backup(backup)
            self.assertEqual(self.read_marker(backup), "current")
            with self.assertRaises(FileExistsError):
                manager.backup(destination)

    def test_restore_preserves_pre_restore_recovery_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "nova.db"
            self.make_database(database, "original")
            manager = DataManager(database, root)
            backup = manager.backup(root / "original.db")

            connection = sqlite3.connect(database)
            connection.execute("UPDATE marker SET value = 'newer'")
            connection.commit()
            connection.close()

            recovery = manager.restore(backup)

            self.assertEqual(self.read_marker(database), "original")
            self.assertEqual(self.read_marker(recovery), "newer")

    def test_invalid_backup_is_rejected_without_changing_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "nova.db"
            self.make_database(database, "safe")
            invalid = root / "invalid.db"
            invalid.write_text("not sqlite", encoding="utf-8")
            manager = DataManager(database, root)

            with self.assertRaises(ValueError):
                manager.restore(invalid)

            self.assertEqual(self.read_marker(database), "safe")

    def test_application_audit_export_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = NovaApplication(base_dir=root)
            app.start()
            app.memory.remember("user.location", "Malmö", category="identity")
            app.memory.remember(
                "inference.favorite_drink",
                "Coffee",
                confidence=0.25,
                source="inferred",
            )
            app.memory.maintain()
            app.conversation.repository.add_episode(
                topic="Nova testing",
                summary="Test episode",
                user_text="Test Nova portability",
                assistant_text="Portability is ready.",
            )

            audit = app.privacy_audit()
            exported = app.export_memory(root / "export.json")
            backup = app.backup_data(root / "backup.db")
            app.stop()

            payload = json.loads(exported.read_text(encoding="utf-8"))
            self.assertEqual(audit["semantic_memories"], 1)
            self.assertEqual(audit["archived_semantic_memories"], 1)
            self.assertEqual(audit["conversation_episodes"], 1)
            self.assertEqual(payload["format"], "nova-memory-export")
            self.assertEqual(payload["format_version"], 2)
            self.assertEqual(payload["semantic_memories"][0]["value"], "Malmö")
            self.assertEqual(
                payload["archived_semantic_memories"][0]["value"],
                "Coffee",
            )
            DataManager(root / "nova.db", root).validate_backup(backup)

    def test_failed_application_restore_restarts_nova(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = NovaApplication(base_dir=root)
            app.start()
            invalid = root / "invalid.db"
            invalid.write_text("not sqlite", encoding="utf-8")

            with self.assertRaises(ValueError):
                app.restore_data(invalid)

            self.assertTrue(app.status()["running"])
            app.stop()


if __name__ == "__main__":
    unittest.main()
