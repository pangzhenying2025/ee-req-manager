import hashlib
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db import Base, Project, Requirement, Signal, SignalEndpoint, TraceLink
from scripts.dev import ROOT, demo_database
from services.demo_data import seed_demo
from tests import database  # noqa: F401


class DeveloperWorkflowTests(unittest.TestCase):
    def test_demo_contains_a_complete_trace_and_is_idempotent(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as session:
                pid = seed_demo(session)
                counts = (
                    session.query(Signal).filter_by(project_id=pid).count(),
                    session.query(SignalEndpoint).filter_by(project_id=pid).count(),
                    session.query(TraceLink).filter_by(project_id=pid).count(),
                )
                self.assertEqual(seed_demo(session), pid)
                self.assertEqual(session.query(Project).count(), 1)
                self.assertEqual(session.query(Signal).count(), 5)
                self.assertEqual(counts, (5, 12, 3))
                self.assertEqual(session.query(Requirement).count(), 3)
        finally:
            engine.dispose()

    def test_demo_refuses_production_database(self):
        with self.assertRaisesRegex(ValueError, "Production"):
            demo_database(ROOT / "ee_req.db")

    def test_demo_preserves_existing_unmarked_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "customer.db"
            path.write_bytes(b"existing customer file")
            digest = hashlib.sha256(path.read_bytes()).digest()
            with self.assertRaisesRegex(ValueError, "non-demo"):
                demo_database(path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), digest)
