"""Reduce stevenmorgan94/vw-mcp's sweep table to the safety lists we refuse.

    uv run python scripts/import-vs-safety.py <path to class-table-v2.json>

The sweep (MIT, (c) 2026 stevenmorgan94; docs/sweep in that repo) called
~2,800 vs.* functions on Vectorworks 2027 against throwaway documents and
classified them: safe, interactive (opens a dialog), crasher, hang,
document-level. See NOTICE.
"""

import json
import sys
from datetime import date
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src" / "vwmcp" / "data" / "vs_safety.json"
CLASSES = {"crasher": "crash", "hang": "hang", "document-level": "document_level",
           "interactive": "interactive"}


def reduce(table: dict) -> dict:
    out = {"crash": [], "hang": [], "document_level": [], "interactive": [], "arg_check": {}}
    for name, e in sorted(table["functions"].items()):
        key = CLASSES.get(e.get("class"))
        if key:
            out[key].append(name)
        if e.get("argCheck") and e.get("badCases"):
            out["arg_check"][name] = sorted(e["badCases"])
    out["source"] = ("stevenmorgan94/vw-mcp docs/sweep/class-table-v2.json (MIT), Vectorworks 2027 "
                     "32.0.0; reduced by scripts/import-vs-safety.py")
    out["reduced"] = date.today().isoformat()
    return out


if __name__ == "__main__":
    src = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    d = reduce(src)
    OUT.write_text(json.dumps(d, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{OUT}: crash {len(d['crash'])}, hang {len(d['hang'])}, interactive {len(d['interactive'])}, "
          f"document-level {len(d['document_level'])}, arg checks {len(d['arg_check'])}")
