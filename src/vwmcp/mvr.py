"""MVR export pre-flight: find the data gaps that make an MVR (My Virtual Rig)
export from Vectorworks Spotlight incomplete or wrong.

Pure functions over rows read from the document (see `vwlib.mvr_data`). Nothing
in VectorScript triggers the export itself, so the export stays a menu action
(File > Export > Export MVR); this tool finds what to fix beforehand.

Each MVR fixture needs: a GDTF fixture type and mode (else the fixture has no
geometry or channel layout in the receiving console/visualizer), a unique
Fixture ID (MVR's identity), a patch whose footprint does not collide with
another fixture in its universe, and a 3D symbol (2D-only symbols export as
empty geometry). A position name that matches no position object exports the
fixture loose.
"""

from __future__ import annotations

import re
from collections import Counter

# Lighting Device fields the checks read. Missing ones are reported, not fatal.
FIELDS = [
    "Unit Number", "Channel", "Position", "Inst Type", "Symbol Name", "Fixture Mode",
    "GDTF Fixture Name", "Fixture ID", "UniverseAddress", "Absolute Address",
    "Num Channels",
]
# Logical field -> names it may have in a document, best first (live 2026-11-20
# on a VW 2026 plot: "GDTF Fixture Mode" is separate from "Fixture Mode"; the
# "FixtureID" field there holds the fixture *type* name, e.g. "Astera AX5", so
# it is NOT an alias for a per-fixture id and the id checks stay skipped until
# a document has a real "Fixture ID" field).
ALIASES = {
    "Fixture Mode": ["GDTF Fixture Mode", "Fixture Mode"],
}
ERROR, WARNING = "error", "warning"
# check -> (severity, fields it needs)
NEEDS = {
    "no_gdtf": (ERROR, ["GDTF Fixture Name"]),
    "gdtf_unlinked": (ERROR, ["GDTF Fixture Name", "GDTF Fixture Type ID"]),
    "no_mode": (ERROR, ["Fixture Mode"]),
    "no_fixture_id": (ERROR, ["Fixture ID"]),
    "duplicate_fixture_id": (ERROR, ["Fixture ID"]),
    "unpatched": (ERROR, ["UniverseAddress"]),
    "address_overlap": (ERROR, ["UniverseAddress", "Num Channels"]),
    "address_shared": (WARNING, ["UniverseAddress", "Num Channels"]),
    "address_past_512": (ERROR, ["UniverseAddress", "Num Channels"]),
    "no_position": (WARNING, ["Position"]),
    "position_without_object": (WARNING, ["Position"]),
    "symbol_without_3d": (WARNING, ["Symbol Name"]),
    "symbol_missing": (WARNING, ["Symbol Name"]),
}
# vs.GetSymbolType: 0 = 2D only, 1 = 3D only, 2 = hybrid (to be confirmed live).
SYMBOL_2D = 0


def parse_address(text: str) -> tuple[int, int] | None:
    """'2/101' -> (2, 101); empty, malformed or '0/0' -> None (unpatched)."""
    m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", text or "")
    if not m:
        return None
    uni, addr = int(m.group(1)), int(m.group(2))
    if uni < 1 or addr < 1:
        return None
    return uni, addr


def _int(text, default=1) -> int:
    try:
        return int(float(str(text).strip()))
    except (TypeError, ValueError):
        return default


def _ref(row: dict) -> dict:
    return {"uuid": row.get("uuid", ""), "position": row.get("Position", ""),
            "unit": row.get("Unit Number", ""), "channel": row.get("Channel", "")}


def _label(row: dict) -> str:
    pos, unit, ch = row.get("Position", ""), row.get("Unit Number", ""), row.get("Channel", "")
    where = " ".join(p for p in (pos, ("unit " + unit) if unit else "") if p)
    return where or ("channel " + ch if ch else row.get("uuid", "?"))


def footprint_overlaps(rows: list[dict]) -> list[tuple[dict, dict]]:
    """Pairs of devices whose DMX footprints overlap inside one universe."""
    by_universe: dict[int, list[tuple[int, int, dict]]] = {}
    for r in rows:
        parsed = parse_address(r.get("UniverseAddress", ""))
        if not parsed:
            continue
        uni, start = parsed
        end = start + max(_int(r.get("Num Channels"), 1), 1) - 1
        by_universe.setdefault(uni, []).append((start, end, r))
    pairs = []
    for items in by_universe.values():
        items.sort(key=lambda t: (t[0], t[1]))
        for i, (s1, e1, r1) in enumerate(items):
            for s2, e2, r2 in items[i + 1:]:
                if s2 > e1:
                    break
                pairs.append((r1, r2))
    return pairs


def run_checks(data: dict) -> dict:
    """data: {"fields": [present field names], "devices": [rows], "positions":
    [names], "symbols": {name: {"type": int}}}. Returns ok, summary, issues."""
    present = set(data.get("fields", []))
    rows = data.get("devices", [])
    # resolve aliases: copy the first present spelling into the logical name
    for logical, names in ALIASES.items():
        found = next((n for n in names if n in present), None)
        if found:
            present.add(logical)
            if found != logical:
                for r in rows:
                    r[logical] = r.get(found, "")
    positions = set(data.get("positions", []))
    symbols = data.get("symbols", {})
    issues: list[dict] = []
    missing = sorted({f for _, (_, need) in NEEDS.items() for f in need if f not in present})
    if missing:
        issues.append({"check": "field_missing", "severity": WARNING,
                       "message": "Lighting Device fields not in this document, checks "
                                  "skipped: " + ", ".join(missing), "devices": []})

    def active(check):
        return all(f in present for f in NEEDS[check][1])

    def add(check, devices, message):
        if devices:
            issues.append({"check": check, "severity": NEEDS[check][0], "message": message,
                           "devices": [_ref(r) for r in devices]})

    def blank(check, field, message):
        if active(check):
            add(check, [r for r in rows if not str(r.get(field, "")).strip()], message)

    blank("no_gdtf", "GDTF Fixture Name",
          "No GDTF fixture type: these export without geometry or channel layout. Pick a "
          "GDTF fixture in the Object Info palette (typing a name into the field does not link it).")
    if active("gdtf_unlinked"):
        ids = {str(r.get("GDTF Fixture Type ID", "0")).strip() for r in rows}
        if rows and ids <= {"", "0"}:
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
    if active("no_mode") and active("no_gdtf"):
        add("no_mode", [r for r in rows if str(r.get("GDTF Fixture Name", "")).strip()
                        and not str(r.get("Fixture Mode", "")).strip()],
            "GDTF fixture set but no GDTF fixture mode (DMX mode) chosen.")
    elif active("no_mode"):
        blank("no_mode", "Fixture Mode", "No fixture mode (DMX mode) chosen.")
    blank("no_fixture_id", "Fixture ID",
          "No Fixture ID: MVR identifies fixtures by it (Spotlight > Numbering can fill it).")
    if active("duplicate_fixture_id"):
        counts = Counter(str(r.get("Fixture ID", "")).strip() for r in rows)
        dups = sorted(k for k, n in counts.items() if k and n > 1)
        for fid in dups:
            add("duplicate_fixture_id",
                [r for r in rows if str(r.get("Fixture ID", "")).strip() == fid],
                "Fixture ID %s is used by %d devices." % (fid, counts[fid]))
    if active("unpatched"):
        add("unpatched", [r for r in rows if parse_address(r.get("UniverseAddress", "")) is None],
            "No DMX patch (UniverseAddress empty or 0/0).")
    if active("address_overlap"):
        for r1, r2 in footprint_overlaps(rows):
            a1, a2 = r1["UniverseAddress"].strip(), r2["UniverseAddress"].strip()
            if parse_address(a1) == parse_address(a2):
                add("address_shared", [r1, r2],
                    "%s and %s share address %s (fine if they are meant to run together)."
                    % (_label(r1), _label(r2), a1))
            else:
                add("address_overlap", [r1, r2],
                    "%s at %s and %s at %s overlap (footprints %s and %s channels)." % (
                        _label(r1), a1, _label(r2), a2, _int(r1.get("Num Channels")),
                        _int(r2.get("Num Channels"))))
    if active("address_past_512"):
        past = []
        for r in rows:
            p = parse_address(r.get("UniverseAddress", ""))
            if p and p[1] + max(_int(r.get("Num Channels"), 1), 1) - 1 > 512:
                past.append(r)
        add("address_past_512", past, "Footprint runs past channel 512 of its universe.")
    if active("no_position"):
        add("no_position", [r for r in rows if not str(r.get("Position", "")).strip()],
            "No position: these export as loose fixtures.")
        for name in sorted({str(r.get("Position", "")).strip() for r in rows}
                           - positions - {""}):
            add("position_without_object",
                [r for r in rows if str(r.get("Position", "")).strip() == name],
                "Position '%s' has no position object (truss, pipe, Light Position)." % name)
    if active("symbol_without_3d"):
        for name in sorted({str(r.get("Symbol Name", "")).strip() for r in rows} - {""}):
            devs = [r for r in rows if str(r.get("Symbol Name", "")).strip() == name]
            info = symbols.get(name)
            if info is None:
                add("symbol_missing", devs, "Symbol '%s' is not in the document." % name)
            elif info.get("type") == SYMBOL_2D:
                add("symbol_without_3d", devs,
                    "Symbol '%s' is 2D only: exports as empty geometry (import a hybrid "
                    "or 3D symbol, or rely on the GDTF model)." % name)

    summary = Counter()
    for i in issues:
        if i["check"] not in ("field_missing", "field_unused"):
            summary[i["check"]] += len(i["devices"])
    return {
        "ok": not any(i["severity"] == ERROR for i in issues),
        "device_count": len(rows),
        "summary": dict(summary),
        "issues": issues,
    }
