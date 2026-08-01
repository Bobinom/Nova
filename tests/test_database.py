import sqlite3
import tempfile
import unittest
from pathlib import Path

from nova.app import NovaApplication
from nova.core.database import DatabaseManager


class DatabaseManagerTests(unittest.TestCase):
    def test_fresh_database_migrates_to_current_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = DatabaseManager(root / "nova.db", root)

            health = manager.prepare()

            self.assertEqual(health["status"], "healthy")
            self.assertEqual(
                health["schema_version"],
                DatabaseManager.CURRENT_SCHEMA_VERSION,
            )
            self.assertEqual(health["missing_tables"], [])

    def test_legacy_database_migration_preserves_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "nova.db"
            connection = sqlite3.connect(database)
            connection.execute(
                "CREATE TABLE app_state (key TEXT PRIMARY KEY, value_json TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO app_state(key, value_json) VALUES (?, ?)",
                ("marker", '"safe"'),
            )
            connection.commit()
            connection.close()

            manager = DatabaseManager(database, root)
            manager.prepare()

            connection = sqlite3.connect(database)
            marker = connection.execute(
                "SELECT value_json FROM app_state WHERE key = 'marker'"
            ).fetchone()[0]
            connection.close()
            self.assertEqual(marker, '"safe"')
            self.assertEqual(manager.health()["status"], "healthy")

    def test_prepare_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = DatabaseManager(root / "nova.db", root)

            first = manager.prepare()
            second = manager.prepare()

            self.assertEqual(first["schema_version"], second["schema_version"])
            self.assertEqual(manager.recoveries(), [])

    def test_corrupt_database_is_quarantined_and_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "nova.db"
            corrupt_bytes = b"this is not sqlite"
            database.write_bytes(corrupt_bytes)
            manager = DatabaseManager(database, root)

            health = manager.prepare()

            self.assertEqual(health["status"], "healthy")
            self.assertIsNotNone(health["last_recovery"])
            recovery = Path(health["last_recovery"])
            self.assertEqual(recovery.read_bytes(), corrupt_bytes)
            self.assertEqual(manager.recoveries(), [recovery])

    def test_application_reports_database_health(self):
        with tempfile.TemporaryDirectory() as directory:
            app = NovaApplication(base_dir=Path(directory))
            app.start()

            health = app.database_health()

            self.assertEqual(health["status"], "healthy")
            self.assertEqual(health["schema_version"], 2)
            self.assertEqual(app.database_recoveries(), [])
            app.stop()

    def test_application_recovers_a_corrupt_database_during_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corrupt_bytes = b"damaged nova database"
            (root / "nova.db").write_bytes(corrupt_bytes)
            app = NovaApplication(base_dir=root)

            app.start()

            self.assertEqual(app.database_health()["status"], "healthy")
            recoveries = app.database_recoveries()
            self.assertEqual(len(recoveries), 1)
            self.assertEqual(Path(recoveries[0]).read_bytes(), corrupt_bytes)
            app.stop()

    def test_future_schema_is_rejected_without_downgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = DatabaseManager(root / "nova.db", root)
            manager.prepare()
            connection = sqlite3.connect(root / "nova.db")
            connection.execute(
                "UPDATE nova_schema SET version = ? WHERE singleton = 1",
                (DatabaseManager.CURRENT_SCHEMA_VERSION + 1,),
            )
            connection.commit()
            connection.close()

            with self.assertRaisesRegex(RuntimeError, "newer than this Nova"):
                manager.prepare()

            connection = sqlite3.connect(root / "nova.db")
            version = connection.execute(
                "SELECT version FROM nova_schema WHERE singleton = 1"
            ).fetchone()[0]
            connection.close()
            self.assertEqual(version, DatabaseManager.CURRENT_SCHEMA_VERSION + 1)
            self.assertEqual(manager.recoveries(), [])

    def test_non_corruption_access_error_is_not_quarantined(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "nova.db"
            database.write_bytes(b"temporary")
            manager = DatabaseManager(database, root)
            manager._integrity_check = lambda: ("error", "database is locked")

            with self.assertRaisesRegex(RuntimeError, "Could not verify"):
                manager.prepare()

            self.assertEqual(database.read_bytes(), b"temporary")
            self.assertEqual(manager.recoveries(), [])


if __name__ == "__main__":
    unittest.main()
