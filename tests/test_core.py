import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from sqlalchemy import text


TEST_DIR = tempfile.TemporaryDirectory()
os.environ["EE_REQ_DB_PATH"] = str(Path(TEST_DIR.name) / "core.db")

import db  # noqa: E402


class RequirementsCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    @classmethod
    def tearDownClass(cls):
        db.engine.dispose()
        TEST_DIR.cleanup()

    def setUp(self):
        self.session = db.SessionLocal()

    def tearDown(self):
        self.session.rollback()
        self.session.close()

    def test_foreign_keys_are_enabled(self):
        enabled = self.session.execute(text("PRAGMA foreign_keys")).scalar()
        self.assertEqual(enabled, 1)

    def test_requirement_dimensions_are_available(self):
        columns = {row[1] for row in self.session.execute(text("PRAGMA table_info(requirements)"))}
        self.assertIn("req_level", columns)
        self.assertIn("req_nature", columns)

    def test_requirement_ids_are_isolated_by_vehicle_project(self):
        p1 = db.Project(name="P1")
        p2 = db.Project(name="P2")
        self.session.add_all([p1, p2])
        self.session.flush()
        m1 = db.RequirementModule(project_id=p1.id, code="FRS", title="P1 FRS")
        m2 = db.RequirementModule(project_id=p2.id, code="FRS", title="P2 FRS")
        self.session.add_all([m1, m2])
        self.session.flush()
        self.session.add_all([
            db.Requirement(project_id=p1.id, module_id=m1.id, req_id="REQ-0001", title="A", text="System shall A"),
            db.Requirement(project_id=p2.id, module_id=m2.id, req_id="REQ-0001", title="B", text="System shall B"),
        ])
        self.session.commit()
        self.assertEqual(self.session.query(db.Requirement).filter_by(req_id="REQ-0001").count(), 2)

    def test_trace_and_baseline_round_trip(self):
        project = db.Project(name="TraceProject")
        self.session.add(project)
        self.session.flush()
        module = db.RequirementModule(project_id=project.id, code="SYS", title="System")
        function = db.Function(project_id=project.id, func_id="FUNC-001", name="Lock")
        self.session.add_all([module, function])
        self.session.flush()
        requirement = db.Requirement(
            project_id=project.id, module_id=module.id, req_id="SYS-001",
            title="Lock vehicle", text="Vehicle shall lock on command",
        )
        self.session.add(requirement)
        self.session.flush()
        self.session.add(db.TraceLink(
            project_id=project.id, source_type="Requirement", source_id=requirement.id,
            target_type="Function", target_id=function.id, link_type="allocates",
        ))
        baseline = db.Baseline(project_id=project.id, name="Gate-1")
        self.session.add(baseline)
        self.session.flush()
        self.session.add(db.BaselineItem(
            baseline_id=baseline.id, artifact_type="Requirement", artifact_id=requirement.id,
            snapshot='{"req_id":"SYS-001","version":1}',
        ))
        self.session.commit()
        self.assertEqual(self.session.query(db.TraceLink).filter_by(project_id=project.id).count(), 1)
        self.assertEqual(len(baseline.items), 1)


class LegacyMigrationTests(unittest.TestCase):
    def test_legacy_function_columns_are_migrated_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "legacy.db")
            conn = sqlite3.connect(path)
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT)")
            cursor.execute("INSERT INTO projects VALUES (1, '通用')")
            cursor.execute("""
                CREATE TABLE functions (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, func_id TEXT UNIQUE NOT NULL,
                    category TEXT, module TEXT, description TEXT, priority TEXT, status TEXT,
                    asil_level TEXT, created_at TEXT, updated_at TEXT
                )
            """)
            cursor.execute("ALTER TABLE functions ADD COLUMN project_id INTEGER DEFAULT 1")
            cursor.execute("ALTER TABLE functions ADD COLUMN source_project_id INTEGER")
            cursor.execute("""
                INSERT INTO functions
                (id, name, func_id, category, module, description, priority, status,
                 asil_level, created_at, updated_at, project_id, source_project_id)
                VALUES (7, 'Door Lock', 'FUNC-007', 'Body', 'BCM', 'desc', 'High',
                        'Approved', 'ASIL-B', '2026-01-01', '2026-01-02', 1, NULL)
            """)
            conn.commit()
            old_db_path = db.DB_PATH
            try:
                db.DB_PATH = path
                db._migrate_unique_constraints(conn, cursor, 1)
            finally:
                db.DB_PATH = old_db_path
            row = conn.execute(
                "SELECT id, project_id, name, func_id, module, status, asil_level FROM functions"
            ).fetchone()
            conn.close()
            self.assertEqual(row, (7, 1, "Door Lock", "FUNC-007", "BCM", "Approved", "ASIL-B"))


if __name__ == "__main__":
    unittest.main()
