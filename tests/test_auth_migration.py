"""The v3 to v4 schema migration must preserve a populated database and its decision log."""
import os
import tempfile
import unittest

from eoip import db


class AuthMigration(unittest.TestCase):
    def test_v3_upgrade_is_additive_and_preserves_decision_rows(self):
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        try:
            conn = db.init_db(path)
            before_zones = conn.execute("SELECT COUNT(*) FROM zones").fetchone()[0]
            created = "2026-10-09T12:34:56.000+00:00"
            conn.execute("""INSERT INTO decisions (run_id, action, operator, note, priority_at_decision,
                           created_at, snapshot) VALUES (1,'approve','Historical operator','legacy reason','P2',?,'{}')""",
                         (created,))

            # Recreate the v3 decisions table shape and mark the database v3.
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DROP INDEX IF EXISTS ix_decisions_incident")
            conn.execute("ALTER TABLE decisions RENAME TO decisions_v4")
            conn.execute("""CREATE TABLE decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL DEFAULT 1,
                incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL,
                recommendation_id INTEGER REFERENCES recommendations(id) ON DELETE SET NULL,
                action TEXT NOT NULL, operator TEXT NOT NULL, note TEXT, priority_at_decision TEXT NOT NULL,
                created_at TEXT NOT NULL, snapshot TEXT NOT NULL DEFAULT '{}')""")
            conn.execute("""INSERT INTO decisions (id,run_id,incident_id,recommendation_id,action,operator,note,
                           priority_at_decision,created_at,snapshot)
                           SELECT id,run_id,incident_id,recommendation_id,action,operator,note,
                           priority_at_decision,created_at,snapshot FROM decisions_v4""")
            conn.execute("DROP TABLE decisions_v4")
            conn.execute("PRAGMA user_version = 3")
            conn.execute("PRAGMA foreign_keys = ON")

            db.init_schema(conn)
            row = conn.execute("SELECT * FROM decisions").fetchone()
            columns = {item[1] for item in conn.execute("PRAGMA table_info(decisions)")}
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 4)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM zones").fetchone()[0], before_zones)
            self.assertEqual((row["id"], row["operator"], row["note"], row["created_at"]),
                             (1, "Historical operator", "legacy reason", created))
            self.assertIn("employee_id", columns)
            self.assertIn("employee_number", columns)
            self.assertIsNone(row["employee_id"])
            self.assertIsNone(row["employee_number"])
            # Django edition: accounts live in Django's auth tables, not in custom EOIP tables
            self.assertFalse({"employees", "employee_sessions"} & db._table_names(conn))
            conn.close()
        finally:
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.remove(path + suffix)
                except OSError:
                    pass


if __name__ == "__main__":
    unittest.main()
