"""Browser check of the web UI (not part of `unittest discover`).

    python tests/browser/run_check.py --lang tr --old 89bd486   # Turkish UI must match an older version
    python tests/browser/run_check.py --lang en                 # English UI: no Turkish text, no raw keys

What it does:
  * creates sample data (current sample_data.py, chosen language) in a temporary folder — real
    user data is never touched (TODO_DATA_DIR points to the temp folder);
  * serves gui/web over HTTP on free local ports and bridges window.pywebview.api to the real Api;
  * also renders the current version on a schema-1 copy of the same data (old Turkish file/field
    names, converted by the app's own migration when the server starts) and requires the UI to be
    identical to the run on schema-2 data;
  * runs ui_snapshot.py in headless Edge (Playwright, channel "msedge"): 37 scripted UI states with
    the clock frozen (browser and server at the same moment), then a press-hold-drag test of the selection bubble and a tab-label overflow check;
  * with --old <git ref>: renders that version from `git archive` the same way and requires every
    visible text line and title/aria-label/placeholder to be identical (versions before schema 2 get
    the schema-1 copy of the data, since they only read the old files);
  * fails on console errors, page errors, bubble or overflow problems. Temporary files are removed.

Needs: pip install -r requirements-dev.txt and Microsoft Edge installed (Playwright launches it via channel "msedge").
"""
import argparse
import difflib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
LOCALES = {"tr": "tr-TR", "en": "en-US"}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def export_ref(ref, dest):
    data = subprocess.run(["git", "archive", ref, "gui"], cwd=ROOT, capture_output=True, check=True).stdout
    Path(dest).mkdir(parents=True, exist_ok=True)
    tmp_tar = Path(dest) / "gui.tar"
    tmp_tar.write_bytes(data)
    with tarfile.open(tmp_tar) as tar:
        tar.extractall(dest)
    tmp_tar.unlink()
    return Path(dest) / "gui"


def make_data(lang, dest):
    env = dict(os.environ, TODO_DATA_DIR=str(dest))
    env.pop("TODO_VERI_DIZINI", None)
    code = ("import storage, sample_data; "
            f"assert str(storage.DATA_DIR) == {str(dest)!r}, storage.DATA_DIR; "
            f"sample_data.create_demo_data({lang!r})")
    subprocess.run([sys.executable, "-c", code], cwd=ROOT / "gui", env=env, check=True)


def make_schema1_copy(source, dest):
    """Writes the schema-2 sample data in `source` as schema-1 files (gorevler.json ...) into `dest`."""
    sys.path.insert(0, str(ROOT / "gui"))
    try:
        import schema  # no side effects on import
    finally:
        sys.path.pop(0)
    Path(dest).mkdir(parents=True)
    for kind in schema.KINDS:
        content = json.loads((Path(source) / schema.FILE_NAMES[2][kind]).read_text(encoding="utf-8"))
        records = schema.parse(kind, content)
        (Path(dest) / schema.FILE_NAMES[1][kind]).write_text(
            json.dumps(schema.serialize(kind, records, 1), ensure_ascii=False, indent=2), encoding="utf-8")


def wait_port(port, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise RuntimeError(f"server on port {port} did not start")


def snapshot(gui_dir, data_dir, lang, fixed_ms, out, python):
    port = free_port()
    server = subprocess.Popen([sys.executable, str(HERE / "serve.py"), str(gui_dir), str(port), str(data_dir),
                               str(fixed_ms)])
    try:
        wait_port(port)
        subprocess.run([python, str(HERE / "ui_snapshot.py"), f"http://127.0.0.1:{port}", LOCALES[lang], str(out), str(fixed_ms)],
                       check=True)
    finally:
        server.terminate()
        server.wait(10)
    return json.loads(Path(out).read_text(encoding="utf-8"))


def compare(old, new):
    diffs = []
    for state, a in old["states"].items():
        b = new["states"].get(state)
        if b is None:
            diffs.append(f"{state}: missing in new")
            continue
        for key in ("lines", "attrs", "lang", "title"):
            if a[key] != b[key]:
                if isinstance(a[key], list):
                    detail = list(difflib.unified_diff(a[key], b[key], lineterm="", n=0))[2:12]
                else:
                    detail = [f"{a[key]!r} -> {b[key]!r}"]
                diffs.append(f"{state} {key}: " + " | ".join(detail))
    return diffs


def problems(result, lang):
    out = list(result["errors"])
    if not result["checks"].get("bubble_ok"):
        out.append(f"bubble check failed: {result['checks'].get('bubble')}")
    if not result["checks"].get("tabs_ok"):
        out.append(f"tab label overflow: {result['checks'].get('tabs')}")
    if lang == "en":
        for state, snap in result["states"].items():
            for text in snap["lines"] + snap["attrs"]:
                if re.search(r"[çğıöşüÇĞİÖŞÜ]", text):
                    out.append(f"{state}: Turkish text in English UI: {text!r}")
                if re.search(r"\b(?:[a-z]+\.){1,2}[a-z][A-Za-z]+\b", text) and not re.search(r"\d", text):
                    out.append(f"{state}: raw message key? {text!r}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lang", choices=sorted(LOCALES), default="tr")
    ap.add_argument("--old", help="git ref of a version whose UI text must be identical (Turkish check)")
    ap.add_argument("--python", default=sys.executable, help="Python that has Playwright installed")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="todolist-uicheck-"))
    try:
        base = tmp / "data"
        base.mkdir()
        make_data(args.lang, base)
        legacy = tmp / "data-schema1"
        make_schema1_copy(base, legacy)
        fixed = int(time.time() * 1000)
        failures = []

        def run(name, gui_dir, source=base):
            data = tmp / f"data-{name}"
            shutil.copytree(source, data)
            result = snapshot(gui_dir, data, args.lang, fixed, tmp / f"{name}.json", args.python)
            failures.extend(f"[{name}] {p}" for p in problems(result, args.lang))
            print(f"{name}: {len(result['states'])} states, bubble_ok={result['checks']['bubble_ok']}, "
                  f"tabs_ok={result['checks']['tabs_ok']}, errors={len(result['errors'])}")
            return result

        new = run("current", ROOT / "gui")
        migrated = run("current-on-schema1-data", ROOT / "gui", legacy)
        converted = tmp / "data-current-on-schema1-data"
        if not ((converted / ".schema_v2_done.json").exists() and (converted / "items.json").exists()):
            failures.append("[schema1-vs-schema2] the schema-1 data was not migrated when the app started")
        diffs = compare(new, migrated)
        print(f"schema-1 data (migrated at start) vs schema-2 data: {len(diffs)} difference(s)")
        failures.extend(f"[schema1-vs-schema2] {d}" for d in diffs)
        if args.old:
            old_gui = export_ref(args.old, tmp / "old")
            old_source = base if (old_gui / "schema.py").exists() else legacy
            old = run(f"old-{args.old}", old_gui, old_source)
            diffs = compare(old, new)
            lines = sum(len(s["lines"]) + len(s["attrs"]) for s in old["states"].values())
            print(f"compared {len(old['states'])} states / {lines} text lines with {args.old}: {len(diffs)} difference(s)")
            failures.extend(diffs)
        for f in failures:
            print("FAIL", f)
        print("OK" if not failures else f"{len(failures)} problem(s)")
        return 0 if not failures else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
