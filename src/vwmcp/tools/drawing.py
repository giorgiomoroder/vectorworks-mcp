"""Drawing-side tools: libraries, plug-in objects, layers, classes, move,
delete, view. Writes are journaled for vw_revert_last."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.mcpserver.exceptions import ToolError

from vwmcp import app, classes, library, platform
from vwmcp.app import READ, WRITE, mcp, vw


def _journal(result: dict, tool: str, ops: list[dict] | None) -> dict:
    app.get_journal().record(result.pop("document"), tool, ops)
    return result


@mcp.tool(annotations=READ)
def vw_list_library_files(query: str = "", limit: int = 50) -> list[dict]:
    """Vectorworks library files (.vwx) on this Mac whose path contains every
    word of `query`, e.g. "lighting", "truss", "people", "stage deck", "audio".
    Searches the Vectorworks application libraries and the user libraries.
    Reads the disk only; then use vw_list_library_resources on a path."""
    return library.find_library_files(query, limit=limit)


@mcp.tool(annotations=READ)
def vw_list_library_resources(
    path: str, name_contains: str | None = None, type_code: int = 16, limit: int = 500
) -> dict:
    """Names of the resources inside a library file (from vw_list_library_files)
    without importing anything. type_code 16 = symbol definitions, which
    includes plug-in styles (truss, lighting pipe, fixture symbols); 47 =
    record formats."""
    return vw("library_resources", path=path, type_code=type_code,
              name_contains=name_contains, limit=limit)


@mcp.tool(annotations=WRITE)
def vw_import_resource(
    path: str, name: str, new_name: str | None = None, type_code: int = 16,
    document: str | None = None,
) -> dict:
    """Import one resource (symbol or plug-in style) from a library file into
    the document through Vectorworks' own importer, so it can then be placed
    with vw_insert_symbol / vw_create_pio. If the document already has a
    resource with that name, give new_name to import a copy. Revertible.
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    out = vw("import_resource", path=path, name=name, type_code=type_code, new_name=new_name)
    return _journal(out, "vw_import_resource", [{"op": "resource", "name": out["name"]}])


@mcp.tool(annotations=WRITE)
def vw_create_pio(
    plugin: str,
    x: float,
    y: float,
    rotation: float = 0.0,
    parameters: dict[str, Any] | None = None,
    layer: str | None = None,
    class_name: str | None = None,
    document: str | None = None,
) -> dict:
    """Place a Spotlight/Vectorworks plug-in object by its INTERNAL name at x, y
    (document units) with a rotation, and set parameters by field name. Known
    names: "TrussItem" (truss; parameters Symbol = a truss symbol in the
    document, Name, Type, PositionName), "Lighting Device", "Light Position
    Obj". Use vw_find_objects(type="Plug-in Object") + vw_get_pio_parameters on
    an existing object to learn other names and fields. Unknown parameter
    names abort the call and nothing is placed. Revertible.
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    info = vw("create_pio", plugin=plugin, x=x, y=y, rotation=rotation,
              parameters=parameters, layer=layer)
    out = _journal(info, "vw_create_pio", [{"op": "created", "uuid": info["uuid"]}])
    if class_name:
        # A new plug-in object's first regeneration resets its class, so assign
        # it in a second job (live finding 2026-11-17).
        vw("set_objects_class", uuids=[info["uuid"]], cls=class_name)
        out["class"] = class_name
    return out


@mcp.tool(annotations=READ)
def vw_get_pio_parameters(uuid: str) -> dict:
    """All parameter fields of a plug-in object (truss, fixture, stage deck...)
    with their current values, plus the plug-in name."""
    return vw("pio_parameters", uuid=uuid)


@mcp.tool(annotations=WRITE)
def vw_set_pio_parameters(uuid: str, values: dict[str, Any], document: str | None = None) -> dict:
    """Set parameter fields on a plug-in object by field name and regenerate
    it. All-or-nothing: an unknown field name changes nothing. Revertible.
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    out = vw("set_pio_parameters", uuid=uuid, values=values)
    ops = [{"op": "fields", "uuid": uuid, "record": out["record"], "before": out["before"]}]
    _journal(out, "vw_set_pio_parameters", ops)
    return {"uuid": uuid, "plugin": out["record"], "after": vw("get_record", uuid=uuid, record=out["record"])}


@mcp.tool(annotations=WRITE)
def vw_create_layer(
    name: str, kind: Literal["design", "sheet"] = "design", scale: float | None = None,
    activate: bool = False,
    document: str | None = None,
) -> dict:
    """Create a design or sheet layer (design layers: optional scale denominator,
    e.g. 48 for 1/4" = 1'). The user's active layer stays active unless
    activate=True. Revertible (the layer is deleted).
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    out = vw("create_layer", name=name, kind=kind, scale=scale, activate=activate)
    return _journal(out, "vw_create_layer", [{"op": "layer", "name": name}])


@mcp.tool(annotations=WRITE)
def vw_create_class(name: str, document: str | None = None) -> dict:
    """Create a class (use "-" for hierarchy, e.g. "Lighting-Truss"). The active
    class is left unchanged. Revertible.
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    out = vw("create_class", name=name)
    return _journal(out, "vw_create_class", [{"op": "class", "name": name}])


@mcp.tool(annotations=WRITE)
def vw_apply_class_standard(
    standard: str = "spotlight", only: list[str] | None = None, overwrite: bool = False,
    document: str | None = None,
) -> dict:
    """Give the document a consistent class set with colours and line weights,
    so plots look tidy and layers can be filtered: the "spotlight" standard has
    Lighting-Instruments / -Labels / -Positions / -Focus Points / -Cables,
    Rigging-Truss / -Hoists, Stage-Decks / -Steps, Soft Goods, Audio, Video,
    Scenery, People, Venue-Architecture / -Seating, Notes, Dimensions. Missing
    classes are created and styled; existing ones are left alone unless
    overwrite=True (then their pen, fill and line weight are changed and
    recorded for revert). `only` limits it to names or prefixes, e.g.
    ["Lighting", "Rigging-Truss"]. Afterwards use vw_create_pio / insert tools
    with class_name=, or move objects into classes with vw_set_record. One
    revertible step (created classes are deleted, restyled ones restored).
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    try:
        spec = classes.load(standard)
        existing = vw("class_attrs", names=[c["name"] for c in spec])
        todo = classes.plan(spec, existing, only=only, overwrite=overwrite)
    except (KeyError, ValueError) as e:
        raise ToolError(str(e).strip("'\"")) from e
    if not todo["create"] and not todo["restyle"]:
        return {"standard": standard, "created": [], "restyled": [], "unchanged": todo["unchanged"],
                "note": "Nothing to do" + (": all classes exist (overwrite=True restyles them)." if not overwrite else ".")}
    out = vw("apply_class_attrs", create=todo["create"], restyle=todo["restyle"])
    before = out.pop("before", {})
    ops = [{"op": "class", "name": n} for n in out["created"]]
    ops += [{"op": "class_attrs", "name": n, "before": before[n]} for n in out["restyled"] if n in before]
    out["unchanged"] = todo["unchanged"]
    out["standard"] = standard
    return _journal(out, "vw_apply_class_standard", ops)


@mcp.tool(annotations=WRITE)
def vw_create_sheet(
    name: str,
    layers: list[str],
    scale: float = 48,
    hide_classes: list[str] | None = None,
    title: str | None = None,
    sheet_number: str | None = None,
    project: str | None = None,
    document: str | None = None,
) -> dict:
    """A presentation sheet: a sheet layer `name` with one viewport that shows
    the given design layers at 1:`scale` (48 = 1/4" = 1'-0", 96 = 1/8", 50 or
    100 for metric) in Top/Plan, with `hide_classes` (e.g. ["Notes",
    "Lighting-Focus Points"]) hidden in that viewport. With `title`,
    `sheet_number` or `project` a Title Block Border is added at the sheet
    origin and those fields written where the title block style has them
    (the result lists fields_set / fields_unknown / fields_available). The
    user's active layer is restored. One vw_revert_last deletes the sheet with
    its viewport and title block. Follow up with vw_set_view / vw_screenshot
    after the user switches to the sheet, or vw_render_layers for a picture.
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    if not layers:
        raise ToolError("layers: name at least one design layer to show in the viewport")
    if scale <= 0:
        raise ToolError("scale must be positive (48 = 1/4\" = 1')")
    app.require_document(document)
    tb = {}
    if title is not None:
        tb["Sheet Title"] = title
    if sheet_number is not None:
        tb["Sheet Number"] = sheet_number
    if project is not None:
        tb["Project Name"] = project
    out = vw("create_sheet", name=name, layers=layers, scale=scale, hide_classes=hide_classes,
             title_block=tb or None)
    return _journal(out, "vw_create_sheet", [{"op": "layer", "name": name}])


@mcp.tool(annotations=WRITE)
def vw_delete_objects(uuids: list[str], document: str | None = None) -> dict:
    """Delete objects by uuid. All-or-nothing: if any uuid is unknown nothing is
    deleted. NOT revertible with vw_revert_last (only Cmd-Z in Vectorworks),
    and it blocks reverting earlier edits, so confirm with the user first.
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    if not uuids:
        raise ToolError("no uuids given")
    out = vw("delete_objects", uuids=uuids)
    return _journal(out, "vw_delete_objects", None)


@mcp.tool(annotations=WRITE)
def vw_move_objects(
    uuids: list[str], dx: float = 0.0, dy: float = 0.0, dz: float = 0.0,
    document: str | None = None,
) -> dict:
    """Move objects by an offset in document units (dz for 3D). All-or-nothing
    on unknown uuids. Revertible (moved back).
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    if not uuids:
        raise ToolError("no uuids given")
    out = vw("move_objects", uuids=uuids, dx=dx, dy=dy, dz=dz)
    ops = [{"op": "move", "uuid": u, "dx": dx, "dy": dy, "dz": dz} for u in uuids]
    return _journal(out, "vw_move_objects", ops)


@mcp.tool(annotations=WRITE)
def vw_set_view(
    view: Literal["top_plan", "top", "bottom", "front", "back", "left", "right",
                  "iso", "iso_right", "iso_left"] | None = None,
    fit: bool = False,
) -> dict:
    """Change the drawing view (standard 3D views or Top/Plan) and/or zoom to
    fit all objects, e.g. before vw_screenshot. Changes no objects, so it is
    not journaled."""
    return vw("set_view", view=view, fit=fit)


@mcp.tool(annotations=WRITE)
def vw_insert_truss_run(
    symbol: str,
    x: float,
    y: float,
    count: int,
    rotation: float = 0.0,
    z: float = 0.0,
    position_name: str | None = None,
    layer: str | None = None,
    class_name: str | None = None,
    library_path: str | None = None,
    document: str | None = None,
) -> dict:
    """Place a straight run of `count` truss pieces end to end, the way
    Spotlight's Insert Truss tool does: TrussItem objects on the symbol's
    length centres, starting at (x, y) and heading along `rotation` degrees
    (0 = +x, 90 = +y), centres at height z (document units), linked into one
    new Braceworks truss system, dimensions and type from the symbol's
    Braceworks record. `symbol` must be a truss symbol in the document, or
    give `library_path` (from vw_list_library_files) to import it first.
    All-or-nothing; one vw_revert_last removes the whole run (and the
    import).
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    if count < 1:
        raise ToolError("count must be at least 1")
    out = vw("insert_truss_run", symbol=symbol, x=x, y=y, count=count, rotation=rotation,
             z=z, position_name=position_name, layer=layer, truss_system=None,
             library_path=library_path)
    ops = [{"op": "created", "uuid": p["uuid"]} for p in out["pieces"]]
    if out.get("imported"):
        ops.append({"op": "resource", "name": out["imported"]})
    out = _journal(out, "vw_insert_truss_run", ops)
    if class_name:  # second job: see vw_create_pio
        vw("set_objects_class", uuids=[p["uuid"] for p in out["pieces"]], cls=class_name)
        out["class"] = class_name
    return out


@mcp.tool(annotations=READ)
def vw_list_truss(system: str | None = None, layer: str | None = None) -> dict:
    """Inventory of truss in the document: TrussItem objects grouped by
    truss system (the Braceworks "T<n>" name), each run's pieces in order
    along the C_START_UUID chain, with count, total length and weight,
    symbols, position names, each piece's 3D centre and the run's plan
    bounding box (document units, view-independent). `linked` is False when a
    run's pieces are not chained. Filter by `system` or `layer`."""
    return vw("list_truss", system=system, layer=layer)


@mcp.tool(annotations=WRITE)
def vw_insert_lighting_devices(
    symbol: str,
    x: float,
    y: float,
    count: int = 1,
    spacing: float = 0.0,
    rotation: float = 0.0,
    position: str | None = None,
    z: float | None = None,
    start_unit: int | None = 1,
    unit_step: int = 1,
    channel: int | None = None,
    channel_step: int = 1,
    purpose: str | None = None,
    layer: str | None = None,
    class_name: str | None = None,
    library_path: str | None = None,
    document: str | None = None,
) -> dict:
    """Hang `count` lighting fixtures of a fixture symbol (must be in the
    document, or give `library_path` to import it) from (x, y) along
    `rotation` degrees, `spacing` apart (document units), the way Spotlight's
    insertion tool does: each becomes a Lighting Device with Inst Type,
    wattage, DMX footprint and GDTF data from the symbol. Sets Position (a
    position name from vw_list_positions; devices are raised to that
    position's height unless z is given), Unit Number from start_unit,
    Channel from `channel`, and Purpose. All-or-nothing; one vw_revert_last
    removes them all. Fields are re-read and anything Spotlight overrode is
    reported under not_applied.
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    if count < 1:
        raise ToolError("count must be at least 1")
    out = vw("insert_lighting_devices", symbol=symbol, x=x, y=y, count=count, spacing=spacing,
             rotation=rotation, z=z, position=position, start_unit=start_unit,
             unit_step=unit_step, channel=channel, channel_step=channel_step,
             purpose=purpose, layer=layer, library_path=library_path)
    ops = [{"op": "created", "uuid": d["uuid"]} for d in out["devices"]]
    if out.get("imported"):
        ops.append({"op": "resource", "name": out["imported"]})
    out = _journal(out, "vw_insert_lighting_devices", ops)
    uuids = [d["uuid"] for d in out["devices"]]
    if class_name:  # second job: see vw_create_pio
        vw("set_objects_class", uuids=uuids, cls=class_name)
        out["class"] = class_name
    # Verify what Spotlight kept (it can renumber or reject values on reset).
    wanted = {}
    if position:
        wanted["Position"] = position
    if purpose:
        wanted["Purpose"] = purpose
    check = ["Position", "Unit Number", "Channel", "Purpose", "Inst Type"]
    actual = vw("read_devices", uuids=uuids, fields=check)
    not_applied = []
    for i, (d, now) in enumerate(zip(out["devices"], actual)):
        want = dict(wanted)
        if start_unit is not None:
            want["Unit Number"] = str(start_unit + unit_step * i)
        if channel is not None:
            want["Channel"] = str(channel + channel_step * i)
        missed = {k: {"requested": v, "actual": now.get(k, "")} for k, v in want.items()
                  if str(v).strip() != str(now.get(k, "")).strip()}
        d.update({k: now.get(k, "") for k in check})
        if missed:
            not_applied.append({"uuid": d["uuid"], "not_applied": missed})
    if not_applied:
        out["not_applied"] = not_applied
    return out


@mcp.tool(annotations=WRITE)
def vw_insert_stage_decks(
    width: float,
    depth: float,
    height: float,
    x: float,
    y: float,
    columns: int = 1,
    rows: int = 1,
    rotation: float = 0.0,
    structure: Literal["Legs-Basic", "Legs-Braced", "Folding", "Deck Only", "Border", "Simple"] = "Legs-Basic",
    purpose: str | None = None,
    position: str | None = None,
    layer: str | None = None,
    class_name: str | None = None,
    document: str | None = None,
) -> dict:
    """Build a platform from Spotlight Stage Deck objects: `columns` x `rows`
    rectangular decks of `width` x `depth` at `height` (all document units),
    tiled edge to edge. (x, y) is the platform's corner: each deck extends
    +width along `rotation` degrees (0 = +x) and +depth at +90 from it, so at
    rotation 0 the platform fills x..x+width*columns, y..y+depth*rows.
    `structure` is the deck's leg style; `purpose`/`position` fill the deck's
    Spotlight fields. Returns each deck's 3D centre and size. All-or-nothing;
    one vw_revert_last removes the whole platform.
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    if columns < 1 or rows < 1:
        raise ToolError("columns and rows must be at least 1")
    out = vw("insert_stage_decks", width=width, depth=depth, height=height, x=x, y=y,
             columns=columns, rows=rows, rotation=rotation, structure=structure,
             purpose=purpose, position=position, layer=layer)
    ops = [{"op": "created", "uuid": d["uuid"]} for d in out["decks"]]
    out = _journal(out, "vw_insert_stage_decks", ops)
    uuids = [d["uuid"] for d in out["decks"]]
    if class_name:  # second job: see vw_create_pio
        vw("set_objects_class", uuids=uuids, cls=class_name)
        out["class"] = class_name
    # Geometry exists only after the creating job ends: read it back now.
    for d, ext in zip(out["decks"], vw("object_extents", uuids=uuids)):
        d.update(ext)
    return out


@mcp.tool(annotations=WRITE)
def vw_insert_platform(
    width: float,
    depth: float,
    height: float,
    x: float,
    y: float,
    columns: int = 1,
    rows: int = 1,
    rotation: float = 0.0,
    steps_on: Literal["front", "back", "left", "right"] | None = None,
    step_count: int | None = None,
    tread_width: float | None = None,
    step_kind: Literal["Self-Adjusting", "Frame Free-Standing", "Solid Free-Standing", "Open Free-Standing", "Simple"] = "Self-Adjusting",
    rails: bool = False,
    structure: Literal["Legs-Basic", "Legs-Braced", "Folding", "Deck Only", "Border", "Simple"] = "Legs-Basic",
    purpose: str | None = None,
    position: str | None = None,
    layer: str | None = None,
    class_name: str | None = None,
    document: str | None = None,
) -> dict:
    """A platform with its steps in one call: `columns` x `rows` Stage Decks of
    `width` x `depth` at `height` from corner (x, y) (as vw_insert_stage_decks),
    plus one flight of Stage Steps centred on the chosen edge, descending away
    from the platform. Edges are in the platform's own frame: "front" is the
    edge through (x, y) along `rotation`, "back" opposite, "left" the edge
    through (x, y) across, "right" opposite. `step_count` defaults to about one
    per 8 inches; `rails` puts a rail on both sides; `step_kind` "Simple" gives
    a compact flight. All document units. Everything is one revertible step;
    the result has each deck's and the flight's 3D centre and size.
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    if columns < 1 or rows < 1:
        raise ToolError("columns and rows must be at least 1")
    steps = None
    if steps_on:
        sx, sy, srot = platform.step_origin(x, y, width, depth, columns, rows, rotation, steps_on)
        steps = {"x": sx, "y": sy, "rotation": srot, "steps": step_count, "tread_width": tread_width,
                 "kind": step_kind, "rail_left": rails, "rail_right": rails}
    out = vw("insert_platform", width=width, depth=depth, height=height, x=x, y=y, columns=columns,
             rows=rows, rotation=rotation, structure=structure, purpose=purpose, position=position,
             layer=layer, steps=steps)
    uuids = [d["uuid"] for d in out["decks"]] + ([out["steps"]["uuid"]] if out.get("steps") else [])
    out = _journal(out, "vw_insert_platform", [{"op": "created", "uuid": u} for u in uuids])
    if class_name:  # second job: see vw_create_pio
        vw("set_objects_class", uuids=uuids, cls=class_name)
        out["class"] = class_name
    extents = {e["uuid"]: e for e in vw("object_extents", uuids=uuids)}
    for d in out["decks"]:
        d.update(extents.get(d["uuid"], {}))
    if out.get("steps"):
        out["steps"].update(extents.get(out["steps"]["uuid"], {}))
    return out


@mcp.tool(annotations=WRITE)
def vw_insert_stage_ramp(
    x: float,
    y: float,
    stage_height: float,
    rotation: float = 0.0,
    tread_width: float | None = None,
    ramp_length: float | None = None,
    pitch_angle: float | None = None,
    kind: Literal["Legs", "Solid", "Simple"] = "Legs",
    rail_left: bool = False,
    rail_right: bool = False,
    arrow: bool = False,
    purpose: str | None = None,
    position: str | None = None,
    layer: str | None = None,
    class_name: str | None = None,
    document: str | None = None,
) -> dict:
    """A Spotlight Stage Ramp down from a stage edge. (x, y) is the top
    centre of the ramp on the edge; at `rotation` 0 the stage is on the +y
    side and the ramp descends toward -y (same convention as
    vw_insert_stage_steps). Give either `ramp_length` (measured along the
    slope) or `pitch_angle` in degrees; `stage_height`, `tread_width` and
    `ramp_length` are document units. `arrow` draws the plug-in's "down"
    arrow in plan. Returns the ramp's 3D centre and size (its plan length is
    size[1] at rotation 0). One vw_revert_last removes it.
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    out = vw("insert_stage_ramp", x=x, y=y, stage_height=stage_height, rotation=rotation,
             tread_width=tread_width, ramp_length=ramp_length, pitch_angle=pitch_angle, kind=kind,
             rail_left=rail_left, rail_right=rail_right, arrow=arrow, purpose=purpose,
             position=position, layer=layer)
    out = _journal(out, "vw_insert_stage_ramp", [{"op": "created", "uuid": out["uuid"]}])
    if class_name:  # second job: see vw_create_pio
        vw("set_objects_class", uuids=[out["uuid"]], cls=class_name)
        out["class"] = class_name
    out.update(vw("object_extents", uuids=[out["uuid"]])[0])
    return out


@mcp.tool(annotations=WRITE)
def vw_insert_soft_goods(
    points: list[list[float]],
    height: float,
    function: Literal["Curtain", "Truss Border", "Pipe-and-Drape"] = "Curtain",
    opening_width: float | None = None,
    open_from: str | None = None,
    traveler: bool = False,
    add_pipe: bool = False,
    add_track: bool = False,
    purpose: str | None = None,
    position: str | None = None,
    layer: str | None = None,
    class_name: str | None = None,
    document: str | None = None,
) -> dict:
    """A Spotlight Soft Goods run (curtain, truss border or pipe-and-drape)
    along the open polyline through `points` ([[x, y], ...], at least two,
    document units), `height` tall (document units). A curtain can have an
    opening: `opening_width` and `open_from` (the plug-in's popup text, e.g.
    "Center"); `traveler` marks it as a traveler; `add_pipe` / `add_track`
    draw the hanging hardware. Returns the object's 3D centre and size plus
    the path length. One vw_revert_last removes it (the path goes with it).
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    out = vw("insert_soft_goods", points=points, height=height, function=function,
             opening_width=opening_width, open_from=open_from, traveler=traveler,
             add_pipe=add_pipe, add_track=add_track, purpose=purpose, position=position, layer=layer)
    out = _journal(out, "vw_insert_soft_goods", [{"op": "created", "uuid": out["uuid"]}])
    if class_name:  # second job: see vw_create_pio
        vw("set_objects_class", uuids=[out["uuid"]], cls=class_name)
        out["class"] = class_name
    out.update(vw("object_extents", uuids=[out["uuid"]])[0])
    return out


@mcp.tool(annotations=WRITE)
def vw_insert_stage_steps(
    x: float,
    y: float,
    stage_height: float,
    rotation: float = 0.0,
    tread_width: float | None = None,
    steps: int | None = None,
    kind: Literal["Self-Adjusting", "Frame Free-Standing", "Solid Free-Standing", "Open Free-Standing", "Simple"] = "Self-Adjusting",
    rail_left: bool = False,
    rail_right: bool = False,
    stringer_length: float | None = None,
    purpose: str | None = None,
    position: str | None = None,
    layer: str | None = None,
    class_name: str | None = None,
    document: str | None = None,
) -> dict:
    """A flight of Spotlight Stage Steps down from a stage edge. (x, y) is the
    top centre of the flight on the edge; at `rotation` 0 the stage is on
    the +y side and the steps descend toward -y (rotate with the platform,
    e.g. 90 for a platform that extends -x). `stage_height`, `tread_width`
    and `stringer_length` are document units; `steps` defaults to about one
    per 8 inches of height. The default "Self-Adjusting" kind is a rental
    unit with a fixed stringer (6 ft unless `stringer_length` is given), so a
    low flight lies at a shallow pitch; use kind "Simple" for a compact
    flight. Returns the flight's 3D centre and size. One vw_revert_last
    removes it.
    document: optional guard; if given and another document is active,
    nothing changes (use vw_switch_document first)."""
    app.require_document(document)
    out = vw("insert_stage_steps", x=x, y=y, stage_height=stage_height, rotation=rotation,
             tread_width=tread_width, steps=steps, kind=kind, rail_left=rail_left,
             rail_right=rail_right, stringer_length=stringer_length, purpose=purpose,
             position=position, layer=layer)
    out = _journal(out, "vw_insert_stage_steps", [{"op": "created", "uuid": out["uuid"]}])
    if class_name:  # second job: see vw_create_pio
        vw("set_objects_class", uuids=[out["uuid"]], cls=class_name)
        out["class"] = class_name
    out.update(vw("object_extents", uuids=[out["uuid"]])[0])
    return out
