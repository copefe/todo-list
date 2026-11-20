"""Reading and writing the data files.

The data directory is chosen and migrated when this module is imported (see migration.py for the
directory selection order and the two one-time migrations). The rest of the app only sees
schema-2 records (English field names, see schema.py).

Normally the files are the schema-2 ones (items.json, categories.json, completion_history.json).
Only if the schema migration failed does this session keep reading and writing the old schema-1
files (gorevler.json ...) exactly like the previous version did; the migration is retried on the
next start.
"""
import jsonio
import migration
import schema

_MIGRATION = migration.prepare_data_dir()
DATA_DIR = _MIGRATION.directory
SCHEMA_IN_USE = _MIGRATION.schema_version  # 2 normally, 1 after a failed migration
MIGRATION_ERROR = _MIGRATION.error  # if not None, the app shows it to the user at startup
MIGRATION_WARNING = _MIGRATION.warning  # shown at startup too (old files changed after the conversion)
MIGRATION_RESULT = _MIGRATION


def data_file(kind: str):
    """Path of the items/categories/history file in use (looked up on every call)."""
    return DATA_DIR / schema.FILE_NAMES[SCHEMA_IN_USE][kind]


ITEMS_FILE = data_file("items")
CATEGORIES_FILE = data_file("categories")
HISTORY_FILE = data_file("history")


def _read(kind: str) -> list:
    content = jsonio.read_json(data_file(kind), None)
    return [] if content is None else schema.parse(kind, content)


def _write(kind: str, records: list) -> None:
    jsonio.write_json_atomic(data_file(kind), schema.serialize(kind, records, SCHEMA_IN_USE))


def read_items() -> list:
    return _read("items")


def write_items(items: list) -> None:
    _write("items", items)


def read_categories() -> list:
    return _read("categories")


def write_categories(categories: list) -> None:
    _write("categories", categories)


def read_history() -> list:
    return _read("history")


def write_history(history: list) -> None:
    _write("history", history)


def append_history(record: dict) -> None:
    history = read_history()
    history.append(record)
    write_history(history)
