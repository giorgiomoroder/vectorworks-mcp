"""Channel hookup import: a CSV/TSV sheet (one row per device) becomes the
`updates` list that vw_set_lighting_device_fields takes.

Headers are matched to Lighting Device field names case-insensitively; a few
common sheet headers have aliases (Addr/Address -> UniverseAddress, Unit ->
Unit Number, Inst/Instrument/Type -> Inst Type). Unknown headers are reported
as ignored, never written. Rows without a key value, or with nothing to
write, are skipped and counted.
"""

from __future__ import annotations

import csv
from pathlib import Path

KEYS = {
    "channel": ["Channel"],
    "unit_number": ["Unit Number"],
    "position+unit_number": ["Position", "Unit Number"],
}
SELECTOR_NAME = {"Channel": "channel", "Unit Number": "unit_number", "Position": "position"}
ALIASES = {
    "addr": "UniverseAddress", "address": "UniverseAddress", "dmx": "UniverseAddress",
    "universe/address": "UniverseAddress", "unit": "Unit Number", "unit #": "Unit Number",
    "u#": "Unit Number", "ch": "Channel", "chan": "Channel", "inst": "Inst Type",
    "instrument": "Inst Type", "type": "Inst Type", "gel": "Color", "gobo": "Template",
    "dim": "Dimmer", "circuit": "Circuit Number", "pos": "Position", "watt": "Wattage",
    "watts": "Wattage",
}


def read_table(path: str | Path) -> list[dict[str, str]]:
    """Rows of a .csv or .tsv file (first row = headers, BOM tolerated)."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in (".csv", ".tsv", ".txt"):
        raise ValueError(f"{path.name}: export the sheet as .csv or .tsv first "
                         "(File > Download/Save As in the spreadsheet app)")
    delimiter = "\t" if ext == ".tsv" else ","
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        return [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in reader]


def _canonical(header: str, known: dict[str, str]) -> str | None:
    h = header.strip()
    low = h.lower()
    if low in known:
        return known[low]
    if low in ALIASES and ALIASES[low].lower() in known:
        return known[ALIASES[low].lower()]
    return None


def plan_updates(rows: list[dict], key: str = "channel", known_fields: list[str] | None = None,
                 column_map: dict[str, str] | None = None) -> dict:
    """Turn sheet rows into vw_set_lighting_device_fields updates."""
    if key not in KEYS:
        raise ValueError(f"unknown key {key!r}; use one of {', '.join(KEYS)}")
    known = {f.lower(): f for f in (known_fields or [])}
    headers = list(rows[0].keys()) if rows else []
    mapping: dict[str, str] = {}
    ignored: list[str] = []
    for h in headers:
        target = (column_map or {}).get(h) or _canonical(h, known)
        if target:
            mapping[h] = target
        elif h:
            ignored.append(h)
    key_fields = KEYS[key]
    by_field = {v: k for k, v in mapping.items()}
    missing = [f for f in key_fields if f not in by_field]
    if missing:
        raise ValueError("no column for the key field(s) %s; headers: %s"
                         % (", ".join(missing), ", ".join(headers)))
    updates, skipped = [], 0
    for row in rows:
        selector = {SELECTOR_NAME[f]: row.get(by_field[f], "").strip() for f in key_fields}
        if not all(selector.values()):
            skipped += 1
            continue
        fields = {t: row.get(h, "").strip() for h, t in mapping.items()
                  if t not in key_fields and row.get(h, "").strip()}
        if not fields:
            skipped += 1
            continue
        updates.append({**selector, "fields": fields})
    return {"updates": updates, "ignored": ignored, "skipped_rows": skipped,
            "columns": {h: t for h, t in mapping.items() if t not in key_fields}}
