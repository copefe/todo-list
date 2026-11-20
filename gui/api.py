"""Methods exposed to the web UI through pywebview (window.pywebview.api.<name>).

Items are returned with the schema-2 field names (schema.py): id, title, done, year, month, day,
hour, minute, routine, category, frequency, streak, weekdays. The `fields` dict passed to
update_item uses the same names; the schema-1 (Turkish) names are still accepted there.

Errors are returned as message keys ("err.*" in web/locales/*.json); the UI translates them.
"""
import datetime
import uuid

import logic
import schema
import storage

_EDITABLE_FIELDS = {"title", "category", "year", "month", "day", "hour", "minute", "frequency", "weekdays"}


_DATE_FIELDS = ("year", "month", "day", "hour", "minute")
_PAST_TOLERANCE = datetime.timedelta(minutes=1)


def _is_in_past(year, month, day, hour, minute) -> bool:
    return datetime.datetime(int(year), int(month), int(day), int(hour), int(minute)) < logic.now() - _PAST_TOLERANCE


def _validate_weekdays(weekdays) -> list:
    """Validates weekdays (0=Mon ... 6=Sun); returns a sorted list without duplicates. Empty = no selection."""
    if not weekdays:
        return []
    if not isinstance(weekdays, (list, tuple)):
        raise ValueError("err.invalidWeekdays")
    try:
        result = sorted({int(g) for g in weekdays})
    except (ValueError, TypeError):
        raise ValueError("err.invalidWeekdays")
    if any(g < 0 or g > 6 for g in result):
        raise ValueError("err.invalidWeekdays")
    return result


class Api:
    def get_state(self):
        all_items = logic.fill_missing_fields(storage.read_items())
        tasks = [o for o in all_items if not o.get("routine", False)]
        routines = [o for o in all_items if o.get("routine", False)]

        current = logic.now()
        tasks = logic.order_tasks(tasks, current)
        routines = logic.advance_routines(routines, current)

        storage.write_items(tasks + routines)

        routines_by_streak = sorted(routines, key=lambda o: o.get("streak", 0), reverse=True)

        return {
            "tasks": tasks,
            "routines": routines,
            "categories": self._build_category_list(all_items),
            "routines_by_streak": routines_by_streak,
        }

    def add_task(self, name, year, month, day, hour, minute, category):
        name = (name or "").strip()
        if not name:
            return {"success": False, "error": "err.taskNameEmpty", "id": None}
        try:
            datetime.datetime(int(year), int(month), int(day), int(hour), int(minute))
        except (ValueError, TypeError):
            return {"success": False, "error": "err.invalidDate", "id": None}
        if _is_in_past(year, month, day, hour, minute):
            return {"success": False, "error": "err.dateInPast", "id": None}

        new_id = uuid.uuid4().hex
        item = {
            "id": new_id,
            "title": name,
            "done": False,
            "year": int(year), "month": int(month), "day": int(day), "hour": int(hour), "minute": int(minute),
            "routine": False,
            "category": (category or "").strip(),
        }
        items = storage.read_items()
        items.append(item)
        storage.write_items(items)
        self._save_category_if_needed(item["category"])
        return {"success": True, "error": None, "id": new_id}

    def add_routine(self, name, frequency, year, month, day, hour, minute, category, weekdays=None):
        name = (name or "").strip()
        if not name:
            return {"success": False, "error": "err.routineNameEmpty", "id": None}
        try:
            if int(frequency) <= 0:
                return {"success": False, "error": "err.frequencyPositive", "id": None}
        except (ValueError, TypeError):
            return {"success": False, "error": "err.invalidFrequency", "id": None}
        try:
            days = _validate_weekdays(weekdays)
        except ValueError as exc:
            return {"success": False, "error": str(exc), "id": None}
        if days and int(frequency) != 1:
            return {"success": False, "error": "err.weekdaysAndFrequency", "id": None}
        try:
            datetime.datetime(int(year), int(month), int(day), int(hour), int(minute))
        except (ValueError, TypeError):
            return {"success": False, "error": "err.invalidDate", "id": None}
        if _is_in_past(year, month, day, hour, minute):
            return {"success": False, "error": "err.dateInPast", "id": None}

        new_id = uuid.uuid4().hex
        item = {
            "id": new_id,
            "title": name,
            "done": False,
            "frequency": int(frequency),
            "routine": True,
            "year": int(year), "month": int(month), "day": int(day), "hour": int(hour), "minute": int(minute),
            "streak": 0,
            "category": (category or "").strip(),
        }
        if days:
            # The first date is snapped to one of the selected days (the time stays the same).
            first = logic.snap_to_weekday(
                datetime.datetime(int(year), int(month), int(day), int(hour), int(minute)), days)
            item.update({"year": first.year, "month": first.month, "day": first.day, "hour": first.hour, "minute": first.minute})
            item["weekdays"] = days
        items = storage.read_items()
        items.append(item)
        storage.write_items(items)
        self._save_category_if_needed(item["category"])
        return {"success": True, "error": None, "id": new_id}

    def update_item(self, id, fields):
        items = storage.read_items()
        target = next((o for o in items if o.get("id") == id), None)
        if target is None:
            return {"success": False, "error": "err.itemNotFound"}

        fields = schema.item_to_v2(dict(fields or {}))  # schema-1 field names are still accepted
        updated = dict(target)
        weekdays_changed = "weekdays" in fields
        for field, value in fields.items():
            if field in _EDITABLE_FIELDS and field != "weekdays":
                updated[field] = value
        if weekdays_changed:
            try:
                days = _validate_weekdays(fields["weekdays"])
            except ValueError as exc:
                return {"success": False, "error": str(exc)}
            if days and not updated.get("routine", False):
                return {"success": False, "error": "err.weekdaysRoutineOnly"}
            if days:
                updated["weekdays"] = days
            else:
                updated.pop("weekdays", None)  # empty list = weekly repeat is turned off

        if not str(updated.get("title", "")).strip():
            return {"success": False, "error": "err.nameEmpty"}
        updated["title"] = str(updated["title"]).strip()
        updated["category"] = str(updated.get("category") or "").strip()

        try:
            datetime.datetime(int(updated["year"]), int(updated["month"]), int(updated["day"]), int(updated["hour"]), int(updated["minute"]))
        except (ValueError, TypeError, KeyError):
            return {"success": False, "error": "err.invalidDate"}

        # Only a NEW date is checked; editing name/category/frequency must not reject
        # an overdue item, and the old values in the file are not changed.
        date_changed = any(updated[a] != target.get(a) for a in _DATE_FIELDS)
        if date_changed and _is_in_past(*(updated[a] for a in _DATE_FIELDS)):
            return {"success": False, "error": "err.dateInPast"}

        if updated.get("routine", False):
            try:
                if int(updated.get("frequency", 0)) <= 0:
                    return {"success": False, "error": "err.frequencyPositive"}
            except (ValueError, TypeError):
                return {"success": False, "error": "err.invalidFrequency"}
            if updated.get("weekdays") and int(updated.get("frequency", 1)) != 1:
                return {"success": False, "error": "err.weekdaysAndFrequency"}
            if updated.get("weekdays") and (date_changed or weekdays_changed):
                # If the date (or the days) changed, the first date is snapped to one of the selected days.
                first = logic.snap_to_weekday(
                    datetime.datetime(*(int(updated[a]) for a in _DATE_FIELDS)), updated["weekdays"])
                updated.update({"year": first.year, "month": first.month, "day": first.day, "hour": first.hour, "minute": first.minute})

        for i, item in enumerate(items):
            if item.get("id") == id:
                items[i] = updated
                break
        storage.write_items(items)
        if "category" in fields:
            self._save_category_if_needed(updated["category"])
        return {"success": True, "error": None}

    def delete_items(self, ids):
        items = storage.read_items()
        id_set = set(ids)
        remaining = [o for o in items if o.get("id") not in id_set]
        deleted_count = len(items) - len(remaining)
        storage.write_items(remaining)
        return {"success": True, "deleted_count": deleted_count}

    def complete_items(self, ids):
        items = logic.fill_missing_fields(storage.read_items())
        id_set = set(ids)
        current = logic.now()
        today = current.date().isoformat()
        # A routine whose cycle has ended is first advanced to the new cycle, so the
        # completion is written to the current cycle, not the missed old one.
        logic.advance_routines([o for o in items if o.get("routine", False)], current)
        for item in items:
            if item.get("id") in id_set and not item.get("done", False):
                item["done"] = True
                storage.append_history({"date": today, "type": "routine" if item.get("routine", False) else "task"})
        storage.write_items(items)
        return {"success": True}

    def _get_categories(self):
        items = logic.fill_missing_fields(storage.read_items())
        return self._build_category_list(items)

    def add_category(self, name):
        name = (name or "").strip()
        if not name:
            return {"success": False, "error": "err.categoryNameEmpty", "categories": self._get_categories()}
        saved = storage.read_categories()
        if name in saved:
            return {"success": False, "error": "err.categoryExists", "categories": self._get_categories()}
        saved.append(name)
        storage.write_categories(saved)
        return {"success": True, "error": None, "categories": self._get_categories()}

    def delete_category(self, name):
        saved = [k for k in storage.read_categories() if k != name]
        storage.write_categories(saved)
        items = storage.read_items()
        for item in items:
            if item.get("category") == name:
                item["category"] = ""
        storage.write_items(items)
        return {"success": True, "categories": self._get_categories()}

    def weekly_completions(self, week_start_iso=None):
        if week_start_iso:
            start = datetime.date.fromisoformat(week_start_iso)
        else:
            today = logic.now().date()
            start = today - datetime.timedelta(days=today.weekday())
        return logic.weekly_summary(storage.read_history(), start)

    def monthly_completions(self, year=None, month=None):
        today = logic.now().date()
        year = int(year) if year else today.year
        month = int(month) if month else today.month
        return logic.monthly_summary(storage.read_history(), year, month)

    def donut_data(self, kind):
        items = logic.fill_missing_fields(storage.read_items())
        # kind: "task" | "routine"
        filtered = [o for o in items if o.get("routine", False) == (kind == "routine")]
        all_categories = self._build_category_list(items)
        return logic.compute_donut(filtered, all_categories)

    def _build_category_list(self, items):
        saved = storage.read_categories()
        result = list(saved)
        for item in items:
            category = item.get("category")
            if category and category not in result:
                result.append(category)
        return result

    def _save_category_if_needed(self, name):
        if not name:
            return
        saved = storage.read_categories()
        if name not in saved:
            saved.append(name)
            storage.write_categories(saved)
