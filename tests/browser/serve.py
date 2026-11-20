"""Test server: serves <gui_dir>/web and forwards window.pywebview.api calls to the real Api.

Usage: python serve.py <gui_dir> <port> <data_dir> [fixed_epoch_ms]   (used by run_check.py; works for old and new versions)
With fixed_epoch_ms the server-side clock (logic.now) is frozen at the same moment as the browser clock, so
routines/tasks falling due during a run cannot make two runs differ.
The data dir is set BEFORE the gui modules are imported, so real user data is never touched.
"""
import json
import os
import sys
import mimetypes
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

gui_dir, port, data_dir = Path(sys.argv[1]).resolve(), int(sys.argv[2]), sys.argv[3]
fixed_ms = int(sys.argv[4]) if len(sys.argv) > 4 else None
os.environ["TODO_DATA_DIR"] = data_dir
os.environ["TODO_VERI_DIZINI"] = data_dir
sys.path.insert(0, str(gui_dir))
import api  # noqa: E402

assert str(Path(data_dir).resolve()) in str(getattr(__import__("storage" if (gui_dir / "storage.py").exists() else "veri"),
                                                    "DATA_DIR" if (gui_dir / "storage.py").exists() else "KOK_DIZIN").resolve())
if fixed_ms is not None:
    import datetime
    _logic = sys.modules.get("logic") or sys.modules.get("mantik")
    _frozen = datetime.datetime.fromtimestamp(fixed_ms / 1000)
    for _name in ("now", "simdiki_zaman"):
        if hasattr(_logic, _name):
            setattr(_logic, _name, lambda: _frozen)
API = api.Api()
WEB = gui_dir / "web"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0].lstrip("/") or "index.html"
        if path == "favicon.ico":
            self.send_response(204); self.end_headers(); return
        f = (WEB / path).resolve()
        if not str(f).startswith(str(WEB)) or not f.is_file():
            self.send_response(404); self.end_headers(); return
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(f))[0] or "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        name = self.path.rsplit("/", 1)[-1]
        args = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"[]")
        try:
            if name in ("tam_ekran_degistir", "toggle_fullscreen"):
                result = {"basarili": True, "success": True}
            else:
                result = getattr(API, name)(*args)
            body, code = json.dumps(result).encode(), 200
        except Exception as exc:  # surfaced to the page as a rejected call
            body, code = repr(exc).encode(), 500
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
