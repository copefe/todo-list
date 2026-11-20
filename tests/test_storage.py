"""Tests for storage.py, migration.py, schema.py and migrate_data.py.

They never touch real data: everything runs in temporary folders with made-up data.
Run (from the repo root):  python -m unittest discover -s tests -v
"""
import copy
import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest import mock

# storage.py chooses a directory when imported; support sets a temporary TODO_DATA_DIR first.
from support import SESSION_DIR as _SESSION_DIR  # noqa: E402  (must come before gui imports)

import migrate_data  # noqa: E402
import migration  # noqa: E402
import schema  # noqa: E402
import storage  # noqa: E402

V1 = schema.FILE_NAMES[1]
V2 = schema.FILE_NAMES[2]
V1_FILES = tuple(V1.values())
V2_FILES = tuple(V2.values())

# Made-up schema-1 data (Turkish keys, bare lists) covering every stored field.
V1_ITEMS = [
    {"id": "a1", "görev": "Örnek görev", "tamamlandı": False, "yıl": 2030, "ay": 1, "gün": 31, "saat": 23,
     "dakika": 59, "rutin": False, "kategori": "Ders"},
    {"id": "a2", "görev": "Eski kategori", "tamamlandı": True, "yıl": 2029, "ay": 12, "gün": 1, "saat": 0,
     "dakika": 0, "rutin": False, "kategori": "Kategorisiz"},
    {"id": "r1", "görev": "Haftalık rutin", "tamamlandı": True, "sıklık": 1, "rutin": True, "yıl": 2030,
     "ay": 2, "gün": 4, "saat": 8, "dakika": 5, "streak": 7, "kategori": "", "hafta_gunleri": [0, 2, 4]},
    {"id": "r2", "görev": "Üç günde bir", "tamamlandı": False, "sıklık": 3, "rutin": True, "yıl": 2030,
     "ay": 2, "gün": 5, "saat": 21, "dakika": 30, "streak": 0, "kategori": "Spor", "ekstra": {"x": 1}},
]
V1_CATEGORIES = ["Ders", "Spor", "Kategorisiz"]
V1_HISTORY = [{"tarih": "2030-01-01", "tip": "rutin"}, {"tarih": "2030-01-01", "tip": "görev"},
              {"tarih": "2030-01-02", "tip": "rutin"}, {"tarih": "bozuk-tarih", "tip": "başka"}]
V1_CONTENT = {"items": V1_ITEMS, "categories": V1_CATEGORIES, "history": V1_HISTORY}


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_sample(directory: Path, names=V1_FILES, label="old"):
    """Small placeholder files for the relocation tests (content does not matter there)."""
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).write_text(json.dumps([{"görev": f"{label}-{name}", "tamamlandı": False}],
                                                 ensure_ascii=False), encoding="utf-8")


def _write_v1(directory: Path, kinds=schema.KINDS):
    directory.mkdir(parents=True, exist_ok=True)
    for kind in kinds:
        (directory / V1[kind]).write_text(json.dumps(V1_CONTENT[kind], ensure_ascii=False, indent=2), encoding="utf-8")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="todolist-test-"))
        self.new = self.root / "new"
        self.old = self.root / "old"
        self.new.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def hashes(self, directory, names):
        return {n: _hash(directory / n) for n in names if (directory / n).exists()}


class SafetyTest(unittest.TestCase):
    def test_tests_do_not_use_real_directory(self):
        self.assertEqual(storage.DATA_DIR, Path(_SESSION_DIR))
        self.assertTrue(str(storage.ITEMS_FILE).startswith(_SESSION_DIR))
        self.assertEqual(storage.SCHEMA_IN_USE, 2)
        self.assertEqual(storage.ITEMS_FILE.name, "items.json")


class DirectorySelectionTest(TempDirTest):
    def test_windows_appdata(self):
        d = migration.user_data_dir("win32", {"APPDATA": r"C:\X\Roaming"}, home=r"C:\Users\u")
        self.assertEqual(d, Path(r"C:\X\Roaming") / "ToDoList")

    def test_windows_without_appdata_uses_home(self):
        d = migration.user_data_dir("win32", {}, home="/home")
        self.assertEqual(d, Path("/home") / "AppData" / "Roaming" / "ToDoList")

    def test_macos(self):
        d = migration.user_data_dir("darwin", {}, home="/Users/u")
        self.assertEqual(d, Path("/Users/u") / "Library" / "Application Support" / "ToDoList")

    def test_linux_xdg(self):
        d = migration.user_data_dir("linux", {"XDG_DATA_HOME": "/xdg"}, home="/home/u")
        self.assertEqual(d, Path("/xdg") / "ToDoList")

    def test_linux_default(self):
        d = migration.user_data_dir("linux", {}, home="/home/u")
        self.assertEqual(d, Path("/home/u") / ".local" / "share" / "ToDoList")

    def test_legacy_locations(self):
        exe = self.root / "dist" / "To-Do List.exe"
        self.assertEqual(migration.legacy_locations(frozen=True, executable=str(exe)), [exe.resolve().parent])
        repo_root = Path(migration.__file__).resolve().parent.parent
        self.assertEqual(migration.legacy_locations(frozen=False), [repo_root])

    def test_env_var_wins_and_skips_relocation(self):
        target = self.root / "env"
        _write_sample(self.old)
        with mock.patch.dict(os.environ, {"TODO_DATA_DIR": str(target)}), \
                mock.patch.object(migration, "user_data_dir", return_value=self.new), \
                mock.patch.object(migration, "legacy_locations", return_value=[self.old]):
            result = migration.prepare_data_dir()
        self.assertEqual(result.directory, target)
        self.assertTrue(target.is_dir())  # created if missing
        self.assertEqual(list(self.new.iterdir()), [])  # user directory/relocation untouched
        self.assertEqual(result.schema_version, 2)

    def test_legacy_env_var_name_still_accepted(self):
        target = self.root / "legacy-env"
        env = {k: v for k, v in os.environ.items() if k != "TODO_DATA_DIR"}
        env["TODO_VERI_DIZINI"] = str(target)
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(migration, "user_data_dir", return_value=self.new), \
                mock.patch.object(migration, "legacy_locations", return_value=[self.old]):
            result = migration.prepare_data_dir()
        self.assertEqual(result.directory, target)
        self.assertEqual(result.status, "env")

    def test_without_env_uses_user_dir_not_legacy(self):
        target = self.root / "missing" / "ToDoList"
        _write_sample(self.old)
        env = {k: v for k, v in os.environ.items() if k not in ("TODO_DATA_DIR", "TODO_VERI_DIZINI")}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(migration, "user_data_dir", return_value=target), \
                mock.patch.object(migration, "legacy_locations", return_value=[self.old]):
            result = migration.prepare_data_dir()
        self.assertEqual(result.directory, target)
        self.assertTrue(target.is_dir())


class RelocationTest(TempDirTest):
    def test_first_relocation_copies_and_leaves_old_untouched(self):
        _write_sample(self.old)
        before = self.hashes(self.old, V1_FILES)

        result = migration.relocate(self.new, [self.old])

        self.assertEqual(result.status, "copied")
        self.assertEqual(result.directory, self.new)
        for name in V1_FILES:
            self.assertTrue((self.old / name).exists(), "old file must stay in place")
            self.assertEqual(_hash(self.old / name), before[name])
            self.assertEqual(_hash(self.new / name), before[name])
        marker = _load(self.new / migration.RELOCATION_MARKER)
        self.assertEqual(marker["status"], "copied")
        self.assertEqual({k["file"] for k in marker["files"]}, set(V1_FILES))

    def test_new_name_files_are_relocated_too(self):
        _write_sample(self.old, names=V2_FILES)
        result = migration.relocate(self.new, [self.old])
        self.assertEqual(result.status, "copied")
        for name in V2_FILES:
            self.assertEqual(_hash(self.new / name), _hash(self.old / name))

    def test_missing_files_are_fine(self):
        _write_sample(self.old, names=["gorevler.json"])
        result = migration.relocate(self.new, [self.old])
        self.assertEqual(result.status, "copied")
        self.assertTrue((self.new / "gorevler.json").exists())
        self.assertFalse((self.new / "kategoriler.json").exists())

    def test_marker_prevents_rerun(self):
        _write_sample(self.old)
        migration.relocate(self.new, [self.old])
        for name in V1_FILES:
            (self.new / name).unlink()  # even if the new directory becomes empty
        _write_sample(self.old, label="changed")
        result = migration.relocate(self.new, [self.old])
        self.assertEqual(result.status, "marker_exists")
        self.assertFalse(any((self.new / name).exists() for name in V1_FILES))

    def test_old_marker_name_is_recognised(self):
        # Data directories migrated by the previous version only have .gecis_tamam.json.
        _write_sample(self.old)
        (self.new / migration.LEGACY_RELOCATION_MARKER).write_text('{"durum": "kopyalandi"}', encoding="utf-8")
        result = migration.relocate(self.new, [self.old])
        self.assertEqual(result.status, "marker_exists")
        self.assertFalse(any((self.new / name).exists() for name in V1_FILES))
        self.assertFalse((self.new / migration.RELOCATION_MARKER).exists())

    def test_existing_data_is_not_overwritten(self):
        _write_sample(self.old)
        _write_sample(self.new, names=["gorevler.json"], label="new")
        before = _hash(self.new / "gorevler.json")

        result = migration.relocate(self.new, [self.old])

        self.assertEqual(result.status, "data_exists")
        self.assertEqual(result.directory, self.new)
        self.assertEqual(_hash(self.new / "gorevler.json"), before)
        self.assertFalse((self.new / "kategoriler.json").exists(), "missing files must not be mixed in either")

    def test_no_legacy_data_starts_empty(self):
        result = migration.relocate(self.new, [self.old])
        self.assertEqual(result.status, "no_legacy")
        self.assertEqual(result.directory, self.new)
        self.assertFalse((self.new / migration.RELOCATION_MARKER).exists())

    def test_corrupted_copy_falls_back_to_old_location(self):
        _write_sample(self.old)
        before = self.hashes(self.old, V1_FILES)

        def corrupting_copy(source, target):
            shutil.copy2(source, target)
            if target.name == "kategoriler.json":
                with open(target, "ab") as f:
                    f.write(b"corrupt")

        with mock.patch.object(migration, "_copy", corrupting_copy):
            result = migration.relocate(self.new, [self.old])

        self.assertEqual(result.status, "error")
        self.assertEqual(result.directory, self.old, "must keep reading from the old location")
        self.assertEqual(result.schema_version, 1, "old location is used with the old file format")
        self.assertTrue(result.error)
        for name in V1_FILES:
            self.assertEqual(_hash(self.old / name), before[name], "old files must not change")
            self.assertFalse((self.new / name).exists(), "a partial copy must not count as data")
        self.assertFalse((self.new / migration.RELOCATION_MARKER).exists())
        self.assertIn("MIGRATION ERROR", (self.new / migration.MIGRATION_LOG).read_text(encoding="utf-8"))

        # On the next launch the relocation is retried with a normal copy and succeeds.
        result = migration.relocate(self.new, [self.old])
        self.assertEqual(result.status, "copied")
        for name in V1_FILES:
            self.assertEqual(_hash(self.new / name), before[name])

    def test_copy_exception_falls_back_to_old_location(self):
        _write_sample(self.old)

        def failing(source, target):
            raise OSError("disk full")

        with mock.patch.object(migration, "_copy", failing):
            result = migration.relocate(self.new, [self.old])
        self.assertEqual(result.status, "error")
        self.assertEqual(result.directory, self.old)


class SchemaConversionTest(TempDirTest):
    def convert(self):
        return migration.convert_schema(self.new)

    def test_converts_into_new_files_and_leaves_old_untouched(self):
        _write_v1(self.new)
        before = self.hashes(self.new, V1_FILES)

        result = self.convert()

        self.assertEqual(result.status, "converted")
        self.assertEqual(result.schema_version, 2)
        self.assertEqual(self.hashes(self.new, V1_FILES), before, "old files must not change")
        items = _load(self.new / "items.json")
        self.assertEqual(items["schema_version"], 2)
        self.assertEqual(len(items["items"]), len(V1_ITEMS))
        self.assertEqual(items["items"][0], {"id": "a1", "title": "Örnek görev", "done": False, "year": 2030,
                                             "month": 1, "day": 31, "hour": 23, "minute": 59, "routine": False,
                                             "category": "Ders"})
        self.assertEqual(items["items"][2]["weekdays"], [0, 2, 4])
        self.assertEqual(items["items"][2]["frequency"], 1)
        self.assertEqual(items["items"][2]["streak"], 7)
        self.assertEqual(items["items"][1]["category"], "Kategorisiz", "values are not changed by the conversion")
        self.assertEqual(items["items"][3]["ekstra"], {"x": 1}, "unknown fields are kept")
        self.assertEqual(_load(self.new / "categories.json"), {"schema_version": 2, "categories": V1_CATEGORIES})
        self.assertEqual(_load(self.new / "completion_history.json")["completions"],
                         [{"date": "2030-01-01", "type": "routine"}, {"date": "2030-01-01", "type": "task"},
                          {"date": "2030-01-02", "type": "routine"}, {"date": "bozuk-tarih", "type": "başka"}])

        marker = _load(self.new / migration.SCHEMA_MARKER)
        self.assertEqual((marker["status"], marker["from_schema"], marker["to_schema"]), ("converted", 1, 2))
        by_source = {f["source"]: f for f in marker["files"]}
        self.assertEqual(set(by_source), set(V1_FILES))
        self.assertEqual(by_source["gorevler.json"]["records"], 4)
        self.assertEqual(by_source["gorevler.json"]["source_sha256"], before["gorevler.json"])
        self.assertEqual(by_source["gorevler.json"]["target_sha256"], _hash(self.new / "items.json"))
        self.assertNotIn("Örnek", json.dumps(marker, ensure_ascii=False), "the marker holds no user data")
        self.assertIn("Schema migration complete", (self.new / migration.MIGRATION_LOG).read_text(encoding="utf-8"))

    def test_storage_reads_converted_data_as_schema_2(self):
        _write_v1(self.new)
        self.convert()
        with mock.patch.object(storage, "DATA_DIR", self.new), mock.patch.object(storage, "SCHEMA_IN_USE", 2):
            self.assertEqual(storage.read_items(), schema.records_to_v2("items", V1_ITEMS))
            self.assertEqual(storage.read_categories(), V1_CATEGORIES)
            self.assertEqual([r["type"] for r in storage.read_history()], ["routine", "task", "routine", "başka"])

    def test_second_run_does_nothing(self):
        _write_v1(self.new)
        self.convert()
        after = self.hashes(self.new, V1_FILES + V2_FILES)
        result = self.convert()
        self.assertEqual(result.status, "marker_exists")
        self.assertEqual(self.hashes(self.new, V1_FILES + V2_FILES), after)

    def test_marker_prevents_rerun_even_if_new_files_are_deleted(self):
        _write_v1(self.new)
        self.convert()
        for name in V2_FILES:
            (self.new / name).unlink()
        result = self.convert()
        self.assertEqual(result.status, "marker_exists")
        self.assertFalse(any((self.new / n).exists() for n in V2_FILES), "old data must not come back")

    def test_existing_new_file_is_never_overwritten(self):
        _write_v1(self.new)
        mine = {"schema_version": 2, "items": [{"id": "x", "title": "already new"}]}
        (self.new / "items.json").write_text(json.dumps(mine), encoding="utf-8")
        before = _hash(self.new / "items.json")

        result = self.convert()

        self.assertEqual(result.status, "converted")
        self.assertEqual(_hash(self.new / "items.json"), before)
        self.assertTrue((self.new / "categories.json").exists(), "the missing ones are still converted")
        self.assertEqual(_load(self.new / migration.SCHEMA_MARKER)["kept_existing"], ["items.json"])

    def test_only_some_old_files(self):
        _write_v1(self.new, kinds=["items"])
        result = self.convert()
        self.assertEqual(result.status, "converted")
        self.assertTrue((self.new / "items.json").exists())
        self.assertFalse((self.new / "categories.json").exists())
        self.assertFalse((self.new / "completion_history.json").exists())

    def test_nothing_to_convert(self):
        result = self.convert()
        self.assertEqual(result.status, "no_legacy")
        self.assertEqual(result.schema_version, 2)
        self.assertEqual(list(self.new.iterdir()), [])

    def assertFailedSafely(self, result, before):
        self.assertEqual(result.status, "error")
        self.assertEqual(result.schema_version, 1, "must keep working with the old files")
        self.assertEqual(result.directory, self.new)
        self.assertTrue(result.error)
        self.assertEqual(self.hashes(self.new, V1_FILES), before, "old files must not change")
        self.assertFalse(any((self.new / n).exists() for n in V2_FILES), "a partial conversion must not count as data")
        self.assertFalse((self.new / migration.SCHEMA_MARKER).exists())
        self.assertIn("SCHEMA MIGRATION ERROR", (self.new / migration.MIGRATION_LOG).read_text(encoding="utf-8"))

    def test_corrupt_json_falls_back_to_old_files_and_retries(self):
        _write_v1(self.new)
        (self.new / "tamamlama_gecmisi.json").write_text('[{"tarih": "2030-01-01", ', encoding="utf-8")
        before = self.hashes(self.new, V1_FILES)

        result = self.convert()

        self.assertFailedSafely(result, before)
        set_aside = [p.name for p in self.new.iterdir() if migration.FAILED_SUFFIX in p.name]
        self.assertEqual(len(set_aside), 2, "items.json and categories.json were written first, then set aside")
        self.assertTrue(all(n.startswith(("items.json", "categories.json")) for n in set_aside))

        # Next start (file fixed): the conversion runs again and succeeds.
        _write_v1(self.new, kinds=["history"])
        self.assertEqual(self.convert().status, "converted")

    def test_wrong_file_shape_falls_back(self):
        _write_v1(self.new)
        (self.new / "gorevler.json").write_text('{"not": "a list"}', encoding="utf-8")
        before = self.hashes(self.new, V1_FILES)
        self.assertFailedSafely(self.convert(), before)

    def test_unverifiable_write_falls_back(self):
        _write_v1(self.new)
        before = self.hashes(self.new, V1_FILES)

        def lossy_write(path, content):
            content = copy.deepcopy(content)
            if path.name == "completion_history.json":
                content["completions"].pop()  # a record goes missing
            migration.jsonio.write_json_atomic(path, content)

        with mock.patch.object(migration, "_write_new_file", lossy_write):
            result = self.convert()
        self.assertFailedSafely(result, before)
        self.assertIn("record count", result.error_detail)

    def test_changed_value_is_detected(self):
        new = schema.serialize("items", schema.records_to_v2("items", V1_ITEMS))
        new["items"][2]["streak"] = 8
        with self.assertRaisesRegex(ValueError, "streak"):
            schema.verify_conversion("items", V1_ITEMS, new)
        new = schema.serialize("items", schema.records_to_v2("items", V1_ITEMS))
        new["items"][0]["extra"] = 1
        with self.assertRaisesRegex(ValueError, "fields differ"):
            schema.verify_conversion("items", V1_ITEMS, new)
        new = schema.serialize("history", schema.records_to_v2("history", V1_HISTORY))
        new["completions"][1]["type"] = "routine"
        with self.assertRaisesRegex(ValueError, "type"):
            schema.verify_conversion("history", V1_HISTORY, new)

    def test_write_error_falls_back(self):
        _write_v1(self.new)
        before = self.hashes(self.new, V1_FILES)
        with mock.patch.object(migration, "_write_new_file", side_effect=OSError("disk full")):
            self.assertFailedSafely(self.convert(), before)

    def test_old_files_keep_working_after_failure(self):
        # Fallback mode: the session reads AND writes the old files exactly like the previous version.
        _write_v1(self.new)
        with mock.patch.object(storage, "DATA_DIR", self.new), mock.patch.object(storage, "SCHEMA_IN_USE", 1):
            items = storage.read_items()
            self.assertEqual(items, schema.records_to_v2("items", V1_ITEMS))
            storage.write_items(items)
            storage.append_history({"date": "2030-01-03", "type": "task"})
        self.assertEqual(_load(self.new / "gorevler.json"), V1_ITEMS, "written back in the old format")
        self.assertEqual(_load(self.new / "tamamlama_gecmisi.json")[-1], {"tarih": "2030-01-03", "tip": "görev"})
        self.assertFalse(any((self.new / n).exists() for n in V2_FILES))


class StartupTest(TempDirTest):
    """prepare_data_dir: relocation + schema conversion together, as on the app's first start."""

    def start(self, legacy=None):
        env = {k: v for k, v in os.environ.items() if k not in ("TODO_DATA_DIR", "TODO_VERI_DIZINI")}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(migration, "user_data_dir", return_value=self.new), \
                mock.patch.object(migration, "legacy_locations", return_value=[legacy or self.old]):
            return migration.prepare_data_dir()

    def test_already_relocated_data_is_converted(self):
        # The situation after the previous version: data + .gecis_tamam.json + gecis.log in the user folder.
        _write_v1(self.new)
        (self.new / migration.LEGACY_RELOCATION_MARKER).write_text('{"durum": "kopyalandi"}', encoding="utf-8")
        (self.new / migration.LEGACY_MIGRATION_LOG).write_text("old log\n", encoding="utf-8")
        before = self.hashes(self.new, V1_FILES + (migration.LEGACY_RELOCATION_MARKER, migration.LEGACY_MIGRATION_LOG))

        result = self.start()

        self.assertEqual((result.status, result.schema_result.status), ("marker_exists", "converted"))
        self.assertEqual((result.directory, result.schema_version, result.error), (self.new, 2, None))
        self.assertEqual(self.hashes(self.new, tuple(before)), before)
        self.assertTrue(all((self.new / n).exists() for n in V2_FILES))
        # Third start: nothing happens.
        after = self.hashes(self.new, V1_FILES + V2_FILES)
        self.assertEqual(self.start().schema_result.status, "marker_exists")
        self.assertEqual(self.hashes(self.new, V1_FILES + V2_FILES), after)

    def test_old_exe_folder_is_relocated_then_converted(self):
        _write_v1(self.old)
        before = self.hashes(self.old, V1_FILES)

        result = self.start()

        self.assertEqual((result.status, result.schema_result.status), ("copied", "converted"))
        self.assertEqual(self.hashes(self.old, V1_FILES), before, "the .exe folder stays untouched")
        self.assertEqual(sorted(p.name for p in self.old.iterdir()), sorted(V1_FILES), "nothing written there")
        self.assertEqual(self.hashes(self.new, V1_FILES), before, "verbatim copies next to the new files")
        self.assertTrue(all((self.new / n).exists() for n in V2_FILES))

    def test_failed_relocation_does_not_convert_in_old_location(self):
        _write_v1(self.old)
        with mock.patch.object(migration, "_copy", side_effect=OSError("disk full")):
            result = self.start()
        self.assertEqual((result.status, result.directory, result.schema_version), ("error", self.old, 1))
        self.assertIsNone(result.schema_result)
        self.assertEqual(sorted(p.name for p in self.old.iterdir()), sorted(V1_FILES))

    def test_failed_conversion_reports_visible_error(self):
        _write_v1(self.new)
        (self.new / migration.LEGACY_RELOCATION_MARKER).write_text("{}", encoding="utf-8")
        with mock.patch.object(migration, "_write_new_file", side_effect=OSError("disk full")):
            result = self.start()
        self.assertEqual((result.schema_version, result.schema_result.status), (1, "error"))
        self.assertIn("disk full", result.error)


class ReadCompatibilityTest(TempDirTest):
    def test_new_file_name_with_old_content_is_read(self):
        # e.g. an old file renamed by hand: bare list with Turkish keys
        (self.new / "items.json").write_text(json.dumps(V1_ITEMS, ensure_ascii=False), encoding="utf-8")
        with mock.patch.object(storage, "DATA_DIR", self.new), mock.patch.object(storage, "SCHEMA_IN_USE", 2):
            self.assertEqual(storage.read_items(), schema.records_to_v2("items", V1_ITEMS))

    def test_round_trip_is_lossless(self):
        for kind in schema.KINDS:
            records = V1_CONTENT[kind]
            self.assertEqual(schema.records_to_v1(kind, schema.records_to_v2(kind, records)), records, kind)
            v2 = schema.records_to_v2(kind, records)
            self.assertEqual(schema.records_to_v2(kind, v2), v2, f"{kind}: converting twice changes nothing")

    def test_every_field_has_an_english_name(self):
        for old, new in list(schema.ITEM_FIELDS_V1_TO_V2.items()) + list(schema.HISTORY_FIELDS_V1_TO_V2.items()):
            self.assertRegex(new, r"^[a-z_]+$", old)
        converted = schema.records_to_v2("items", V1_ITEMS)
        self.assertFalse([k for r in converted for k in r if k in schema.ITEM_FIELDS_V1_TO_V2 and
                          schema.ITEM_FIELDS_V1_TO_V2[k] != k])

    def test_unknown_version_number_is_still_read(self):
        content = {"schema_version": 3, "categories": ["a"]}
        self.assertEqual(schema.parse("categories", content), ["a"])
        with self.assertRaises(ValueError):
            schema.parse("categories", {"no": "version"})


class MigrateCommandTest(TempDirTest):
    def run_cmd(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = migrate_data.main(list(args))
        return code, out.getvalue() + err.getvalue()

    def test_check_writes_nothing_and_shows_no_content(self):
        _write_v1(self.new)
        before = sorted((p.name, _hash(p)) for p in self.new.iterdir())
        code, output = self.run_cmd("--data-dir", str(self.new), "--check")
        self.assertEqual(code, 0)
        self.assertIn("pending", output)
        self.assertIn(_hash(self.new / "gorevler.json"), output)
        self.assertNotIn("Örnek", output)
        self.assertEqual(sorted((p.name, _hash(p)) for p in self.new.iterdir()), before)

    def test_convert_then_check(self):
        _write_v1(self.new)
        code, output = self.run_cmd("--data-dir", str(self.new))
        self.assertEqual(code, 0)
        self.assertIn("converted", output)
        self.assertRegex(output, r"items\.json\s+\d+ bytes\s+4 records")
        self.assertNotIn("Örnek", output)
        code, output = self.run_cmd("--data-dir", str(self.new), "--check")
        self.assertIn("already done", output)
        code, output = self.run_cmd("--data-dir", str(self.new))
        self.assertIn("marker_exists", output)

    def test_failure_exit_code(self):
        _write_v1(self.new)
        (self.new / "gorevler.json").write_text("[", encoding="utf-8")
        code, _ = self.run_cmd("--data-dir", str(self.new))
        self.assertEqual(code, 1)
        self.assertEqual(self.run_cmd("--data-dir", str(self.root / "missing"))[0], 2)


class OldVersionUsedAfterConversionTest(TempDirTest):
    """An older app version keeps writing the old files after the conversion: warn, and offer --redo/--keep-new."""

    def setUp(self):
        super().setUp()
        _write_v1(self.new)
        migration.convert_schema(self.new)
        self.new_hashes = self.hashes(self.new, V2_FILES)
        # the old app adds a task to gorevler.json
        (self.new / "gorevler.json").write_text(json.dumps(V1_ITEMS + [dict(V1_ITEMS[0], id="late")],
                                                           ensure_ascii=False), encoding="utf-8")

    def run_cmd(self, *args):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            code = migrate_data.main(["--data-dir", str(self.new), *args])
        return code, out.getvalue()

    def test_startup_warns_but_does_not_reconvert(self):
        result = migration.convert_schema(self.new)
        self.assertEqual(result.status, "marker_exists")
        self.assertEqual(result.changed_old_files, ["gorevler.json"])
        self.assertIn("--redo", result.warning)
        self.assertEqual(self.hashes(self.new, V2_FILES), self.new_hashes, "nothing rewritten automatically")
        self.assertIn("WARNING", self.run_cmd("--check")[1])

    def test_unchanged_old_files_give_no_warning(self):
        _write_v1(self.new)  # back to the converted content
        result = migration.convert_schema(self.new)
        self.assertEqual((result.changed_old_files, result.warning), ([], None))

    def test_redo_sets_new_files_aside_and_converts_again(self):
        old_hash = _hash(self.new / "gorevler.json")
        code, output = self.run_cmd("--redo")
        self.assertEqual(code, 0, output)
        self.assertEqual(len(_load(self.new / "items.json")["items"]), 5)
        self.assertEqual(_hash(self.new / "gorevler.json"), old_hash)
        aside = sorted(p.name for p in self.new.iterdir() if ".before-redo-" in p.name)
        self.assertEqual(len(aside), 4, aside)  # 3 data files + marker, renamed not deleted
        for name in V2_FILES:
            match = [n for n in aside if n.startswith(name + ".before-redo-")]
            self.assertEqual(_hash(self.new / match[0]), self.new_hashes[name])
        self.assertIsNone(migration.convert_schema(self.new).warning)

    def test_keep_new_stops_the_warning(self):
        code, output = self.run_cmd("--keep-new")
        self.assertEqual(code, 0)
        self.assertIn("gorevler.json", output)
        self.assertEqual(self.hashes(self.new, V2_FILES), self.new_hashes)
        self.assertIsNone(migration.convert_schema(self.new).warning)

    def test_redo_without_conversion_is_refused(self):
        shutil.rmtree(self.new)
        _write_v1(self.new)
        self.assertEqual(self.run_cmd("--redo")[0], 2)
        self.assertFalse((self.new / "items.json").exists())


class AtomicWriteTest(TempDirTest):
    def test_writes_and_leaves_no_temp_file(self):
        path = self.new / "items.json"
        migration.jsonio.write_json_atomic(path, [{"title": "a", "done": False}])
        self.assertEqual(_load(path)[0]["title"], "a")
        self.assertEqual([p.name for p in self.new.iterdir()], ["items.json"])

    def test_interrupted_write_keeps_real_file(self):
        path = self.new / "items.json"
        migration.jsonio.write_json_atomic(path, [{"title": "real"}])
        before = _hash(path)
        with self.assertRaises(TypeError):
            migration.jsonio.write_json_atomic(path, [{"title": object()}])  # not serialisable → interrupted
        self.assertEqual(_hash(path), before)
        self.assertFalse(path.with_suffix(".json.tmp").exists())


class SampleDataTest(unittest.TestCase):
    def test_sample_data_written_to_temp_dir(self):
        import sample_data
        for lang in ("tr", "en"):
            self.assertEqual(sample_data.create_demo_data(lang), lang)
            self.assertEqual(len(storage.read_items()), 21)
            self.assertEqual(storage.read_categories(), sample_data.CATEGORIES[lang])
            self.assertTrue(storage.read_history())
        self.assertTrue(str(storage.ITEMS_FILE).startswith(_SESSION_DIR))

    def test_sample_data_uses_schema_2(self):
        import sample_data
        sample_data.create_demo_data("tr")
        for kind in schema.KINDS:
            content = _load(storage.data_file(kind))
            self.assertEqual(content["schema_version"], 2, kind)
        items = _load(storage.ITEMS_FILE)["items"]
        allowed = set(schema.ITEM_FIELDS_V2_TO_V1)
        self.assertEqual([k for item in items for k in item if k not in allowed], [])
        self.assertTrue(any("weekdays" in item for item in items))
        self.assertEqual({r["type"] for r in storage.read_history()}, {"routine", "task"})

    def test_every_name_key_used_exists_in_every_language(self):
        # Root cause of a past KeyError: a name key was removed from one table but still used by
        # create_demo_data. Both languages must define the same keys, and generation must not raise.
        import sample_data
        self.assertEqual(set(sample_data._NAMES["tr"]), set(sample_data._NAMES["en"]))
        self.assertEqual(len(sample_data.CATEGORIES["tr"]), len(sample_data.CATEGORIES["en"]))
        for lang in ("tr", "en"):
            sample_data.create_demo_data(lang)
            names = [o["title"] for o in storage.read_items()]
            self.assertEqual(len(names), len(set(names)), "item names are unique")
            used = {o["category"] for o in storage.read_items() if o["category"]}
            self.assertLessEqual(used, set(sample_data.CATEGORIES[lang]))
            self.assertNotIn("Duolingo", names + storage.read_categories())

    def test_turkish_sample_data_unchanged(self):
        import sample_data
        sample_data.create_demo_data("tr")
        items = storage.read_items()
        self.assertEqual(sample_data.CATEGORIES["tr"], ["Spor", "Dil", "Yazılım", "Ders", "Verimlilik", "Oyun"])
        self.assertEqual(items[0]["title"], "Python proje sunumunu hazırla")
        self.assertEqual(items[-1]["title"], "Oyun saati (en fazla 1 sa)")
        self.assertEqual(items[-1]["category"], "Oyun")

    def test_english_sample_data_has_no_turkish_names(self):
        import sample_data
        sample_data.create_demo_data("en")
        names = [o["title"] for o in storage.read_items()] + storage.read_categories()
        self.assertFalse([n for n in names if any(ch in n for ch in "çğıöşüÇĞİÖŞÜ")])


if __name__ == "__main__":
    unittest.main()
