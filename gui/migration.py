"""Data directory selection and the two one-time, copy-only migrations.

Importing this module does nothing; storage.py calls prepare_data_dir() when it is imported, and
gui/migrate_data.py runs the same steps on request.

Data directory selection order:
  1. TODO_DATA_DIR environment variable (the demo, --demo and the tests use it).
     The old name TODO_VERI_DIZINI is still accepted.
  2. Per-user data directory:
       Windows : %APPDATA%\\ToDoList
       macOS   : ~/Library/Application Support/ToDoList
       Linux   : $XDG_DATA_HOME/ToDoList or ~/.local/share/ToDoList

Migration 1 - relocation (only for the per-user directory): data files found in the repository
root (source runs) or in the .exe's folder (packaged runs) are copied into the per-user directory,
verified with size + SHA-256. Marker: .migration_done.json (the older name .gecis_tamam.json is
recognised too).

Migration 2 - schema 1 -> 2 (in whichever directory is used): gorevler.json, kategoriler.json and
tamamlama_gecmisi.json are read and NEW files items.json, categories.json and
completion_history.json are written with English field names (see schema.py). Each new file is read
back and checked record by record. Marker: .schema_v2_done.json.

Both migrations never delete, move or overwrite an old file and never overwrite a file that already
exists. If anything fails, the files written so far are renamed to <name>.migration-failed-<time>,
no marker is written, the app keeps working with the old data exactly like the previous version,
the user sees a warning, and the migration is retried on the next start. Details go to migration.log.
"""
import datetime
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import i18n
import jsonio
import schema

APP_DIR_NAME = "ToDoList"
DATA_DIR_ENV = "TODO_DATA_DIR"
LEGACY_DATA_DIR_ENV = "TODO_VERI_DIZINI"

RELOCATION_MARKER = ".migration_done.json"
LEGACY_RELOCATION_MARKER = ".gecis_tamam.json"   # written by versions before schema 2
SCHEMA_MARKER = ".schema_v2_done.json"
MIGRATION_LOG = "migration.log"
LEGACY_MIGRATION_LOG = "gecis.log"                # written by versions before schema 2; left as it is
FAILED_SUFFIX = ".migration-failed"

NEW_FILE_NAMES = tuple(schema.FILE_NAMES[2].values())
LEGACY_FILE_NAMES = tuple(schema.FILE_NAMES[1].values())
ALL_DATA_FILE_NAMES = NEW_FILE_NAMES + LEGACY_FILE_NAMES


# ---------------------------------------------------------------- locations

def user_data_dir(platform=None, env=None, home=None) -> Path:
    """Per-user data directory for the operating system (does not create it)."""
    platform = platform or sys.platform
    env = os.environ if env is None else env
    home = Path(home) if home is not None else Path.home()
    if platform.startswith("win"):
        base = Path(env["APPDATA"]) if env.get("APPDATA") else home / "AppData" / "Roaming"
    elif platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(env["XDG_DATA_HOME"]) if env.get("XDG_DATA_HOME") else home / ".local" / "share"
    return base / APP_DIR_NAME


def legacy_locations(frozen=None, executable=None) -> list:
    """Old data locations checked during relocation (packaged: the .exe's folder; development: the repo root)."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if frozen:
        return [Path(executable or sys.executable).resolve().parent]
    return [Path(__file__).resolve().parent.parent]


def data_dir_from_env(env=None):
    """Data directory forced by the environment, or None."""
    env = os.environ if env is None else env
    value = env.get(DATA_DIR_ENV) or env.get(LEGACY_DATA_DIR_ENV)
    return Path(value) if value else None


# ---------------------------------------------------------------- helpers

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _copy(source: Path, target: Path) -> None:
    # Can be patched in tests for the corrupted-copy scenario.
    shutil.copy2(source, target)


def _write_new_file(path: Path, content) -> None:
    # Can be patched in tests for the failed-conversion scenario.
    jsonio.write_json_atomic(path, content)


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _log(directory: Path, message: str) -> None:
    line = f"{_now()} {message}"
    try:
        print(line, file=sys.stderr)
    except Exception:
        pass
    try:
        with open(Path(directory) / MIGRATION_LOG, "a", encoding="utf-8") as file:
            file.write(line + "\n")
    except OSError:
        pass


def _write_marker(directory: Path, name: str, content: dict) -> None:
    jsonio.write_json_atomic(Path(directory) / name, dict(content, time=_now()))


def _set_aside(files) -> None:
    """Renames (never deletes) files written by a failed migration so they do not count as data."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    for file in files:
        try:
            os.replace(file, file.with_name(f"{file.name}{FAILED_SUFFIX}-{stamp}"))
        except OSError:
            pass


def schema_in_use(directory: Path) -> int:
    """Schema the app should read/write in a directory that is NOT being converted:
    2 if any new-name file exists or there is no data at all, otherwise 1."""
    directory = Path(directory)
    if any((directory / n).exists() for n in NEW_FILE_NAMES):
        return 2
    if any((directory / n).exists() for n in LEGACY_FILE_NAMES):
        return 1
    return 2


class MigrationResult:
    def __init__(self, directory: Path, status: str, error: str = None, source: Path = None,
                 error_detail: str = None, schema_version: int = schema.SCHEMA_VERSION):
        self.directory = Path(directory)  # data directory to read from and write to
        # relocation: "marker_exists" | "data_exists" | "no_legacy" | "copied" | "error" | "env"
        # schema:     "marker_exists" | "no_legacy" | "converted" | "error"
        self.status = status
        self.error = error                # message shown to the user (only for "error")
        self.error_detail = error_detail  # technical cause (only for "error")
        self.source = source
        self.schema_version = schema_version  # 1 = keep using the old files, 2 = new files
        self.schema_result = None         # MigrationResult of the schema step (set by prepare_data_dir)
        self.changed_old_files = []       # old files modified after the conversion (an older version used them)
        self.warning = None               # message shown to the user for changed_old_files


# ---------------------------------------------------------------- migration 1: relocation

def _has_data(directory: Path) -> bool:
    return any((Path(directory) / name).exists() for name in ALL_DATA_FILE_NAMES)


def relocation_error_message(cause: str, source: Path, lang: str = None) -> str:
    """Message shown to the user when the relocation fails (in the system language)."""
    return i18n.translate("migration.error", lang, cause=cause, path=source)


def schema_error_message(cause: str, directory: Path, lang: str = None) -> str:
    """Message shown to the user when the schema conversion fails (in the system language)."""
    return i18n.translate("migration.schemaError", lang, cause=cause, path=directory)


def relocate(new: Path, legacy_dirs) -> MigrationResult:
    """One-time, copy-only relocation. Never writes to/deletes old files;
    never overwrites data that already exists in the new directory."""
    new = Path(new)
    if (new / RELOCATION_MARKER).exists() or (new / LEGACY_RELOCATION_MARKER).exists():
        return MigrationResult(new, "marker_exists")
    if _has_data(new):
        _write_marker(new, RELOCATION_MARKER, {"status": "data_existed"})
        return MigrationResult(new, "data_exists")

    source = None
    for candidate in legacy_dirs:
        candidate = Path(candidate)
        if candidate.resolve() != new.resolve() and _has_data(candidate):
            source = candidate
            break
    if source is None:
        return MigrationResult(new, "no_legacy")

    copied, records = [], []
    try:
        for name in ALL_DATA_FILE_NAMES:
            old_file = source / name
            if not old_file.is_file():
                continue
            new_file = new / name
            if new_file.exists():  # someone created it in the meantime: do not touch it
                raise RuntimeError(f"{name} unexpectedly exists in the target")
            size, digest = old_file.stat().st_size, sha256(old_file)
            _copy(old_file, new_file)
            copied.append(new_file)
            if new_file.stat().st_size != size or sha256(new_file) != digest:
                raise RuntimeError(f"copy of {name} could not be verified (size/hash differs)")
            records.append({"file": name, "size": size, "sha256": digest})
    except Exception as exc:
        # Set the partial copy aside (without deleting it); keep using the old location.
        _set_aside(copied)
        _log(new, f"MIGRATION ERROR: data could not be copied to the new directory ({exc}). "
                  f"The app is using the data in the old location: {source}")
        return MigrationResult(source, "error", error=relocation_error_message(str(exc), source),
                               source=source, error_detail=str(exc), schema_version=schema_in_use(source))

    _write_marker(new, RELOCATION_MARKER, {"status": "copied", "source": str(source), "files": records})
    _log(new, f"Migration complete: {len(records)} file(s) copied {source} -> {new} (originals left in place).")
    return MigrationResult(new, "copied", source=source)


# ---------------------------------------------------------------- migration 2: schema 1 -> 2

def convert_schema(directory: Path) -> MigrationResult:
    """One-time conversion of the schema-1 files in `directory` into new schema-2 files.

    Old files are only read. A new file that already exists is kept (never overwritten); only the
    missing ones are written. Every written file is read back and compared record by record."""
    directory = Path(directory)
    if (directory / SCHEMA_MARKER).exists():
        result = MigrationResult(directory, "marker_exists")
        result.changed_old_files = old_files_changed_since_conversion(directory)
        if result.changed_old_files:
            result.warning = i18n.translate("migration.oldFilesChanged", None, path=directory,
                                            files=", ".join(result.changed_old_files))
            _log(directory, "WARNING: old data files changed after the schema migration "
                            f"({', '.join(result.changed_old_files)}); an older version of the app probably used them. "
                            "See `python gui/migrate_data.py --help` (--redo / --keep-new).")
        return result
    old_names = schema.FILE_NAMES[1]
    new_names = schema.FILE_NAMES[2]
    kinds = [k for k in schema.KINDS if (directory / old_names[k]).is_file()]
    if not kinds:
        return MigrationResult(directory, "no_legacy")

    written, files, kept = [], [], []
    try:
        for kind in kinds:
            source, target = directory / old_names[kind], directory / new_names[kind]
            if target.exists():
                kept.append(new_names[kind])
                continue
            raw = source.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            old_content = json.loads(raw.decode("utf-8"))
            if schema.detect_version(old_content) != 1:
                raise ValueError(f"{source.name} is not a schema-1 file")
            _write_new_file(target, schema.serialize(kind, schema.records_to_v2(kind, old_content)))
            written.append(target)
            schema.verify_conversion(kind, old_content, jsonio.read_json(target, None))
            if sha256(source) != digest:
                raise RuntimeError(f"{source.name} changed during the conversion")
            files.append({"source": source.name, "source_size": len(raw), "source_sha256": digest,
                          "target": target.name, "target_sha256": sha256(target), "records": len(old_content)})
    except Exception as exc:
        _set_aside(written)
        _log(directory, f"SCHEMA MIGRATION ERROR: the data files could not be converted to schema "
                        f"{schema.SCHEMA_VERSION} ({type(exc).__name__}: {exc}). The app is using the old files; "
                        f"nothing was deleted or overwritten. Retried on the next start.")
        return MigrationResult(directory, "error", error=schema_error_message(str(exc), directory),
                               error_detail=str(exc), schema_version=1)

    _write_marker(directory, SCHEMA_MARKER, {"status": "converted", "from_schema": 1,
                                             "to_schema": schema.SCHEMA_VERSION, "files": files,
                                             "kept_existing": kept})
    summary = ", ".join(f"{f['source']} -> {f['target']} ({f['records']} records)" for f in files) or "nothing"
    _log(directory, f"Schema migration complete: {summary}"
                    + (f"; kept existing {', '.join(kept)}" if kept else "") + " (old files left in place).")
    return MigrationResult(directory, "converted")


def old_files_changed_since_conversion(directory: Path) -> list:
    """Names of old (schema-1) files whose SHA-256 differs from the one recorded at conversion."""
    directory = Path(directory)
    try:
        marker = jsonio.read_json(directory / SCHEMA_MARKER, {})
        files = marker.get("files", [])
    except Exception:
        return []
    changed = []
    for entry in files:
        path = directory / str(entry.get("source", ""))
        try:
            if path.is_file() and sha256(path) != entry.get("source_sha256"):
                changed.append(path.name)
        except OSError:
            pass
    return changed


def redo_conversion(directory: Path) -> MigrationResult:
    """Converts the old files again (after an older version changed them). Nothing is deleted:
    the current new files and the marker are renamed to <name>.before-redo-<time> first."""
    directory = Path(directory)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    moved = []
    for name in NEW_FILE_NAMES + (SCHEMA_MARKER,):
        path = directory / name
        if path.exists():
            target = path.with_name(f"{name}.before-redo-{stamp}")
            os.replace(path, target)
            moved.append(target.name)
    _log(directory, f"Schema migration redo requested; set aside: {', '.join(moved) or 'nothing'}.")
    return convert_schema(directory)


def accept_new_files(directory: Path) -> list:
    """Keeps the new files as they are: records the old files' current hashes in the marker so that the
    'old files changed' warning stops. Returns the names that were acknowledged."""
    directory = Path(directory)
    changed = old_files_changed_since_conversion(directory)
    if not changed:
        return []
    marker = jsonio.read_json(directory / SCHEMA_MARKER, {})
    for entry in marker.get("files", []):
        if entry.get("source") in changed:
            entry["source_sha256_at_conversion"] = entry.get("source_sha256")
            entry["source_sha256"] = sha256(directory / entry["source"])
    marker["old_changes_ignored"] = _now()
    jsonio.write_json_atomic(directory / SCHEMA_MARKER, marker)
    _log(directory, f"Old-file changes acknowledged, the new files are kept: {', '.join(changed)}.")
    return changed


# ---------------------------------------------------------------- startup

def prepare_data_dir() -> MigrationResult:
    """Chooses the data directory, creates it if missing and runs the migrations if needed."""
    forced = data_dir_from_env()
    if forced is not None:
        forced.mkdir(parents=True, exist_ok=True)
        result = MigrationResult(forced, "env")
    else:
        new = user_data_dir()
        new.mkdir(parents=True, exist_ok=True)
        result = relocate(new, legacy_locations())
        if result.status == "error":
            # Working from the old location exactly as before: nothing new is written there.
            return result

    converted = convert_schema(result.directory)
    result.schema_result = converted
    result.schema_version = converted.schema_version
    result.changed_old_files = converted.changed_old_files
    result.warning = converted.warning
    if converted.status == "error":
        result.error = converted.error
        result.error_detail = converted.error_detail
    return result


def describe(directory: Path) -> list:
    """For checks: name, size, record count and SHA-256 of each data file (never the content)."""
    directory = Path(directory)
    rows = []
    for version in (1, 2):
        for kind, name in schema.FILE_NAMES[version].items():
            path = directory / name
            if not path.is_file():
                continue
            try:
                records = len(schema.parse(kind, jsonio.read_json(path, None)))
            except Exception:
                records = None
            rows.append({"file": name, "schema": version, "size": path.stat().st_size,
                         "records": records, "sha256": sha256(path)})
    return rows
