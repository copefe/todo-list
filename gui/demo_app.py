"""To-Do List - DEMO build.

Same UI and logic as the real app; the data lives in a separate folder (%LOCALAPPDATA%)
and is recreated on every launch with ready-made sample data relative to today.
"""
import os
import sys
from pathlib import Path

DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "To-Do List Demo"
DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["TODO_DATA_DIR"] = str(DATA_DIR)

import webview  # noqa: E402

import i18n  # noqa: E402
from api import Api  # noqa: E402
from sample_data import create_demo_data  # noqa: E402

if getattr(sys, "frozen", False):
    WEB_DIR = Path(sys._MEIPASS) / "web"
else:
    WEB_DIR = Path(__file__).resolve().parent / "web"


class FullscreenApi(Api):
    """For the fullscreen button / F11 in the UI; does not touch data."""

    def toggle_fullscreen(self):
        webview.windows[0].toggle_fullscreen()
        return {"success": True}


if __name__ == "__main__":
    create_demo_data()
    webview.create_window("To-Do List (Demo)", i18n.page_url(WEB_DIR / "index.html"), js_api=FullscreenApi(), width=1320, height=880, min_size=(900, 640), fullscreen=True)
    webview.start()
