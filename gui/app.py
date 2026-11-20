import os
import shutil
import sys
import tempfile
from pathlib import Path

# --demo (or TODO_DEMO=1): starts with sample data in a temporary folder, never touches real data.
# The data directory is chosen when storage.py is imported, so this check runs BEFORE any import.
DEMO = "--demo" in sys.argv[1:] or os.environ.get("TODO_DEMO") == "1"
DEMO_DIR = None
if DEMO:
    DEMO_DIR = tempfile.mkdtemp(prefix="todolist-demo-")
    os.environ["TODO_DATA_DIR"] = DEMO_DIR

import webview  # noqa: E402

import i18n  # noqa: E402
import storage  # noqa: E402
from api import Api  # noqa: E402

if getattr(sys, "frozen", False):
    # Packaged .exe: the web/ folder is inside PyInstaller's temporary extraction folder.
    WEB_DIR = Path(sys._MEIPASS) / "web"
else:
    WEB_DIR = Path(__file__).resolve().parent / "web"


class FullscreenApi(Api):
    """For the fullscreen button / F11 in the UI; does not touch data."""

    def toggle_fullscreen(self):
        webview.windows[0].toggle_fullscreen()
        return {"success": True}


def _show_migration_error(message: str) -> None:
    """If the data migration failed, show a visible warning (details are also in migration.log in the data folder)."""
    print(message, file=sys.stderr)
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, i18n.translate("migration.title"), 0x30)
        except Exception:
            pass


if __name__ == "__main__":
    if DEMO:
        from sample_data import create_demo_data
        create_demo_data()
    elif storage.MIGRATION_ERROR or storage.MIGRATION_WARNING:
        _show_migration_error(storage.MIGRATION_ERROR or storage.MIGRATION_WARNING)

    title = "To-Do List (Demo)" if DEMO else "To-Do List"
    try:
        # Starts fullscreen: the window title bar is hidden. F11 or the top-right button switches back to a window.
        webview.create_window(title, i18n.page_url(WEB_DIR / "index.html"), js_api=FullscreenApi(), width=1320, height=880, min_size=(900, 640), fullscreen=True)
        webview.start()
    finally:
        if DEMO_DIR:
            shutil.rmtree(DEMO_DIR, ignore_errors=True)
