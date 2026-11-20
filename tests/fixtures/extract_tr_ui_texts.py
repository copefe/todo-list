"""Extracts the user-visible Turkish text fragments of the pre-i18n UI (commit 42032eb) into
tr_ui_texts_before_i18n.json. test_i18n.py compares tr.json against this list, so the Turkish UI
can be checked to stay word-for-word the same.

Run from the repo root (needs git):  python tests/fixtures/extract_tr_ui_texts.py
Fragments are pieces of string literals / template literals / markup with tags and ${...} removed:
visible text nodes plus title / aria-label / placeholder values. Code-like pieces (CSS classes,
ids, selectors, colours, API method names, stored field names) are dropped.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from jstok import tokenize  # noqa: E402

COMMIT = "42032eb"
OUT = HERE / "tr_ui_texts_before_i18n.json"
ATTR = re.compile(r'\b(?:title|aria-label|placeholder)="([^"$]*)"')
TAG = re.compile(r"<[^>]*>")
LETTER = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü]")
CODE = re.compile(r"^(?:[a-z0-9]+(?:[-_][a-z0-9]+)+|[#.\[:]\S*|var\(.*|.*[={}].*|[a-z]+[A-Z]\w*|__\w+__|\w+\.json|\d+(?:px|ms|deg|%).*)$")
CODE_WORDS = {
    # stored field names / internal values / DOM / API words that are not visible text
    "sıklık", "tarih", "ad", "hata", "bilgi", "filtre", "sirala", "yon",
    "gorevler", "rutinler", "gorev", "otur", "surukle", "klavye", "birak", "ana", "serit", "maske", "kapali", "ince",
    "yogun", "arka", "mercek", "isilti", "true", "false", "button", "group", "img", "div", "span", "i", "canvas", "role",
    "aktif", "secili", "acik", "bitti", "bitmis", "bugun", "gelecek", "vurgu", "dolu", "yok", "pasif",
    "disabled", "hidden", "matrix", "linear", "arithmetic", "kG", "R", "G", "x", "y", "width", "height", "href",
    "scale", "in", "in2", "result", "type", "values", "slope", "operator", "stdDeviation", "click", "input",
    "keydown", "keyup", "pointerdown", "pointermove", "pointerup", "pointercancel", "scroll", "wheel", "mousedown",
    "mousemove", "mouseup", "focusout", "pointerover", "pointerout", "pywebviewready", "2d", "Enter", "Escape",
    "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "F11",
    # JS-internal values already renamed in 42032eb, and CSS/DOM words
    "back", "glow", "lens", "main", "mask", "off", "strip", "strong", "release", "settle", "keyboard", "drag",
    "routine", "routines", "task", "tasks", "top", "left", "tr", "var", "px", "deg", "c", "c0", "s", "t", "nokta",
    "acilir", "bildirim", "detay", "ekleme", "suruklemede", "T00:00:00",
}
CSS_LIKE = re.compile(r"^(?:--|[#.]|\(prefers|http|[a-z-]+\(|[a-z-]+:$|px|-card$|\" data-)")
CLASS_LIST = re.compile(r"^[a-z0-9-]+(?: [a-z0-9-]+)+$")


def git_show(path):
    return subprocess.run(["git", "show", f"{COMMIT}:{path}"], capture_output=True, check=True).stdout.decode("utf-8")


def literal_parts(src):
    for kind, text in tokenize(src):
        if kind == "str":
            yield text[1:-1].replace("\\'", "'").replace('\\"', '"')
        elif kind == "tpl":
            body = text[1:] if text.startswith("`") else text[1:]
            body = body[:-2] if body.endswith("${") else body[:-1] if body.endswith("`") else body
            yield body


def fragments_from_markup(text):
    out = ATTR.findall(text)
    for piece in TAG.split(text):
        if "<" in piece or ">" in piece:
            continue
        out.append(piece)
    return out


def keep(fragment):
    f = fragment.strip()
    if not f or not LETTER.search(f) or f in CODE_WORDS or CODE.match(f) or CSS_LIKE.match(f):
        return False
    if CLASS_LIST.match(f) and not re.search(r"[çğıöşü]", f) and "-" in f:
        return False
    if re.fullmatch(r"&\w+;", f):  # HTML entity used for escaping
        return False
    if f.startswith(("M", "m")) and re.match(r"^[MmLlHhVvCcSsQqTtAaZz0-9 .,\-]+$", f):  # SVG path data
        return False
    return True


def main():
    found = set()
    js = git_show("gui/web/app.js")
    for part in literal_parts(js):
        for frag in fragments_from_markup(part):
            if keep(frag):
                found.add(frag.strip())
    html = git_show("gui/web/index.html")
    body = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    body = re.sub(r"<svg.*?</svg>", "", body, flags=re.S)
    for frag in fragments_from_markup(body):
        if keep(frag):
            found.add(frag.strip())
    for path in ("gui/api.py", "gui/storage.py", "gui/app.py"):
        src = git_show(path)
        # user-facing strings: API errors, ValueError messages, the migration message and window title
        texts = re.findall(r'"error": "([^"]+)"', src) + re.findall(r'ValueError\("([^"]+)"\)', src)
        texts += re.findall(r'f?"([^"\n]*[çğıöşüÇĞİÖŞÜ][^"\n]*)"', src)
        for text in texts:
            if text.startswith(("görev", "tamamlandı", "yıl", "gün", "sıklık")):
                continue
            for piece in re.split(r"\{\w+\}", text):
                if keep(piece):
                    found.add(piece.strip())
    OUT.write_text(json.dumps(sorted(found), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(len(found), "fragments ->", OUT)


if __name__ == "__main__":
    main()
