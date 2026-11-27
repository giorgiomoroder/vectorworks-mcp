"""Spotlight tools: lighting devices, positions, paperwork reports."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from vwmcp import app, hookup, lightwright, mvr
from vwmcp.app import READ, WRITE, mcp, vw

# Shared description of the `document` guard parameter of the write tools.
DOC = ("Name of the document this call is meant for (as vw_list_documents shows it, with or "
       "without .vwx). If another document is active nothing changes; use vw_switch_document "
       "first. Always set it for a write.")

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
    position: Annotated[str | None, Field(description=(
        "Only devices whose Position field equals this position name exactly (case-sensitive, "
        "as vw_list_positions lists it). Omit for every position."))] = None,
    layer: Annotated[str | None, Field(description=(
        "Only devices on this design layer (exact layer name). Omit for all layers."))] = None,
    fields: Annotated[list[str] | None, Field(description=(
        "Lighting Device parameter names to return, any of: Unit Number, Channel, Dimmer, Universe, "
        "DMX Address, UniverseAddress, Absolute Address, Num Channels, Purpose, Position, Inst Type, "
        "Wattage, Color, Template, Template2, Focus, Circuit Number, Circuit Name, Mark, Symbol Name, "
        "Fixture Mode, GDTF Fixture Name, Device Type, User Field 1 to 6, or any other parameter of "
        "the Lighting Device record. Omit for the default set (all of the above)."))] = None,
    limit: Annotated[int, Field(description=(
        "Maximum number of rows returned, after sorting. Default 5000."))] = 5000,
) -> list[dict]:
    """List the Spotlight Lighting Devices in the live drawing, one row per device, sorted by
    position then unit number.

    Read-only; one job inside Vectorworks. Each row has `uuid` (stable id for
    vw_set_lighting_device_fields and vw_move_objects), `layer`, `class` and the
    requested fields as strings. Use this to look at the plot, verify a write, or
    find a device; use vw_lighting_device_report for paperwork (CSV/JSON file),
    vw_list_positions for the hang structure, and vw_lightwright_snapshot only when
    you want the Lightwright exchange file's view (as of its last export) or the
    bridge is blocked by a dialog.
    """
    return vw("list_lighting_devices", fields=fields, position=position, layer=layer, limit=limit)


@mcp.tool(annotations=WRITE)
def vw_set_lighting_device_fields(
    updates: Annotated[list[dict[str, Any]], Field(description=(
        "One item per device: a selector plus \"fields\". Selector keys: \"uuid\" (from "
        "vw_list_lighting_devices); or \"position\" and \"unit_number\" together (unit numbers "
        "repeat per position); or \"unit_number\" alone when it is unique in the plot; or "
        "\"channel\" when unique. \"fields\" maps Lighting Device parameter names to new string "
        "values, for example {\"position\": \"1E\", \"unit_number\": \"3\", \"fields\": "
        "{\"Channel\": \"101\", \"Color\": \"R02\"}}. Addresses go in \"UniverseAddress\" "
        "as \"universe/address\" such as \"2/101\"."))],
    document: Annotated[str | None, Field(description=DOC)] = None,
) -> list[dict]:
    """Change fields of one or more Lighting Devices in the live drawing, verified by
    reading them back, as one revertible step.

    Changes the document. This is the default way to edit device data; use
    vw_import_hookup for many rows from a spreadsheet export and
    vw_lightwright_patch only for Lightwright round trips or when a dialog
    blocks the bridge. Every selector and field name is validated first; if any
    fails, nothing changes. Universe / DMX Address edits are applied through
    UniverseAddress (Spotlight's source of truth), so set that field rather than
    Universe or DMX Address alone. Undo exactly this call with vw_revert_last.
    Returns one item per device with `uuid`, `before`, `after` (re-read from
    Vectorworks) and `not_applied` for values Spotlight overrode; trust `after`.
    
    GDTF fixture types cannot be assigned here: 'GDTF Fixture Name' and
    'GDTF Fixture Mode' accept text but link nothing (live 2026-11-21);
    the user picks the GDTF in the Object Info palette.
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
def vw_list_positions(
    include_devices: Annotated[bool, Field(description=(
        "True (default) lists each position's devices (uuid, unit number, channel, purpose); "
        "False returns only the positions with their device counts, which is much shorter "
        "on a large plot."))] = True,
) -> dict:
    """List the lighting positions in the live drawing with the devices hung on each,
    plus the devices that have no position and position names no object carries.

    Read-only; one job inside Vectorworks. Positions are Light Position Objects,
    Lighting Pipes, Pipe Ladders, Truss and Hanging Positions, matched to devices
    by the device's Position field (a text match, so a typo shows up here as a
    position name without an object). Returns {positions: [{name, uuid, kind, layer,
    device_count, devices?}],
    by_name: [{name, has_object, device_count, inst_types, universes, channels,
    unpatched}] (one per distinct Position name, also when no object carries it,
    so a plot whose positions are only names still gets an overview),
    unassigned_device_count, device_positions_without_object: {name: count}}.
    Use vw_list_truss for truss runs by system and vw_list_lighting_devices for
    the device rows themselves.
    """
    return vw("list_positions", include_devices=include_devices)


@mcp.tool(annotations=READ)
def vw_lighting_device_report(
    fields: Annotated[list[str] | None, Field(description=(
        "Columns, in order, as Lighting Device parameter names. Omit for the paperwork default: "
        "Position, Unit Number, Inst Type, Wattage, Purpose, Channel, UniverseAddress, Circuit "
        "Number, Color, Template, Focus."))] = None,
    sort_by: Annotated[str | None, Field(description=(
        "Column to sort by, naturally (2 before 10, 1E before 2E; blank values last). Default "
        "Channel; Position then Unit Number gives an instrument schedule. None keeps drawing order."))] = "Channel",
    position: Annotated[str | None, Field(description=(
        "Only devices on this position (exact name). Omit for the whole plot."))] = None,
    format: Annotated[Literal["csv", "json"], Field(description=(
        "\"csv\" (default) for a spreadsheet, \"json\" for a list of row objects."))] = "csv",
    output_path: Annotated[str | None, Field(description=(
        "File path on this Mac to write the report to (folders are created; ~ is expanded). "
        "Omit to only return the text."))] = None,
) -> str:
    """Produce paperwork from the live Lighting Devices, such as a channel hookup or an
    instrument schedule, as CSV or JSON text and optionally a file.

    Read-only in Vectorworks; writes only the file you name. Returns the full
    report text (the same text is written to output_path). For rows to reason
    about rather than a document to hand over, use vw_list_lighting_devices; to
    load a hookup back in, vw_import_hookup.
    """
    fields = fields or REPORT_FIELDS
    rows = vw("list_lighting_devices", fields=fields, position=position)
    text = format_report(sort_rows(rows, sort_by), fields, format)
    if output_path:
        path = Path(output_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return text


@mcp.tool(annotations=READ)
def vw_mvr_check(
    position: Annotated[str | None, Field(description=(
        "Limit the check to the devices on this position (exact name). Omit for the whole plot."))] = None,
) -> dict:
    """Check the Lighting Device data for the gaps that make an MVR export incomplete,
    before the user runs File > Export > Export MVR.

    Read-only; nothing changes and the export itself is a menu action the user
    runs (there is no scripting call for it). Errors, which would break or empty
    the MVR (My Virtual Rig) file: no GDTF fixture type, no fixture mode, missing
    or duplicate Fixture ID, no DMX patch, overlapping DMX footprints in one
    universe, footprint past channel 512. Warnings: device without position,
    position name with no position object, symbol with 2D geometry only (exports
    as empty geometry), symbol missing from the document; gdtf_unlinked: a
    GDTF name typed into the field without a linked fixture type (type id 0),
    which only the Object Info palette's GDTF chooser can fix. Returns {ok,
    device_count, summary: {check: count}, issues: [{check, severity:
    "error" | "warning", message, devices: [{uuid, position, unit, channel}]}],
    document, next_steps}; a "field_missing" issue lists the fields this
    document lacks, whose checks were skipped. Fix findings with
    vw_set_lighting_device_fields (Fixture ID, UniverseAddress, Position,
    Fixture Mode), the Object Info palette (GDTF fixture) or by importing a
    hybrid symbol (vw_list_library, vw_import_resource), then check
    again.
    """
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
    path: Annotated[str, Field(description=(
        "Path on this Mac to a .csv or .tsv exported from the spreadsheet; the first row holds "
        "the column headers."))],
    key: Annotated[Literal["channel", "unit_number", "position+unit_number"], Field(description=(
        "Which column(s) identify the device each row belongs to: \"channel\" (default, the "
        "Channel column), \"unit_number\" (only when unit numbers are unique in the whole plot) "
        "or \"position+unit_number\" (Position and Unit Number columns together; unit numbers "
        "repeat per position)."))] = "channel",
    column_map: Annotated[dict[str, str] | None, Field(description=(
        "Spreadsheet header to Lighting Device field name, for headers the automatic match does "
        "not understand, for example {\"What\": \"Purpose\"}. Automatic matches are "
        "case-insensitive and know Address/Addr/DMX (UniverseAddress), Unit (Unit Number), "
        "Inst/Type (Inst Type) and Gel (Color). Omit when the headers are field names."))] = None,
    dry_run: Annotated[bool, Field(description=(
        "True (default) changes nothing and returns the plan to show the user; False applies it "
        "and then needs `document`."))] = True,
    document: Annotated[str | None, Field(description=(
        DOC + " Required when dry_run is False."))] = None,
) -> dict:
    """Load a channel hookup or instrument schedule from a spreadsheet export into the
    Lighting Devices, as a dry run first and then one revertible step.

    Changes the document only with dry_run=False. Each row is matched to exactly
    one device by `key`; the other columns are written as Lighting Device fields
    when their header is a field name, unknown headers are ignored and listed,
    empty cells are not written. The dry run returns {dry_run, rows, updates
    (the planned per-device changes), ignored_columns, skipped_rows, next_step}.
    Applying goes through vw_set_lighting_device_fields: all-or-nothing (a row
    that matches no device, or several, stops everything), undone with
    vw_revert_last, with `result` holding before/after and `not_applied` for
    values Spotlight overrode. For a handful of edits call
    vw_set_lighting_device_fields directly.
    """
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


# -------------------------------------------------------------- Lightwright


@mcp.tool(annotations=READ)
def vw_lightwright_snapshot(
    position: Annotated[str | None, Field(description=(
        "Only fixtures whose Position matches this name (case-insensitive). Omit for all."))] = None,
    fields: Annotated[list[str] | None, Field(description=(
        "Exchange column names to keep, as the file spells them (Channel, Unit_Number, Inst_Type, "
        "Purpose, Color, Absolute_Address, User_Field_1 ...; the result's `fields` lists what the "
        "export contains). `uid` is always included. Omit for every column."))] = None,
    limit: Annotated[int, Field(description=(
        "Maximum number of fixtures returned (`count` still gives the total). Default 2000."))] = 2000,
) -> dict:
    """Read the Lighting Devices as Spotlight's Lightwright Data Exchange file last
    exported them, from the XML beside the saved document.

    Read-only. The file itself is read without a job (only the document's path
    is asked from Vectorworks), so this works even while a dialog blocks the
    other tools, but it shows the plot as of the last export, which can be older
    than the drawing; vw_list_lighting_devices is the live view. Returns
    {available, path, exported (timestamp), fields, count, fixtures: [{uid,
    lightwright_id, accessories, <fields>...}]}; {available: False, hint} when the
    exchange is off (the hint says how to switch it on); and count 0 with a
    `hint` right after a vw_lightwright_patch, when Vectorworks has written back
    only an acknowledgement and the user must redo the full export. UIDs from
    here are what vw_lightwright_patch takes.
    """
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
    out = {"available": True, "path": snap["path"], "exported": snap["exported"], "fields": snap["fields"],
           "count": len(rows), "fixtures": rows[:limit]}
    if lightwright.is_acknowledgement(snap):
        out["hint"] = lightwright.ACK_HINT
    return out


def _live_values(snap: dict, changes: list[dict]) -> dict:
    """{uid: {xml field: value}} read from the drawing for the fixtures a
    patch touches (one job per position; matched by Unit Number). Fixtures
    not found exactly once are left out, so the inverse falls back to the
    export's values."""
    by_uid = {f["uid"]: f for f in snap["fixtures"]}
    wanted: dict[str, dict[str, list[str]]] = {}  # position -> uid -> xml fields
    for ch in changes:
        f = by_uid.get(ch["uid"])
        if f is None or not f.get("Position") or not f.get("Unit_Number"):
            continue
        wanted.setdefault(f["Position"], {})[ch["uid"]] = [k for k in ch["fields"] if k != "Use_Legend"]
    live = {}
    for position, uids in wanted.items():
        tags = list(dict.fromkeys(t for ts in uids.values() for t in ts))
        fields = ["Unit Number", *(lightwright.record_field(t) for t in tags if lightwright.record_field(t) != "Unit Number")]
        devices = vw("list_lighting_devices", position=position, fields=fields)
        for uid, ts in uids.items():
            unit = by_uid[uid]["Unit_Number"]
            hits = [d for d in devices if str(d.get("Unit Number", "")) == unit]
            if len(hits) == 1:
                live[uid] = {t: hits[0][lightwright.record_field(t)] for t in ts
                             if lightwright.record_field(t) in hits[0]}
    return live


@mcp.tool(annotations=WRITE)
def vw_lightwright_patch(
    changes: Annotated[list[dict], Field(description=(
        "One item per fixture: {\"uid\": \"1246.1.1.0.0\", \"fields\": {\"Channel\": \"201\"}}. "
        "`uid` and the field names (exchange spelling: Channel, Unit_Number, Inst_Type, Purpose, "
        "Color ...) come from vw_lightwright_snapshot; only fields in the export can be written, "
        "plus Symbol_Name, Inst_Type and Wattage."))],
    dry_run: Annotated[bool, Field(description=(
        "True (default) returns the patch text without writing anything; False writes it."))] = True,
    document: Annotated[str | None, Field(description=DOC)] = None,
) -> dict:
    """Change Lighting Device fields through Spotlight's Lightwright Data Exchange file
    instead of a job, for Lightwright round trips or when a dialog blocks the bridge.

    With dry_run=False this changes the document, indirectly: the patch is
    written beside the .vwx and Vectorworks applies it 1 to 2 s after it next
    gains focus, so the user has to click into Vectorworks; verify afterwards
    with vw_list_lighting_devices. Prefer vw_set_lighting_device_fields when the
    bridge works. Refuses deletes, fields not in the export, a Symbol_Name no
    fixture uses yet (an unknown symbol breaks fixture selection drawing-wide,
    irreversibly) and a type change without Wattage. Before writing, the full
    export is copied to ~/.vwmcp/lightwright/ (`backup`) and the drawing's
    current values of the touched fixtures are journaled (`inverse_from`: live,
    or export when a fixture could not be read, in which case the undo restores
    possibly stale export values); vw_revert_last writes the inverse patch, which
    again needs a click. After a patch the file holds only Vectorworks'
    acknowledgement until the next full export. Returns {dry_run, path, changes,
    patch, and when written: backup, inverse_from, note}.
    """
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
    try:
        live = _live_values(snap, changes)
    except Exception:  # noqa: BLE001  (bridge blocked: the export's values will do)
        live = {}
    complete = all(all(k in live.get(ch["uid"], {}) for k in ch["fields"] if k != "Use_Legend")
                   for ch in changes)
    op = lightwright.revert_op(xml, text, snap, changes, live)
    backup = lightwright.backup_export(xml, text, lightwright.BACKUP_DIR)
    lightwright.write_patch(xml, patch)
    app.get_journal().record(info.get("name", ""), "vw_lightwright_patch", [op])
    out["backup"] = str(backup)
    out["inverse_from"] = "live" if complete else "export"
    out["note"] = ("Written. Vectorworks applies it when it next gains focus (click into it); "
                   "then re-read with vw_list_lighting_devices. The full export was copied to "
                   f"{backup}; the file beside the document now holds the patch.")
    if not complete:
        out["note"] += (" The drawing's current values could not be read for every fixture, so "
                        "vw_revert_last restores the export's values, which may be stale.")
    return out
