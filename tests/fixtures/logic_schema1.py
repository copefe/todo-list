# Reference copy of gui/logic.py from commit 89bd486 (schema 1, Turkish field names), kept verbatim
# below this header. tests/test_schema_equivalence.py runs it on schema-1 data and the current
# logic.py on the same data in schema 2, and requires identical results. Do not edit.
import calendar
import datetime
import uuid
from collections import Counter

# Stored item fields (görev, tamamlandı, yıl, ay, gün, saat, dakika, rutin, kategori, sıklık,
# streak, hafta_gunleri) are on-disk data and are intentionally still Turkish.


def now() -> datetime.datetime:
    return datetime.datetime.now()


def _item_datetime(item: dict) -> datetime.datetime:
    return datetime.datetime(item["yıl"], item["ay"], item["gün"], item["saat"], item["dakika"])


def fill_missing_fields(items: list) -> list:
    for item in items:
        if not item.get("id"):
            item["id"] = uuid.uuid4().hex
        # "Kategorisiz" is a legacy stored value meaning "no category".
        if item.get("kategori") == "Kategorisiz" or "kategori" not in item:
            item["kategori"] = ""
        if item.get("rutin", False) and "streak" not in item:
            item["streak"] = 0
    return items


def order_tasks(tasks: list, current: datetime.datetime) -> list:
    active = []
    overdue = []
    for item in tasks:
        remaining = _item_datetime(item) - current
        if remaining.days >= 0:
            active.append(item)
        else:
            overdue.append(item)
    return active + overdue


def snap_to_weekday(date: datetime.datetime, weekdays: list) -> datetime.datetime:
    """Moves to the first selected weekday on or after `date`; the time stays the same. 0=Mon ... 6=Sun."""
    for i in range(7):
        candidate = date + datetime.timedelta(days=i)
        if candidate.weekday() in weekdays:
            return candidate
    return date


def _next_trigger(item: dict, current: datetime.datetime) -> datetime.datetime:
    # If weekdays are selected, the next selected day; otherwise every `sıklık` days.
    weekdays = item.get("hafta_gunleri")
    if weekdays:
        return snap_to_weekday(current + datetime.timedelta(days=1), weekdays)
    return current + datetime.timedelta(days=item["sıklık"])


def advance_routines(routines: list, current: datetime.datetime) -> list:
    # NOTE: no completion-history record is written here - only the streak is computed.
    # The history record is written in api.complete_items() with the date of the moment
    # the user actually marked it done (not the cycle end date) - otherwise a routine
    # whose cycle ends at midnight could advance to the next day before the user had
    # marked it, and the completion looked as if it was written to that "next day".
    for item in routines:
        next_trigger = _item_datetime(item)
        remaining = next_trigger - current

        was_completed = item.get("tamamlandı", False)
        cycles_passed = 0

        while remaining.days < 0:
            next_trigger = _next_trigger(item, next_trigger)
            remaining = next_trigger - current
            cycles_passed += 1

        if cycles_passed > 0:
            item["yıl"] = next_trigger.year
            item["ay"] = next_trigger.month
            item["gün"] = next_trigger.day
            item["saat"] = next_trigger.hour
            item["dakika"] = next_trigger.minute

            if cycles_passed == 1 and was_completed:
                item["streak"] = item.get("streak", 0) + 1
            else:
                item["streak"] = 0

            item["tamamlandı"] = False

    return routines


def compute_bucket(count: int) -> int:
    if count <= 0:
        return 0
    if count <= 3:
        return 1
    if count <= 5:
        return 2
    return 3


def weekly_summary(records: list, week_start: datetime.date) -> dict:
    days = [(week_start + datetime.timedelta(days=i)).isoformat() for i in range(7)]
    counter = {day: 0 for day in days}
    routines = {day: 0 for day in days}
    for record in records:
        if record["tarih"] in counter:
            counter[record["tarih"]] += 1
            if record.get("tip") == "rutin":
                routines[record["tarih"]] += 1
    counts = [counter[day] for day in days]
    buckets = [compute_bucket(count) for count in counts]
    # routines/tasks: per-day breakdown for the tooltip (response only; the record schema does not change)
    return {"days": days, "counts": counts, "buckets": buckets,
            "routines": [routines[day] for day in days], "tasks": [counter[day] - routines[day] for day in days]}


def monthly_summary(records: list, year: int, month: int) -> dict:
    day_count = calendar.monthrange(year, month)[1]
    counter = {}
    routines = {}
    for record in records:
        try:
            date = datetime.date.fromisoformat(record["tarih"])
        except ValueError:
            continue
        if date.year == year and date.month == month:
            counter[date.day] = counter.get(date.day, 0) + 1
            if record.get("tip") == "rutin":
                routines[date.day] = routines.get(date.day, 0) + 1

    days = []
    for day in range(1, day_count + 1):
        count = counter.get(day, 0)
        routine = routines.get(day, 0)
        days.append({"day": day, "count": count, "bucket": compute_bucket(count), "routines": routine, "tasks": count - routine})
    return {"days": days}


def compute_donut(items: list, categories: list) -> list:
    counter = Counter(item["kategori"] for item in items if item.get("kategori"))
    total = sum(counter.values()) or 1
    return [
        {"category": category, "count": counter.get(category, 0), "percent": round(counter.get(category, 0) / total * 100, 1)}
        for category in categories
    ]
