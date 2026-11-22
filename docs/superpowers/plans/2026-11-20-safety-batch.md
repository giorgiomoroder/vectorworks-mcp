# Safety batch: no more dialogs, guarded jobs, faster bridge, Lightwright channel

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop Vectorworks from ever showing the modal Script Errors dialog or crashing on a job we sent, refuse jobs for the wrong (or no) document before they run, make the job protocol cancel cleanly and run faster, and add Spotlight's Lightwright Data Exchange XML as a plug-in-free second data channel.

**Architecture:** The in-app bridge (`vw-plugin/vwmcp/vwmcp_bridge.py`, Python 3.9) grows from a dumb executor to a checked executor: it wraps `vs` in a proxy that validates argument count and types against a bundled signature index and refuses functions a published safety sweep classified as crashers or dialog openers; it compares the active document with the one named in the job before executing; it compiles helper libraries once per session. The server (`client.py`) gains a two-phase wait (claim, then result), cancel-by-rename, re-trigger, a liveness probe, and library references by sha. `vslint.py` gets the same safety table so `vw_exec_python` refuses before sending. A start-screen preflight in `trigger.py` uses the existing CoreGraphics window list. `lightwright.py` reads and patches the Lightwright exchange XML next to the `.vwx`.

**Tech Stack:** Python 3.11+ server (stdlib + mcp), Python 3.9 in-app code, pytest with the fake executor (`tests/test_client.py: FakeExecutor` runs the real bridge). Data files derived from MIT sources: Keystone's `vs_index.json` (type codes, itself from the Vectorworks developer-scripting stub) and stevenmorgan94/vw-mcp's `class-table-v2.json` (safety classes). Attribution goes in a new `NOTICE` file.

**Sources to read before each task (read-only clones, do not execute):**
- `/private/tmp/claude-501/-Users-nitemind-dev-vwx-mcp/ed2e86b5-5a37-41b0-ba86-45e134a82c71/scratchpad/ext/keystone/vw-plugin/vwmcp/vwmcp_bridge.py` (lines 77-240: `check_args`, `CheckedVS`, `load_check_table`; 241-383: `_compiled_lib`, `_run_one`)
- `.../ext/keystone/src/vwmcp/client.py` (claim/cancel/alive/lib_ref)
- `.../ext/keystone/src/vwmcp/data/vs_index.json` (format: `{"_meta": {...}, "f": {name: {"a": params, "t": codes, ...}}}`)
- `.../ext/vwmcp-steven/docs/sweep/class-table-v2.json` (`{"functions": {name: {"class": "safe|interactive|crasher|hang|document-level", "argCheck": bool, "badCases": [...]}}}`)
- `.../ext/bridge/PROTOCOL.md`, `.../ext/bridge/vw_bridge/writer.py`, `.../ext/bridge/tests/fixtures/synthetic_sample.xml`
- If the clones are gone: `git clone --depth 1` the three repos again into separate empty directories under the scratchpad.

**Hard rules that apply to every task:** the bridge stays Python 3.9 (no `match`, no `X | Y`, stdlib only; `tests/test_calls.py` style `ast.parse(..., feature_version=(3, 9))` test for the bridge is added in Task 1). Bump `BRIDGE_VERSION` and `app.EXPECTED_BRIDGE_VERSION` together to `0.2.0` (Task 2) and never again in this batch. Nothing in this plan runs inside Vectorworks until the live checklist at the end; Michael announces when 2026 is open on a throwaway document.

---

## File structure

| File | Responsibility |
|---|---|
| `scripts/import-vs-types.py` (new) | Reduce Keystone's `vs_index.json` to `src/vwmcp/data/vs_types.json` (`{"_meta", "f": {name: {"t", "a"}}}`, entries with type codes only) |
| `scripts/import-vs-safety.py` (new) | Reduce the sweep's `class-table-v2.json` to `src/vwmcp/data/vs_safety.json` (`crash`, `hang`, `document_level`, `interactive`, `arg_check`) |
| `src/vwmcp/data/vs_types.json`, `vs_safety.json` (new) | The two tables, shipped in the wheel and copied next to the bridge by `install.py` |
| `NOTICE` (new) | Attribution for the derived data (Keystone / Seraphin Ernst, Vectorworks developer-scripting stub, vicquick, stevenmorgan94) |
| `vw-plugin/vwmcp/vwmcp_bridge.py` | 0.2.0: `check_args`, `CheckedVS`, `load_tables`, safety refusal, document guard, `_compiled_lib`, `.cancelled`-aware claim, `never_ran` results |
| `src/vwmcp/client.py` | Claim phase + cancel, re-trigger, alive probe, `lib_ref`, `supports_libs`, `housekeep`, `WrongDocument`, `never_ran` |
| `src/vwmcp/trigger.py` | `in_flight()`, `target_alive()`, start-screen preflight via `screenshot.mac_windows` |
| `src/vwmcp/screenshot.py` | `has_document_window(windows)` |
| `src/vwmcp/calls.py` | Send vwlib by sha when the bridge supports it; pass `document` |
| `src/vwmcp/app.py` | `EXPECTED_BRIDGE_VERSION = "0.2.0"`, `DOCUMENT` contextvar, `require_document` sets it, `vw()` passes it and maps `WrongDocument` |
| `src/vwmcp/vslint.py` | Safety classes in `lint(code, allow_dialogs=False)`; `safety_of(name)`; `types_of(name)` |
| `src/vwmcp/tools/generic.py` | `vw_exec_python(..., allow_dialogs=False)`, `vw_vs_lookup` shows types + safety, `vw_revert_last` handles the `lightwright` op |
| `src/vwmcp/install.py` | Copies the two data files beside the bridge |
| `src/vwmcp/doctor.py` | Checks the data files are installed and current, counts `.cancelled` leftovers |
| `src/vwmcp/lightwright.py` (new) | `find_xml`, `parse`, `build_patch`, `inverse_changes` |
| `src/vwmcp/tools/spotlight.py` | `vw_lightwright_snapshot`, `vw_lightwright_patch` |
| `src/vwmcp/config.py` | spotlight group += the two Lightwright tools |
| Tests | `tests/test_bridge.py`, `test_client.py`, `test_calls.py`, `test_server.py`, `test_trigger.py`, `test_screenshot.py`, `test_vslint.py`, `test_install.py`, `test_doctor.py`, new `tests/test_lightwright.py`, `tests/test_data_tables.py` |
| Docs | `docs/vs-notes.md`, `docs/architecture.md`, `docs/claude-config.md`, `README.md`, `CLAUDE.md`, `skills/vectorworks-spotlight/SKILL.md` |

---

### Task 1: Data tables and attribution

**Files:**
- Create: `scripts/import-vs-types.py`, `scripts/import-vs-safety.py`, `NOTICE`
- Create: `src/vwmcp/data/vs_types.json`, `src/vwmcp/data/vs_safety.json`
- Test: `tests/test_data_tables.py`, `tests/test_bridge.py` (3.9 parse test)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_data_tables.py
import ast
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "src" / "vwmcp" / "data"
BRIDGE = Path(__file__).resolve().parents[1] / "vw-plugin" / "vwmcp" / "vwmcp_bridge.py"


def test_vs_types_table_has_codes_and_params():
    d = json.loads((DATA / "vs_types.json").read_text(encoding="utf-8"))
    assert "Keystone" in d["_meta"]["source"]
    f = d["f"]
    assert len(f) > 3000
    assert f["Rect"] == {"t": "PP", "a": "p1:POINT, p2:POINT"}
    assert f["SetRField"]["t"] == "HSSS"
    assert all(set(e["t"]) <= set("HRIBSPQVCF") for e in f.values())
    assert all("t" in e and "a" in e for e in f.values())


def test_vs_safety_table_lists_the_known_crashers():
    d = json.loads((DATA / "vs_safety.json").read_text(encoding="utf-8"))
    assert "stevenmorgan94" in d["source"]
    assert "UprString" in d["crash"] and "TBB_AttachRecords" in d["crash"]
    assert "RetrieveOpenGLPrefs" in d["hang"]
    assert "ProgressDlgYield" in d["document_level"]
    assert "EditProperties" in d["interactive"]
    assert d["arg_check"]["ApplyLightInfoRecord"] == ["wrong-object-type:crash"]
    assert not (set(d["crash"]) & set(d["interactive"]))


def test_bridge_stays_python_3_9():
    ast.parse(BRIDGE.read_text(encoding="utf-8"), str(BRIDGE), feature_version=(3, 9))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_data_tables.py -q`
Expected: 2 FAIL (FileNotFoundError on the json files), 1 PASS (3.9 parse of the current bridge).

- [ ] **Step 3: Write the import scripts**

```python
# scripts/import-vs-types.py
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
        "reduced": date.today().isoformat(), "functions": len(out),
        "codes": "H handle, R real, I integer, B boolean, S string, P point (tuple or 2 numbers), "
                 "Q 3D point, V vector, C colour (one (r,g,b) tuple), F callback"}, "f": out}


if __name__ == "__main__":
    src = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    OUT.write_text(json.dumps(reduce(src), indent=0, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{OUT}: {len(reduce(src)['f'])} functions")
```

```python
# scripts/import-vs-safety.py
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
    print(f"{OUT}: crash {len(d['crash'])}, hang {len(d['hang'])}, interactive {len(d['interactive'])}")
```

- [ ] **Step 4: Generate the tables and write NOTICE**

Run (paths of the read-only clones):
```bash
uv run python scripts/import-vs-types.py "/private/tmp/claude-501/-Users-nitemind-dev-vwx-mcp/ed2e86b5-5a37-41b0-ba86-45e134a82c71/scratchpad/ext/keystone/src/vwmcp/data/vs_index.json"
uv run python scripts/import-vs-safety.py "/private/tmp/claude-501/-Users-nitemind-dev-vwx-mcp/ed2e86b5-5a37-41b0-ba86-45e134a82c71/scratchpad/ext/vwmcp-steven/docs/sweep/class-table-v2.json"
ls -la src/vwmcp/data/
```
Expected: `vs_types.json` about 250 KB with ~3,140 functions; `vs_safety.json`: crash 11, hang 2, interactive 31.

`NOTICE`:
```
vectorworks-mcp
Copyright (c) 2026 giorgiomoroder
MIT License (see LICENSE)

This project includes data derived from the following MIT-licensed works:

src/vwmcp/data/vs_types.json
  Reduced from vs_index.json of "Keystone for Vectorworks"
  (https://github.com/seraphinernst4/vectorworks-2d-mcp), Copyright (c) 2026
  Seraphin Ernst, which in turn was built from the Vectorworks
  developer-scripting vs.py stub and Function Reference, with categories and
  descriptions from vwx-mcp (https://github.com/vicquick/vwx-mcp, Copyright
  (c) 2026 vicquick). Only parameter names and type codes are kept here.

src/vwmcp/data/vs_safety.json
  Reduced from docs/sweep/class-table-v2.json of vw-mcp
  (https://github.com/stevenmorgan94/vw-mcp), Copyright (c) 2026
  stevenmorgan94: the classification of vs.* functions as safe, interactive,
  crasher, hang or document-level, measured on Vectorworks 2027.

The argument-checking proxy in vw-plugin/vwmcp/vwmcp_bridge.py follows the
design of Keystone's CheckedVS (MIT, Seraphin Ernst).
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_data_tables.py -q`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/import-vs-types.py scripts/import-vs-safety.py src/vwmcp/data/vs_types.json src/vwmcp/data/vs_safety.json NOTICE tests/test_data_tables.py
git commit -m "Signature type table and vs.* safety table (from Keystone and the vw-mcp sweep, MIT; NOTICE)"
```

---

### Task 2: Bridge 0.2.0, part 1: checked `vs` proxy and safety refusal

**Files:**
- Modify: `vw-plugin/vwmcp/vwmcp_bridge.py`
- Modify: `src/vwmcp/app.py` (`EXPECTED_BRIDGE_VERSION = "0.2.0"`)
- Test: `tests/test_bridge.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_bridge.py`)

```python
import types

import pytest


def _fn(doc, impl=None):
    f = impl or (lambda *a: ("called", a))
    f.__doc__ = doc
    return f


@pytest.fixture
def typed_vs():
    """A fake vs whose functions carry Vectorworks-style docstrings, so that
    load_tables keeps them (the live parameter count must match the table)."""
    vs = types.ModuleType("vs")
    vs.GetFName = _fn("Definition:\n  vs.GetFName()")
    vs.Rect = _fn("Definition:\n  vs.Rect(p1, p2)")
    vs.SetRField = _fn("Definition:\n  vs.SetRField(h, record, field, value)")
    vs.ColorIndexToRGB = _fn("Definition:\n  vs.ColorIndexToRGB(color)")
    vs.ForEachObject = _fn("Definition:\n  vs.ForEachObject(callback, c)")
    vs.UprString = _fn("Definition:\n  vs.UprString(str)")
    vs.EditProperties = _fn("Definition:\n  vs.EditProperties(h)")
    vs.HMove = _fn("Definition:\n  vs.HMove(h, xOffset, yOffset)")
    vs.calls = []
    return vs


@pytest.fixture
def tables(tmp_path, monkeypatch):
    types_json = {"f": {"Rect": {"t": "PP", "a": "p1:POINT, p2:POINT"},
                        "SetRField": {"t": "HSSS", "a": "h:HANDLE, record:STRING, field:STRING, value:STRING"},
                        "ColorIndexToRGB": {"t": "I", "a": "color:INTEGER"},
                        "ForEachObject": {"t": "FS", "a": "callback:PROCEDURE, c:CRITERIA"},
                        "HMove": {"t": "HRR", "a": "h:HANDLE, xOffset:REAL, yOffset:REAL"},
                        "GetFName": {"t": "", "a": ""}}}
    safety = {"crash": ["UprString"], "hang": [], "document_level": [], "interactive": ["EditProperties"],
              "arg_check": {}}
    (tmp_path / "vs_types.json").write_text(json.dumps(types_json))
    (tmp_path / "vs_safety.json").write_text(json.dumps(safety))
    monkeypatch.setattr(bridge, "_HERE", str(tmp_path))
    bridge._CACHE["tables"] = None
    return tmp_path


def test_check_args_accepts_point_as_tuple_or_two_numbers():
    assert bridge.check_args("PP", ((0, 0), (10, 5))) is None
    assert bridge.check_args("PP", (0, 0, 10, 5)) is None
    assert bridge.check_args("PP", ((0, 0, 1), (1, 1))) is None  # 3-tuples pass (3D points)
    assert "parameter 2 (POINT) needs a tuple or 2 numbers" in bridge.check_args("PP", ((0, 0),))
    assert "too few" in bridge.check_args("HRR", (None, 1))
    assert "too many" in bridge.check_args("PP", ((0, 0), (1, 1), (2, 2)))


def test_check_args_catches_wrong_types():
    assert "got text" in bridge.check_args("HRR", ("not a handle", 1, 2))
    assert "got text" in bridge.check_args("I", ("7",))
    assert "one tuple" in bridge.check_args("C", (1, 2, 3))
    assert bridge.check_args("C", ((1, 2, 3),)) is None
    assert bridge.check_args("I", ((1, 2),)) is not None  # a tuple for one integer
    assert "callable" in bridge.check_args("FS", ("x", "T=1"))


def test_proxy_refuses_bad_call_before_vectorworks_sees_it(root, typed_vs, tables):
    write_job(root, "c1", "vs.ColorIndexToRGB((1000, 2000, 3000))")
    bridge.run_pending(root, vs_module=typed_vs)
    res = read_result(root, "c1")
    assert res["ok"] is False
    assert "VSArgumentError" in res["error"]
    assert "vs.ColorIndexToRGB(color:INTEGER)" in res["error"]


def test_proxy_passes_good_calls_through(root, typed_vs, tables):
    write_job(root, "c2", "vs.Rect((0, 0), (10, 5))\nvs.Rect(0, 0, 10, 5)\nvs.GetFName()")
    bridge.run_pending(root, vs_module=typed_vs)
    res = read_result(root, "c2")
    assert res["ok"] is True and res["value"] == ("called", ()) or res["value"] == ["called", []]


def test_proxy_only_checks_functions_whose_live_signature_matches(root, typed_vs, tables):
    typed_vs.Rect = _fn("Definition:\n  vs.Rect(p1, p2, extra)")  # a future Vectorworks
    bridge._CACHE["tables"] = None
    write_job(root, "c3", "vs.Rect('anything', 'goes', 1)")
    bridge.run_pending(root, vs_module=typed_vs)
    assert read_result(root, "c3")["ok"] is True


def test_proxy_refuses_known_crashers_and_dialog_openers(root, typed_vs, tables):
    write_job(root, "c4", "vs.UprString('abc')")
    bridge.run_pending(root, vs_module=typed_vs)
    res = read_result(root, "c4")
    assert res["ok"] is False and "VSUnsafeError" in res["error"] and "crash" in res["error"]
    write_job(root, "c5", "vs.EditProperties(None)")
    bridge.run_pending(root, vs_module=typed_vs)
    assert "dialog" in read_result(root, "c5")["error"]
    write_job(root, "c6", "vs.EditProperties(None)", allow_dialogs=True)
    bridge.run_pending(root, vs_module=typed_vs)
    assert read_result(root, "c6")["ok"] is True


def test_check_can_be_switched_off_per_job(root, typed_vs, tables):
    write_job(root, "c7", "vs.ColorIndexToRGB((1, 2, 3))", check=False)
    bridge.run_pending(root, vs_module=typed_vs)
    assert read_result(root, "c7")["ok"] is True


def test_proxied_callback_is_unwrapped_for_vectorworks(root, typed_vs, tables):
    seen = {}
    typed_vs.ForEachObject = _fn("Definition:\n  vs.ForEachObject(callback, c)",
                                 lambda cb, c: seen.setdefault("cb", cb))
    typed_vs.SetSelect = _fn("Definition:\n  vs.SetSelect(h)", lambda h: None)  # named parameter: no *args
    bridge._CACHE["tables"] = None
    write_job(root, "c8", "vs.ForEachObject(vs.SetSelect, 'T=RECT')")
    bridge.run_pending(root, vs_module=typed_vs)
    assert read_result(root, "c8")["ok"] is True
    assert seen["cb"] is typed_vs.SetSelect  # the real built-in, not our wrapper


def test_missing_tables_mean_no_checking(root, typed_vs, monkeypatch, tmp_path):
    monkeypatch.setattr(bridge, "_HERE", str(tmp_path / "nowhere"))
    bridge._CACHE["tables"] = None
    write_job(root, "c9", "vs.ColorIndexToRGB((1, 2, 3))")
    bridge.run_pending(root, vs_module=typed_vs)
    assert read_result(root, "c9")["ok"] is True


def test_bridge_version_is_0_2_0():
    assert bridge.BRIDGE_VERSION == "0.2.0"
```

Also update `write_job` at the top of the file to accept extra keys (it already does via `**extra`).

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_bridge.py -q`
Expected: new tests FAIL with AttributeError (`check_args`, `_HERE`, `_CACHE`), version test FAIL.

- [ ] **Step 3: Implement in the bridge**

Replace the header constants and add the checker between `_jsonable` and `_execute`. Keep everything else; `run_pending`'s signature does not change.

```python
import ast
import contextlib
import hashlib
import io
import json
import os
import re
import sys
import time
import traceback
import types

BRIDGE_VERSION = "0.2.0"
DEFAULT_ROOT = os.path.join(os.path.expanduser("~"), ".vwmcp")
HOME_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vwmcp_home.txt")
TYPES_FILE = "vs_types.json"      # installed beside this file by `vwmcp install-plugin`
SAFETY_FILE = "vs_safety.json"
try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:  # pragma: no cover - exec'd without a file
    _HERE = None
# Survives importlib.reload(): tables and compiled libraries built this session.
_CACHE = globals().get("_CACHE") or {"tables": None, "tables_key": None, "libs": {}}


class VSArgumentError(TypeError):
    """A vs.* call whose arguments don't fit its signature. Raised before
    Vectorworks sees the call: it would show the modal Script Errors dialog
    and block every further job until someone clicks OK."""


class VSUnsafeError(RuntimeError):
    """A vs.* function known to crash or hang Vectorworks, or to open a dialog
    (refused unless the job allows dialogs)."""


_NUMBER = (int, float)
_TUPLE_LEN = {"P": (2, 3), "Q": (2, 3), "V": (2, 3), "C": (3,)}
_WIDTH = {"P": 2, "Q": 3, "V": 3}
_TYPE_NAME = {"H": "HANDLE", "R": "REAL", "I": "INTEGER", "B": "BOOLEAN", "S": "STRING",
              "P": "POINT", "Q": "POINT3D", "V": "VECTOR", "C": "COLOR", "F": "callback"}
# re.S: live docstrings put "Definition:" and the signature on different lines
_DEFINITION = re.compile(r"Definition:.*?vs\.\w+\s*\(([^)]*)\)", re.S)


def _live_param_count(fn):
    """Parameter count from Vectorworks' own docstring; None without one."""
    m = _DEFINITION.search(getattr(fn, "__doc__", None) or "")
    if not m:
        return None
    inner = m.group(1).strip()
    return len([p for p in inner.split(",") if p.strip()]) if inner else 0


def _has_var_args(fn):
    code = getattr(fn, "__code__", None)
    return bool(code is not None and code.co_flags & 0x04)


def check_args(codes, args):
    """None if args fit the type codes, else a short description of the problem.
    Conservative: whatever Vectorworks might accept passes (a tuple of numbers
    may also stand for consecutive number parameters)."""
    i, n, k = 0, len(args), 0
    while k < len(codes):
        c = codes[k]
        pos = k + 1
        if c in _TUPLE_LEN:
            if i < n and isinstance(args[i], (tuple, list)):
                if len(args[i]) not in _TUPLE_LEN[c]:
                    return "parameter %d (%s) needs %s values, got a tuple of %d" % (
                        pos, _TYPE_NAME[c], " or ".join(str(x) for x in _TUPLE_LEN[c]), len(args[i]))
                i += 1
                k += 1
                continue
            if c == "C":
                return ("parameter %d (COLOR) must be one tuple (r, g, b); loose numbers are "
                        "ignored silently by Vectorworks" % pos)
            w = _WIDTH[c]
            loose = args[i:i + w]
            if len(loose) < w or not all(isinstance(a, _NUMBER) for a in loose):
                return "parameter %d (%s) needs a tuple or %d numbers" % (pos, _TYPE_NAME[c], w)
            i += w
            k += 1
            continue
        if i >= n:
            return "too few arguments (%d given)" % n
        a = args[i]
        if c in "RIB" and isinstance(a, str):
            return "parameter %d (%s) got text %r" % (pos, _TYPE_NAME[c], a[:40])
        if c in "RI" and isinstance(a, (tuple, list)):
            span = codes[k:k + len(a)]
            if len(a) > 1 and len(span) == len(a) and all(x in "RIB" for x in span):
                i += 1  # one tuple covering consecutive number parameters
                k += len(a)
                continue
            return "parameter %d (%s) got a tuple of %d" % (pos, _TYPE_NAME[c], len(a))
        if c == "H" and isinstance(a, str):
            return ("parameter %d (HANDLE) got text %r; for a UUID use "
                    "vs.GetObjectByUuid(uuid)" % (pos, a[:40]))
        if c == "F":
            if not callable(a):
                return "parameter %d (callback) is not callable" % pos
            if _has_var_args(a):
                return ("parameter %d (callback) uses *args; Vectorworks counts named parameters, "
                        "declare them explicitly (e.g. def f(h))" % pos)
        i += 1
        k += 1
    if i != n:
        return "too many arguments (%d given)" % n
    return None


def _unwrap(a):
    return getattr(a, "__wrapped__", a) if getattr(a, "_vwmcp_checked", False) else a


def _make_checked(name, fn, spec, safety, allow_dialogs):
    codes, params = spec if spec else (None, "")
    reason = safety.get(name)

    def checked(*args, **kwargs):
        if reason == "crash":
            raise VSUnsafeError("vs.%s not called: it crashes Vectorworks (safety sweep)" % name)
        if reason == "hang":
            raise VSUnsafeError("vs.%s not called: it hangs Vectorworks (safety sweep)" % name)
        if reason == "interactive" and not allow_dialogs:
            raise VSUnsafeError("vs.%s not called: it opens a dialog that blocks every further "
                                "job; pass allow_dialogs=True if you really want it" % name)
        if args and any(getattr(a, "_vwmcp_checked", False) for a in args):
            args = tuple(_unwrap(a) for a in args)
        if kwargs and any(getattr(v, "_vwmcp_checked", False) for v in kwargs.values()):
            kwargs = dict((k, _unwrap(v)) for k, v in kwargs.items())
        if codes is not None and not kwargs:
            problem = check_args(codes, args)
            if problem is not None:
                raise VSArgumentError("vs.%s not called: %s. Signature: vs.%s(%s)%s" % (
                    name, problem, name, params,
                    "  [POINT = (x, y) or x, y]" if "P" in codes else ""))
        return fn(*args, **kwargs)

    checked.__name__ = name
    checked.__qualname__ = name
    checked.__doc__ = getattr(fn, "__doc__", None)
    checked.__wrapped__ = fn
    checked._vwmcp_checked = True
    return checked


class CheckedVS(types.ModuleType):
    """Stands in for the `vs` module during a job: every function call is
    checked against the type table and the safety list first."""

    def __init__(self, real, tables, allow_dialogs=False):
        types.ModuleType.__init__(self, "vs", getattr(real, "__doc__", None))
        object.__setattr__(self, "_vw_real", real)
        object.__setattr__(self, "_vw_tables", tables)
        object.__setattr__(self, "_vw_dialogs", allow_dialogs)

    def __getattr__(self, name):
        real = object.__getattribute__(self, "_vw_real")
        value = getattr(real, name)  # AttributeError as usual
        tables = object.__getattribute__(self, "_vw_tables")
        spec = tables["types"].get(name)
        if callable(value) and (spec is not None or name in tables["safety"]):
            value = _make_checked(name, value, spec, tables["safety"],
                                  object.__getattribute__(self, "_vw_dialogs"))
        object.__setattr__(self, name, value)  # cache for this job
        return value

    def __dir__(self):
        return dir(object.__getattribute__(self, "_vw_real"))


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load_tables(vs_module, here=None):
    """{"types": {name: (codes, params)}, "safety": {name: reason}} from the
    json files beside this bridge. A function is type-checked only when the
    live docstring's parameter count agrees with the table (the live API wins;
    a Vectorworks whose signatures changed is simply not checked). Cached per
    file mtimes and vs module; {} tables when the files are missing."""
    here = here or _HERE
    if not here:
        return {"types": {}, "safety": {}}
    tp, sp = os.path.join(here, TYPES_FILE), os.path.join(here, SAFETY_FILE)
    key = (tuple(os.path.getmtime(p) if os.path.isfile(p) else None for p in (tp, sp)), id(vs_module))
    if _CACHE["tables_key"] == key and _CACHE["tables"] is not None:
        return _CACHE["tables"]
    types_table = {}
    for name, entry in ((_read_json(tp) or {}).get("f") or {}).items():
        codes = entry.get("t")
        if codes is None:
            continue
        fn = getattr(vs_module, name, None)
        if fn is None or not callable(fn):
            continue
        live = _live_param_count(fn)
        if live is None or live != len(codes):
            continue
        types_table[name] = (codes, entry.get("a", ""))
    safety = {}
    for reason, names in ((_read_json(sp) or {}).items()):
        if reason in ("crash", "hang", "interactive"):
            for n in names:
                safety[n] = reason
    tables = {"types": types_table, "safety": safety}
    _CACHE["tables"], _CACHE["tables_key"] = tables, key
    return tables
```

In `run_pending`, replace the execution block:

```python
            else:
                run_vs, proxy, saved_vs = vs_module, None, None
                if job.get("check", True):
                    try:
                        tables = load_tables(vs_module)
                        if tables["types"] or tables["safety"]:
                            run_vs = proxy = CheckedVS(vs_module, tables, bool(job.get("allow_dialogs")))
                    except Exception as e:  # checking is a safety net, never a blocker
                        res["warning"] = "argument check unavailable: %s: %s" % (type(e).__name__, e)
                if proxy is not None:
                    saved_vs = sys.modules.get("vs")
                    sys.modules["vs"] = proxy  # `import vs` inside the job gets the proxy too
                try:
                    with contextlib.redirect_stdout(out):
                        value = _execute(job["code"], run_vs)
                finally:
                    if proxy is not None:
                        if saved_vs is None:
                            sys.modules.pop("vs", None)
                        else:
                            sys.modules["vs"] = saved_vs
                res["ok"] = True
                res["value"] = _jsonable(value)
```

Set `EXPECTED_BRIDGE_VERSION = "0.2.0"` in `src/vwmcp/app.py`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_bridge.py tests/test_data_tables.py tests/test_doctor.py -q`
Expected: all PASS (doctor tests compare against `app.EXPECTED_BRIDGE_VERSION`, so they follow). If any test elsewhere hard-codes "0.1.0", update it to read the constant.

- [ ] **Step 5: Commit**

```bash
git add vw-plugin/vwmcp/vwmcp_bridge.py src/vwmcp/app.py tests/test_bridge.py
git commit -m "Bridge 0.2.0: checked vs proxy (types from the table, live-confirmed) and safety refusal of crashers/dialog openers"
```

---

### Task 3: Bridge 0.2.0, part 2: document guard, helper libraries by sha, never_ran

**Files:**
- Modify: `vw-plugin/vwmcp/vwmcp_bridge.py`
- Test: `tests/test_bridge.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_document_guard_refuses_another_document_before_running(root, fake_vs):
    fake_vs.GetFPathName = lambda: "/Users/m/Plot.vwx"
    write_job(root, "d1", "vs.calls.append('ran')", document={"name": "visit-bushwick v2027"})
    bridge.run_pending(root, vs_module=fake_vs)
    res = read_result(root, "d1")
    assert res["ok"] is False and res["never_ran"] is True
    assert res["error"].startswith("WrongDocument:")
    assert "Plot.vwx" in res["error"] and fake_vs.calls == []


def test_document_guard_matches_case_and_extension_insensitively(root, fake_vs):
    fake_vs.GetFPathName = lambda: "/Users/m/Plot.vwx"
    write_job(root, "d2", "vs.calls.append('ran')", document={"name": "plot"})
    bridge.run_pending(root, vs_module=fake_vs)
    assert read_result(root, "d2")["ok"] is True and fake_vs.calls == ["ran"]


def test_document_guard_prefers_the_path_when_both_sides_have_one(root, fake_vs):
    fake_vs.GetFPathName = lambda: "/Users/m/shows/Plot.vwx"
    write_job(root, "d3", "1", document={"name": "Plot", "path": "/Users/m/other/Plot.vwx"})
    bridge.run_pending(root, vs_module=fake_vs)
    assert read_result(root, "d3")["never_ran"] is True


def test_helper_library_is_compiled_once_per_session(root, fake_vs, tmp_path):
    src = "N = globals().get('N', 0)\ndef helper():\n    return 'lib'\n"
    sha = bridge.hashlib.sha256(src.encode("utf-8")).hexdigest()
    lib = tmp_path / f"{sha}.py"
    lib.write_text(src)
    ref = {"name": "vwlib", "sha": sha, "path": str(lib)}
    bridge._CACHE["libs"].clear()
    write_job(root, "l1", "helper()", libs=[ref])
    bridge.run_pending(root, vs_module=fake_vs)
    assert read_result(root, "l1")["value"] == "lib"
    lib.unlink()  # cached: the file is not needed any more this session
    write_job(root, "l2", "helper()", libs=[ref])
    bridge.run_pending(root, vs_module=fake_vs)
    assert read_result(root, "l2")["value"] == "lib"


def test_helper_library_with_wrong_checksum_is_refused(root, fake_vs, tmp_path):
    lib = tmp_path / "x.py"
    lib.write_text("def helper(): return 1\n")
    write_job(root, "l3", "helper()", libs=[{"name": "vwlib", "sha": "0" * 64, "path": str(lib)}])
    bridge.run_pending(root, vs_module=fake_vs)
    assert "checksum" in read_result(root, "l3")["error"]


def test_result_carries_claimed_at(root, fake_vs):
    write_job(root, "t1", "1")
    bridge.run_pending(root, vs_module=fake_vs)
    assert read_result(root, "t1")["claimed_at"] > 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_bridge.py -q -k "document_guard or helper_library or claimed_at"`
Expected: FAIL (KeyError `never_ran`, NameError helper, KeyError claimed_at).

- [ ] **Step 3: Implement**

Add after `_execute`'s definition, and change `_execute` to take `libs`:

```python
def _compiled_lib(lib):
    """Compiled code of a helper library {"name", "sha", "path"} (or "src"),
    cached by sha for the whole Vectorworks session (a bridge import lives as
    long as the app)."""
    sha = lib.get("sha")
    code = _CACHE["libs"].get(sha) if sha else None
    if code is not None:
        return code
    src = lib.get("src")
    if src is None:
        with open(lib["path"], encoding="utf-8") as f:
            src = f.read()
    if sha and hashlib.sha256(src.encode("utf-8")).hexdigest() != sha:
        raise RuntimeError("helper library %s does not match its checksum" % lib.get("path"))
    code = compile(src, "<%s>" % lib.get("name", "lib"), "exec")
    if sha:
        if len(_CACHE["libs"]) > 16:
            _CACHE["libs"].clear()
        _CACHE["libs"][sha] = code
    return code


def _execute(code, vs_module, libs=()):
    scope = {"vs": vs_module, "__name__": "__vwmcp__"}
    for lib in libs:
        exec(_compiled_lib(lib), scope)
    tree = ast.parse(code, "<vwmcp job>", "exec")
    ...  # unchanged from here


def _doc_key(name):
    import unicodedata
    s = unicodedata.normalize("NFC", name or "").strip()
    if s.lower().endswith(".vwx"):
        s = s[:-4]
    return s.casefold()


def _wrong_document(vs_module, want):
    """Error text if the active document is not `want` ({"name", "path"}),
    else None. The path decides when both sides have one; else the name
    (case, .vwx and Unicode form do not matter)."""
    try:
        name = str(vs_module.GetFName() or "")
    except Exception:
        name = ""
    try:
        path = str(vs_module.GetFPathName() or "") if hasattr(vs_module, "GetFPathName") else ""
    except Exception:
        path = ""
    want_path, want_name = want.get("path") or "", want.get("name") or ""
    if want_path and path and _doc_key(path) != _doc_key(name):
        ok = _doc_key(path) == _doc_key(want_path)
    else:
        ok = _doc_key(name) == _doc_key(want_name or os.path.basename(want_path))
    if ok:
        return None
    return "WrongDocument: the active document is %r, not %r; nothing was run" % (
        name or path, want_name or want_path)
```

In `run_pending`: set `res["claimed_at"] = started` in the result template, and before the check/execute block:

```python
                want = job.get("document")
                problem = _wrong_document(vs_module, want) if want else None
                if problem:
                    res["error"] = problem
                    res["never_ran"] = True
                else:
                    ... (the check/proxy/execute block from Task 2, with
                         _execute(job["code"], run_vs, job.get("libs") or ()))
```

Keep the `ttl` expiry branch; set `res["never_ran"] = True` there too.

- [ ] **Step 4: Run all bridge tests**

Run: `uv run pytest tests/test_bridge.py tests/test_data_tables.py -q`
Expected: all PASS, including the 3.9 parse test.

- [ ] **Step 5: Commit**

```bash
git add vw-plugin/vwmcp/vwmcp_bridge.py tests/test_bridge.py
git commit -m "Bridge: document guard before running (WrongDocument, never_ran), helper libraries compiled once per session"
```

---

### Task 4: Client: claim phase, cancel by rename, re-trigger, liveness, libraries

**Files:**
- Modify: `src/vwmcp/client.py`, `src/vwmcp/trigger.py`
- Test: `tests/test_client.py`, `tests/test_trigger.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_client.py`)

```python
import time

from vwmcp.client import BridgeError, WrongDocument


class CountingTrigger:
    def __init__(self):
        self.fired = 0
        self.alive = True

    def __call__(self):
        self.fired += 1

    def in_flight(self):
        return False

    def target_alive(self):
        return self.alive


def test_unclaimed_job_is_cancelled_by_rename_and_never_ran(root, fake_vs):
    b = make_bridge(root, lambda: None, claim_timeout=0.1, timeout=5)
    with pytest.raises(BridgeTimeout) as e:
        b.run("1")
    assert e.value.never_ran is True
    assert list((root / "jobs").glob("*.json")) == []
    assert len(list((root / "jobs").glob("*.cancelled"))) == 1
    # a bridge arriving late finds nothing to run
    assert vwmcp_bridge.run_pending(root, vs_module=fake_vs) == 0


def test_trigger_is_refired_while_unclaimed(root, fake_vs):
    t = CountingTrigger()
    b = make_bridge(root, t, claim_timeout=0.3, timeout=1)
    b.retrigger_after = 0.05
    with pytest.raises(BridgeTimeout):
        b.run("1")
    assert t.fired >= 3


def test_claimed_job_waits_for_result_beyond_claim_timeout(root, fake_vs):
    # claimed at once, result after 0.3 s: claim_timeout 0.1 must not cut it off
    class SlowExecutor(FakeExecutor):
        def __call__(self):
            self.triggers += 1

            def run():
                claimed = vwmcp_bridge._claim_oldest(str(self.root / "jobs"))
                time.sleep(0.3)
                # finish by hand: put the job back and run it
                import os
                os.replace(claimed, claimed[: -len(".running")] + ".json")
                vwmcp_bridge.run_pending(self.root, vs_module=self.vs)

            threading.Thread(target=run).start()

    b = make_bridge(root, SlowExecutor(root, fake_vs), claim_timeout=0.1, timeout=2)
    assert b.run("2")["value"] == 2


def test_result_timeout_message_says_vectorworks_is_still_working(root, fake_vs):
    class ClaimOnly:
        def __call__(self):
            vwmcp_bridge._claim_oldest(str(root / "jobs"))

    b = make_bridge(root, ClaimOnly(), claim_timeout=0.5, timeout=0.1)
    with pytest.raises(BridgeTimeout, match="still working"):
        b.run("1")


def test_stops_waiting_when_vectorworks_is_gone(root, fake_vs):
    t = CountingTrigger()

    def claim_then_die():
        t.fired += 1
        vwmcp_bridge._claim_oldest(str(root / "jobs"))
        t.alive = False

    t.__class__ = type("T", (CountingTrigger,), {"__call__": lambda self: claim_then_die()})
    b = make_bridge(root, t, claim_timeout=0.5, timeout=5)
    b.alive_every = 0.02
    with pytest.raises(BridgeError, match="quit or restarted"):
        b.run("1")


def test_wrong_document_result_raises_wrong_document(root, fake_vs):
    fake_vs.GetFPathName = lambda: "/x/Plot.vwx"
    b = make_bridge(root, FakeExecutor(root, fake_vs))
    with pytest.raises(WrongDocument) as e:
        b.run("1", document={"name": "Other"})
    assert e.value.never_ran is True and "Plot" in str(e.value)


def test_lib_ref_writes_the_library_once_and_bridge_version_is_learned(root, fake_vs):
    b = make_bridge(root, FakeExecutor(root, fake_vs))
    assert b.supports_libs() is False  # version unknown before the first result
    b.run("1")
    assert b.bridge_version == vwmcp_bridge.BRIDGE_VERSION and b.supports_libs() is True
    ref = b.lib_ref("vwlib", "def helper():\n    return 7\n")
    assert (root / "lib" / f"{ref['sha']}.py").is_file()
    same = b.lib_ref("vwlib", "def helper():\n    return 7\n")
    assert same == ref and len(list((root / "lib").glob("*.py"))) == 1
    assert b.run("helper()", libs=[ref])["value"] == 7


def test_housekeep_removes_old_leftovers(root, fake_vs):
    b = make_bridge(root, lambda: None)
    (root / "jobs").mkdir(parents=True)
    (root / "results").mkdir(parents=True)
    old = root / "jobs" / "x.cancelled"
    old.write_text("{}")
    fresh = root / "results" / "y.json"
    fresh.write_text("{}")
    assert b.housekeep(now=time.time() + 7200) == 2  # both older than an hour at that time
    assert not old.exists() and not fresh.exists()
```

Append to `tests/test_trigger.py`:

```python
def test_in_flight_and_target_alive(root):
    t, procs = make(root, uptime=120)
    assert t.in_flight() is False
    t()
    assert t.in_flight() is True  # FakeProc(done=False)
    assert t.target_alive() is True
    t.uptime = lambda: None
    assert t.target_alive() is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_client.py tests/test_trigger.py -q`
Expected: new tests FAIL (unexpected keyword `claim_timeout`, ImportError `WrongDocument`, AttributeError `in_flight`).

- [ ] **Step 3: Implement the client**

Rewrite `src/vwmcp/client.py` (keep `BridgeError`, `BridgeTimeout`, `TriggerError`, the lock, `_new_job_id`, `log`):

```python
"""Server side of the job-folder bridge.

The server writes <root>/jobs/<id>.json (via .tmp), fires the trigger that
makes Vectorworks run "MCP Run Job" (vwmcp_bridge.run_pending), then waits
in two phases:

1. up to `claim_timeout` (15 s) for Vectorworks to claim the job (the bridge
   renames it to .running). Not claimed in time: the server renames it to
   .cancelled. If that rename succeeds the job can never run (never_ran); if
   it fails, Vectorworks claimed it at that moment and the server keeps
   waiting. While unclaimed the trigger is re-fired every 2 s (an Apple
   Event can be swallowed while Vectorworks is busy).
2. up to `timeout` for the result of a claimed job. Every 2 s the trigger's
   target_alive() is asked whether Vectorworks still runs.

Helper libraries (vwlib) are written once to <root>/lib/<sha>.py and sent by
reference; the bridge compiles them once per Vectorworks session.
"""

from __future__ import annotations

import contextlib
import hashlib
import itertools
import json
import os
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

DEFAULT_ROOT = Path(os.environ.get("VWMCP_HOME", Path.home() / ".vwmcp"))
DEFAULT_TIMEOUT = float(os.environ.get("VWMCP_TIMEOUT", "120"))
DEFAULT_CLAIM_TIMEOUT = float(os.environ.get("VWMCP_CLAIM_TIMEOUT", "15"))
STALE_AFTER = 3600.0        # leftovers older than this are removed by housekeep()
RETRIGGER_AFTER = 2.0
ALIVE_EVERY = 2.0


class BridgeError(RuntimeError):
    """The bridge could not deliver a job or its result."""

    never_ran = False  # True: the job never ran in Vectorworks, nothing changed


class BridgeTimeout(BridgeError):
    pass


class TriggerError(BridgeError):
    never_ran = True


class WrongDocument(BridgeError):
    """The bridge found another document active than the one the job named."""

    never_ran = True


def _version_tuple(v: str | None) -> tuple:
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return ()


class Bridge:
    def __init__(self, root: Path | str = DEFAULT_ROOT, trigger: Callable[[], None] | None = None,
                 timeout: float = DEFAULT_TIMEOUT, poll_interval: float = 0.05,
                 claim_timeout: float = DEFAULT_CLAIM_TIMEOUT):
        self.root = Path(root)
        self.jobs = self.root / "jobs"
        self.results = self.root / "results"
        self.libdir = self.root / "lib"
        self.log_path = self.root / "vwmcp.log"
        if trigger is None:
            from vwmcp.trigger import default_trigger
            trigger = default_trigger(self.root)
        self.trigger = trigger
        self.timeout = timeout
        self.claim_timeout = claim_timeout
        self.poll_interval = poll_interval
        self.retrigger_after = RETRIGGER_AFTER
        self.alive_every = ALIVE_EVERY
        self._lock = threading.Lock()  # one job in flight: one trigger, one undo step
        self._seq = itertools.count()
        self.bridge_version: str | None = None  # learned from the first result
        self._libs: dict[str, dict] = {}
        self.last_timing: dict = {}
        self._housekept = 0.0

    def log(self, message: str) -> None: ...  # unchanged
    def _new_job_id(self) -> str: ...        # unchanged

    def supports_libs(self) -> bool:
        return _version_tuple(self.bridge_version) >= (0, 2, 0)

    supports_guard = supports_libs

    def lib_ref(self, name: str, source: str) -> dict:
        sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
        path = self.libdir / f"{sha}.py"
        ref = self._libs.get(sha)
        if ref is None or not path.is_file():
            self.libdir.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(source, encoding="utf-8")
            os.replace(tmp, path)
            ref = {"name": name, "sha": sha, "path": str(path)}
            self._libs[sha] = ref
        return ref

    def housekeep(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        removed = 0
        for folder, pattern in ((self.results, "*.json"), (self.results, "*.tmp"),
                                (self.jobs, "*.cancelled"), (self.jobs, "*.tmp")):
            for p in folder.glob(pattern) if folder.is_dir() else ():
                with contextlib.suppress(OSError):
                    if now - p.stat().st_mtime > STALE_AFTER:
                        p.unlink()
                        removed += 1
        if self.libdir.is_dir():
            for p in self.libdir.glob("*.py"):
                with contextlib.suppress(OSError):
                    if p.stem not in self._libs and now - p.stat().st_mtime > 7 * 86400:
                        p.unlink()
                        removed += 1
        self._housekept = now
        return removed

    def run(self, code: str, timeout: float | None = None, libs: list[dict] | None = None,
            check: bool = True, document: dict | None = None, allow_dialogs: bool = False) -> dict:
        """Run code inside Vectorworks; return the bridge's result dict.
        document={"name", "path"}: the bridge refuses to run when another
        document is active (WrongDocument, nothing ran)."""
        timeout = self.timeout if timeout is None else timeout
        with self._lock:
            if time.time() - self._housekept > 600:
                with contextlib.suppress(OSError):
                    self.housekeep()
            res = self._run_locked(code, timeout, libs, check, document, allow_dialogs)
        err = res.get("error") or ""
        if err.startswith("WrongDocument:"):
            raise WrongDocument(err[len("WrongDocument:"):].strip())
        return res

    def _run_locked(self, code, timeout, libs, check, document, allow_dialogs) -> dict:
        self.jobs.mkdir(parents=True, exist_ok=True)
        self.results.mkdir(parents=True, exist_ok=True)
        job_id = self._new_job_id()
        job_path = self.jobs / f"{job_id}.json"
        result_path = self.results / f"{job_id}.json"
        created = time.time()
        job = {"id": job_id, "code": code, "created": created, "ttl": self.claim_timeout + 60,
               "protocol": 2}
        if libs:
            job["libs"] = libs
        if not check:
            job["check"] = False
        if document:
            job["document"] = document
        if allow_dialogs:
            job["allow_dialogs"] = True
        tmp = self.jobs / f"{job_id}.tmp"
        tmp.write_text(json.dumps(job), encoding="utf-8")
        os.replace(tmp, job_path)

        t0 = time.monotonic()
        try:
            self.trigger()
        except TriggerError as e:
            if self._cancel(job_path):
                self.log(f"trigger failed for job {job_id}: {e}")
                raise
        # 1. the claim
        claimed_at = None
        last_fire = t0
        while claimed_at is None:
            if result_path.exists() or not job_path.exists():
                claimed_at = time.monotonic()
                break
            now = time.monotonic()
            if now - t0 >= self.claim_timeout or time.time() - created >= self.claim_timeout:
                if self._cancel(job_path):
                    msg = self._not_claimed_message()
                    self.log(f"not claimed in {self.claim_timeout:g}s, cancelled {job_id}")
                    err = BridgeTimeout(msg)
                    err.never_ran = True
                    raise err
                claimed_at = now
                break
            if now - last_fire >= self.retrigger_after and not self._trigger_in_flight():
                last_fire = now
                with contextlib.suppress(TriggerError):
                    self.trigger()
            time.sleep(self.poll_interval)
        # 2. the result
        deadline = claimed_at + timeout
        alive = getattr(self.trigger, "target_alive", None)
        next_probe = claimed_at + self.alive_every
        while time.monotonic() < deadline:
            if result_path.exists():
                res = self._consume(result_path)
                self.bridge_version = res.get("bridge_version") or self.bridge_version
                self.last_timing = {"claim_s": round(claimed_at - t0, 3),
                                    "total_s": round(time.monotonic() - t0, 3), "vw_s": res.get("duration")}
                return res
            if callable(alive) and time.monotonic() >= next_probe:
                next_probe = time.monotonic() + self.alive_every
                if alive() is False and not result_path.exists():
                    msg = ("Vectorworks quit or restarted while working on this request; it did not "
                           "finish. Open Vectorworks with your document and check what was done.")
                    self.log(f"target gone, job {job_id}")
                    raise BridgeError(msg)
            time.sleep(self.poll_interval)
        msg = (f"Vectorworks is still working on this request after {timeout:g}s. It keeps "
               "running there; its result will be discarded. Check Vectorworks (vw_screenshot) "
               "and try again with a smaller request.")
        self.log(f"result timeout job {job_id}")
        raise BridgeTimeout(msg)

    def _trigger_in_flight(self) -> bool:
        probe = getattr(self.trigger, "in_flight", None)
        return bool(probe()) if callable(probe) else False

    def _not_claimed_message(self) -> str:
        return (f"Vectorworks did not pick up the job within {self.claim_timeout:g}s. Check that a "
                "document is open, no dialog or menu is open (a right-click menu left open also "
                "blocks it; vw_screenshot reports what is in front), and the 'MCP Run Job' menu "
                "command is in your workspace. The request was cancelled and will not run later.")

    def _cancel(self, job_path: Path) -> bool:
        try:
            os.replace(job_path, job_path.with_suffix(".cancelled"))
            return True
        except FileNotFoundError:
            return False

    def _consume(self, result_path: Path) -> dict:
        for attempt in range(5):
            try:
                res = json.loads(result_path.read_text(encoding="utf-8"))
                break
            except (json.JSONDecodeError, OSError):
                if attempt == 4:
                    raise
                time.sleep(0.02)
        with contextlib.suppress(FileNotFoundError):
            result_path.unlink()
        return res
```

Existing tests in `tests/test_client.py` to update (they encode the old single-phase wait):
- `test_timeout_when_vectorworks_never_claims_job`: use `claim_timeout=0.1` instead of `timeout=0.1`; assertions stay (message contains "MCP Run Job"; `*.json` list empty).
- `test_timeout_is_logged_with_timestamp`: use `claim_timeout=0.05`; the log line is now `"not claimed in 0.05s, cancelled <id>"`, so assert `"cancelled" in log.lower()` (keep the timestamp assertion).
- `test_job_carries_ttl_so_stale_jobs_never_run`: the ttl is now `claim_timeout + 60`; build the bridge with `claim_timeout=5` and assert `seen["ttl"] == 65`.

In `_run_locked`, the `except TriggerError` branch deliberately swallows the error when `_cancel` fails: a failed cancel means Vectorworks claimed the job in the meantime (an earlier Apple Event or a second server), so we wait for its result instead. Add that as a comment.

Note that `_HERE` in the repo checkout is `vw-plugin/vwmcp/`, which never holds the tables, so only the `tables` fixture in `tests/test_bridge.py` exercises `CheckedVS`; every other suite runs the plain `vs`.

In `src/vwmcp/trigger.py` add to `MacTrigger`:

```python
    def in_flight(self) -> bool:
        """An osascript we started has not returned yet."""
        return self._pending is not None and self._pending.poll() is None

    def target_alive(self) -> bool:
        return self.uptime() is not None
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_client.py tests/test_trigger.py tests/test_bridge.py -q`
Expected: all PASS. Then the whole suite: `uv run pytest -q`; fix anything that constructed `Bridge(timeout=...)` expecting the old single-phase behaviour (search `tests/` for `timeout=` on `make_bridge`/`Bridge(`).

- [ ] **Step 5: Commit**

```bash
git add src/vwmcp/client.py src/vwmcp/trigger.py tests/test_client.py tests/test_trigger.py
git commit -m "Client: claim phase with cancel-by-rename and re-trigger, liveness probe, WrongDocument, helper libraries by sha, housekeeping"
```

---

### Task 5: Send vwlib by reference; document guard from the tools; `allow_dialogs`

**Files:**
- Modify: `src/vwmcp/calls.py`, `src/vwmcp/app.py`, `src/vwmcp/tools/generic.py`
- Test: `tests/test_calls.py`, `tests/test_server.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_calls.py` (append; see the existing tests there for how a bridge with the fake executor is made):

```python
# tests/ has no __init__.py: sibling test modules import by bare name
# (repo convention, see tests/test_vslint.py: `from test_server import ...`).
from test_client import FakeExecutor, make_bridge


def test_vwlib_goes_by_reference_once_the_bridge_version_is_known(root, fake_vs):
    b = make_bridge(root, FakeExecutor(root, fake_vs))
    assert calls.call(b, "current_document") == "Plot.vwx"  # first call: inline source
    assert b.supports_libs()
    assert calls.call(b, "current_document") == "Plot.vwx"  # second: by reference
    libs = list((root / "lib").glob("*.py"))
    assert len(libs) == 1 and "def current_document" in libs[0].read_text()


def test_call_passes_the_document_to_the_job(root, fake_vs):
    from vwmcp.client import WrongDocument
    fake_vs.GetFPathName = lambda: "/x/Plot.vwx"
    b = make_bridge(root, FakeExecutor(root, fake_vs))
    with pytest.raises(WrongDocument):
        calls.call(b, "current_document", document={"name": "Other"})
```

`tests/test_server.py` (append). The file already has autouse fixtures `bridge` (a `Bridge` on the fake executor, installed as `app.get_bridge`; `tests/test_server.py:48`), `vs` and `journal`; build on them, do not touch `app.get_bridge` yourself:

```python
@pytest.fixture
def bridge_with_fake(bridge, vs):
    return bridge, vs


@pytest.fixture(autouse=True)
def clear_document_guard():
    """Tests set app.DOCUMENT in the main thread's context; never let it leak."""
    yield
    app.DOCUMENT.set(None)


def test_require_document_guards_every_later_call_in_the_request(bridge_with_fake):
    bridge, fake_vs = bridge_with_fake
    fake_vs.GetFPathName = lambda: "/x/Plot.vwx"
    bridge.run("1")  # learn the version
    app.require_document("Plot")  # matches: no error, sets the guard
    assert app.DOCUMENT.get() == {"name": "Plot"}
    assert app.vw("current_document") == "Plot.vwx"
    # another document: the pre-check refuses with a ToolError naming both
    with pytest.raises(ToolError, match="Plot.vwx"):
        app.require_document("Other")


def test_require_document_without_pre_check_fails_inside_the_job(bridge_with_fake):
    bridge, fake_vs = bridge_with_fake
    fake_vs.GetFPathName = lambda: "/x/Plot.vwx"
    bridge.run("1")
    app.DOCUMENT.set({"name": "Other"})  # as if the user switched after the pre-check
    with pytest.raises(ToolError, match="not 'Other'"):
        app.vw("current_document")


def test_exec_python_can_allow_dialogs(bridge_with_fake, monkeypatch):
    bridge, fake_vs = bridge_with_fake
    seen = {}

    def fake_run(code, **kw):
        seen.update(kw)
        return {"ok": True, "stdout": "", "value": {"created": [], "document": "Plot.vwx",
                                                   "value": None, "stdout": ""}}

    monkeypatch.setattr(bridge, "run", fake_run)
    generic.vw_exec_python("vs.EditProperties(None)", allow_dialogs=True)  # tracked path (exec_tracked)
    assert seen["allow_dialogs"] is True
    seen.clear()
    generic.vw_exec_python("1", modifies_document=False, allow_dialogs=True)  # raw path (_run_raw)
    assert seen["allow_dialogs"] is True
```

Read `generic.py` first: `vw_exec_python` with `modifies_document=True` does **not** use `_run_raw`; `_exec_python` calls `calls.call_result(bridge, "exec_tracked", code=code)` and the user's code runs inside vwlib's `exec_tracked`. So `allow_dialogs` must travel as an explicit parameter of `call_result` (never as a vwlib kwarg), and both branches of `_exec_python` plus `vw_exec_file` pass it. The lint result for the tracked path uses `allow_dialogs` too. `tests/test_revert.py:40` and `tests/test_vslint.py:90` monkeypatch `generic._run_raw` with `lambda code, timeout=None`: give those fakes `**kw`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_calls.py tests/test_server.py -q`
Expected: FAIL (TypeError unexpected `document`, AttributeError `app.DOCUMENT`).

- [ ] **Step 3: Implement**

`src/vwmcp/calls.py`:

```python
def call_result(bridge: Bridge, fn: str, timeout: float | None = None,
                document: dict | None = None, allow_dialogs: bool = False, **kwargs) -> dict:
    """Run vwlib.<fn>(**kwargs) in Vectorworks; return the full bridge result.
    vwlib travels inline until the bridge's version is known, then by
    reference (compiled once per Vectorworks session). `document` and
    `allow_dialogs` are job options, never vwlib arguments."""
    tail = f"import json as _json\nresult = {fn}(**_json.loads({json.dumps(kwargs)!r}))\n"
    opts = {"timeout": timeout, "document": document, "allow_dialogs": allow_dialogs}
    if bridge.supports_libs():
        res = bridge.run(tail, libs=[bridge.lib_ref("vwlib", VWLIB_SOURCE)], **opts)
    else:
        res = bridge.run(f"{VWLIB_SOURCE}\n{tail}", **opts)
    return raise_for_result(res)


def call(bridge: Bridge, fn: str, document: dict | None = None, **kwargs):
    return call_result(bridge, fn, document=document, **kwargs)["value"]
```

`generic.py`: `_run_raw(code, timeout=None, allow_dialogs=False)` → `bridge.run(code, timeout=timeout, allow_dialogs=allow_dialogs)`; `_exec_python(code, modifies_document, allow_dialogs=False)` passes it to `vslint.lint` (Task 6), to `calls.call_result(..., allow_dialogs=allow_dialogs)` on the tracked branch and to `_run_raw` on the other; `vw_exec_file` gains the same parameter. Update the `vw_exec_python` docstring's "timeout ... default 30" to the new default (120 s after the claim).

```python
```

`src/vwmcp/app.py`:

```python
import contextvars
from vwmcp.client import Bridge, BridgeError, WrongDocument

# The document the current tool call works in ({"name", "path"} or None).
# Set by require_document; vw() names it in every job so the bridge refuses
# to run in another document. Each MCP request runs in its own task, so the
# value never leaks into the next tool call.
DOCUMENT: contextvars.ContextVar[dict | None] = contextvars.ContextVar("vwmcp_document", default=None)


def vw(fn: str, **kwargs):
    try:
        return calls.call(get_bridge(), fn, document=DOCUMENT.get(), **kwargs)
    except WrongDocument as e:
        want = (DOCUMENT.get() or {}).get("name", "")
        raise ToolError(f"Not done: {e} Bring {want!r} to the front (vw_switch_document) and try "
                        "again.") from e
    except calls.VWError as e:
        raise ToolError(f"{e}\n\n{e.traceback}".strip()) from e
    except BridgeError as e:
        raise ToolError(str(e)) from e


def require_document(document: str | None) -> None:
    """Refuse a write when `document` is given and another document is active,
    and make every later call of this request carry the document so the
    bridge checks again right before running (the user may switch documents
    between our calls)."""
    if not document:
        DOCUMENT.set(None)
        return
    DOCUMENT.set(None)
    current = vw("current_document")
    if _doc_key(current) != _doc_key(document):
        raise ToolError(f"Not done: the active document is {current!r}, not {document!r}. "
                        "Bring the right one to the front (vw_switch_document) and try again.")
    DOCUMENT.set({"name": document})
```

`src/vwmcp/tools/generic.py`: `vw_exec_python(code: str, modifies_document: bool = True, allow_dialogs: bool = False)` as described above (`vslint.lint(..., allow_dialogs=...)` arrives in Task 6; until then do not pass it to the lint). Docstring: "allow_dialogs: let the code call vs.* functions that open a dialog (they block all further jobs until the user closes it); refused by default."

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: all PASS (the FakeDoc tests in `tests/test_drawing.py` go through `app.vw`; they must still pass with `document=None`).

- [ ] **Step 5: Commit**

```bash
git add src/vwmcp/calls.py src/vwmcp/app.py src/vwmcp/tools/generic.py tests/test_calls.py tests/test_server.py
git commit -m "vwlib by reference, document guard carried into every job of a write tool, allow_dialogs on vw_exec_python"
```

---

### Task 6: Lint knows the safety classes; `vw_vs_lookup` shows types and safety

**Files:**
- Modify: `src/vwmcp/vslint.py`, `src/vwmcp/tools/generic.py` (`vw_vs_lookup`, `_run_raw`)
- Test: `tests/test_vslint.py`, `tests/test_server.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_vslint.py`)

```python
def test_lint_refuses_known_crashers_and_hangs():
    r = lint("vs.UprString('x')\nvs.RetrieveOpenGLPrefs()")
    msgs = " ".join(e["message"] for e in r["errors"])
    assert "crashes Vectorworks" in msgs and "hangs Vectorworks" in msgs


def test_lint_refuses_dialog_openers_unless_allowed():
    assert any("dialog" in e["message"] for e in lint("vs.EditProperties(h)")["errors"])
    assert lint("vs.EditProperties(h)", allow_dialogs=True)["errors"] == []


def test_lint_warns_about_document_level_and_wrong_type_crashers():
    r = lint("vs.ProgressDlgYield(1)\nvs.ApplyLightInfoRecord(h, 'x')")
    msgs = " ".join(w["message"] for w in r["warnings"])
    assert "ProgressDlgYield" in msgs and "wrong object type" in msgs


def test_safety_and_types_lookup():
    assert safety_of("UprString") == "crash"
    assert safety_of("Rect") is None
    assert types_of("Rect") == {"t": "PP", "a": "p1:POINT, p2:POINT"}
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_vslint.py -q`
Expected: FAIL (unexpected keyword `allow_dialogs`, ImportError `safety_of`).

- [ ] **Step 3: Implement**

In `src/vwmcp/vslint.py`:

```python
@lru_cache(maxsize=1)
def load_safety() -> dict:
    path = DATA_DIR / "vs_safety.json"
    if not path.exists():
        return {"crash": [], "hang": [], "document_level": [], "interactive": [], "arg_check": {}}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_types() -> dict:
    path = DATA_DIR / "vs_types.json"
    return json.loads(path.read_text(encoding="utf-8")).get("f", {}) if path.exists() else {}


def safety_of(name: str) -> str | None:
    """'crash', 'hang', 'interactive', 'document_level' or None (safe/unknown)."""
    s = load_safety()
    for key in ("crash", "hang", "interactive", "document_level"):
        if name in s.get(key, ()):
            return key
    return None


def types_of(name: str) -> dict | None:
    return load_types().get(name)
```

In `lint(code, filename="<code>", year=None, allow_dialogs=False)`, after the deprecated check and before the unknown-name check:

```python
        reason = safety_of(name)
        if reason == "crash":
            errors.append({"line": line, "message": f"vs.{name} crashes Vectorworks (safety sweep); not sent."})
            continue
        if reason == "hang":
            errors.append({"line": line, "message": f"vs.{name} hangs Vectorworks (safety sweep); not sent."})
            continue
        if reason == "interactive" and not allow_dialogs:
            errors.append({"line": line, "message": f"vs.{name} opens a dialog that blocks all further jobs; "
                           "pass allow_dialogs=True if that is what you want."})
            continue
        if reason == "document_level":
            warnings.append({"line": line, "message": f"vs.{name} changes the document state in a way the "
                             "safety sweep flagged (document-level); be sure."})
        bad = load_safety().get("arg_check", {}).get(name, [])
        if any(c.startswith("wrong-object-type") for c in bad):
            warnings.append({"line": line, "message": f"vs.{name} crashes Vectorworks when given a handle "
                             "of the wrong object type; check GetTypeN first."})
```

Update the module docstring (safety table, `allow_dialogs`). In `generic.py`, `_run_raw(code, allow_dialogs=False)` lints with `allow_dialogs` and runs with it; `vw_vs_lookup` adds `"types": vslint.types_of(name)` and `"safety": vslint.safety_of(name)` to each hit.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_vslint.py tests/test_server.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vwmcp/vslint.py src/vwmcp/tools/generic.py tests/test_vslint.py tests/test_server.py
git commit -m "Lint refuses known crashers, hangs and dialog openers (vs_safety.json); vw_vs_lookup shows types and safety"
```

---

### Task 7: Start-screen preflight

**Files:**
- Modify: `src/vwmcp/screenshot.py`, `src/vwmcp/trigger.py`
- Test: `tests/test_screenshot.py`, `tests/test_trigger.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_screenshot.py` (append; `Window(id, title, layer, x, y, width, height)`):

```python
from vwmcp.screenshot import has_document_window


def test_a_titled_document_window_counts():
    ws = [Window(1, "test_mcp.vwx", 0, 0, 0, 1800, 1100), Window(2, "", 0, 0, 0, 300, 40)]
    assert has_document_window(ws, app="Vectorworks 2026") is True


def test_only_the_start_screen_does_not_count():
    ws = [Window(1, "Vectorworks 2026", 0, 0, 0, 1400, 900), Window(2, "", 0, 0, 0, 300, 40)]
    assert has_document_window(ws, app="Vectorworks 2026") is False


def test_no_titles_at_all_means_we_cannot_tell_so_we_do_not_block():
    ws = [Window(1, "", 0, 0, 0, 1800, 1100)]  # no Screen Recording permission: titles hidden
    assert has_document_window(ws, app="Vectorworks 2026") is None
    assert has_document_window([], app="Vectorworks 2026") is None
```

`tests/test_trigger.py` (append):

```python
def test_refuses_when_only_the_start_screen_is_open(root):
    from vwmcp.screenshot import Window
    t, procs = make(root, uptime=120)
    t.windows = lambda: [Window(1, "Vectorworks 2026", 0, 0, 0, 1400, 900)]
    with pytest.raises(TriggerError, match="No document is open"):
        t()
    assert procs == []


def test_sends_when_a_document_window_exists_or_titles_are_unknown(root):
    from vwmcp.screenshot import Window
    t, procs = make(root, uptime=120)
    t.windows = lambda: [Window(1, "Plot.vwx", 0, 0, 0, 1400, 900)]
    t()
    t.windows = lambda: []
    t._pending = None
    t()
    assert len(procs) == 2
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_screenshot.py tests/test_trigger.py -q`
Expected: ImportError / AttributeError.

- [ ] **Step 3: Implement**

`src/vwmcp/screenshot.py`:

```python
# Titles of Vectorworks' own windows when no document is open (start screen):
# the app's name. Extend after the live check (vs-notes "Start screen").
START_SCREEN_TITLES = {"Vectorworks", "Home Screen", "Start Screen"}


def has_document_window(windows: list[Window], app: str) -> bool | None:
    """True if a document window is on screen, False if only the start
    screen / helper windows are, None if we cannot tell (no titles: the
    Screen Recording permission hides them, or no windows at all)."""
    normal = [w for w in windows if w.layer == 0 and w.height >= 200]
    titled = [w for w in normal if w.title.strip()]
    if not titled:
        return None
    start = START_SCREEN_TITLES | {app}
    return any(w.title.strip() not in start and normal_level_blocker(w) is None for w in titled)
```

`src/vwmcp/trigger.py`, in `MacTrigger.__init__` add `windows: Callable[[], list] | None = None` →
`self.windows = windows or (lambda: _mac_windows(app))` where

```python
def _mac_windows(app: str) -> list:
    try:
        from vwmcp import screenshot
        return screenshot.mac_windows(app)
    except Exception:  # noqa: BLE001 - the preflight never blocks on its own failure
        return []
```

and in `__call__`, after the uptime checks and before `_previous_still_running`:

```python
        from vwmcp.screenshot import has_document_window
        if has_document_window(self.windows(), self.app) is False:
            raise TriggerError(
                f"No document is open in {self.app} (only the start screen). A job sent now "
                "would crash Vectorworks (Keystone, 2026 and 2027). Open a document first.")
```

`mac_windows` matches the owning app's name with a substring; pass `self.app` (e.g. "Vectorworks 2026"). If the live check shows the owner is reported as plain "Vectorworks", use `self.app.split(" ")[0]` like `screenshot.screenshot` does; a mismatch only disables the preflight (empty list → None → not blocked).

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_screenshot.py tests/test_trigger.py tests/test_client.py -q`
Expected: PASS. Make `tests/test_trigger.py::make` pass `windows=lambda: []`, and do the same in `test_waits_briefly_for_previous_event_to_finish`, which builds `MacTrigger` directly: otherwise that test calls the real window list and fails on a Mac whose Vectorworks shows the start screen.

- [ ] **Step 5: Commit**

```bash
git add src/vwmcp/screenshot.py src/vwmcp/trigger.py tests/test_screenshot.py tests/test_trigger.py
git commit -m "Refuse to trigger when only the start screen is open (window list; start-screen jobs crash Vectorworks)"
```

---

### Task 8: Install and doctor know the data files and the new leftovers

**Files:**
- Modify: `src/vwmcp/install.py`, `src/vwmcp/app.py` (`bundled_data`), `src/vwmcp/doctor.py`, `scripts/build-mcpb.py` (nothing: `src/vwmcp` tree already includes `data/`)
- Test: `tests/test_install.py`, `tests/test_doctor.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_install.py`:

```python
def test_install_copies_the_type_and_safety_tables(tmp_path):
    target = tmp_path / "Plug-ins" / "vwmcp"
    install.install_plugin(target, menu_command=None)
    assert (target / "vs_types.json").is_file() and (target / "vs_safety.json").is_file()
    assert json.loads((target / "vs_types.json").read_text())["f"]["Rect"]["t"] == "PP"
```

and update `test_install_is_idempotent` (line 22) to expect `["__init__.py", "vs_safety.json", "vs_types.json", "vwmcp_bridge.py"]`.

`tests/test_doctor.py` uses `setup_home(tmp_path, bridge_version=...)` + `run(home, root)` returning `{check.name: Check}` (`Check` has `name`, `ok`, `detail`, `fix`). The existing stale-files check is named `runtime` (`doctor.check_runtime(root, now, fix)`), the bridge check `bridge`. Append:

```python
def test_bridge_check_reports_missing_or_outdated_tables(tmp_path):
    home = setup_home(tmp_path, bridge_version=app.EXPECTED_BRIDGE_VERSION)
    target = install.plugin_dir("2026", platform="darwin", home=home)
    (target / "vs_safety.json").unlink()
    c = run(home, home / ".vwmcp")["bridge"]
    assert c.ok is False and "vs_safety.json" in c.detail and "install-plugin" in c.fix
    (target / "vs_safety.json").write_text("{}")  # present but not the bundled one
    c = run(home, home / ".vwmcp")["bridge"]
    assert c.ok is False and "outdated" in c.detail


def test_runtime_check_counts_cancelled_jobs_and_stale_libraries(tmp_path):
    home = setup_home(tmp_path, bridge_version=app.EXPECTED_BRIDGE_VERSION)
    root = home / ".vwmcp"
    (root / "jobs").mkdir(parents=True)
    (root / "lib").mkdir()
    old = time.time() - 8 * 86400
    for p in (root / "jobs" / "x.cancelled", root / "lib" / "abc.py"):
        p.write_text("{}")
        os.utime(p, (old, old))
    c = run(home, root)["runtime"]
    assert c.ok and "1 cancelled" in c.detail and "1 stale librar" in c.detail  # harmless, like stale results
    run(home, root, fix=True)
    assert not (root / "jobs" / "x.cancelled").exists() and not (root / "lib" / "abc.py").exists()
```

Read `check_runtime` and `check_bridge` before changing them: `check_bridge` gains the tables comparison (missing → "missing vs_safety.json"; different text → "outdated"); `check_runtime` gains `jobs/*.cancelled` (older than an hour) and `lib/*.py` (older than 7 days) to its stale list, removed with `fix=True`. Check how `run_checks` passes `fix` and `now`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_install.py tests/test_doctor.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

`app.py`: `def bundled_data(name: str) -> str: return resources.files("vwmcp").joinpath("data", name).read_text(encoding="utf-8")`.

`install.py` `install_plugin`: after writing the bridge, `for name in ("vs_types.json", "vs_safety.json"): (target / name).write_text(app.bundled_data(name), encoding="utf-8")`; add to the message "with the vs.* type and safety tables".

`doctor.py`: a check "bridge tables": both files exist beside the installed bridge and equal the bundled ones (compare text; detail says which is missing/outdated; `--fix` reinstalls via the existing fix path). Extend the stale-files glob with `jobs/*.cancelled` and `lib/*.py` older than 7 days.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_install.py tests/test_doctor.py -q` then `uv run pytest -q`.

- [ ] **Step 5: Commit**

```bash
git add src/vwmcp/install.py src/vwmcp/app.py src/vwmcp/doctor.py tests/test_install.py tests/test_doctor.py
git commit -m "install-plugin ships the type and safety tables beside the bridge; doctor checks them and cancelled leftovers"
```

---

### Task 9: Lightwright Data Exchange: snapshot and patch

**Files:**
- Create: `src/vwmcp/lightwright.py`, `tests/test_lightwright.py`
- Modify: `src/vwmcp/tools/spotlight.py`, `src/vwmcp/tools/generic.py` (`vw_revert_last`), `src/vwmcp/config.py`
- Test: `tests/test_spotlight.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_lightwright.py
from pathlib import Path

import pytest

from vwmcp import lightwright as lw

SAMPLE = """<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<SLData>
  <ExportFieldList>
    <AppStamp>Vectorworks</AppStamp>
    <TimeStamp>20260101120000</TimeStamp>
    <Absolute_Address>Absolute Address</Absolute_Address>
    <Inst_Type>Instrument Type</Inst_Type>
    <Unit_Number>Unit Number</Unit_Number>
    <Color>Color</Color>
    <Channel>Channel</Channel>
    <Position>Position</Position>
    <Wattage>Wattage</Wattage>
    <Purpose>Purpose</Purpose>
  </ExportFieldList>
  <InstrumentData>
    <Action>Entire Plot</Action>
    <AppStamp>Vectorworks</AppStamp>
    <VWVersion>3150</VWVersion>
    <VWBuild>862586</VWBuild>
    <AutoRot2D>false</AutoRot2D>
    <UID_1001_1_1_0_0>
      <Action>Update</Action>
      <TimeStamp>20260101120000</TimeStamp>
      <AppStamp>Vectorworks</AppStamp>
      <UID>1001.1.1.0.0</UID>
      <Lightwright_ID>155226:2C4:1C:1:Vecto</Lightwright_ID>
      <Device_Type>Moving Light</Device_Type>
      <Symbol_Name>Ayrton EagleStrike</Symbol_Name>
      <Layer>Lighting</Layer>
      <Absolute_Address>1</Absolute_Address>
      <Inst_Type>Ayrton EagleStrike</Inst_Type>
      <Unit_Number>1</Unit_Number>
      <Color />
      <Channel>101</Channel>
      <Position>LX 1</Position>
      <Wattage>700 W</Wattage>
      <Purpose />
      <X_Location_mm>1000</X_Location_mm>
      <Accessories>
        <UID_1001_1_1_1_1><Device_Type>Static Accessory</Device_Type></UID_1001_1_1_1_1>
      </Accessories>
    </UID_1001_1_1_0_0>
    <UID_1002_1_1_0_0>
      <Action>Update</Action>
      <UID>1002.1.1.0.0</UID>
      <Lightwright_ID>155226:2C4:1C:2:Vecto</Lightwright_ID>
      <Device_Type>Light</Device_Type>
      <Symbol_Name>Source Four 26deg</Symbol_Name>
      <Inst_Type>Source Four 26deg</Inst_Type>
      <Unit_Number>2</Unit_Number>
      <Channel>102</Channel>
      <Position>LX 1</Position>
      <Wattage>750 W</Wattage>
    </UID_1002_1_1_0_0>
  </InstrumentData>
</SLData>
"""


@pytest.fixture
def xml(tmp_path):
    p = tmp_path / "Plot.xml"
    p.write_text(SAMPLE, encoding="utf-8")
    (tmp_path / "Plot.vwx").write_bytes(b"")
    return p


def test_find_xml_next_to_the_document(xml, tmp_path):
    assert lw.find_xml(str(tmp_path / "Plot.vwx")) == xml
    assert lw.find_xml(str(tmp_path / "Other.vwx")) is None
    assert lw.find_xml("") is None


def test_parse_reads_fields_and_skips_accessories(xml):
    snap = lw.parse(xml)
    assert snap["exported"] == "20260101120000" and snap["vw_version"] == "3150"
    assert snap["fields"][:2] == ["Absolute_Address", "Inst_Type"]
    assert len(snap["fixtures"]) == 2
    f = snap["fixtures"][0]
    assert f["uid"] == "1001.1.1.0.0" and f["Channel"] == "101" and f["Color"] == ""
    assert f["accessories"] == 1 and "X_Location_mm" in f


def test_build_patch_emits_only_the_changed_fields_with_the_metadata(xml):
    snap = lw.parse(xml)
    patch = lw.build_patch(xml.read_text(), snap, [{"uid": "1001.1.1.0.0", "fields": {"Channel": "201"}}],
                           now="20260102030405")
    assert "<AppStamp>Lightwright</AppStamp>" in patch
    assert "<ExportFieldList>" in patch and "<Absolute_Address>Absolute Address</Absolute_Address>" in patch
    block = patch[patch.index("<UID_1001_1_1_0_0>"):patch.index("</UID_1001_1_1_0_0>")]
    assert "<Channel>201</Channel>" in block and "<Position>" not in block
    assert "<Lightwright_ID>155226:2C4:1C:1:Vecto</Lightwright_ID>" in block
    assert "<UID>1001.1.1.0.0</UID>" in block and "<Action>Update</Action>" in block
    assert "<TimeStamp>20260102030405</TimeStamp>" in block
    assert "UID_1002" not in patch


def test_build_patch_guards(xml):
    snap = lw.parse(xml)
    text = xml.read_text()
    with pytest.raises(lw.PatchError, match="not in the export"):
        lw.build_patch(text, snap, [{"uid": "1001.1.1.0.0", "fields": {"User_Field_1": "x"}}])
    with pytest.raises(lw.PatchError, match="unknown fixture"):
        lw.build_patch(text, snap, [{"uid": "9.9.9.9.9", "fields": {"Channel": "1"}}])
    with pytest.raises(lw.PatchError, match="Delete"):
        lw.build_patch(text, snap, [{"uid": "1001.1.1.0.0", "fields": {"Action": "Delete"}}])
    # a type swap needs a Symbol_Name some fixture already uses, and a Wattage
    with pytest.raises(lw.PatchError, match="no fixture uses"):
        lw.build_patch(text, snap, [{"uid": "1001.1.1.0.0", "fields": {"Inst_Type": "Robe", "Symbol_Name": "Robe", "Wattage": "1 W"}}])
    with pytest.raises(lw.PatchError, match="Wattage"):
        lw.build_patch(text, snap, [{"uid": "1001.1.1.0.0", "fields": {"Inst_Type": "Source Four 26deg", "Symbol_Name": "Source Four 26deg"}}])
    ok = lw.build_patch(text, snap, [{"uid": "1001.1.1.0.0", "fields": {
        "Inst_Type": "Source Four 26deg", "Symbol_Name": "Source Four 26deg", "Wattage": "750 W"}}])
    assert "<Use_Legend />" in ok or "<Use_Legend/>" in ok


def test_inverse_changes_restore_previous_values(xml):
    snap = lw.parse(xml)
    changes = [{"uid": "1001.1.1.0.0", "fields": {"Channel": "201", "Purpose": "Key"}}]
    assert lw.inverse_changes(snap, changes) == [{"uid": "1001.1.1.0.0", "fields": {"Channel": "101", "Purpose": ""}}]


def test_values_are_xml_escaped(xml):
    snap = lw.parse(xml)
    patch = lw.build_patch(xml.read_text(), snap, [{"uid": "1001.1.1.0.0", "fields": {"Purpose": "R&J <act 2>"}}])
    assert "<Purpose>R&amp;J &lt;act 2&gt;</Purpose>" in patch
```

`tests/test_spotlight.py` (append; follow the file's pattern of monkeypatching `app.vw`):

```python
def test_lightwright_snapshot_reports_when_the_exchange_is_off(monkeypatch, tmp_path):
    (tmp_path / "Plot.vwx").write_bytes(b"")
    monkeypatch.setattr(spotlight, "vw", lambda fn, **kw: {"name": "Plot.vwx", "path": str(tmp_path / "Plot.vwx")})
    out = spotlight.vw_lightwright_snapshot()
    assert out["available"] is False and "Spotlight Preferences" in out["hint"]


def test_lightwright_patch_dry_run_writes_nothing(monkeypatch, tmp_path):
    from test_lightwright import SAMPLE  # bare module name: tests/ has no __init__.py
    (tmp_path / "Plot.vwx").write_bytes(b"")
    xml = tmp_path / "Plot.xml"
    xml.write_text(SAMPLE)
    monkeypatch.setattr(spotlight, "vw", lambda fn, **kw: {"name": "Plot.vwx", "path": str(tmp_path / "Plot.vwx")})
    monkeypatch.setattr(spotlight.app, "require_document", lambda d: None)
    out = spotlight.vw_lightwright_patch([{"uid": "1001.1.1.0.0", "fields": {"Channel": "5"}}])
    assert out["dry_run"] is True and "<Channel>5</Channel>" in out["patch"]
    assert xml.read_text() == SAMPLE
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_lightwright.py tests/test_spotlight.py -q`
Expected: ImportError.

- [ ] **Step 3: Implement `src/vwmcp/lightwright.py`**

```python
"""Spotlight's Lightwright Data Exchange XML as a second data channel.

With Spotlight > Preferences > Lightwright > "Use automatic Lightwright Data
Exchange" on, Vectorworks writes <document>.xml next to the .vwx whenever
it loses focus (and on a full export), and watches that file for patches
stamped "Lightwright". Format decoded by Gribiche64/vectorworks-bridge
(PROTOCOL.md, MIT, May 2026, VW 2026); no plug-in involved.

Read: every Lighting Device with the exported fields, even while a dialog
blocks the bridge. Write: a sparse patch (only changed fields, Action=Update)
that Vectorworks applies 1 to 2 s after it next gains focus. Guards (from
the protocol's hard lessons): never Delete; a Symbol_Name must already be
used by a fixture in the export (an unknown one breaks fixture selection in
the whole drawing, irreversibly); a type change must carry Wattage (it is
not updated by Vectorworks).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

META = {"Action", "TimeStamp", "AppStamp", "UID", "Lightwright_ID", "Use_Legend", "Accessories"}
# Written by every export whatever the field list says (the protocol's type-swap fields).
ALWAYS_WRITABLE = {"Symbol_Name", "Inst_Type", "Wattage"}
HINT = ("Turn on the exchange in Spotlight Preferences (Spotlight > Preferences > Lightwright > "
        "'Use automatic Lightwright Data Exchange' "
        "(check 'Perform a full export' once), save, and click into another app and back: "
        "Vectorworks then writes <document>.xml next to the .vwx.")


class PatchError(ValueError):
    pass


def find_xml(doc_path: str | None) -> Path | None:
    if not doc_path:
        return None
    p = Path(doc_path)
    candidate = p.with_suffix(".xml")
    if candidate.is_file():
        return candidate
    for other in sorted(p.parent.glob("*.xml")) if p.parent.is_dir() else ():
        try:
            head = other.read_text(encoding="utf-8", errors="replace")[:400]
        except OSError:
            continue
        if "<SLData>" in head and other.stem.casefold() == p.stem.casefold():
            return other
    return None


def parse(path: Path) -> dict:
    root = ET.parse(path).getroot()
    efl = root.find("ExportFieldList")
    fields = [c.tag for c in efl] if efl is not None else []
    fields = [f for f in fields if f not in ("AppStamp", "TimeStamp")]
    data = root.find("InstrumentData")
    if data is None:
        raise PatchError(f"{path.name} has no <InstrumentData>")
    fixtures = []
    for el in data:
        if not el.tag.startswith("UID_"):
            continue
        row = {"uid": (el.findtext("UID") or el.tag[4:].replace("_", ".")).strip(),
               "lightwright_id": (el.findtext("Lightwright_ID") or "").strip()}
        acc = el.find("Accessories")
        row["accessories"] = sum(1 for c in acc if c.tag.startswith("UID_")) if acc is not None else 0
        for c in el:
            if c.tag in META:
                continue
            row[c.tag] = (c.text or "").strip()
        fixtures.append(row)
    return {"path": str(path), "exported": (efl.findtext("TimeStamp") if efl is not None else "") or "",
            "vw_version": data.findtext("VWVersion") or "", "vw_build": data.findtext("VWBuild") or "",
            "fields": fields, "fixtures": fixtures}


def _block(text: str, tag: str) -> str:
    m = re.search(rf"<{tag}\b.*?</{tag}>", text, re.S)
    if not m:
        raise PatchError(f"the export has no <{tag}>")
    return m.group(0)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def build_patch(xml_text: str, snapshot: dict, changes: list[dict], now: str | None = None) -> str:
    """Lightwright-style sparse patch for `changes` ([{"uid", "fields": {...}}])
    against the snapshot the XML was parsed into. Raises PatchError on
    anything the protocol says not to do."""
    if not changes:
        raise PatchError("no changes")
    by_uid = {f["uid"]: f for f in snapshot["fixtures"]}
    writable = set(snapshot["fields"]) | ALWAYS_WRITABLE
    in_use = {f.get("Symbol_Name") for f in snapshot["fixtures"] if f.get("Symbol_Name")}
    blocks = []
    stamp = now or utc_now()
    for ch in changes:
        uid, fields = ch.get("uid", ""), dict(ch.get("fields") or {})
        if uid not in by_uid:
            raise PatchError(f"unknown fixture UID {uid!r} (not in the export)")
        if not fields:
            raise PatchError(f"no fields for {uid}")
        if "Action" in fields:
            raise PatchError("Action is set by the patch (Update); Delete is refused on purpose")
        for name in fields:
            if name in META:
                raise PatchError(f"{name} is protocol metadata, not a fixture field")
            if name not in writable:
                raise PatchError(f"{name!r} is not in the export field list; add it in Spotlight "
                                 f"Preferences > Lightwright, or use vw_set_lighting_device_fields")
        sym = fields.get("Symbol_Name")
        if sym and sym not in in_use:
            raise PatchError(f"Symbol_Name {sym!r}: no fixture uses it in this drawing yet. An unknown "
                             "symbol breaks fixture selection for the whole drawing (irreversibly). "
                             "Place one fixture of that type first.")
        if "Inst_Type" in fields and "Wattage" not in fields:
            raise PatchError("a type change (Inst_Type) must set Wattage too: Vectorworks keeps the old one")
        if "Inst_Type" in fields:
            fields.setdefault("Use_Legend", None)
        lines = [f"    <{uid_tag(uid)}>"]
        for name, value in fields.items():
            lines.append(f"      <{name} />" if value is None else f"      <{name}>{escape(str(value))}</{name}>")
        lid = by_uid[uid].get("lightwright_id", "")
        lines += [f"      <Lightwright_ID>{escape(lid)}</Lightwright_ID>", f"      <UID>{uid}</UID>",
                  "      <AppStamp>Lightwright</AppStamp>", f"      <TimeStamp>{stamp}</TimeStamp>",
                  "      <Action>Update</Action>", f"    </{uid_tag(uid)}>"]
        blocks.append("\n".join(lines))
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>', "<SLData>",
        "  <Inventory>", "    <AppStamp>Lightwright</AppStamp>", "  </Inventory>",
        "  " + _block(xml_text, "ExportFieldList"),
        "  <InstrumentData>", "    <AppStamp>Lightwright</AppStamp>",
        f"    <VWVersion>{snapshot.get('vw_version') or '3150'}</VWVersion>",
        f"    <VWBuild>{snapshot.get('vw_build') or '0'}</VWBuild>", "    <AutoRot2D>false</AutoRot2D>",
        *blocks, "  </InstrumentData>", "</SLData>", ""])


def uid_tag(uid: str) -> str:
    return "UID_" + uid.replace(".", "_")


def inverse_changes(snapshot: dict, changes: list[dict]) -> list[dict]:
    """The changes that would restore the snapshot's values (for revert)."""
    by_uid = {f["uid"]: f for f in snapshot["fixtures"]}
    out = []
    for ch in changes:
        prev = by_uid.get(ch["uid"], {})
        out.append({"uid": ch["uid"], "fields": {k: prev.get(k, "") for k in ch["fields"] if k != "Use_Legend"}})
    return out


def write_patch(path: Path, patch: str) -> None:
    """Overwrite the exchange file in place (no rename: Vectorworks watches
    this path with FSEvents)."""
    path.write_text(patch, encoding="utf-8")
```

Tools in `src/vwmcp/tools/spotlight.py`:

```python
@mcp.tool(annotations=READ)
def vw_lightwright_snapshot(position: str | None = None, fields: list[str] | None = None,
                            limit: int = 2000) -> dict:
    """Read every Lighting Device from the Lightwright Data Exchange XML that
    Spotlight writes next to the saved document (when the exchange is on).
    Works even while a dialog blocks other tools, but shows the state as of
    the last export (Vectorworks rewrites it when it loses focus). Returns
    {available, path, exported, fields, count, fixtures:[{uid, Channel, ...}]}
    or {available: False, hint} with how to switch the exchange on."""
    info = vw("document_info")
    xml = lightwright.find_xml(info.get("path"))
    if xml is None:
        return {"available": False, "document": info.get("name"), "hint": lightwright.HINT}
    snap = lightwright.parse(xml)
    rows = snap["fixtures"]
    if position:
        rows = [r for r in rows if r.get("Position", "").casefold() == position.casefold()]
    if fields:
        rows = [{k: r.get(k, "") for k in ["uid", *fields]} for r in rows]
    return {"available": True, "path": snap["path"], "exported": snap["exported"], "fields": snap["fields"],
            "count": len(rows), "fixtures": rows[:limit]}


@mcp.tool(annotations=WRITE)
def vw_lightwright_patch(changes: list[dict], dry_run: bool = True, document: str | None = None) -> dict:
    """Change Lighting Device fields through the Lightwright exchange file
    instead of a job: changes = [{"uid": "1246.1.1.0.0", "fields": {"Channel": "201"}}]
    (UIDs and field names from vw_lightwright_snapshot). dry_run (default)
    returns the patch without writing. Applied patches land in Vectorworks 1
    to 2 s after it next gains focus (click into it); verify with
    vw_list_lighting_devices. Reverted by vw_revert_last (inverse patch).
    Refuses deletes, unknown fields, symbols no fixture uses, and type
    changes without Wattage. Prefer vw_set_lighting_device_fields when the
    bridge works; this is for Lightwright round trips and blocked sessions."""
    app.require_document(document)
    info = vw("document_info")
    xml = lightwright.find_xml(info.get("path"))
    if xml is None:
        raise ToolError("No Lightwright exchange file next to this document. " + lightwright.HINT)
    text = xml.read_text(encoding="utf-8")
    snap = lightwright.parse(xml)
    try:
        patch = lightwright.build_patch(text, snap, changes)
    except lightwright.PatchError as e:
        raise ToolError(str(e)) from e
    out = {"dry_run": dry_run, "path": str(xml), "changes": len(changes), "patch": patch}
    if dry_run:
        return out
    inverse = lightwright.inverse_changes(snap, changes)
    lightwright.write_patch(xml, patch)
    app.get_journal().record(info.get("name", ""), "vw_lightwright_patch",
                             [{"op": "lightwright", "path": str(xml), "changes": inverse}])
    out["note"] = "Written. Vectorworks applies it when it next gains focus; then re-read."
    return out
```

`vw_revert_last` in `generic.py`: if every op in the entry is `{"op": "lightwright", ...}`, do it server-side: read the file, `parse`, `build_patch(text, snap, op["changes"])`, `write_patch`; return `{"reverted_tool": ..., "lightwright": True, "changes": n}`. Otherwise unchanged. `config.TOOL_GROUPS["spotlight"]` += the two tool names. Add `from vwmcp import lightwright` in spotlight.py.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_lightwright.py tests/test_spotlight.py tests/test_skill.py tests/test_mcpb.py -q`
Expected: PASS (the skill test only requires named tools to exist).

- [ ] **Step 5: Commit**

```bash
git add src/vwmcp/lightwright.py src/vwmcp/tools/spotlight.py src/vwmcp/tools/generic.py src/vwmcp/config.py tests/test_lightwright.py tests/test_spotlight.py
git commit -m "Lightwright Data Exchange: vw_lightwright_snapshot and vw_lightwright_patch (sparse Update patches, protocol guards, revert by inverse patch)"
```

---

### Task 10: Docs, skill, notes, bundle

**Files:**
- Modify: `README.md` (tool table rows: Lightwright x2; "Safety" paragraph: checked proxy, safety table, document guard, start-screen guard, `allow_dialogs`; troubleshooting rows), `docs/architecture.md` (job protocol 0.2: claim/cancel, libs, document, check), `docs/claude-config.md` (`VWMCP_CLAIM_TIMEOUT` = 15, `VWMCP_TIMEOUT` now 120 and means "after Vectorworks took the job"), `src/vwmcp/tools/generic.py` (`vw_exec_python` docstring still says "default 30"), `docs/vs-notes.md` (section "Safety tables and checked vs (2026-11-20, offline)": what is checked, what is not (argument *values*, handle object types), the start-screen crash from Keystone, the Lightwright protocol summary and guards; "Live check" list below), `CLAUDE.md` (layout lines for `lightwright.py`, data tables, bridge 0.2; hard rule paragraph about Script Errors now says the proxy prevents the known cases; TOOL_GROUPS), `skills/vectorworks-spotlight/SKILL.md` (recipe: "Lightwright round trip", note on `allow_dialogs`), `CLAUDE.local.md` (session history + pick-up list).

- [ ] **Step 1: Write the docs** as listed. Keep the README's install steps unchanged.

- [ ] **Step 2: Rebuild the bundle and validate**

Run: `uv run python scripts/build-mcpb.py --validate` and `uv run pytest -q` (expect ~300 tests, all green) and `uv run vwmcp lint src/vwmcp/vwlib.py` (unchanged vwlib, still clean).

- [ ] **Step 3: Commit**

```bash
git add README.md docs/ CLAUDE.md skills/ 
git commit -m "Docs: checked vs proxy, safety tables, document and start-screen guards, job protocol 0.2, Lightwright channel"
```

---

## Live check (done 2026-11-20/21 on VW 2026 31.7, Bobby Lee plot; results in vs-notes "Live findings 2026-11-21")

1. **[done: reloaded in place with importlib.reload, no restart needed]** `vwmcp install-plugin` (2026) → bridge 0.2.0 plus the two tables land in `~/Library/Application Support/Vectorworks/2026/Plug-ins/vwmcp/`. **Vectorworks caches the imported bridge module**: Michael must restart Vectorworks 2026 (or we accept that the first live pass runs on 0.1.0 and the server falls back to inline vwlib, no guard). Then `vw_ping` → `bridge_version` 0.2.0; `vw_doctor`.
2. **[done: VSArgumentError in 9 ms, no window; 2,218 functions agree with their docstrings]** Proxy: `vw_exec_python("vs.ColorIndexToRGB((1000,2000,3000))")` → `VSArgumentError` text, **no Script Errors dialog** (this is the exact call that annoyed Michael). `vw_exec_python("vs.UprString('a')")` → refused by the lint before sending; with the lint bypassed (`vw_exec_file`? no: lint runs there too) just confirm the lint message.
3. **[done: vw_s 18 ms -> 10 ms]** Typed tools unchanged: `vw_list_lighting_devices` on the Bobby Lee plot, `vw_insert_stage_decks` + revert on test_mcp.vwx; check `last_timing` in the log (vwlib by reference: `vw_s` should drop from ~10 ms to ~1 ms of compile time).
4. **[done: WrongDocument + never_ran; layer create/revert clean]** Document guard: with test_mcp.vwx in front, `vw_create_layer(..., document="BobbyLee...")` → refused with the pre-check; then set up the race: call a write with `document="test_mcp"` and have Michael click the other document between… not reproducible by hand; instead confirm the job JSON carries `"document"` (log) and that `WrongDocument` is what the bridge returns when the name differs (use `vw_exec_python` via a bridge.run with `document={"name": "nope"}` from a scratch script).
5. **[done: start screen is one untitled window; rule changed to 'no titled normal window + Screen Recording granted'; refused in 60 ms]** Start screen: close all documents in 2026 (start screen showing), run `vw_screenshot` → note the start-screen window's title in `in_front`/window list; update `START_SCREEN_TITLES` if it differs from the app name; then `vw_ping` must be refused with "No document is open" **without sending anything**. Do not test the crash itself.
6. **[NOT reproducible: right-click menu does not stay open; About and Preferences dialogs do not block jobs. Unit tests only]** Claim/cancel: open a right-click menu in Vectorworks, call `vw_ping` → after 15 s "did not pick up ... cancelled"; close the menu; confirm no job runs late (`ls ~/.vwmcp/jobs` shows a `.cancelled`, `vw_ping` works).
7. **[done: patch and revert landed; export was stale (inverse now from live values); Vectorworks writes back an empty acknowledgement; backup added]** Lightwright: in the Bobby Lee plot, Spotlight > Preferences > Lightwright, turn the exchange on with a full export, save, click away and back → `vw_lightwright_snapshot` finds the XML (note the exact file name convention in vs-notes). `vw_lightwright_patch` dry run; apply one Channel change on a test unit; click into Vectorworks; `vw_list_lighting_devices` shows it; `vw_revert_last` writes the inverse; click into Vectorworks; verify. Turn the exchange off again afterwards if Michael does not use Lightwright.
8. **[done]** Record everything in `docs/vs-notes.md` ("Live findings" with the date) and tick the roadmap in `CLAUDE.md`.
