"""Shared test setup. Import this BEFORE any gui module.

storage.py chooses its data directory when it is imported; so that tests never touch the real
directory or the migration, a temporary TODO_DATA_DIR is set first. All test modules share it
(storage is imported once per process).
"""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUI = ROOT / "gui"
WEB = GUI / "web"

SESSION_DIR = tempfile.mkdtemp(prefix="todolist-test-")
os.environ["TODO_DATA_DIR"] = SESSION_DIR
os.environ.pop("TODO_VERI_DIZINI", None)
if str(GUI) not in sys.path:
    sys.path.insert(0, str(GUI))
atexit.register(shutil.rmtree, SESSION_DIR, True)
