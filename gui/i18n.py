"""Python-side translations: same flat key → text files as the web UI (web/locales/<lang>.json).

Used for texts produced outside the web page (the migration warning box) and to choose the
language of the demo/sample data. The web UI chooses its own language from navigator.language;
on Windows both follow the user's display language.
"""
import json
import locale
import os
import sys
from pathlib import Path

SUPPORTED = ("tr", "en")
DEFAULT = "en"


def page_url(index_html) -> str:
    """Window URL for the web UI; adds ?lang= when TODO_LANG is en/tr (otherwise the page detects the language)."""
    forced = os.environ.get("TODO_LANG", "").strip().lower()
    return f"{index_html}?lang={forced}" if forced in SUPPORTED else str(index_html)


def _locales_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "web" / "locales"
    return Path(__file__).resolve().parent / "web" / "locales"


def normalize(lang) -> str:
    """'tr', 'tr-TR', 'tr_TR.UTF-8', 'Turkish_Türkiye' → 'tr'; anything else → 'en'."""
    value = (lang or "").strip().lower()
    return "tr" if value.startswith(("tr", "turkish")) else DEFAULT


def system_language() -> str:
    """The user's UI language: TODO_LANG (en/tr) if set, else Windows display language, otherwise LANGUAGE/LC_ALL/LC_MESSAGES/LANG or the locale."""
    forced = os.environ.get("TODO_LANG", "").strip().lower()
    if forced in SUPPORTED:
        return forced
    if sys.platform.startswith("win"):
        try:
            import ctypes
            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "tr" if (langid & 0x3FF) == 0x1F else DEFAULT  # LANG_TURKISH primary language id
        except Exception:
            pass
    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        if os.environ.get(name):
            return normalize(os.environ[name])
    try:
        return normalize(locale.getlocale()[0])
    except Exception:
        return DEFAULT


_cache = {}


def _messages(lang: str) -> dict:
    if lang not in _cache:
        try:
            with open(_locales_dir() / f"{lang}.json", encoding="utf-8") as file:
                _cache[lang] = json.load(file)
        except (OSError, ValueError):
            _cache[lang] = {}
    return _cache[lang]


def translate(key: str, lang: str = None, **params) -> str:
    """Looks the key up in the language, then in English; falls back to the key itself."""
    lang = normalize(lang) if lang else system_language()
    for table in (_messages(lang), _messages(DEFAULT)):
        if key in table:
            text = table[key]
            break
    else:
        return key
    for name, value in params.items():
        text = text.replace("{" + name + "}", str(value))
    return text
