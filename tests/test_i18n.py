"""Translation tests: locale files, keys used in code, and "the Turkish UI did not change".

Run (from the repo root):  python -m unittest discover -s tests -v
The pixel-free runtime check (old vs new UI rendered in a browser) is described in veri-ayirma-HANDOFF.md.
"""
import json
import re
import unittest

from support import WEB, GUI, ROOT  # noqa: E402  (must come before gui imports)

import api  # noqa: E402
import i18n  # noqa: E402
import migration  # noqa: E402

TR = json.loads((WEB / "locales" / "tr.json").read_text(encoding="utf-8"))
EN = json.loads((WEB / "locales" / "en.json").read_text(encoding="utf-8"))
BEFORE = json.loads((ROOT / "tests" / "fixtures" / "tr_ui_texts_before_i18n.json").read_text(encoding="utf-8"))
PLURAL = re.compile(r"_(zero|one|two|few|many|other)$")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
EDGE = " \t\n·,;:.()–—-→"

# Month/day names now come from Intl.DateTimeFormat("tr") instead of hard-coded arrays; the browser
# check compares them. Listed here so the fixture stays complete.
INTL_NAMES = {
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
    "Pazar", "Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi",
    "Paz", "Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "P", "S", "Ç", "C",
}
UNTRANSLATED = {"To-Do List"}  # app name, same in every language
# Texts added after the i18n step: they did not exist in the old UI, so the fixture cannot cover them.
ADDED_LATER = {"migration.schemaError", "migration.oldFilesChanged"}


def base_key(key):
    return PLURAL.sub("", key)


def en_has(key):
    return key in EN or (f"{key}_one" in EN and f"{key}_other" in EN)


class LocaleFilesTest(unittest.TestCase):
    def test_values_are_non_empty_strings(self):
        for name, table in (("tr", TR), ("en", EN)):
            for key, value in table.items():
                self.assertIsInstance(value, str, f"{name}:{key}")
                self.assertTrue(value.strip(), f"{name}:{key} is empty")

    def test_english_has_every_key(self):
        missing = [k for k in TR if not en_has(k)]
        self.assertEqual(missing, [], "keys missing in en.json")

    def test_english_has_no_unknown_keys(self):
        unknown = [k for k in EN if base_key(k) not in TR]
        self.assertEqual(unknown, [], "en.json keys that tr.json does not have")

    def test_turkish_has_no_plural_variants(self):
        self.assertEqual([k for k in TR if PLURAL.search(k)], [])

    def test_placeholders_match(self):
        for key, value in TR.items():
            expected = set(PLACEHOLDER.findall(value))
            variants = [k for k in EN if base_key(k) == key]
            for variant in variants:
                got = set(PLACEHOLDER.findall(EN[variant]))
                if variant.endswith("_one"):
                    self.assertLessEqual(got, expected, variant)  # "every day" may drop {n}
                else:
                    self.assertEqual(got, expected, variant)


class KeysUsedInCodeTest(unittest.TestCase):
    def assertKnown(self, keys, where):
        missing = sorted(k for k in keys if k not in TR or not en_has(k))
        self.assertEqual(missing, [], f"unknown keys in {where}")

    def test_app_js_keys(self):
        js = (WEB / "app.js").read_text(encoding="utf-8")
        namespaces = "|".join(sorted({k.split(".")[0] for k in TR}))
        literal = set(re.findall(rf'"((?:{namespaces})\.[A-Za-z0-9_.]+)"', js))
        literal = {k for k in literal if not k.endswith(".")}
        self.assertGreater(len(literal), 100)
        self.assertKnown(literal, "app.js")
        # Keys built from state values: msg("tab." + tab), msg("sort.field." + field), msg("sort.dir." + dir)
        self.assertIn('msg("tab." + tab)', js)
        self.assertKnown({f"tab.{v}" for v in ("active", "done", "all")}, "tab.*")
        self.assertKnown({f"sort.field.{v}" for v in ("remaining", "name", "category", "streak")}, "sort.field.*")
        self.assertKnown({f"sort.dir.{v}" for v in ("asc", "desc")}, "sort.dir.*")

    def test_index_html_keys(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        keys = set(re.findall(r'data-i18n(?:-title|-aria-label|-placeholder)?="([^"]+)"', html))
        self.assertGreater(len(keys), 30)
        self.assertKnown(keys, "index.html")

    def test_index_html_default_text_is_turkish_value(self):
        # The built-in markup still shows the Turkish text (identical to tr.json) before translations load.
        html = (WEB / "index.html").read_text(encoding="utf-8")
        for key, text in re.findall(r'data-i18n="([^"]+)"[^>]*>([^<]*)<', html):
            self.assertEqual(text, TR[key], key)

    def test_python_keys(self):
        keys = set()
        for path in GUI.glob("*.py"):
            src = path.read_text(encoding="utf-8")
            keys |= set(re.findall(r'"(err\.[A-Za-z]+)"', src))
            keys |= set(re.findall(r'translate\(\s*"([\w.]+)"', src))
        self.assertGreater(len(keys), 10)
        self.assertKnown(keys, "gui/*.py")


class TurkishUnchangedTest(unittest.TestCase):
    """tr.json must hold the pre-i18n Turkish texts word for word (fixture: tests/fixtures)."""

    def test_every_old_text_is_in_tr_json(self):
        values = list(TR.values())
        missing = []
        for fragment in BEFORE:
            if fragment in INTL_NAMES or fragment in UNTRANSLATED:
                continue
            core = fragment.strip(EDGE)
            if core and not any(core in v for v in values):
                missing.append(fragment)
        self.assertEqual(missing, [], "old Turkish texts that tr.json lost")

    def test_every_tr_text_comes_from_the_old_ui(self):
        # Each literal piece of a tr.json value must be fully covered by old fragments. Texts that the old
        # code glued together (e.g. `${"Görev"} ekle`, `Henüz ${noun} yok.`) are covered by their old parts.
        cores = sorted({f.strip(EDGE) for f in BEFORE if f not in INTL_NAMES} - {""}, key=len, reverse=True)
        unknown = []
        for key, value in TR.items():
            if key in ADDED_LATER:
                continue
            for piece in PLACEHOLDER.split(value)[::2]:
                rest = piece
                for core in cores:
                    rest = rest.replace(core, " ")
                if re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", rest):
                    unknown.append((key, piece, rest.strip()))
        self.assertEqual(unknown, [], "tr.json texts that did not exist before (typo?)")


class PythonTranslateTest(unittest.TestCase):
    def test_normalize(self):
        for value in ("tr", "TR", "tr-TR", "tr_TR.UTF-8", "Turkish_Türkiye"):
            self.assertEqual(i18n.normalize(value), "tr", value)
        for value in ("en", "en-US", "de-DE", "", None):
            self.assertEqual(i18n.normalize(value), "en", value)
        self.assertIn(i18n.system_language(), ("tr", "en"))

    def test_todo_lang_override(self):
        import os
        from pathlib import Path
        from unittest import mock
        index = Path("web") / "index.html"
        for value, lang in (("en", "en"), ("tr", "tr"), ("EN", "en"), (" tr ", "tr")):
            with mock.patch.dict(os.environ, {"TODO_LANG": value}):
                self.assertEqual(i18n.system_language(), lang)
                self.assertTrue(i18n.page_url(index).endswith(f"?lang={lang}"))
        for value in ("", "de", "xx"):
            with mock.patch.dict(os.environ, {"TODO_LANG": value}):
                self.assertEqual(i18n.page_url(index), str(index))
        env = {k: v for k, v in os.environ.items() if k != "TODO_LANG"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(i18n.page_url(index), str(index))
        js = (WEB / "i18n.js").read_text(encoding="utf-8")
        self.assertIn('get("lang")', js)
        self.assertLess(js.index('get("lang")'), js.index("localStorage.getItem"))

    def test_translate(self):
        self.assertEqual(i18n.translate("err.invalidDate", "tr"), "Geçersiz tarih.")
        self.assertEqual(i18n.translate("err.invalidDate", "en"), "Invalid date.")
        self.assertEqual(i18n.translate("no.such.key", "tr"), "no.such.key")

    def test_migration_message_turkish_unchanged(self):
        self.assertEqual(
            migration.relocation_error_message("disk dolu", "C:\\eski", "tr"),
            "Veriler yeni klasöre kopyalanamadı (disk dolu). Uygulama eski konumdaki verilerle çalışıyor: C:\\eski")
        self.assertIn("could not be copied", migration.relocation_error_message("x", "y", "en"))
        self.assertEqual(i18n.translate("migration.title", "tr"), "To-Do List - Veri geçişi")
        self.assertIn("disk dolu", migration.schema_error_message("disk dolu", "C:\\veri", "tr"))
        self.assertIn("could not be converted", migration.schema_error_message("x", "y", "en"))

    def test_api_returns_known_error_keys(self):
        a = api.Api()
        results = [
            a.add_task("", 2030, 1, 1, 10, 0, ""),
            a.add_task("x", 2030, 2, 30, 10, 0, ""),
            a.add_task("x", 2000, 1, 1, 10, 0, ""),
            a.add_routine("", 1, 2030, 1, 1, 10, 0, ""),
            a.add_routine("x", 0, 2030, 1, 1, 10, 0, ""),
            a.add_routine("x", "a", 2030, 1, 1, 10, 0, ""),
            a.add_routine("x", 1, 2030, 1, 1, 10, 0, "", [9]),
            a.add_routine("x", 2, 2030, 1, 1, 10, 0, "", [1]),
            a.update_item("missing", {}),
            a.add_category(""),
        ]
        a.add_category("Test-category")
        results.append(a.add_category("Test-category"))
        expected = ["err.taskNameEmpty", "err.invalidDate", "err.dateInPast", "err.routineNameEmpty",
                    "err.frequencyPositive", "err.invalidFrequency", "err.invalidWeekdays",
                    "err.weekdaysAndFrequency", "err.itemNotFound", "err.categoryNameEmpty", "err.categoryExists"]
        self.assertEqual([r["error"] for r in results], expected)
        for r in results:
            self.assertFalse(r["success"])
            self.assertIn(r["error"], TR)


if __name__ == "__main__":
    unittest.main()
