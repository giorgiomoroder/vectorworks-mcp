"""Class standards: named sets of classes with pen/fill colours and line
weights (data/class_standards.json), and the pure plan of what applying one
to a document means (create missing classes; restyle existing ones only when
asked). Colours are RGB 0-255 here; vwlib converts to Vectorworks' 0-65535."""

from __future__ import annotations

import json
from importlib import resources

_DATA = None


def _data() -> dict:
    global _DATA
    if _DATA is None:
        text = resources.files("vwmcp").joinpath("data", "class_standards.json").read_text(encoding="utf-8")
        _DATA = json.loads(text)
    return _DATA


def standards() -> list[str]:
    return sorted(_data())


def load(name: str) -> list[dict]:
    """The classes of a standard, validated."""
    if name not in _data():
        raise KeyError(f"unknown class standard {name!r}; known: {', '.join(standards())}")
    spec = _data()[name]["classes"]
    seen = set()
    for c in spec:
        if c["name"] in seen:
            raise ValueError(f"duplicate class {c['name']!r} in standard {name!r}")
        seen.add(c["name"])
        for key in ("pen", "fill"):
            rgb = c.get(key)
            if rgb is not None and not (len(rgb) == 3 and all(isinstance(v, int) and 0 <= v <= 255 for v in rgb)):
                raise ValueError(f"{c['name']}: {key} must be [r, g, b] 0-255")
        if not isinstance(c["line_weight"], int) or not 1 <= c["line_weight"] <= 100:
            raise ValueError(f"{c['name']}: line_weight must be 1-100 mils")
    return spec


def _same_style(spec: dict, attrs: dict) -> bool:
    return (list(attrs.get("pen") or []) == list(spec["pen"])
            and (attrs.get("fill") is None if spec["fill"] is None else list(attrs.get("fill") or []) == list(spec["fill"]))
            and attrs.get("line_weight") == spec["line_weight"])


def plan(spec: list[dict], existing: dict, only: list[str] | None = None, overwrite: bool = False) -> dict:
    """existing: {name: {"exists": bool, "pen": [...], "fill": [...]|None,
    "line_weight": n}} as vwlib.class_attrs returns. `only` keeps classes whose
    name equals an entry or starts with it (e.g. "Stage" = Stage-Decks, Stage-Steps)."""
    if only:
        wanted = [c for c in spec if any(c["name"] == o or c["name"].startswith(o) for o in only)]
        unmatched = [o for o in only if not any(c["name"] == o or c["name"].startswith(o) for c in spec)]
        if unmatched:
            raise KeyError(f"not in this standard: {', '.join(unmatched)}; classes: "
                           f"{', '.join(c['name'] for c in spec)}")
        spec = wanted
    create, restyle, unchanged = [], [], []
    for c in spec:
        attrs = existing.get(c["name"]) or {}
        if not attrs.get("exists"):
            create.append(c)
        elif overwrite and not _same_style(c, attrs):
            restyle.append(c)
        else:
            unchanged.append(c["name"])
    return {"create": create, "restyle": restyle, "unchanged": unchanged}
