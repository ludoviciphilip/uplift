"""Minimal, order-preserving reader/writer for Valve's text KeyValues (VDF).

Steam's text files (libraryfolders.vdf, appmanifest_*.acf, localconfig.vdf,
loginusers.vdf) are nested ``"key" "value"`` / ``"key" { ... }`` blocks.
Round-tripping must not reorder or drop anything, because we rewrite
localconfig.vdf, which holds every per-game setting of the user.
"""
from __future__ import annotations

_ESC = {"n": "\n", "t": "\t", "\\": "\\", '"': '"'}


class VDFError(ValueError):
    pass


def _tokens(text: str):
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "/" and text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j + 1
        elif c in "{}":
            yield c
            i += 1
        elif c == '"':
            i += 1
            out = []
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    out.append(_ESC.get(text[i + 1], "\\" + text[i + 1]))
                    i += 2
                else:
                    out.append(text[i])
                    i += 1
            if i >= n:
                raise VDFError("unterminated string")
            i += 1
            yield ("s", "".join(out))
        elif c == "[":  # conditional like [$WIN32] — skip
            j = text.find("]", i)
            i = n if j < 0 else j + 1
        else:  # unquoted token
            j = i
            while j < n and text[j] not in ' \t\r\n{}"':
                j += 1
            yield ("s", text[i:j])
            i = j


def loads(text: str) -> dict:
    if text.startswith("\ufeff"):
        text = text[1:]
    root: dict = {}
    stack = [root]
    key = None
    for tok in _tokens(text):
        if tok == "{":
            if key is None:
                raise VDFError("block without key")
            new: dict = {}
            stack[-1][key] = new
            stack.append(new)
            key = None
        elif tok == "}":
            if len(stack) == 1:
                raise VDFError("unbalanced }")
            stack.pop()
            key = None
        else:
            s = tok[1]
            if key is None:
                key = s
            else:
                stack[-1][key] = s
                key = None
    if len(stack) != 1:
        raise VDFError("unbalanced {")
    return root


def load(path) -> dict:
    with open(path, encoding="utf-8", errors="surrogateescape") as f:
        return loads(f.read())


def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t") + '"'


def dumps(d: dict, level: int = 0) -> str:
    out = []
    ind = "\t" * level
    for k, v in d.items():
        if isinstance(v, dict):
            out.append(f"{ind}{_q(k)}\n{ind}{{\n{dumps(v, level + 1)}{ind}}}\n")
        else:
            out.append(f"{ind}{_q(k)}\t\t{_q(str(v))}\n")
    return "".join(out)


def dump(d: dict, path) -> None:
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(dumps(d))


def iget(d: dict, *keys, default=None):
    """Case-insensitive nested lookup (Steam mixes "apps" / "Apps")."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        if k in cur:
            cur = cur[k]
            continue
        kl = k.lower()
        for kk in cur:
            if kk.lower() == kl:
                cur = cur[kk]
                break
        else:
            return default
    return cur


def isetdefault(d: dict, key: str, default):
    kl = key.lower()
    for kk in d:
        if kk.lower() == kl:
            return d[kk]
    d[key] = default
    return default
