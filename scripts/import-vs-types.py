"""Reduce Keystone's vs_index.json to the type table the bridge needs.

    uv run python scripts/import-vs-types.py <path to keystone vs_index.json>

Keeps only functions with type codes ("t") and their parameter list ("a").
Keystone (github.com/seraphinernst4/vectorworks-2d-mcp, MIT, (c) 2026
Seraphin Ernst) built the codes from the Vectorworks developer-scripting
vs.py stub and Function Reference; see NOTICE.
"""

import json
import sys
from datetime import date
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src" / "vwmcp" / "data" / "vs_types.json"
CODES = ("H handle, R real, I integer, B boolean, S string, P point (tuple or 2 numbers), "
         "Q 3D point, V vector, C colour (one (r,g,b) tuple), F callback")


def reduce(index: dict) -> dict:
    out = {}
    for name, e in sorted(index["f"].items()):
        t = e.get("t")
        if t is None:
            continue
        out[name] = {"t": t, "a": e.get("a", "")}
    meta = index.get("_meta", {})
    return {"_meta": {
        "source": "Keystone vs_index.json (seraphinernst4/vectorworks-2d-mcp, MIT), built "
                  f"{meta.get('built', '?')} from the Vectorworks developer-scripting vs.py stub "
                  "and Function Reference; reduced to type codes by scripts/import-vs-types.py",
        "reduced": date.today().isoformat(), "functions": len(out), "codes": CODES}, "f": out}


if __name__ == "__main__":
    src = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    table = reduce(src)
    OUT.write_text(json.dumps(table, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{OUT}: {len(table['f'])} functions")
