"""Sample (demo) data generation: shared by demo_app.py and app.py --demo.

The task and category names follow the language (system language by default: see i18n.py).
They are only written to the demo/temporary data directory, never mixed into real data.

Note: this module imports storage.py; to avoid touching real data the caller must set
the TODO_DATA_DIR environment variable BEFORE importing it.
"""
import datetime
import os
import random

import i18n
import storage

# Per language: category names and item names. The shape of the data (dates, streaks, done flags,
# categories by position) is identical in every language.
CATEGORIES = {
    "tr": ["Spor", "Dil", "Yazılım", "Ders", "Verimlilik", "Oyun"],
    "en": ["Sport", "Languages", "Coding", "Study", "Productivity", "Gaming"],
}
_NAMES = {
    "tr": {
        "presentation": "Python proje sunumunu hazırla", "homework": "Veri yapıları ödevini teslim et",
        "exam": "Algoritma vizesine çalış", "api": "API entegrasyonunu bitir", "groceries": "Haftalık alışveriş",
        "mods": "Yeni oyun için mod listesi çıkar", "shoes": "Spor ayakkabısı al", "room": "Odayı topla",
        "internship": "Staj başvurusu gönder", "lab": "Fizik laboratuvar raporu",
        "branches": "Git branch'lerini temizle", "library": "Kütüphaneden kitap iade et", "bill": "Telefon faturasını öde",
        "gym": "Spor salonu", "language": "Yabancı dil çalışması", "practice": "Python pratik", "home_workout": "Evde spor",
        "review": "Ders tekrarı", "read": "Kitap oku", "journal": "Günlük yaz", "gaming": "Oyun saati (en fazla 1 sa)",
    },
    "en": {
        "presentation": "Prepare the Python project presentation", "homework": "Hand in the data structures assignment",
        "exam": "Study for the algorithms midterm", "api": "Finish the API integration", "groceries": "Weekly grocery run",
        "mods": "List mods for the new game", "shoes": "Buy running shoes", "room": "Tidy up the room",
        "internship": "Send the internship application", "lab": "Physics lab report",
        "branches": "Clean up Git branches", "library": "Return library books", "bill": "Pay the phone bill",
        "gym": "Gym", "language": "Language practice", "practice": "Python practice", "home_workout": "Home workout",
        "review": "Review lecture notes", "read": "Read a book", "journal": "Write in the journal",
        "gaming": "Gaming time (1 h max)",
    },
}
# Category index into CATEGORIES[lang]
SPORT, LANGUAGES, CODING, STUDY, PRODUCTIVITY, GAMING = range(6)


def _item(name, category, day_offset, hour, minute=0, routine=False, frequency=1, streak=0, done=False, weekdays=None):
    t = datetime.datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0) + datetime.timedelta(days=day_offset)
    # Schema-2 field names (schema.py); storage writes them in the current file format.
    item = {
        "id": os.urandom(16).hex(), "title": name, "done": done,
        "year": t.year, "month": t.month, "day": t.day, "hour": t.hour, "minute": t.minute,
        "routine": routine, "category": category,
    }
    if routine:
        item["frequency"] = frequency
        item["streak"] = streak
        if weekdays:
            item["weekdays"] = weekdays
    return item


def create_demo_data(lang=None):
    lang = i18n.normalize(lang) if lang else i18n.system_language()
    n, c = _NAMES[lang], CATEGORIES[lang]
    now = datetime.datetime.now()
    later = min(now.hour + 2, 23)  # today's routines stay "not yet due"
    items = [
        # Tasks
        _item(n["presentation"], c[CODING], 1, 18),
        _item(n["homework"], c[STUDY], 2, 23, 59),
        _item(n["exam"], c[STUDY], 4, 14),
        _item(n["api"], c[CODING], 3, 17, 30),
        _item(n["groceries"], c[PRODUCTIVITY], 1, 12),
        _item(n["mods"], c[GAMING], 6, 21),
        _item(n["shoes"], c[SPORT], 5, 16),
        _item(n["room"], c[PRODUCTIVITY], 0, 23, 30),
        _item(n["internship"], c[CODING], 7, 12),
        _item(n["lab"], c[STUDY], 9, 20),
        _item(n["branches"], c[CODING], 2, 11, done=True),
        _item(n["library"], c[STUDY], 3, 15, done=True),
        _item(n["bill"], c[PRODUCTIVITY], 4, 10, done=True),
        # Routines
        _item(n["gym"], c[SPORT], 0, later, routine=True, streak=12, weekdays=[0, 2, 4]),
        _item(n["language"], c[LANGUAGES], 0, 23, 30, routine=True, streak=34, done=True),
        _item(n["practice"], c[CODING], 0, 23, 0, routine=True, streak=8),
        _item(n["home_workout"], c[SPORT], 1, 8, routine=True, streak=5),
        _item(n["review"], c[STUDY], 0, 22, routine=True, streak=21, done=True),
        _item(n["read"], c[PRODUCTIVITY], 0, 23, 45, routine=True, streak=3),
        _item(n["journal"], c[PRODUCTIVITY], 1, 22, routine=True, streak=0),
        _item(n["gaming"], c[GAMING], 0, 21, routine=True, streak=2, done=True),
    ]
    storage.write_items(items)
    storage.write_categories(list(c))

    # Completion history for the last 75 days: fills the heatmap/chart, weekends a bit quieter.
    # History records: keys and "type" values ("routine"/"task") are language-independent.
    rng = random.Random(42)
    today = now.date()
    history = []
    for back in range(75, -1, -1):
        day = today - datetime.timedelta(days=back)
        base = 2 if day.weekday() >= 5 else 4
        count = max(0, base + rng.randint(-2, 4))
        if rng.random() < 0.07:
            count = 0
        if back == 0:
            count = 4  # today's completions (3 routines + 0 tasks) + sample
        for _ in range(count):
            history.append({"date": day.isoformat(), "type": "routine" if rng.random() < 0.65 else "task"})
    storage.write_history(history)
    return lang
