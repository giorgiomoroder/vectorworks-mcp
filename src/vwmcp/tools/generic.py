"""Generic Vectorworks tools: session, document, objects, records, symbols."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.utilities.types import Image
from mcp.types import TextContent
from pydantic import Field

from vwmcp import app, calls, config, documents, render, screenshot, viewmap, vslint
from vwmcp.app import READ, WRITE, mcp, vw
from vwmcp.client import BridgeError
from vwmcp.journal import JournalError
from vwmcp.trigger import DEFAULT_APP

# Shared description of the `document` guard parameter of every write tool.
DOC = ('Name of the document this must run in, as vw_list_documents shows it (".vwx" may be '
       'left out) or its full path. If another document is active, nothing changes. Omit to '
       'act on whatever document is active.')

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


def _run_raw(code: str, timeout: float | None = None, allow_dialogs: bool = False) -> dict:
    try:
        return app.get_bridge().run(code, timeout=timeout, allow_dialogs=allow_dialogs)
    except BridgeError as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations=READ)
def vw_ping() -> dict:
    """Check that Vectorworks answers: one tiny job through the bridge.

    Read-only. Returns {vectorworks_version, build, document (the active one),
    bridge_version, documents (all open ones), warning?}. The warning says when
    the installed bridge is older than this server expects or when this
    Vectorworks version is untested. Call it once at session start, after
    vw_list_documents. If it fails or times out, call vw_doctor (which never
    touches Vectorworks) and vw_screenshot (to see a blocking dialog)."""
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
    try:
        out["documents"] = documents.list_documents()["documents"]
    except Exception as e:  # noqa: BLE001  (AppleScript trouble must not fail a ping)
        out["documents_error"] = str(e)
    return out


@mcp.tool(annotations=WRITE)
def vw_doctor(
    fix: Annotated[bool, Field(description=(
        "False (default): only report. True: also remove stale job and result files and, when "
        "the bridge is missing or outdated, install it into the user's Vectorworks Plug-ins "
        "folder (the only file written outside this server's own folder); Vectorworks must "
        "then be restarted once."))] = False,
) -> dict:
    """Check this Vectorworks MCP setup on this Mac without touching Vectorworks.

    Checks: bridge installed in the right Plug-ins folder and up to date (with
    its check tables), the 'MCP Run Job' command file present, Claude Desktop /
    Claude Code configured for this Vectorworks version, Vectorworks running,
    stale job files, recent log errors. Returns {ok, checks: [{name, ok
    (true / false / null = could not check here), detail, fix}], next_step,
    installed?}. Use it first when vw_ping fails; vw_ping is the live test
    that this one deliberately does not do. Not checked here: whether 'MCP Run
    Job' is in a menu and the macOS Automation permission."""
    from vwmcp import doctor, install

    root = app.get_bridge().root
    checks = doctor.run_checks(root=root, fix=fix)
    out: dict[str, Any] = {}
    bridge = next((c for c in checks if c.name == "bridge"), None)
    if fix and bridge is not None and bridge.ok is False:
        target = install.plugin_dir(config.VW_VERSION)
        out["installed"] = install.install_plugin(target, home=root)
        checks = doctor.run_checks(root=root, fix=False)
    out["ok"] = all(c.ok is not False for c in checks)
    out["checks"] = [{"name": c.name, "ok": c.ok, "detail": c.detail, "fix": c.fix} for c in checks]
    if "installed" in out:
        out["next_step"] = (f"Bridge installed. {install.MENU_STEP} Quit and reopen Vectorworks so it "
                            "loads the command, then call vw_ping.")
    elif not out["ok"]:
        out["next_step"] = ("Apply the fix lines above; vw_doctor(fix=True) installs a missing or "
                            "outdated bridge and removes stale files. Not checked here: whether "
                            "'MCP Run Job' is in a menu and the macOS Automation permission "
                            "(vw_ping tests those).")
    else:
        out["next_step"] = "Setup looks fine. If vw_ping still fails, check vw_screenshot for a dialog in front."
    return out


@mcp.tool(annotations=WRITE)
def vw_exec_python(
    code: Annotated[str | None, Field(description=(
        "Python source to run inside Vectorworks with `vs` in scope (or give `path` instead). Python 3.9 syntax "
        "(Vectorworks 2026 embeds 3.9; no match statements, no `X | Y` types). Its stdout, "
        "the value of the last expression or of a variable named `result`, and any "
        "traceback are returned. Handles are only valid during the call: return UUIDs "
        "(vs.GetObjectUuid) to refer to objects later."))] = None,
    path: Annotated[str | None, Field(description=(
        "Instead of code: path of a Python script file on this Mac (\"~\" is expanded), for "
        "example in the project's _claude_scripts folder. Its contents run exactly like code; "
        "give one of code and path, not both."))] = None,
    modifies_document: Annotated[bool, Field(description=(
        "True (default): the objects the code creates are recorded so vw_revert_last can "
        "delete exactly those, even if the code fails halfway. False: run as read-only code "
        "(faster, no journal entry); use it for anything that only reads."))] = True,
    timeout: Annotated[float | None, Field(description=(
        "Seconds to wait for the result once Vectorworks has taken the job. Default 120; "
        "raise it for scripts that create many objects."))] = None,
    document: Annotated[str | None, Field(description=DOC)] = None,
    lint: Annotated[bool, Field(description=(
        "True (default): check the code before sending it (same as vw_lint). Syntax errors, "
        "vs.* calls with a wrong argument count, deprecated calls and functions known to crash "
        "Vectorworks or open a dialog stop the call with a report; unknown vs.* names come back "
        "as lint_warnings. False skips the check; only when the check itself is wrong."))] = True,
    allow_dialogs: Annotated[bool, Field(description=(
        "False (default): vs.* functions that open a dialog are refused, because an open dialog "
        "blocks every further job until the user closes it. True: allow them on purpose."))] = False,
) -> dict:
    """Run arbitrary Python inside Vectorworks; the last resort when no typed tool fits.

    Prefer the typed vw_* tools (they verify and revert precisely); give
    `path` for a script that already lives in a file, and use vw_lint to
    check code without running it. The code is linted first, then every vs.*
    call is checked inside Vectorworks (argument count and types, known
    crashers): a bad call comes back as VSArgumentError / VSUnsafeError in
    the result instead of opening the modal "Script Errors" window. Look up
    signatures with vw_vs_lookup.

    Changes the document when the code does. Objects the code creates are
    revertible with vw_revert_last; changes to objects that existed before
    (moves, attributes, deletions) are not, and such a call blocks stepping
    further back. Returns {ok, value, stdout, error, traceback, created,
    revertable, warning?, lint_warnings?}."""
    if (code is None) == (path is None):
        raise ToolError("Give either code or path, not both and not neither.")
    app.require_document(document)
    filename = "<vw_exec_python>"
    if path is not None:
        p = Path(path).expanduser()
        try:
            code = p.read_text(encoding="utf-8")
        except OSError as e:
            raise ToolError(f"Can't read {p}: {e}") from e
        filename = p.name
        if timeout is None:
            timeout = 120
    lint_warnings = _preflight(code, filename, allow_dialogs) if lint else []
    out = _exec_python(code, modifies_document, timeout, allow_dialogs)
    if lint_warnings:
        out["lint_warnings"] = lint_warnings
    return out


def _preflight(code: str, filename: str, allow_dialogs: bool = False) -> list[str]:
    """Lint code; raise ToolError on errors, return warning lines."""
    report = vslint.lint(code, filename, year=config.VW_VERSION, allow_dialogs=allow_dialogs)
    if report["errors"]:
        raise ToolError(
            "Not sent to Vectorworks: this would likely open the blocking Script Errors dialog.\n"
            + vslint.format_report(report, filename)
            + "\nFix the code (check signatures with vw_vs_lookup), or pass lint=False if the check is wrong.")
    return [f"line {w['line']}: {w['message']}" for w in report["warnings"]]


def _exec_python(code: str, modifies_document: bool, timeout: float | None,
                 allow_dialogs: bool = False) -> dict:
    if not modifies_document:
        res = _run_raw(code, timeout, allow_dialogs=allow_dialogs)
        return {k: res.get(k) for k in ("ok", "value", "stdout", "error", "traceback")}
    try:
        res = calls.call_result(app.get_bridge(), "exec_tracked", timeout=timeout,
                                document=app.DOCUMENT.get(), allow_dialogs=allow_dialogs, code=code)
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


@mcp.tool(annotations=READ)
def vw_lint(
    code: Annotated[str | None, Field(description=(
        "Python source to check. Pass either code or path, not both."))] = None,
    path: Annotated[str | None, Field(description=(
        "Path of a Python script file on this Mac to check instead of code, for example a menu "
        "command script. Pass either code or path, not both."))] = None,
) -> dict:
    """Check Python meant for Vectorworks without running it.

    Finds syntax errors, vs.* calls with a wrong number of arguments,
    deprecated calls (these would open the blocking "Script Errors" window)
    and functions a published safety sweep found to crash or hang Vectorworks
    or to open a dialog; unknown vs.* names are warnings. Works without
    Vectorworks running. Argument types and values are not checked here (the
    bridge checks types when the code runs). vw_exec_python and vw_exec_python
    run this check themselves, so call it directly only to check a script you
    do not intend to run yet. Returns {ok, errors, warnings, api}."""
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
    """List the documents open in Vectorworks, front to back, and which one is active.

    Read-only; asks macOS from outside Vectorworks (no job, no Accessibility
    permission). Returns {documents: [names], active, paths: {name: path}}
    for the paths this server has learned. Every other tool works on the
    active document, so call this at session start and before writes; switch
    with vw_switch_document. Fails with "No document is open" when only the
    start screen shows."""
    _remember_active()
    try:
        return documents.list_documents()
    except documents.DocumentsError as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations=WRITE)
def vw_switch_document(
    name: Annotated[str, Field(description=(
        "The document to bring to the front: its name as vw_list_documents shows it (\".vwx\" "
        "may be left out) or its full path. It must already be open and saved; unsaved "
        "documents cannot be switched to and closed files are not opened."))],
) -> dict:
    """Bring one of the open, saved Vectorworks documents to the front.

    Changes only which document is active (no drawing change); verified
    afterwards by reading the front window's name. All other tools act on the
    active document, so use this before writing when vw_list_documents shows
    the wrong one in front. Returns {active, switched, documents}."""
    _remember_active()
    try:
        out = documents.switch_document(name)
    except documents.DocumentsError as e:
        raise ToolError(str(e)) from e
    _remember_active()
    return out


@mcp.tool(annotations=READ)
def vw_export_geometry(
    layer: Annotated[str | None, Field(description=(
        "Name of the design layer to read. Default: the active layer."))] = None,
    classes: Annotated[list[str] | None, Field(description=(
        "Only objects in these classes (exact names). Default: every class."))] = None,
    out_path: Annotated[str | None, Field(description=(
        "File path on this Mac (\"~\" is expanded). When given, the full JSON is written there "
        "and only a summary comes back; use it for large layers to keep the conversation "
        "small. Default: the geometry is returned inline."))] = None,
    limit: Annotated[int, Field(description=(
        "Maximum number of objects to export; the result says `truncated` when the layer has "
        "more. Default 20000."))] = 20000,
    timeout: Annotated[float | None, Field(description=(
        "Seconds to wait for Vectorworks once it has taken the job. Default 60."))] = 60,
    attributes: Annotated[bool, Field(description=(
        "True (default): each object also carries `attrs` with its fill (pattern 0 none / 1 "
        "solid background colour / 2 solid foreground colour, colours as #rrggbb), its pen "
        "(colour, weight in mils, style) and whether each follows the class (`by_class`). "
        "False: geometry only."))] = True,
) -> dict:
    """Read the 2D geometry of one design layer as numbers, in document units.

    Read-only. Lines and polygons come as points, arcs as centre / radius /
    angles, texts with origin and string, dimensions with their text; groups
    are descended, plug-in objects (chain dimensions, doors) are one entry
    each. Use it to verify what is really in the file, or to compare fill and
    pen attributes with neighbouring objects before drawing in the same
    style; vw_render_layers draws the same data as a picture, vw_screenshot
    shows the real window instead. Returns {document, layer, objects: [{type,
    class, uuid, points | origin | center, attrs?...}], truncated}, or with
    out_path {path, count, by_type, by_class, extent}."""
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
    layers: Annotated[list[str] | None, Field(description=(
        "Design layer names, drawn in this order (later ones on top). Default: the active "
        "layer only."))] = None,
    bbox: Annotated[list[float] | None, Field(description=(
        "[x_min, y_min, x_max, y_max] in document units to zoom in on. Default: everything "
        "on the chosen layers."))] = None,
    classes: Annotated[list[str] | None, Field(description=(
        "Only objects in these classes (exact names). Default: every class."))] = None,
    max_size: Annotated[int, Field(description=(
        "Length of the image's long side in pixels. Default 1600."))] = 1600,
    fills: Annotated[bool, Field(description=(
        "True (default): paint solid fills (always below all lines). False: outlines only."))] = True,
    out_path: Annotated[str | None, Field(description=(
        "File path on this Mac to also save the PNG to (\"~\" is expanded). Default: the image "
        "is only returned."))] = None,
    timeout: Annotated[float | None, Field(description=(
        "Seconds to wait for Vectorworks per layer once it has taken the job. Default 60."))] = 60,
) -> Image:
    """Draw design layers as a PNG from their real geometry, whatever the Vectorworks window shows.

    Read-only; one geometry job per layer, no Screen Recording needed. Use it
    to check drawing work on any layer, visible or hidden; vw_screenshot shows
    the real window instead (and any blocking dialog), vw_export_geometry
    returns the same data as numbers. It is a check picture, not a plot:
    object colours, solid fills and line weights are shown; hatches, dash
    styles, opacity and curved polyline segments are not, texts are marked
    with a small cross at their origin, and symbols / plug-in objects are
    grey boxes. Returns the image."""
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
    source: Annotated[str, Field(description="Name of the existing design layer to copy.")],
    name: Annotated[str, Field(description="Name for the new layer; must not exist yet.")],
    visibility: Annotated[str | None, Field(description=(
        "Visibility of the copy: \"visible\", \"hidden\" or \"gray\". Default: the same as the "
        "source has now. Layers share coordinates, so a visible copy lies exactly on top of "
        "the original."))] = None,
    uuid_map: Annotated[bool, Field(description=(
        "True: also return `uuid_map` {source object uuid: copy uuid}, including objects "
        "inside groups. Default False."))] = False,
    document: Annotated[str | None, Field(description=DOC)] = None,
) -> dict:
    """Copy a design layer with all its objects, to try a variant without touching the original.

    Changes the document: one new layer, one revertible step (vw_revert_last
    deletes the copy). The copy keeps the scale and is placed right after the
    source in the layer list; the active layer stays active. Use
    vw_create_layer for an empty layer. Returns {document, layer, source,
    objects, source_objects, after_source, scale, visibility, uuid_map when
    asked for}; objects below source_objects means not every object was
    copied."""
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
    uuid: Annotated[str, Field(description=(
        "UUID of the polygon or polyline (from vw_find_objects, vw_get_selection or "
        "vw_export_geometry)."))],
    points: Annotated[list[list[float]], Field(description=(
        "The complete new vertex list, [[x, y], ...] in document units; vertices are added "
        "or removed to match its length."))],
    vertex_types: Annotated[list[int] | None, Field(description=(
        "Polylines only: one type per point, 0 corner, 1 bezier, 2 cubic, 3 arc, 4 radius. "
        "Default: all corners. Ignored for polygons."))] = None,
    arc_radii: Annotated[list[float] | None, Field(description=(
        "Polylines only: one radius per point in document units, used for type 4 (radius) "
        "vertices. Default: none."))] = None,
    document: Annotated[str | None, Field(description=DOC)] = None,
) -> dict:
    """Replace every vertex of one polygon or polyline with a new point list.

    Changes the document; one revertible step (vw_revert_last restores the
    previous vertices). Works the same for both object types (the plain
    vs.SetPolyPt silently does nothing on polylines). Use vw_move_objects to
    shift a shape unchanged. Returns {points (read back), area_before,
    area_after, applied, warning?}; applied is false when Vectorworks did
    not take every point."""
    app.require_document(document)
    out = vw("set_vertices", uuid=uuid, points=points, vertex_types=vertex_types, arc_radii=arc_radii)
    app.get_journal().record(out.pop("document"), "vw_set_vertices",
                             [{"op": "vertices", "uuid": uuid, "before": out.pop("before")}])
    if not out["applied"]:
        out["warning"] = "Vectorworks did not apply every point; compare `points` with what you sent."
    return out


@mcp.tool(annotations=READ)
def vw_vs_lookup(
    query: Annotated[str, Field(description=(
        "Words to look for in function names and their built-in docs, all of which must "
        "match, such as \"record field\", \"symbol insert\" or \"LDevice\". Case-insensitive."))],
    limit: Annotated[int, Field(description=(
        "Maximum number of matches, best name matches first. Default 25."))] = 25,
) -> list[dict]:
    """Search the vs.* scripting API of the running Vectorworks by keyword.

    Read-only (one small job). Use it before writing code for vw_exec_python:
    it shows the signature the bridge will enforce. Returns [{name, doc
    (signature and description as Vectorworks ships them), types (the
    parameter types the bridge checks, \"name:TYPE, ...\" plus the codes), safety
    (null, or \"crash\" / \"hang\" / \"interactive\" / \"document_level\" from the
    safety sweep: crash and hang are refused, interactive needs
    allow_dialogs)}]."""
    res = _run_raw(LOOKUP_CODE % __import__("json").dumps({"query": query, "limit": limit}))
    if not res["ok"]:
        raise ToolError(res["error"])
    hits = res["value"]
    for hit in hits:
        hit["types"] = vslint.types_of(hit["name"])
        hit["safety"] = vslint.safety_of(hit["name"])
    return hits


@mcp.tool(annotations=READ)
def vw_document_info() -> dict:
    """Describe the active Vectorworks document: name, path, units, active layer and class, counts.

    Read-only, one small job. Returns {name, path (empty for an unsaved
    document), units: {display_name, area_name}, active_layer, active_class,
    layer_count, class_count, selection_count}. Use it to confirm which
    document a write will land in;
    vw_list_documents lists all open documents without a job."""
    return vw("document_info")


@mcp.tool(annotations=READ)
def vw_list_layers() -> list[dict]:
    """List every layer of the active document, design and sheet layers alike.

    Read-only. Returns [{name, kind (design / sheet), visibility
    (Vectorworks' numeric code), active}] in the document's layer order. Create layers with
    vw_create_layer, copy one with vw_duplicate_layer."""
    return vw("list_layers")


@mcp.tool(annotations=READ)
def vw_list_classes(
    name_contains: Annotated[str | None, Field(description=(
        "Only classes whose name contains this text (case-insensitive). Default: all classes."))] = None,
) -> list[str]:
    """List the class names of the active document, optionally filtered by a substring.

    Read-only. Returns the names as strings, in Vectorworks' order; class
    hierarchy shows as \"Parent-Child\". Create classes with vw_create_class or
    a whole set with vw_apply_class_standard."""
    return vw("list_classes", name_contains=name_contains)


@mcp.tool(annotations=READ)
def vw_get_selection(
    limit: Annotated[int, Field(description=(
        "Maximum number of selected objects to return. Default 500."))] = 500,
) -> list[dict]:
    """Describe the objects the user has selected on the active layer.

    Read-only. Returns [{uuid, type, type_code, name, class, layer, bbox,
    records (attached record names)}]. Use it
    when the user says \"this one\"; vw_find_objects searches by criteria
    instead. UUIDs stay valid across calls."""
    return vw("get_selection", limit=limit)


@mcp.tool(annotations=READ)
def vw_find_objects(
    class_name: Annotated[str | None, Field(description=(
        "Exact class name the objects must be in."))] = None,
    layer: Annotated[str | None, Field(description=(
        "Exact layer name. Default: every layer."))] = None,
    object_type: Annotated[str | None, Field(description=(
        "Vectorworks object type name, such as \"Symbol\", \"Rectangle\", \"Polygon\", "
        "\"Plug-in Object\", \"Group\"."))] = None,
    plugin: Annotated[str | None, Field(description=(
        "Plug-in object name, such as \"Lighting Device\", \"TrussItem\" or \"Stage Deck\"; "
        "implies plug-in objects only."))] = None,
    record: Annotated[str | None, Field(description=(
        "Name of a record format that must be attached to the object (a plug-in object's "
        "parameters count as a record of its plug-in name)."))] = None,
    field: Annotated[str | None, Field(description=(
        "With record: field name whose value must equal `value`."))] = None,
    value: Annotated[str | None, Field(description=(
        "With record and field: the value to match, compared as text."))] = None,
    name: Annotated[str | None, Field(description=(
        "Exact object name (as set in the Object Info palette)."))] = None,
    limit: Annotated[int, Field(description=(
        "Maximum number of objects to return. Default 500."))] = 500,
) -> list[dict]:
    """Find objects in the active document by class, layer, type, plug-in, record or name.

    Read-only; every given criterion must match (all are exact, not
    substrings). Returns [{uuid, type, name, class, layer, bbox, records,
    symbol or plugin name}], the same shape as vw_get_selection. For Lighting
    Devices with their fields use vw_list_lighting_devices instead."""
    return vw(
        "find_objects", cls=class_name, layer=layer, type_=object_type, plugin=plugin,
        record=record, field=field, value=value, name=name, limit=limit,
    )


@mcp.tool(annotations=READ)
def vw_get_record(
    uuid: Annotated[str, Field(description="UUID of the object (from vw_find_objects, vw_get_selection or an insert tool's result).")],
    record: Annotated[str | None, Field(description=(
        "Record format name attached to the object. Omitted: the object's own plug-in parameter "
        "record (truss, lighting device, stage deck, hoist and every other plug-in object); an "
        "error if the object is not a plug-in object."))] = None,
) -> dict[str, Any]:
    """Read every field of one record on one object, or a plug-in object's parameters when no record is named.

    Read-only. Returns {record (the name resolved, which is also what
    vw_create_pio needs as the plug-in name), fields: {field name: value as
    text}}. Write with vw_set_record; for Lighting Devices prefer
    vw_list_lighting_devices and vw_set_lighting_device_fields, which know
    Spotlight's rules."""
    return vw("record_fields", uuid=uuid, record=record)


@mcp.tool(annotations=WRITE)
def vw_set_record(
    uuid: Annotated[str, Field(description="UUID of the object to change.")],
    values: Annotated[dict[str, Any], Field(description=(
        "{field name: new value}, names exactly as vw_get_record lists them. Every name must "
        "exist on that record, or nothing changes; values are written as text."))],
    record: Annotated[str | None, Field(description=(
        "Record format name. Omitted: the object's own plug-in parameter record, which is then "
        "regenerated so the change shows."))] = None,
    document: Annotated[str | None, Field(description=DOC)] = None,
) -> dict[str, Any]:
    """Set fields of one record on one object, or a plug-in object's parameters when no record is named.

    Changes the document; one revertible step (vw_revert_last restores the
    previous values). Unknown field names are rejected before anything
    changes. For Lighting Devices use vw_set_lighting_device_fields, which
    applies Spotlight's address rules and verifies the result. Returns {uuid,
    record, after: the whole record read back after the change, so values
    Vectorworks rejected show their actual state}."""
    app.require_document(document)
    out = vw("set_record", uuid=uuid, record=record, values=values)
    app.get_journal().record(
        out["document"], "vw_set_record",
        [{"op": "fields", "uuid": uuid, "record": out["record"], "before": out["before"]}],
    )
    after = vw("record_fields", uuid=uuid, record=out["record"])
    return {"uuid": uuid, "record": out["record"], "after": after["fields"]}


@mcp.tool(annotations=READ)
def vw_list_symbols(
    name_contains: Annotated[str | None, Field(description=(
        "Only symbols whose name contains this text (case-insensitive)."))] = None,
    folder: Annotated[str | None, Field(description=(
        "Only symbols whose resource folder path contains this text."))] = None,
    limit: Annotated[int, Field(description="Maximum number of symbols to return. Default 1000.")] = 1000,
) -> list[dict]:
    """List the symbol definitions already in the active document's resources.

    Read-only. Returns [{name, folder}]. These are the names vw_insert_symbol
    and vw_insert_lighting_devices accept; a symbol that is not in the
    document yet comes in from a library with vw_list_library and
    vw_import_resource."""
    return vw("list_symbols", name_contains=name_contains, folder=folder, limit=limit)


@mcp.tool(annotations=WRITE)
def vw_insert_symbol(
    name: Annotated[str, Field(description=(
        "Symbol definition name as vw_list_symbols shows it; it must be in the document's "
        "resources already (import with vw_import_resource)."))],
    x: Annotated[float, Field(description="Insertion point x in document units.")],
    y: Annotated[float, Field(description="Insertion point y in document units.")],
    z: Annotated[float | None, Field(description=(
        "Height (z) in document units for a 3D or hybrid symbol. Default: 0, the layer's plane."))] = None,
    layer: Annotated[str | None, Field(description=(
        "Design layer to place it on. Default: the active layer."))] = None,
    class_name: Annotated[str | None, Field(description=(
        "Class to put the instance in. Default: the active class."))] = None,
    rotation: Annotated[float, Field(description="Rotation in degrees, counter-clockwise. Default 0.")] = 0.0,
    document: Annotated[str | None, Field(description=DOC)] = None,
) -> dict:
    """Place one instance of a symbol from the document's resources at a point.

    Changes the document; one revertible step (vw_revert_last deletes the
    instance). For lighting fixtures use vw_insert_lighting_devices, which
    also converts them to Lighting Devices; for truss use vw_insert_truss_run.
    Returns {uuid, name, layer, class, x, y, z}."""
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
def vw_revert_last(
    document: Annotated[str | None, Field(description=DOC)] = None,
) -> dict:
    """Undo exactly the most recent write this server made in the active document.

    Changes the document (back to its previous state for that one call).
    Every typed write tool records what it changed; this restores previous
    field values, vertices, class attributes, deletes objects, layers and
    classes that were created, or writes the inverse Lightwright patch. Call
    it repeatedly to step further back. Not possible: vw_delete_objects, and
    a vw_exec_python call that created nothing (it only changed existing
    objects); such an entry blocks stepping further back. Use this instead of
    Cmd-Z, which merges consecutive scripted edits. Returns {reverted_tool,
    ...what was restored or deleted, note?}."""
    app.require_document(document)
    journal = app.get_journal()
    document = vw("current_document")
    try:
        entry = journal.pop(document)
    except JournalError as e:
        raise ToolError(str(e)) from e
    ops = entry["ops"] or []
    if ops and all(op.get("op") == "lightwright" for op in ops):
        # Written through the Lightwright exchange file, reverted the same way
        # (server side: the inverse patch from the journaled envelope).
        from vwmcp import lightwright

        try:
            n = 0
            for op in ops:
                lightwright.write_patch(Path(op["path"]), lightwright.render_patch(op["envelope"], op["changes"]))
                n += len(op["changes"])
        except OSError as e:
            journal.record(entry["document"], entry["tool"], entry["ops"])  # put it back
            raise ToolError(f"Could not write the inverse patch: {e}") from e
        return {"reverted_tool": entry["tool"], "lightwright": True, "changes": n,
                "note": "Inverse patch written; Vectorworks applies it when it next gains focus."}
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


_LAST_MAPPING: viewmap.Mapping | None = None


@mcp.tool(annotations=READ)
def vw_screenshot(
    title: Annotated[str | None, Field(description=(
        "Part of a document window's title, to pick one when several are open. Default: the "
        "largest document window."))] = None,
    max_width: Annotated[int, Field(description=(
        "The image is shrunk to at most this many pixels wide. Default 1600."))] = 1600,
    mapping: Annotated[bool, Field(description=(
        "True: run one small job to read the view (centre, zoom, layer scale) and return "
        "`mapping`, so a pixel in the picture can be turned into drawing coordinates with "
        "vw_point_to_world (exact in Top/Plan views only). Default False: no job at all."))] = False,
) -> list[Image | TextContent]:
    """Capture the Vectorworks document window as an image, without going through Vectorworks.

    Read-only; no job and no Apple Event (unless mapping is requested), so it
    works even while a dialog blocks every other tool. Use it to check drawn
    results or to see what is in front; vw_render_layers draws layers from
    their geometry instead, independent of the window. Returns the image plus
    JSON {window (screen geometry), path (saved PNG), in_front (dialogs or
    open menus that stall jobs), mapping? or mapping_error?, view?}."""
    global _LAST_MAPPING
    try:
        path, window, in_front = screenshot.screenshot(
            app=DEFAULT_APP,
            root=app.get_bridge().root,
            title=title,
            max_width=max_width,
        )
    except screenshot.ScreenshotError as e:
        raise ToolError(str(e)) from e
    meta: dict[str, Any] = {"window": window.as_dict(), "path": str(path), "in_front": in_front}
    if mapping:
        try:
            view = vw("view_mapping")
            m = viewmap.Mapping.from_view(view, window.as_dict(), viewmap.png_size(path),
                                          canvas=viewmap.canvas_bbox(path),
                                          points_per_inch=viewmap.display_points_per_inch())
            _LAST_MAPPING = m
            meta["mapping"] = m.as_dict()
            meta["view"] = {k: view[k] for k in ("zoom", "layer_scale", "projection", "layer") if k in view}
        except (ToolError, ValueError, OSError) as e:
            meta["mapping_error"] = str(e)
    return [Image(path=str(path)), TextContent(type="text", text=json.dumps(meta))]


@mcp.tool(annotations=READ)
def vw_point_to_world(
    px: Annotated[float, Field(description="Pixel x in the screenshot image, from its left edge.")],
    py: Annotated[float, Field(description="Pixel y in the screenshot image, from its top edge.")],
    mapping: Annotated[dict | None, Field(description=(
        "The `mapping` dict returned by an earlier vw_screenshot(mapping=True). Default: the "
        "most recent one in this server session."))] = None,
) -> dict:
    """Turn a pixel of the last mapped screenshot into drawing coordinates.

    Pure arithmetic, no job, read-only. Use it to say where something seen in
    the picture is, such as the gap a truss should fill, or to check that an
    object landed where it looks. Needs a prior vw_screenshot(mapping=True).
    Exact in Top/Plan views only; otherwise the result carries a warning.
    Returns {x, y, units, warning?}."""
    m = viewmap.Mapping.from_dict(mapping) if mapping else _LAST_MAPPING
    if m is None:
        raise ToolError("No mapping yet: call vw_screenshot(mapping=True) first.")
    x, y = m.to_world(px, py)
    out = {"x": x, "y": y, "units": m.units}
    if m.warning:
        out["warning"] = m.warning
    return out
