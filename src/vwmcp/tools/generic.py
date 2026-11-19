"""Generic Vectorworks tools: session, document, objects, records, symbols."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.utilities.types import Image
from mcp.types import TextContent

from vwmcp import app, calls, config, documents, render, screenshot, vslint
from vwmcp.app import READ, WRITE, mcp, vw
from vwmcp.client import BridgeError
from vwmcp.journal import JournalError
from vwmcp.trigger import DEFAULT_APP

PING_CODE = """
v = vs.GetVersionEx()
result = {"version": "%d.%d.%d" % tuple(v[:3]), "build": v[-1], "document": vs.GetFName()}
"""

LOOKUP_CODE = """
import json as _json
_q = _json.loads(%r)
_words = _q["query"].lower().split()
_hits = []
for _n in dir(vs):
    if _n.startswith("_"):
        continue
    _doc = getattr(getattr(vs, _n), "__doc__", None) or ""
    _hay = (_n + " " + _doc).lower()
    if all(w in _hay for w in _words):
        _score = sum(w in _n.lower() for w in _words)
        _hits.append((-_score, _n, _doc))
_hits.sort()
result = [{"name": n, "doc": d} for _, n, d in _hits[: _q["limit"]]]
"""


def _run_raw(code: str, timeout: float | None = None) -> dict:
    try:
        return app.get_bridge().run(code, timeout=timeout)
    except BridgeError as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations=READ)
def vw_ping() -> dict:
    """Check the Vectorworks bridge: returns Vectorworks version, active document
    and bridge version. Warns if the installed bridge doesn't match this server."""
    res = _run_raw(PING_CODE)
    if not res["ok"]:
        raise ToolError(res["error"])
    out = {
        "vectorworks_version": res["value"]["version"],
        "build": res["value"]["build"],
        "document": res["value"]["document"],
        "bridge_version": res.get("bridge_version"),
    }
    warnings = []
    if out["bridge_version"] != app.EXPECTED_BRIDGE_VERSION:
        warnings.append(
            f"Installed bridge is {out['bridge_version']}, server expects "
            f"{app.EXPECTED_BRIDGE_VERSION}. Run `vwmcp install-plugin` and retry."
        )
    major = int(out["vectorworks_version"].split(".")[0])
    if major not in app.TESTED_VW_MAJORS:
        tested = ", ".join(f"Vectorworks {y}" for y in app.TESTED_VW_MAJORS.values())
        warnings.append(
            f"Vectorworks {out['vectorworks_version']} is untested (tested: {tested}). "
            "Field names and behavior may differ; verify results and save first."
        )
    if warnings:
        out["warning"] = " ".join(warnings)
    return out


@mcp.tool(annotations=WRITE)
def vw_exec_python(
    code: str, modifies_document: bool = True, timeout: float | None = None,
    document: str | None = None, lint: bool = True,
) -> dict:
    """Run arbitrary Python inside Vectorworks with `vs` in scope.

    Returns stdout, the value of the last expression (or of a variable named
    `result`), and the traceback if it raised. Vectorworks embeds Python 3.9
    (2026) or 3.14 (2027); stay 3.9-compatible to be safe. Handles are only
    valid during the call; return UUIDs (vs.GetObjectUuid) to refer to
    objects later. A wrong vs.* signature can pop a modal "Script Errors"
    dialog in Vectorworks instead of raising; check with vw_vs_lookup first.

    With modifies_document=True (default) the objects the code creates are
    recorded, even if it fails halfway, and vw_revert_last deletes exactly
    those. Changes to objects that existed before (moves, attributes,
    deletions) are not revertible. Set modifies_document=False for read-only
    code (faster, no journal entry). timeout: seconds to wait (default 30);
    raise it for large drawing scripts.

    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first).
    lint (default True): the code is checked before it is sent (vw_lint).
    Syntax errors, vs.* calls with a wrong number of arguments and
    deprecated calls stop the call with a report instead of opening the
    blocking Script Errors dialog; unknown vs.* names come back as
    `lint_warnings`. lint=False skips the check (only if the check is wrong).
    """
    app.require_document(document)
    lint_warnings = _preflight(code, "<vw_exec_python>") if lint else []
    out = _exec_python(code, modifies_document, timeout)
    if lint_warnings:
        out["lint_warnings"] = lint_warnings
    return out


def _preflight(code: str, filename: str) -> list[str]:
    """Lint code; raise ToolError on errors, return warning lines."""
    report = vslint.lint(code, filename, year=config.VW_VERSION)
    if report["errors"]:
        raise ToolError(
            "Not sent to Vectorworks: this would likely open the blocking Script Errors dialog.\n"
            + vslint.format_report(report, filename)
            + "\nFix the code (check signatures with vw_vs_lookup), or pass lint=False if the check is wrong.")
    return [f"line {w['line']}: {w['message']}" for w in report["warnings"]]


def _exec_python(code: str, modifies_document: bool, timeout: float | None) -> dict:
    if not modifies_document:
        res = _run_raw(code, timeout)
        return {k: res.get(k) for k in ("ok", "value", "stdout", "error", "traceback")}
    try:
        res = calls.call_result(app.get_bridge(), "exec_tracked", timeout=timeout, code=code)
    except calls.VWError as e:
        raise ToolError(f"{e}\n\n{e.traceback}".strip()) from e
    except BridgeError as e:
        raise ToolError(str(e)) from e
    out = res["value"]
    created = out.get("created") or []
    deleted = out.get("deleted_existing") or 0
    # No created objects: it changed existing ones (or nothing) -> revert barrier.
    app.get_journal().record(
        out["document"], "vw_exec_python",
        [{"op": "created", "uuid": u} for u in created] or None,
    )
    result = {
        "ok": out.get("error") is None,
        "value": out.get("value"),
        "stdout": res.get("stdout", ""),
        "error": out.get("error"),
        "traceback": out.get("traceback"),
        "created": len(created),
        "revertable": bool(created),
    }
    if deleted:
        result["warning"] = (
            f"{deleted} pre-existing object(s) were deleted; vw_revert_last can't restore them."
        )
    return result


@mcp.tool(annotations=WRITE)
def vw_exec_file(
    path: str, modifies_document: bool = True, timeout: float | None = 120,
    document: str | None = None, lint: bool = True,
) -> dict:
    """Run a Python script file (a path on this Mac, e.g. in the project's
    _claude_scripts folder) inside Vectorworks, exactly like vw_exec_python
    with its contents: created objects are revertible, the file is linted
    first. Default timeout 120 s for large scripts.
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    p = Path(path).expanduser()
    try:
        code = p.read_text(encoding="utf-8")
    except OSError as e:
        raise ToolError(f"Can't read {p}: {e}") from e
    lint_warnings = _preflight(code, p.name) if lint else []
    out = _exec_python(code, modifies_document, timeout)
    if lint_warnings:
        out["lint_warnings"] = lint_warnings
    return out


@mcp.tool(annotations=READ)
def vw_lint(code: str | None = None, path: str | None = None) -> dict:
    """Check Python for Vectorworks without running it: syntax errors, vs.*
    calls with a wrong number of arguments, deprecated calls (these would open
    the blocking "Script Errors" dialog) and unknown vs.* names. Pass code or
    the path of a script file (e.g. a menu command script). Works without
    Vectorworks. Argument types are not checked."""
    if (code is None) == (path is None):
        raise ToolError("Pass either code or path.")
    name = "<code>"
    if path is not None:
        p = Path(path).expanduser()
        try:
            code = p.read_text(encoding="utf-8")
        except OSError as e:
            raise ToolError(f"Can't read {p}: {e}") from e
        name = str(p)
    report = vslint.lint(code, name, year=config.VW_VERSION)
    report["ok"] = not report["errors"]
    report["api"] = vslint.load_api(config.VW_VERSION).get("vectorworks")
    return report


def _remember_active() -> None:
    """Note the active document's path (Vectorworks' AppleScript doesn't report it)."""
    try:
        info = vw("document_info")
        documents.remember(info.get("name", ""), info.get("path", ""))
    except Exception:
        pass  # a dialog may be open; listing still works without it


@mcp.tool(annotations=READ)
def vw_list_documents() -> dict:
    """Open Vectorworks documents (front to back; `active` is the one all
    other tools work on) and the known file paths. Uses AppleScript from
    outside Vectorworks, no Accessibility permission needed."""
    _remember_active()
    try:
        return documents.list_documents()
    except documents.DocumentsError as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations=WRITE)
def vw_switch_document(name: str) -> dict:
    """Bring an open, saved document to the front: `name` as vw_list_documents
    shows it (".vwx" may be left out) or its full path. Verified afterwards.
    Unsaved documents can't be switched to; doesn't open closed files. All
    other tools act on the active document, so check vw_document_info before
    writing."""
    _remember_active()
    try:
        out = documents.switch_document(name)
    except documents.DocumentsError as e:
        raise ToolError(str(e)) from e
    _remember_active()
    return out


@mcp.tool(annotations=READ)
def vw_export_geometry(
    layer: str | None = None,
    classes: list[str] | None = None,
    out_path: str | None = None,
    limit: int = 20000,
    timeout: float | None = 60,
    attributes: bool = True,
) -> dict:
    """Read back the 2D geometry of one layer (default: active layer), in
    document units: lines and polygons as points, arcs as center/radius/
    angles, texts with origin and string, dimensions with their text.
    Descends into groups; plug-in objects (chain dimensions, doors) are one
    entry each. Use it to verify what is really in the file, e.g. to render
    it over a scan. Optionally filter by exact class names.

    attributes (default on): every object also gets "attrs" with its fill
    (pattern 0 none / 1 solid background color / 2 solid foreground color,
    colors as #rrggbb) and pen (color, weight in mils, style) and whether
    each follows the class ("by_class"). Compare these with neighboring
    objects before drawing new ones in the same style.

    With out_path (a file path on this Mac, e.g. in the project folder) the
    full JSON is written there and only a summary is returned; use that for
    large layers to keep the conversation small."""
    try:
        res = calls.call_result(
            app.get_bridge(), "export_geometry", timeout=timeout,
            layer=layer, classes=classes, limit=limit, attributes=attributes,
        )
    except calls.VWError as e:
        raise ToolError(f"{e}\n\n{e.traceback}".strip()) from e
    except BridgeError as e:
        raise ToolError(str(e)) from e
    data = res["value"]
    if not out_path:
        return data
    path = Path(out_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"path": str(path), **geometry_summary(data)}


def geometry_summary(data: dict) -> dict:
    """Counts per type and class plus the extent of all points."""
    by_type: dict[str, int] = {}
    by_class: dict[str, int] = {}
    xs: list[float] = []
    ys: list[float] = []
    for o in data["objects"]:
        by_type[o["type"]] = by_type.get(o["type"], 0) + 1
        by_class[o["class"]] = by_class.get(o["class"], 0) + 1
        for p in o.get("points") or []:
            xs.append(p[0])
            ys.append(p[1])
        for key in ("origin", "center"):
            if key in o:
                xs.append(o[key][0])
                ys.append(o[key][1])
    extent = [[min(xs), min(ys)], [max(xs), max(ys)]] if xs else None
    return {
        "document": data["document"], "layer": data["layer"], "count": len(data["objects"]),
        "truncated": data["truncated"], "by_type": by_type, "by_class": by_class, "extent": extent,
    }


@mcp.tool(annotations=READ)
def vw_render_layers(
    layers: list[str] | None = None,
    bbox: list[float] | None = None,
    classes: list[str] | None = None,
    max_size: int = 1600,
    fills: bool = True,
    out_path: str | None = None,
    timeout: float | None = 60,
) -> Image:
    """Picture of design layers drawn from their real geometry, independent
    of what the Vectorworks window shows (no Screen Recording needed). Use
    it to check drawing work on any layer, visible or not.

    layers: layer names, drawn in this order (default: the active layer).
    bbox: [x_min, y_min, x_max, y_max] in document units to zoom in
    (default: everything). max_size: long side in px. out_path: also save
    the PNG there. It is a check picture, not a plot: object colors, solid
    fills and line weights are shown; hatches, dash styles, opacity and
    curved polyline segments are not, texts are only marked with a small
    cross at their origin, and symbols / plug-in objects are gray boxes.
    All fills are painted below all lines."""
    exported = []
    for name in layers or [None]:
        try:
            res = calls.call_result(
                app.get_bridge(), "export_geometry", timeout=timeout,
                layer=name, classes=classes, limit=20000, attributes=True,
            )
        except calls.VWError as e:
            raise ToolError(f"{e}\n\n{e.traceback}".strip()) from e
        except BridgeError as e:
            raise ToolError(str(e)) from e
        exported.append(res["value"])
    try:
        data, _info = render.render(exported, bbox=bbox, max_size=max_size, fills=fills)
    except ValueError as e:
        raise ToolError(str(e)) from e
    if out_path:
        path = Path(out_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return Image(data=data, format="png")


@mcp.tool(annotations=WRITE)
def vw_duplicate_layer(
    source: str,
    name: str,
    visibility: str | None = None,
    uuid_map: bool = False,
    document: str | None = None,
) -> dict:
    """Copy a design layer with all its objects, e.g. to try a variant
    without touching the original. The copy keeps the scale, is placed
    right after the source in the layer list, and the active layer stays
    active. visibility: "visible", "hidden" or "gray"; default: the same as
    the source has now (layers share coordinates, so a visible copy lies
    exactly on top of the original). uuid_map=True also returns
    {source object uuid: copy uuid}, including objects inside groups.
    Revertible with vw_revert_last (deletes the copy).
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    out = vw("duplicate_layer", source=source, name=name, visibility=visibility, uuid_map=uuid_map)
    app.get_journal().record(out.pop("document"), "vw_duplicate_layer",
                             [{"op": "layer_created", "name": name}])
    if out["objects"] != out["source_objects"]:
        out["warning"] = (f"Only {out['objects']} of {out['source_objects']} objects were copied; "
                          "check the layer before working on it.")
    if not out["after_source"]:
        out["warning"] = (out.get("warning", "") + " The copy could not be moved next to the "
                          "source in the layer list.").strip()
    return out


@mcp.tool(annotations=WRITE)
def vw_set_vertices(
    uuid: str,
    points: list[list[float]],
    vertex_types: list[int] | None = None,
    arc_radii: list[float] | None = None,
    document: str | None = None,
) -> dict:
    """Replace all vertices of a polygon or polyline with `points`
    ([[x, y], ...] in document units), adding or removing vertices as
    needed. Works the same for both object types (the plain vs.SetPolyPt
    silently does nothing on polylines). vertex_types / arc_radii (one per
    point; 0 corner, 1 bezier, 2 cubic, 3 arc, 4 radius) only for
    polylines; default all corners. Returns the points read back, the area
    before and after, and "applied": false with a warning if Vectorworks
    did not take every point. Revertible with vw_revert_last.
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    out = vw("set_vertices", uuid=uuid, points=points, vertex_types=vertex_types, arc_radii=arc_radii)
    app.get_journal().record(out.pop("document"), "vw_set_vertices",
                             [{"op": "vertices", "uuid": uuid, "before": out.pop("before")}])
    if not out["applied"]:
        out["warning"] = "Vectorworks did not apply every point; compare `points` with what you sent."
    return out


@mcp.tool(annotations=READ)
def vw_vs_lookup(query: str, limit: int = 25) -> list[dict]:
    """Search the live vs.* API (names and built-in docs) of the running
    Vectorworks, e.g. "record field", "symbol insert", "LDevice". Returns
    function names with their signature/description."""
    res = _run_raw(LOOKUP_CODE % __import__("json").dumps({"query": query, "limit": limit}))
    if not res["ok"]:
        raise ToolError(res["error"])
    return res["value"]


@mcp.tool(annotations=READ)
def vw_document_info() -> dict:
    """Active document: name, path, units, active layer/class, counts, selection size."""
    return vw("document_info")


@mcp.tool(annotations=READ)
def vw_list_layers() -> list[dict]:
    """All layers (design and sheet) with visibility and which one is active."""
    return vw("list_layers")


@mcp.tool(annotations=READ)
def vw_list_classes(name_contains: str | None = None) -> list[str]:
    """All class names, optionally filtered by a case-insensitive substring."""
    return vw("list_classes", name_contains=name_contains)


@mcp.tool(annotations=READ)
def vw_get_selection(limit: int = 500) -> list[dict]:
    """Selected objects on the active layer: uuid, type, name, class, layer,
    bbox, attached records, and symbol / plug-in name where relevant."""
    return vw("get_selection", limit=limit)


@mcp.tool(annotations=READ)
def vw_find_objects(
    class_name: str | None = None,
    layer: str | None = None,
    object_type: str | None = None,
    plugin: str | None = None,
    record: str | None = None,
    field: str | None = None,
    value: str | None = None,
    name: str | None = None,
    limit: int = 500,
) -> list[dict]:
    """Find objects by any combination of exact class, layer, type ("Symbol",
    "Rectangle", "Plug-in Object"...), plug-in name ("Lighting Device"),
    attached record (optionally with field == value) and object name."""
    return vw(
        "find_objects", cls=class_name, layer=layer, type_=object_type, plugin=plugin,
        record=record, field=field, value=value, name=name, limit=limit,
    )


@mcp.tool(annotations=READ)
def vw_get_record(uuid: str, record: str) -> dict[str, Any]:
    """All field values of a record (or a plug-in object's parameters, using
    its plug-in name as the record) on the object with this UUID."""
    return vw("get_record", uuid=uuid, record=record)


@mcp.tool(annotations=WRITE)
def vw_set_record(
    uuid: str, record: str, values: dict[str, Any], document: str | None = None
) -> dict[str, Any]:
    """Set record fields (or plug-in parameters) on one object; unknown field
    names are rejected before anything changes. One undo step. Returns the
    record afterwards.
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    out = vw("set_record", uuid=uuid, record=record, values=values)
    app.get_journal().record(
        out["document"], "vw_set_record",
        [{"op": "fields", "uuid": uuid, "record": record, "before": out["before"]}],
    )
    return vw("get_record", uuid=uuid, record=record)


@mcp.tool(annotations=READ)
def vw_list_symbols(
    name_contains: str | None = None, folder: str | None = None, limit: int = 1000
) -> list[dict]:
    """Symbol definitions in the document's resource list, with their folder
    path; filter by name and/or folder substring (e.g. fixture lookup)."""
    return vw("list_symbols", name_contains=name_contains, folder=folder, limit=limit)


@mcp.tool(annotations=WRITE)
def vw_insert_symbol(
    name: str,
    x: float,
    y: float,
    z: float | None = None,
    layer: str | None = None,
    class_name: str | None = None,
    rotation: float = 0.0,
    document: str | None = None,
) -> dict:
    """Place a symbol from the document's resources at x, y (document units),
    optionally at height z, on a layer and in a class. One undo step.
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    info = vw(
        "insert_symbol", name=name, x=x, y=y, z=z, layer=layer, cls=class_name,
        rotation=rotation,
    )
    app.get_journal().record(
        info.pop("document"), "vw_insert_symbol", [{"op": "created", "uuid": info["uuid"]}]
    )
    return info


@mcp.tool(annotations=WRITE)
def vw_revert_last(document: str | None = None) -> dict:
    """Undo exactly the last MCP write in the active document: restores the
    previous field values of vw_set_record / vw_set_lighting_device_fields,
    the previous vertices after vw_set_vertices, deletes the symbol
    vw_insert_symbol placed, the layer vw_duplicate_layer made, or the
    objects a vw_exec_python call created. Call repeatedly to step further back.
    (Vectorworks' own Cmd-Z merges consecutive MCP edits.) A vw_exec_python
    call that created nothing (it only changed existing objects) can't be
    reverted and blocks stepping further back.
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    journal = app.get_journal()
    document = vw("current_document")
    try:
        entry = journal.pop(document)
    except JournalError as e:
        raise ToolError(str(e)) from e
    try:
        result = vw("revert", ops=entry["ops"])
    except ToolError:
        journal.record(entry["document"], entry["tool"], entry["ops"])  # put it back
        raise
    out = {"reverted_tool": entry["tool"], **result}
    if entry["tool"] == "vw_exec_python":
        out["note"] = (
            "Deleted the objects that vw_exec_python call created. Changes it made "
            "to pre-existing objects are not undone."
        )
    return out


@mcp.tool(annotations=READ)
def vw_screenshot(title: str | None = None, max_width: int = 1600) -> list[Image | TextContent]:
    """Capture the Vectorworks document window as an image, to check drawn results
    or to see which dialog is blocking. Does not go through Vectorworks at all
    (no job, no Apple Event), so it works even when other tools time out.
    `title` picks a document window by (partial) title when several are open;
    the image is shrunk to `max_width` pixels. Returns the image plus window
    geometry (screen points), the saved file path, and `in_front`: any dialog
    or open menu (a right-click menu left open also stalls jobs) that the
    document capture would not show."""
    try:
        path, window, in_front = screenshot.screenshot(
            app=DEFAULT_APP,
            root=app.get_bridge().root,
            title=title,
            max_width=max_width,
        )
    except screenshot.ScreenshotError as e:
        raise ToolError(str(e)) from e
    meta = {"window": window.as_dict(), "path": str(path), "in_front": in_front}
    return [Image(path=str(path)), TextContent(type="text", text=json.dumps(meta))]
