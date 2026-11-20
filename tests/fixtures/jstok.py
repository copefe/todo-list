"""Minimal JS tokenizer: enough for app.js (strings, template literals with ${}, comments, regex literals)."""
import re

ID_START = re.compile(r"[A-Za-z_$À-￿]")
ID_PART = re.compile(r"[A-Za-z0-9_$À-￿]")
PUNCT = ["===", "!==", "...", "**=", "=>", "==", "!=", "<=", ">=", "&&", "||", "??", "?.", "++", "--", "+=", "-=", "*=", "/=", "%=", "**",
         "<<", ">>"]
REGEX_PREV = set("(,=:[!&|?{};+-*%<>~^") | {"return", "typeof", "case", "do", "else", "in", "of", "=>", "&&", "||", "==", "===", "!=", "!==", "??"}


def tokenize(src):
    toks = []  # (kind, text)  kind: ws, comment, str, tpl_chunk, ident, num, punct, regex
    i, n = 0, len(src)

    def last_sig():
        for k, t in reversed(toks):
            if k not in ("ws", "comment"):
                return k, t
        return None, None

    def read_template(i):
        # src[i] == '`'; returns end index; appends tokens
        j = i + 1
        start = i
        while True:
            c = src[j]
            if c == "\\":
                j += 2
                continue
            if c == "`":
                toks.append(("tpl", src[start:j + 1]))
                return j + 1
            if c == "$" and src[j + 1] == "{":
                toks.append(("tpl", src[start:j + 2]))
                j = read_code(j + 2, until_brace=True)
                # src[j] == '}'
                start = j
                j += 1
                continue
            j += 1

    def read_code(i, until_brace=False):
        depth = 0
        while i < n:
            c = src[i]
            if until_brace:
                if c == "{":
                    depth += 1
                elif c == "}":
                    if depth == 0:
                        return i
                    depth -= 1
            if c.isspace():
                j = i
                while j < n and src[j].isspace():
                    j += 1
                toks.append(("ws", src[i:j])); i = j; continue
            if src.startswith("//", i):
                j = src.find("\n", i)
                j = n if j < 0 else j
                toks.append(("comment", src[i:j])); i = j; continue
            if src.startswith("/*", i):
                j = src.index("*/", i) + 2
                toks.append(("comment", src[i:j])); i = j; continue
            if c in "\"'":
                j = i + 1
                while src[j] != c:
                    j += 2 if src[j] == "\\" else 1
                toks.append(("str", src[i:j + 1])); i = j + 1; continue
            if c == "`":
                i = read_template(i); continue
            if c == "/":
                k, t = last_sig()
                if k is None or (k == "punct" and t in REGEX_PREV) or (k == "ident" and t in REGEX_PREV):
                    j = i + 1
                    in_cls = False
                    while True:
                        d = src[j]
                        if d == "\\":
                            j += 2; continue
                        if d == "[":
                            in_cls = True
                        elif d == "]":
                            in_cls = False
                        elif d == "/" and not in_cls:
                            break
                        j += 1
                    j += 1
                    while j < n and src[j].isalpha():
                        j += 1
                    toks.append(("regex", src[i:j])); i = j; continue
            if ID_START.match(c):
                j = i + 1
                while j < n and ID_PART.match(src[j]):
                    j += 1
                toks.append(("ident", src[i:j])); i = j; continue
            if c.isdigit() or (c == "." and i + 1 < n and src[i + 1].isdigit()):
                m = re.compile(r"0x[0-9a-fA-F]+|\d*\.?\d+(?:e[+-]?\d+)?").match(src, i)
                toks.append(("num", m.group())); i = m.end(); continue
            for p in PUNCT:
                if src.startswith(p, i):
                    toks.append(("punct", p)); i += len(p); break
            else:
                toks.append(("punct", c)); i += 1
        return i

    read_code(0)
    assert "".join(t for _, t in toks) == src, "roundtrip failed"
    return toks
