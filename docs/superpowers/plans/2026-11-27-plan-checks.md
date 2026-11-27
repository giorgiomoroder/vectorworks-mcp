# Plan checks (GDTF false positive, positions by name) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `vw_mvr_check` stop flagging every linked GDTF device on a Vectorworks 2027 plot where `GDTF Fixture Type ID` is never populated, and make `vw_list_positions` useful when positions exist only as names on the devices.

**Architecture:** Two independent, pure-Python changes. (1) `src/vwmcp/mvr.py::run_checks` gets a data-driven skip for `gdtf_unlinked` plus a `field_unused` warning. (2) `src/vwmcp/vwlib.py` (runs inside Vectorworks) gets a pure helper `summarize_positions(rows, named)` that `list_positions` uses to add a `by_name` key; the tool docstring in `src/vwmcp/tools/spotlight.py` is corrected. Spec: `docs/superpowers/specs/2026-11-27-plan-checks-design.md`.

**Tech Stack:** Python; pytest via `uv run pytest`; `vwlib.py` is Python 3.9 syntax, stdlib only, checked by `uv run vwmcp lint src/vwmcp/vwlib.py` and `tests/test_calls.py`.

## Global Constraints

- Branch `spotlight-plan-checks` (based on upstream `main`). Commit subjects in the form "Area: Sentence".
- `src/vwmcp/vwlib.py`: Python 3.9 syntax (no `match`, no `X | Y`), stdlib only, lint clean. It is executed inside Vectorworks; keep helpers pure where possible.
- `src/vwmcp/mvr.py` is server-side (Python 3.11+ allowed, but follow the file's existing style).
- English for code, docs and messages. macOS behaviour unchanged: on a document where any device has a non-zero `GDTF Fixture Type ID`, the `gdtf_unlinked` rule runs exactly as before.
- Field names used (exact): `Position`, `Inst Type`, `Channel`, `UniverseAddress`, `GDTF Fixture Name`, `GDTF Fixture Type ID`.

---

### Task 1: `gdtf_unlinked` skipped when the id field is never populated

**Files:**
- Modify: `src/vwmcp/mvr.py` (inside `run_checks`, the `if active("gdtf_unlinked"):` block, ~line 143)
- Test: `tests/test_mvr.py` (append)

**Interfaces:**
- Consumes: `run_checks(data) -> dict` with `issues: [{check, severity, message, devices}]`, `summary: {check: count}`; test helpers `device(...)`, `data(...)`, `issue(out, check)`, `checks(out)` already in `tests/test_mvr.py`.
- Produces: a new issue check name `"field_unused"` (severity `"warning"`, `devices: []`).

- [ ] **Step 1: Write the failing test** (append to `tests/test_mvr.py`)

```python
def test_gdtf_type_id_never_populated_skips_the_unlinked_check():
    # Live 2026-11-27 (Vectorworks 2027 32.1.0, German, Windows): every linked
    # device had 'GDTF Fixture Type ID' == "0" while carrying a real GDTF mode
    # and channel count. With no non-zero id anywhere, the id says nothing.
    rows = [{**device(uuid=u), "GDTF Fixture Type ID": "0"} for u in ("a", "b", "c")]
    out = mvr.run_checks(data(rows))
    assert "gdtf_unlinked" not in checks(out)
    note = issue(out, "field_unused")
    assert note["severity"] == "warning" and note["devices"] == []
    assert "GDTF Fixture Type ID" in note["message"] and "skipped" in note["message"]
    assert out["summary"].get("gdtf_unlinked", 0) == 0
    # one non-zero id in the document: the macOS rule applies again
    rows[0]["GDTF Fixture Type ID"] = "12"
    out2 = mvr.run_checks(data(rows))
    assert [d["uuid"] for d in issue(out2, "gdtf_unlinked")["devices"]] == ["b", "c"]
    assert "field_unused" not in checks(out2)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_mvr.py::test_gdtf_type_id_never_populated_skips_the_unlinked_check -q`
Expected: FAIL (`gdtf_unlinked` is in `checks(out)` / no `field_unused` issue).

- [ ] **Step 3: Implement** — replace the `if active("gdtf_unlinked"):` block in `run_checks` with:

```python
    if active("gdtf_unlinked"):
        ids = {str(r.get("GDTF Fixture Type ID", "0")).strip() for r in rows}
        if ids <= {"", "0"}:
            # Live 2026-11-27 (VW 2027, German): the id stays 0 on every linked
            # device; only a document that populates it can tell linked from typed.
            issues.append({"check": "field_unused", "severity": WARNING,
                           "message": "GDTF Fixture Type ID is 0 on every device (seen on "
                                      "Vectorworks 2027): the unlinked check is skipped; a GDTF "
                                      "fixture mode and channel count show the link instead.",
                           "devices": []})
        else:
            add("gdtf_unlinked",
                [r for r in rows if str(r.get("GDTF Fixture Name", "")).strip()
                 and str(r.get("GDTF Fixture Type ID", "0")).strip() in ("", "0")],
                "A GDTF name is typed in but no fixture type is linked (type id 0): the MVR gets no "
                "geometry or channel layout. Choose the GDTF in the Object Info palette's GDTF chooser; "
                "writing the field does not link it (live 2026-11-21).")
```

Check how `summary` is computed (it counts devices per check from `issues`); an issue with `devices: []` must not raise there — `field_missing` already works the same way, so follow it. Check `WARNING` is the module constant already defined (`ERROR, WARNING = "error", "warning"`).

- [ ] **Step 4: Run the file's tests**

Run: `uv run pytest tests/test_mvr.py -q`
Expected: all pass, including `test_gdtf_name_typed_but_not_linked_is_an_error` and `test_clean_plot_is_ok` (a clean plot has id "12" on every device, so no `field_unused` note appears — verify that test still passes; if `test_clean_plot_is_ok` asserts an empty issue list, the `ids <= {"", "0"}` guard keeps it empty).

- [ ] **Step 5: Commit**

```bash
git add src/vwmcp/mvr.py tests/test_mvr.py
git commit -m "MVR check: Skip gdtf_unlinked when the type id is never populated"
```

---

### Task 2: `summarize_positions` and the `by_name` key

**Files:**
- Modify: `src/vwmcp/vwlib.py` (add `summarize_positions` right above `list_positions`, ~line 529; change `list_positions`)
- Modify: `src/vwmcp/tools/spotlight.py` (`vw_list_positions` docstring, ~lines 148-168)
- Test: `tests/test_positions.py` (new)

**Interfaces:**
- Consumes: `vwlib._natural(s)` (natural sort key), `vwlib.ld_row(h, fields) -> dict` (field name → string), `vwlib.lighting_devices()`, `vwlib.LD` (the "Lighting Device" record name).
- Produces: `summarize_positions(rows, named) -> list[dict]` where `rows` is a list of dicts with keys `Position`, `Inst Type`, `Channel`, `UniverseAddress` (strings) and `named` is a set of position names that have an object; returns `[{"name", "has_object", "device_count", "inst_types", "universes", "channels", "unpatched"}]` sorted by `_natural(name)`, names `""` excluded.

- [ ] **Step 1: Write the failing tests** (`tests/test_positions.py`)

```python
"""summarize_positions is executed inside Vectorworks; load vwlib with a fake vs."""
import types

from vwmcp import vwlib


def load(fake_vs):
    mod = types.ModuleType("vwlib_live")
    mod.vs = fake_vs
    exec(open(vwlib.__file__, encoding="utf-8").read(), mod.__dict__)
    return mod


def row(position, inst="Robin Forte", channel="101", address="1/1"):
    return {"Position": position, "Inst Type": inst, "Channel": channel,
            "UniverseAddress": address}


def test_summary_per_position_name(fake_vs):
    m = load(fake_vs)
    rows = [row("K C", "Roxx", "401", "14/1"), row("K C", "Roxx", "402", "14/82"),
            row("K C", "MAC Ultra", "438", "15/1"), row("K C", "MAC Ultra", "x", ""),
            row("LX 1", channel="101", address="1/1"), row("", "Hazer", "801", "21/501")]
    out = m.summarize_positions(rows, named={"LX 1"})
    assert [p["name"] for p in out] == ["K C", "LX 1"]
    kc = out[0]
    assert kc["has_object"] is False and kc["device_count"] == 4
    assert list(kc["inst_types"].items()) == [("Roxx", 2), ("MAC Ultra", 2)]
    assert kc["universes"] == [14, 15] and kc["channels"] == [401, 438] and kc["unpatched"] == 1
    lx = out[1]
    assert lx["has_object"] is True and lx["channels"] == [101, 101] and lx["universes"] == [1]


def test_zero_address_counts_as_unpatched_and_channels_can_be_none(fake_vs):
    m = load(fake_vs)
    out = m.summarize_positions([row("L 1", channel="", address="0/0")], named=set())
    assert out == [{"name": "L 1", "has_object": False, "device_count": 1,
                    "inst_types": {"Robin Forte": 1}, "universes": [], "channels": None,
                    "unpatched": 1}]


def test_names_sort_naturally(fake_vs):
    m = load(fake_vs)
    out = m.summarize_positions([row("LX 10"), row("LX 2"), row("K SL")], named=set())
    assert [p["name"] for p in out] == ["K SL", "LX 2", "LX 10"]
```

`fake_vs` is the fixture from `tests/conftest.py`. Loading `vwlib` via `exec` needs nothing from `vs` at import time (the existing `tests/test_drawing.py::test_dimension_strings_read_back_in_document_units` uses the same pattern).

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_positions.py -q`
Expected: FAIL, `AttributeError: module 'vwlib_live' has no attribute 'summarize_positions'`.

- [ ] **Step 3: Implement** — in `src/vwmcp/vwlib.py`, directly above `def list_positions`:

```python
def _universe_of(address):
    """'14/1' -> 14; '', '0/0', malformed -> None (unpatched)."""
    text = _str(address).strip()
    if "/" not in text:
        return None
    uni, _, chan = text.partition("/")
    try:
        u, c = int(uni), int(chan)
    except ValueError:
        return None
    return u if (u, c) != (0, 0) else None


def summarize_positions(rows, named):
    """One summary per distinct non-empty Position name over device rows
    (keys Position, Inst Type, Channel, UniverseAddress). `named` holds the
    names that have a position object. Pure; also used by tests."""
    groups = {}
    for r in rows:
        name = _str(r.get("Position", "")).strip()
        if name:
            groups.setdefault(name, []).append(r)
    out = []
    for name in sorted(groups, key=_natural):
        devs = groups[name]
        types = {}
        for r in devs:
            t = _str(r.get("Inst Type", ""))
            types[t] = types.get(t, 0) + 1
        inst_types = dict(sorted(types.items(), key=lambda kv: (-kv[1], kv[0])))
        universes = sorted({u for u in (_universe_of(r.get("UniverseAddress", "")) for r in devs)
                            if u is not None})
        unpatched = sum(1 for r in devs if _universe_of(r.get("UniverseAddress", "")) is None)
        chans = []
        for r in devs:
            try:
                chans.append(int(_str(r.get("Channel", "")).strip()))
            except ValueError:
                pass
        out.append({"name": name, "has_object": name in named, "device_count": len(devs),
                    "inst_types": inst_types, "universes": universes,
                    "channels": [min(chans), max(chans)] if chans else None,
                    "unpatched": unpatched})
    return out
```

Then change `list_positions` so the device rows carry the two extra fields for the summary but the returned per-device rows stay as before:

```python
def list_positions(include_devices=True):
    devices, rows = {}, []
    for h in lighting_devices():
        r = ld_row(h, ["Unit Number", "Channel", "Inst Type", "Purpose", "UniverseAddress"])
        r["Position"] = _str(vs.GetRField(h, LD, "Position"))
        rows.append(r)
        devices.setdefault(r["Position"], []).append(
            {k: r[k] for k in ("uuid", "Unit Number", "Channel", "Inst Type", "Purpose") if k in r})
    positions, named = [], set()
    for h in all_objects("(T=86)"):
        plug = pio_name(h)
        if plug not in POSITION_PLUGINS:
            continue
        nm = _str(vs.GetRField(h, plug, POSITION_PLUGINS[plug]))
        named.add(nm)
        devs = sorted(devices.get(nm, []), key=lambda r: _natural(r["Unit Number"]))
        p = {"name": nm, "uuid": h_uuid(h), "kind": plug,
             "layer": _str(vs.GetLName(vs.GetLayer(h))), "device_count": len(devs) if nm else 0}
        if include_devices and nm:
            p["devices"] = devs
        positions.append(p)
    positions.sort(key=lambda p: _natural(p["name"]))
    orphans = dict((k, len(v)) for k, v in devices.items() if k and k not in named)
    return {"positions": positions,
            "by_name": summarize_positions(rows, named),
            "unassigned_device_count": len(devices.get("", [])),
            "device_positions_without_object": orphans}
```

Check what keys `ld_row` returns (it includes `uuid`; verify by reading `ld_row` at ~line 402) so the per-device dict above keeps exactly the keys the old code returned (`uuid`, `Unit Number`, `Channel`, `Inst Type`, `Purpose`). If `ld_row` adds other keys (e.g. `layer`), keep the old shape: build the per-device dict from the old field list and only use `UniverseAddress` for the summary.

- [ ] **Step 4: Fix the tool docstring** in `src/vwmcp/tools/spotlight.py::vw_list_positions` — replace the "Returns {...}" sentence with:

```
    Returns {positions: [{name, uuid, kind, layer, device_count, devices?}],
    by_name: [{name, has_object, device_count, inst_types, universes, channels,
    unpatched}] (one per distinct Position name, also when no object carries it,
    so a plot whose positions are only names still gets an overview),
    unassigned_device_count, device_positions_without_object: {name: count}}.
```

- [ ] **Step 5: Run tests and lint**

Run: `uv run pytest tests/test_positions.py tests/test_calls.py tests/test_spotlight.py -q && uv run vwmcp lint src/vwmcp/vwlib.py`
Expected: pass, lint ok (`test_calls.py` enforces the 3.9 syntax).

- [ ] **Step 6: Commit**

```bash
git add src/vwmcp/vwlib.py src/vwmcp/tools/spotlight.py tests/test_positions.py
git commit -m "Positions: Summarise devices per position name, with or without an object"
```

---

### Task 3: Docs

**Files:**
- Modify: `CHANGELOG.md` (under `## Unreleased`), `docs/vs-notes.md` (append a short "Live findings 2026-11-27 (Windows, 2027 German)" entry), `README.md` only if it describes `vw_list_positions`' return shape (grep first; otherwise leave).

- [ ] **Step 1:** CHANGELOG, under Unreleased:

```
- `vw_mvr_check`: on a document where `GDTF Fixture Type ID` is 0 on every
  device (seen on Vectorworks 2027, German, Windows) the `gdtf_unlinked`
  check is skipped with one `field_unused` warning instead of flagging every
  linked device; a non-zero id anywhere keeps the old rule.
- `vw_list_positions`: new `by_name` list, one summary per Position name
  (device count, instrument types, universes, channel range, unpatched) whether
  or not a position object carries the name. Live on a 273-device plot whose
  positions were names only.
```

- [ ] **Step 2:** `docs/vs-notes.md` entry (facts only): VW 2027 32.1.0 German, Windows 11: `GDTF Fixture Type ID` and `GDTF Fixture Custom ID` are "0" on all 247 GDTF devices while `GDTF Fixture Mode` (e.g. "Mode 1 - Standard 16 bit.Robin Forte") and `Num Channels` (54) are set; the document has no `Fixture ID` field, only `FixtureID` holding the fixture type name (as on the BL plot); `ForEachObject` with criteria and a direct `FLayer/FInLayer/NextObj` walk both return the same 273 devices, including ones on invisible layers.
- [ ] **Step 3:** `uv run pytest -q` (expect only the 5 known failures); commit `Docs: Record the 2027 Windows plot findings`.

## Self-review notes
- Spec §1 → Task 1; §2 (helper, `by_name`, docstring) → Task 2; verification/docs → Task 3.
- Names consistent: `summarize_positions(rows, named)`, `_universe_of`, `by_name`, `field_unused`.

## Deviations during implementation
- `inst_types` ties keep first-seen order: the dict is sorted by count only, with no name tie-break.
- Per-device rows in `list_positions` are the `ld_row` output minus `UniverseAddress` and `Position`, which keeps `layer` and `class`, instead of a fixed key list.
- `field_unused` is excluded from `summary`, guarded by `rows and` (no note on an empty document), and decided on the whole document (`gdtf_id_populated`, set in `vw_mvr_check` before the position filter) so the filter cannot change it.
- `_universe_of` requires universe >= 1 and address >= 1, matching `mvr.parse_address`, so `14/0` and `0/5` count as unpatched too.
