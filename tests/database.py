"""Bind db.py to a disposable database before any test imports it."""

import atexit
import os
import sys
import tempfile
from pathlib import Path

TEST_DIR = tempfile.TemporaryDirectory(prefix="ee-req-unit-")
os.environ["EE_REQ_DB_PATH"] = str(Path(TEST_DIR.name) / "unit.db")


def _cleanup():
    if "db" in sys.modules:
        sys.modules["db"].engine.dispose()
    TEST_DIR.cleanup()


atexit.register(_cleanup)
