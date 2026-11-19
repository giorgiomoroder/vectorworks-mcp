"""Pre-flight check for Python sent to Vectorworks.

Vectorworks reports some script problems not as Python exceptions but with a
modal "Script Errors" dialog that blocks the application until the user
clicks OK: wrong number of arguments to a vs.* function, deprecated calls
that "will generate error", syntax errors in scripts run from menu commands.
This module catches what can be caught before the code is sent:

- syntax errors (ast.parse);
- vs.* calls with too few or too many arguments, checked against the
  signatures from the live docstrings (data/vs_api_<year>.json);
- calls to deprecated functions that generate an error;
- unknown vs.* names (a warning only: Python raises AttributeError for
  those, no dialog).

Point arguments may be passed as one tuple or as separate numbers, so a
parameter that looks like a point (p, p1, startPt, center, ...) may take 1 to
3 arguments. Calls with *args / **kwargs are not checked.

Refresh the table for a new Vectorworks version with `vwmcp dump-api`
(Vectorworks running): it reads every vs.* docstring and `build_table`
converts "Definition: ... vs.Name(a, b)" into data/vs_api_<year>.json
(keys: signatures {name: [params]}, deprecated {name: replacement},
known_without_signature [names]). The table of the server's version is
used when bundled, else the newest one.
"""

from __future__ import annotations

import ast
import json
import re
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
POINTISH = re.compile(r"(^p\d?$|^pt|pt\d?$|point|^v\d?$|start|end|center|centre|move|origin|corner|sect|loc$)",
                      re.IGNORECASE)


@lru_cache(maxsize=4)
def load_api(year: str | None = None) -> dict:
    """Signature table for a Vectorworks year (default: newest bundled)."""
    files = sorted(DATA_DIR.glob("vs_api_*.json"))
    if not files:
        return {"signatures": {}, "deprecated": {}, "known_without_signature": []}
    path = DATA_DIR / f"vs_api_{year}.json" if year else files[-1]
    if not path.exists():
        path = files[-1]
    return json.loads(path.read_text(encoding="utf-8"))


def _vs_aliases(tree: ast.AST) -> set[str]:
    names = {"vs"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "vs":
                    names.add(a.asname or "vs")
    return names


def _range(params: list[str]) -> tuple[int, int]:
    n = len(params)
    k = sum(1 for p in params if POINTISH.search(p))
    return n, n + 2 * k


def lint(code: str, filename: str = "<code>", year: str | None = None) -> dict:
    """Check code. Returns {"errors": [...], "warnings": [...]}; each item is
    {"line": int, "message": str}. Errors would likely block Vectorworks."""
    errors, warnings = [], []
    try:
        tree = ast.parse(code, filename, "exec")
    except SyntaxError as e:
        line = (e.text or "").rstrip("\n")
        errors.append({"line": e.lineno or 0,
                       "message": f"SyntaxError: {e.msg}" + (f"  ->  {line.strip()}" if line else "")})
        return {"errors": errors, "warnings": warnings}

    api = load_api(year)
    sigs, dep = api.get("signatures", {}), api.get("deprecated", {})
    known = set(sigs) | set(api.get("known_without_signature", [])) | set(dep)
    aliases = _vs_aliases(tree)

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id in aliases):
            continue
        name = node.func.attr
        line = node.lineno
        if name in dep:
            hint = f" Use vs.{dep[name]} instead." if dep[name] else ""
            errors.append({"line": line, "message": f"vs.{name} is deprecated and generates an error.{hint}"})
            continue
        if known and name not in known:
            warnings.append({"line": line, "message": f"vs.{name} is not in the Vectorworks API (AttributeError)."})
            continue
        if name not in sigs:
            continue
        if any(isinstance(a, ast.Starred) for a in node.args) or node.keywords:
            continue
        lo, hi = _range(sigs[name])
        n = len(node.args)
        if n < lo or n > hi:
            want = str(lo) if lo == hi else f"{lo}-{hi}"
            errors.append({"line": line, "message":
                           f"vs.{name} takes {want} argument(s), got {n}: vs.{name}({', '.join(sigs[name])})"})
    return {"errors": errors, "warnings": warnings}


DOCS_CODE = "{n: getattr(vs, n).__doc__ for n in dir(vs) if not n.startswith('_')}"
_DEF = re.compile(r"Definition:.*?vs\.(\w+)\((.*?)\)\s*$", re.S)
_DEP = re.compile(r"Deprecated - will generate error\.?(?:.*?\bUse (?:vs\.)?(\w+))?", re.S)


def build_table(docs: dict, vectorworks: str) -> dict:
    """Signature table from {name: docstring} as read inside Vectorworks."""
    sigs, dep, plain = {}, {}, []
    for name, doc in sorted(docs.items()):
        doc = doc or ""
        m = _DEP.search(doc)
        if m:
            dep[name] = m.group(1) or ""
            continue
        m = _DEF.search(doc)
        if m and m.group(1) == name:
            params = [a.strip() for a in m.group(2).split(",") if a.strip()]
            sigs[name] = params
        else:
            plain.append(name)
    return {"vectorworks": vectorworks, "source": "live vs.* docstrings",
            "signatures": sigs, "deprecated": dep, "known_without_signature": plain}


def format_report(report: dict, filename: str = "code") -> str:
    lines = []
    for kind in ("errors", "warnings"):
        for item in report.get(kind, []):
            lines.append(f"{filename}:{item['line']}: {kind[:-1]}: {item['message']}")
    return "\n".join(lines)
