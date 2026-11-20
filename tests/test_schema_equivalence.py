"""Schema 1 and schema 2 must give exactly the same results on the same data.

1. Logic level: tests/fixtures/logic_schema1.py (verbatim logic.py of the last schema-1 version) runs
   on schema-1 records, the current gui/logic.py runs on the same records converted to schema 2.
   Results are compared after converting the old output with schema.py. Covered: routine
   advancing and streaks (midnight crossing, weekday routines, every-N-days, missed cycles) swept over
   many "now" values, due-date ordering, history summaries (past completions, malformed dates), donut,
   missing-field filling.
2. API level: the real Api runs (a) on schema-1 files in fallback mode, (b) on schema-2 files, and
   (c) on schema-1 files converted by the migration; every response and the stored data must match.

All data is made up; everything runs in temporary folders.
"""
import copy
import datetime
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import ROOT  # noqa: E402  (must come before gui imports)

import api  # noqa: E402
import logic  # noqa: E402
import migration  # noqa: E402
import schema  # noqa: E402
import storage  # noqa: E402

_spec = importlib.util.spec_from_file_location("logic_schema1", ROOT / "tests" / "fixtures" / "logic_schema1.py")
old_logic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(old_logic)

DT = datetime.datetime


def v1_item(id, due, routine=False, done=False, frequency=1, streak=None, weekdays=None, category="Ders"):
    item = {"id": id, "görev": f"Görev {id}", "tamamlandı": done, "yıl": due.year, "ay": due.month,
            "gün": due.day, "saat": due.hour, "dakika": due.minute, "rutin": routine, "kategori": category}
    if routine:
        item["sıklık"] = frequency
        if streak is not None:
            item["streak"] = streak
        if weekdays:
            item["hafta_gunleri"] = weekdays
    return item


def to_v2(records, kind="items"):
    return schema.records_to_v2(kind, copy.deepcopy(records))


# Routines exercising every branch of advance_routines. 2026-03-09 is a Monday.
ROUTINES = [
    v1_item("midnight", DT(2026, 3, 9, 23, 30), routine=True, done=True, streak=4),
    v1_item("midnight-undone", DT(2026, 3, 9, 23, 59), routine=True, streak=4),
    v1_item("exactly-midnight", DT(2026, 3, 10, 0, 0), routine=True, done=True, streak=1),
    v1_item("every-3-days", DT(2026, 3, 9, 7, 15), routine=True, done=True, frequency=3, streak=9),
    v1_item("weekdays", DT(2026, 3, 9, 8, 0), routine=True, done=True, streak=12, weekdays=[0, 2, 4]),
    v1_item("weekend", DT(2026, 3, 14, 10, 0), routine=True, done=True, streak=2, weekdays=[5, 6]),
    v1_item("sunday-only", DT(2026, 3, 15, 22, 0), routine=True, streak=0, weekdays=[6]),
    v1_item("no-streak-yet", DT(2026, 3, 9, 12, 0), routine=True, done=True),
    v1_item("month-end", DT(2026, 2, 28, 23, 45), routine=True, done=True, frequency=2, streak=3),
]

TASKS = [
    v1_item("t-past", DT(2026, 3, 8, 9, 0)),
    v1_item("t-midnight", DT(2026, 3, 9, 23, 59)),
    v1_item("t-next-day", DT(2026, 3, 10, 0, 0), done=True),
    v1_item("t-later", DT(2026, 3, 20, 18, 30), category="Kategorisiz"),
    v1_item("t-long-ago", DT(2025, 12, 31, 23, 59), category=""),
]

HISTORY = (
    [{"tarih": f"2026-03-{d:02d}", "tip": "rutin"} for d in (2, 2, 3, 9, 9, 9, 10, 15, 31)]
    + [{"tarih": f"2026-03-{d:02d}", "tip": "görev"} for d in (1, 9, 10, 10, 16)]
    + [{"tarih": "2026-02-28", "tip": "rutin"}, {"tarih": "2025-03-09", "tip": "görev"},
       {"tarih": "not-a-date", "tip": "rutin"}, {"tarih": "2026-04-01", "tip": "görev"}]
)


def sweep_times():
    """'now' values from before the first due date to several weeks later, hitting every hour and
    the minutes around midnight."""
    start = DT(2026, 2, 27, 0, 0)
    times = [start + datetime.timedelta(minutes=97 * i) for i in range(int(24 * 60 * 30 / 97))]
    for day in range(8, 18):
        for hm in ((23, 29), (23, 30), (23, 31), (23, 59), (0, 0), (0, 1)):
            times.append(DT(2026, 3, day, *hm))
    return times


class LogicEquivalenceTest(unittest.TestCase):
    def test_reference_is_the_schema_1_logic(self):
        self.assertIn('item["yıl"]', Path(_spec.origin).read_text(encoding="utf-8"))
        self.assertNotIn('"yıl"', Path(logic.__file__).read_text(encoding="utf-8"))

    def test_advance_routines_streaks_and_due_dates(self):
        checked = 0
        for now in sweep_times():
            old = old_logic.advance_routines(copy.deepcopy(ROUTINES), now)
            new = logic.advance_routines(to_v2(ROUTINES), now)
            self.assertEqual(new, to_v2(old), f"now={now}")
            checked += 1
        self.assertGreater(checked, 400)

    def test_repeated_advancing_day_by_day(self):
        # The app advances on every get_state: simulate opening it at changing times over five weeks,
        # completing some routines in between, on both schemas side by side.
        old, new = copy.deepcopy(ROUTINES), to_v2(ROUTINES)
        now = DT(2026, 3, 9, 6, 0)
        for step in range(5 * 24 // 5):
            now += datetime.timedelta(hours=5, minutes=13)
            old = old_logic.advance_routines(old, now)
            new = logic.advance_routines(new, now)
            if step % 3 == 0:
                for o, n in zip(old, new):
                    if o["id"] in ("midnight", "weekdays", "every-3-days"):
                        o["tamamlandı"] = True
                        n["done"] = True
            self.assertEqual(new, to_v2(old), f"step {step}, now={now}")

    def test_midnight_crossing_explicitly(self):
        before = DT(2026, 3, 9, 23, 59)
        after = DT(2026, 3, 10, 0, 5)
        for now in (before, after):
            old = old_logic.advance_routines(copy.deepcopy(ROUTINES[:3]), now)
            new = logic.advance_routines(to_v2(ROUTINES[:3]), now)
            self.assertEqual(new, to_v2(old))
        # Sanity check of what "identical" means here: one cycle passed over midnight -> the completed
        # routine keeps its streak (+1); the uncompleted one resets; two passed cycles reset as well.
        moved = {r["id"]: r for r in logic.advance_routines(to_v2(ROUTINES[:3]), after)}
        self.assertEqual((moved["midnight"]["streak"], moved["midnight"]["done"]), (5, False))
        self.assertEqual((moved["midnight"]["day"], moved["midnight"]["hour"]), (10, 23))
        self.assertEqual(moved["midnight-undone"]["streak"], 0)
        self.assertEqual(moved["exactly-midnight"]["streak"], 2, "due 00:00 and completed: passed 5 minutes ago")
        two_days = {r["id"]: r for r in logic.advance_routines(to_v2(ROUTINES[:1]), DT(2026, 3, 11, 0, 5))}
        self.assertEqual(two_days["midnight"]["streak"], 0)

    def test_weekday_routine_snaps_to_selected_days(self):
        for now in (DT(2026, 3, 10, 9), DT(2026, 3, 11, 7, 59), DT(2026, 3, 11, 8, 1), DT(2026, 3, 13, 23), DT(2026, 3, 16, 9)):
            old = old_logic.advance_routines([copy.deepcopy(ROUTINES[4])], now)
            new = logic.advance_routines(to_v2([ROUTINES[4]]), now)
            self.assertEqual(new, to_v2(old), str(now))
            self.assertIn(DT(new[0]["year"], new[0]["month"], new[0]["day"]).weekday(), [0, 2, 4])

    def test_task_order_by_due_date(self):
        for now in sweep_times()[::7]:
            old = old_logic.order_tasks(copy.deepcopy(TASKS), now)
            new = logic.order_tasks(to_v2(TASKS), now)
            self.assertEqual([t["id"] for t in new], [t["id"] for t in old], str(now))
            self.assertEqual(new, to_v2(old))

    def test_fill_missing_fields(self):
        items = copy.deepcopy(TASKS + ROUTINES)
        del items[0]["kategori"]
        items.append({"görev": "no id", "tamamlandı": False, "rutin": True, "sıklık": 1,
                      "yıl": 2026, "ay": 3, "gün": 9, "saat": 1, "dakika": 0})
        with mock.patch("uuid.uuid4") as fake:
            fake.return_value.hex = "fixed"
            old = old_logic.fill_missing_fields(copy.deepcopy(items))
            new = logic.fill_missing_fields(to_v2(items))
        self.assertEqual(new, to_v2(old))
        self.assertEqual(new[3]["category"], "", "legacy 'Kategorisiz' still means no category")

    def test_history_summaries(self):
        history_v2 = to_v2(HISTORY, "history")
        for week_start in (datetime.date(2026, 3, 2), datetime.date(2026, 3, 9), datetime.date(2026, 2, 23),
                           datetime.date(2026, 3, 30)):
            self.assertEqual(logic.weekly_summary(history_v2, week_start), old_logic.weekly_summary(HISTORY, week_start))
        for year, month in ((2026, 3), (2026, 2), (2025, 3), (2026, 4)):
            self.assertEqual(logic.monthly_summary(history_v2, year, month), old_logic.monthly_summary(HISTORY, year, month))
        week = logic.weekly_summary(history_v2, datetime.date(2026, 3, 9))
        self.assertEqual((week["counts"][0], week["routines"][0], week["tasks"][0]), (4, 3, 1))

    def test_donut(self):
        categories = ["Ders", "Spor", "Boş"]
        items = copy.deepcopy(TASKS + ROUTINES)
        items[0]["kategori"] = "Spor"
        self.assertEqual(logic.compute_donut(to_v2(items), categories), old_logic.compute_donut(items, categories))


class ApiEquivalenceTest(unittest.TestCase):
    """The same user actions through the real Api on schema-1 files, schema-2 files and migrated files."""

    NOW = DT(2026, 3, 9, 23, 50)

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="todolist-test-eq-"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def make_dir(self, name, version):
        directory = self.root / name
        directory.mkdir()
        content = {"items": TASKS + ROUTINES, "categories": ["Ders", "Spor"], "history": HISTORY}
        for kind, records in content.items():
            data = copy.deepcopy(records) if version == 1 else schema.serialize(kind, to_v2(records, kind))
            (directory / schema.FILE_NAMES[version][kind]).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return directory

    def scenario(self, directory, version):
        """Runs a fixed sequence of API calls; returns every response plus the final stored data."""
        out = []
        clock = {"now": self.NOW}
        with mock.patch.object(storage, "DATA_DIR", directory), mock.patch.object(storage, "SCHEMA_IN_USE", version), \
                mock.patch.object(logic, "now", lambda: clock["now"]), mock.patch("uuid.uuid4") as fake:
            fake.return_value.hex = "new-id"
            a = api.Api()
            out.append(a.get_state())
            out.append(a.complete_items(["weekdays", "t-midnight", "every-3-days"]))
            clock["now"] = DT(2026, 3, 10, 0, 10)  # past midnight
            out.append(a.get_state())
            out.append(a.complete_items(["midnight", "weekdays"]))
            out.append(a.update_item("t-later", {"title": "Renamed", "category": "Spor"}))
            out.append(a.update_item("weekend", {"weekdays": [6]}))
            out.append(a.update_item("every-3-days", {"sıklık": 2}))  # schema-1 key still accepted
            out.append(a.add_task("New", 2026, 3, 12, 9, 0, "Yeni"))
            out.append(a.add_routine("New routine", 1, 2026, 3, 11, 7, 30, "", [1, 3]))
            clock["now"] = DT(2026, 3, 16, 12, 0)  # a week later, several missed cycles
            out.append(a.get_state())
            out.append(a.weekly_completions("2026-03-09"))
            out.append(a.weekly_completions())
            out.append(a.monthly_completions(2026, 3))
            out.append(a.donut_data("task"))
            out.append(a.donut_data("routine"))
            out.append(a.delete_category("Ders"))
            out.append(a.delete_items(["t-past"]))
            out.append(a.get_state())
            stored = {"items": storage.read_items(), "categories": storage.read_categories(),
                      "history": storage.read_history()}
        return out, stored

    def test_old_files_new_files_and_migrated_files_behave_identically(self):
        old_dir = self.make_dir("schema1", 1)
        new_dir = self.make_dir("schema2", 2)
        migrated_dir = self.make_dir("migrated", 1)
        self.assertEqual(migration.convert_schema(migrated_dir).status, "converted")

        old = self.scenario(old_dir, 1)
        new = self.scenario(new_dir, 2)
        migrated = self.scenario(migrated_dir, 2)

        self.assertEqual(new, old)
        self.assertEqual(migrated, old)
        # Each mode wrote its own file format.
        self.assertIsInstance(json.loads((old_dir / "gorevler.json").read_text(encoding="utf-8")), list)
        self.assertFalse((old_dir / "items.json").exists())
        self.assertEqual(json.loads((new_dir / "items.json").read_text(encoding="utf-8"))["schema_version"], 2)
        self.assertFalse((new_dir / "gorevler.json").exists())

    def test_history_records_written_by_the_api(self):
        new_dir = self.make_dir("schema2", 2)
        _, stored = self.scenario(new_dir, 2)
        added = stored["history"][len(HISTORY):]
        # get_state stores tasks before routines, so the task is recorded first; the routine completed
        # after midnight is dated the 10th (the day it was marked, not its cycle).
        self.assertEqual(added, [{"date": "2026-03-09", "type": "task"}, {"date": "2026-03-09", "type": "routine"},
                                 {"date": "2026-03-09", "type": "routine"}, {"date": "2026-03-10", "type": "routine"}])


if __name__ == "__main__":
    unittest.main()
