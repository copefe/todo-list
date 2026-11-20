"""Reading JSON files and writing them atomically (shared by storage.py and migration.py)."""
import json
import os
from pathlib import Path


def read_json(path: Path, default):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return default


def write_json_atomic(path: Path, data) -> None:
    temp_path = Path(path).with_suffix(Path(path).suffix + ".tmp")
    try:
        with open(temp_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    except BaseException:
        # If the write is interrupted the real file stays intact; the temp file is cleaned up.
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise
