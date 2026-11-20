"""Spotlight tools: lighting devices, positions, paperwork reports."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any, Literal

from mcp.server.mcpserver.exceptions import ToolError

from vwmcp import app, hookup, mvr
from vwmcp.app import READ, WRITE, mcp, vw

REPORT_FIELDS = [
    "Position", "Unit Number", "Inst Type", "Wattage", "Purpose", "Channel",
    "UniverseAddress", "Circuit Number", "Color", "Template", "Focus",
]


def _sort_key(value: str):
    parts = re.split(r"(\d+)", value or "")
    return (value == "", [(0, int(p)) if p.isdigit() else (1, p.lower()) for p in parts])


def sort_rows(rows: list[dict], sort_by: str | None) -> list[dict]:
    if not sort_by:
        return rows
    return sorted(rows, key=lambda r: _sort_key(str(r.get(sort_by, ""))))


def _same(a: Any, b: Any) -> bool:
    return str(a).strip() == str(b).strip()


def verify_updates(requested: list[dict], before: list[dict], actual: list[dict]) -> list[dict]:
    """Compare requested values to what Vectorworks kept after the reset."""
    out = []
    for req, prev, now in zip(requested, before, actual):
        after = {k: now.get(k, "") for k in req["fields"]}
        item = {"uuid": prev["uuid"], "before": prev.get("before", {}), "after": after}
        missed = {
            k: {"requested": str(v), "actual": after[k]}
            for k, v in req["fields"].items()
            if not _same(v, after[k])
        }
        if missed:
            item["not_applied"] = missed
        out.append(item)
    return out


def format_report(rows: list[dict], fields: list[str], fmt: str) -> str:
    if fmt == "json":
        return json.dumps([{f: r.get(f, "") for f in fields} for r in rows], indent=2)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(fields)
    for r in rows:
        w.writerow([r.get(f, "") for f in fields])
    return buf.getvalue()


@mcp.tool(annotations=READ)
def vw_list_lighting_devices(
    position: str | None = None,
    layer: str | None = None,
    fields: list[str] | None = None,
    limit: int = 5000,
) -> list[dict]:
    """All Spotlight Lighting Devices, sorted by position then unit number.

    Default fields: Unit Number, Channel, Dimmer, Universe, DMX Address,
    UniverseAddress, Absolute Address, Num Channels, Purpose, Position,
    Inst Type, Wattage, Color, Template (gobo), Template2, Focus, Circuit
    Number/Name, Mark, Symbol Name, Fixture Mode, GDTF Fixture Name, Device
    Type, User Field 1-6. Pass `fields` to choose others (any Lighting Device
    parameter name). Filter by exact position name or layer. Each row has a uuid.
    """
    return vw("list_lighting_devices", fields=fields, position=position, layer=layer, limit=limit)


@mcp.tool(annotations=WRITE)
def vw_set_lighting_device_fields(
    updates: list[dict[str, Any]], document: str | None = None
) -> list[dict]:
    """Bulk-edit Lighting Device fields in one undo step.

    `updates` is a list of {selector, "fields": {name: value}} where selector is
    one of: "uuid"; "position" + "unit_number" (unit numbers repeat per
    position); "unit_number" alone if unique; or "channel" if unique.
    Example: [{"position": "1E", "unit_number": "3", "fields": {"Channel": "101",
    "Color": "R02"}}].

    All selectors and field names are validated first; if any fail, nothing
    changes. Revert exactly this call with vw_revert_last. Universe / DMX Address edits are applied via UniverseAddress
    (Spotlight's source of truth). Returns before/after per device as re-read
    from Vectorworks, with `not_applied` listing anything Spotlight overrode.
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first).
    """
    app.require_document(document)
    for u in updates:
        if not isinstance(u.get("fields"), dict) or not u["fields"]:
            raise ToolError(f"each update needs a non-empty 'fields' object: {u!r}")
    out = vw("set_lighting_device_fields", updates=updates)
    before = out["devices"]
    app.get_journal().record(
        out["document"], "vw_set_lighting_device_fields",
        [{"op": "fields", "uuid": b["uuid"], "record": "Lighting Device", "before": b["before"]}
         for b in before],
    )
    fields = sorted({k for u in updates for k in u["fields"]})
    actual = vw("read_devices", uuids=[b["uuid"] for b in before], fields=fields)
    return verify_updates(updates, before, actual)


@mcp.tool(annotations=READ)
def vw_list_positions(include_devices: bool = True) -> dict:
    """Lighting positions (Light Position Obj, Lighting Pipe, Ladder, Truss,
    Hanging Position) with the devices whose Position field names them.
    Also reports how many devices have no position, and position names used
    by devices that have no matching position object."""
    return vw("list_positions", include_devices=include_devices)


@mcp.tool(annotations=READ)
def vw_lighting_device_report(
    fields: list[str] | None = None,
    sort_by: str | None = "Channel",
    position: str | None = None,
    format: Literal["csv", "json"] = "csv",
    output_path: str | None = None,
) -> str:
    """Paperwork export of Lighting Devices (channel hookup, instrument
    schedule...). Default columns: Position, Unit Number, Inst Type, Wattage,
    Purpose, Channel, UniverseAddress, Circuit Number, Color, Template, Focus.
    Sorted naturally by `sort_by` (blank values last). Returns the CSV/JSON
    text, and also writes it to `output_path` if given."""
    fields = fields or REPORT_FIELDS
    rows = vw("list_lighting_devices", fields=fields, position=position)
    text = format_report(sort_rows(rows, sort_by), fields, format)
    if output_path:
        path = Path(output_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return text


@mcp.tool(annotations=READ)
def vw_mvr_check(position: str | None = None) -> dict:
    """Pre-flight for File > Export > Export MVR: finds the Lighting Device data
    gaps that make an MVR (My Virtual Rig) file incomplete, without changing
    anything. Errors (would break the export): no GDTF fixture type, no fixture
    mode, missing or duplicate Fixture ID, no DMX patch, overlapping DMX
    footprints in one universe, footprint past channel 512. Warnings: device
    without position, position name with no position object, symbol with 2D
    geometry only (exports as empty geometry), symbol missing from the document.
    Fields this document lacks are listed under `field_missing` and their checks
    skipped. `position` limits the check to one position. Fix findings with
    vw_set_lighting_device_fields (Fixture ID, UniverseAddress, Position) or by
    importing a hybrid symbol (vw_list_library_resources / vw_import_resource).
    The export itself has no scripting call; run it from the File menu after a
    clean check."""
    data = vw("mvr_data")
    if position is not None:
        data["devices"] = [r for r in data["devices"] if r.get("Position", "") == position]
    out = mvr.run_checks(data)
    out["document"] = data.get("document", "")
    out["next_steps"] = (
        "Fix errors with vw_set_lighting_device_fields (Fixture ID, UniverseAddress, "
        "Position, Fixture Mode) or in the Object Info palette (GDTF fixture); then "
        "File > Export > Export MVR in Vectorworks."
        if not out["ok"] else "No blocking issues: File > Export > Export MVR in Vectorworks."
    )
    return out


@mcp.tool(annotations=WRITE)
def vw_import_hookup(
    path: str,
    key: Literal["channel", "unit_number", "position+unit_number"] = "channel",
    column_map: dict[str, str] | None = None,
    dry_run: bool = True,
    document: str | None = None,
) -> dict:
    """Import a channel hookup / instrument schedule from a spreadsheet export
    (.csv or .tsv, first row = headers) into the Lighting Devices. Each row is
    matched to one device by `key`: its Channel, its Unit Number, or Position +
    Unit Number (unit numbers repeat per position). The other columns are
    written as Lighting Device fields when their header is a field name
    (case-insensitive; Address/Addr/DMX mean UniverseAddress, Unit means Unit
    Number, Inst/Type mean Inst Type, Gel means Color); `column_map` overrides
    that, e.g. {"What": "Purpose"}. Unknown headers are ignored and listed.
    Empty cells are not written. With dry_run (default) nothing changes: you get
    the planned updates, ignored columns and skipped rows to show the user.
    With dry_run=False and `document` set, the updates go through
    vw_set_lighting_device_fields: all-or-nothing (a row that matches no device
    or several stops everything), one revertible step, with `not_applied` for
    anything Spotlight overrode. """ + app.DOCUMENT_HINT
    try:
        rows = hookup.read_table(path)
    except (OSError, ValueError) as e:
        raise ToolError(str(e)) from e
    known = vw("ld_field_names")
    try:
        plan = hookup.plan_updates(rows, key=key, known_fields=known, column_map=column_map)
    except ValueError as e:
        raise ToolError(str(e)) from e
    out = {"dry_run": dry_run, "rows": len(rows), **plan}
    if dry_run:
        out["next_step"] = "Show this plan to the user; run again with dry_run=False and document=... to apply."
        return out
    if not document:
        raise ToolError("Applying needs document=<name of the plot> so the hookup cannot land in another open file.")
    if not plan["updates"]:
        raise ToolError("Nothing to apply: every row was skipped (empty key or no values).")
    out["result"] = vw_set_lighting_device_fields(plan["updates"], document=document)
    return out
