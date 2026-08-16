import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import db
from collaboration import acquire_lock, active_sessions, release_lock, touch_session


class CollaborationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.TemporaryDirectory()
        cls.test_engine = create_engine(
            f"sqlite:///{Path(cls.test_dir.name) / 'collaboration.db'}",
            connect_args={"timeout": 10, "check_same_thread": False},
        )

        @event.listens_for(cls.test_engine, "connect")
        def _configure_sqlite(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=10000")

        cls.Session = sessionmaker(bind=cls.test_engine)
        db.Base.metadata.create_all(cls.test_engine)

    @classmethod
    def tearDownClass(cls):
        cls.test_engine.dispose()
        cls.test_dir.cleanup()

    def setUp(self):
        session = self.Session()
        project = db.Project(name=f"Collab-{id(self)}")
        session.add(project)
        session.commit()
        self.project_id = project.id
        session.close()

    def tearDown(self):
        session = self.Session()
        session.query(db.EditLock).filter_by(project_id=self.project_id).delete()
        session.query(db.CollaborationSession).filter_by(project_id=self.project_id).delete()
        session.query(db.Project).filter_by(id=self.project_id).delete()
        session.commit()
        session.close()

    def test_presence_is_project_scoped(self):
        session = self.Session()
        now = datetime(2026, 8, 12, 8, 0, 0)
        touch_session(
            session,
            session_id="alice-session",
            user_name="Alice",
            project_id=self.project_id,
            page_name="需求规范",
            now=now,
        )
        rows = active_sessions(session, self.project_id, now=now + timedelta(seconds=5))
        self.assertEqual([(row.user_name, row.page_name) for row in rows], [("Alice", "需求规范")])
        self.assertEqual(active_sessions(session, self.project_id, now=now + timedelta(seconds=40)), [])
        session.close()

    def test_edit_lock_blocks_second_session_and_can_be_released(self):
        session = self.Session()
        first = acquire_lock(
            session,
            project_id=self.project_id,
            artifact_type="Requirement",
            artifact_id=101,
            session_id="alice-session",
            user_name="Alice",
        )
        second = acquire_lock(
            session,
            project_id=self.project_id,
            artifact_type="Requirement",
            artifact_id=101,
            session_id="bob-session",
            user_name="Bob",
        )
        self.assertTrue(first.acquired)
        self.assertFalse(second.acquired)
        self.assertEqual(second.owner_name, "Alice")
        self.assertTrue(release_lock(
            session,
            project_id=self.project_id,
            artifact_type="Requirement",
            artifact_id=101,
            session_id="alice-session",
        ))
        third = acquire_lock(
            session,
            project_id=self.project_id,
            artifact_type="Requirement",
            artifact_id=101,
            session_id="bob-session",
            user_name="Bob",
        )
        self.assertTrue(third.acquired)
        session.close()

    def test_expired_lock_can_be_reclaimed(self):
        session = self.Session()
        now = datetime(2026, 8, 12, 9, 0, 0)
        acquire_lock(
            session,
            project_id=self.project_id,
            artifact_type="Signal",
            artifact_id=7,
            session_id="alice-session",
            user_name="Alice",
            now=now,
            ttl_seconds=10,
        )
        reclaimed = acquire_lock(
            session,
            project_id=self.project_id,
            artifact_type="Signal",
            artifact_id=7,
            session_id="bob-session",
            user_name="Bob",
            now=now + timedelta(seconds=11),
        )
        self.assertTrue(reclaimed.acquired)
        self.assertEqual(reclaimed.owner_name, "Bob")
        session.close()

    def test_simultaneous_acquire_has_one_winner(self):
        def compete(user_name):
            session = self.Session()
            try:
                return acquire_lock(
                    session,
                    project_id=self.project_id,
                    artifact_type="Function",
                    artifact_id=55,
                    session_id=f"{user_name}-session",
                    user_name=user_name,
                )
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(compete, ["Alice", "Bob"]))
        self.assertEqual(sum(result.acquired for result in results), 1)
        self.assertEqual({result.owner_name for result in results}, {next(r.owner_name for r in results if r.acquired)})


if __name__ == "__main__":
    unittest.main()
