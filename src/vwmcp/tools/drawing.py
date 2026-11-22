"""Drawing-side tools: libraries, plug-in objects, layers, classes, move,
delete, view. Writes are journaled for vw_revert_last."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from vwmcp import app, classes, library, platform
from vwmcp.app import READ, WRITE, mcp, vw


def _journal(result: dict, tool: str, ops: list[dict] | None) -> dict:
    app.get_journal().record(result.pop("document"), tool, ops)
    return result


def _d(text: str) -> Any:
    """A fresh pydantic Field carrying a parameter description (the MCP schema
    takes descriptions from Annotated metadata only, not from docstrings)."""
    return Field(description=text)


# Descriptions shared by many tools (each call makes a fresh Field).
_DOCUMENT = ("Name of the document this call may change, as listed by vw_list_documents. "
             "If given and another document is in front, nothing changes and the call fails; "
             "use vw_switch_document first. Always pass it for writes.")
_LAYER = "Design layer to place the new object(s) on, by name. Omitted: the user's active layer."
_CLASS = ("Class to assign to the new object(s), by name (created if missing). Applied in a "
          "second step and reported as 'class' in the result. Omitted: the active class.")
_PURPOSE = "Text for the object's Spotlight 'Purpose' field. Omitted: left empty."
_POSITION = "Text for the object's Spotlight 'Position' field. Omitted: left empty."
_UNITS = "document units"


@mcp.tool(annotations=READ)
def vw_list_library_files(
    query: Annotated[str, _d("Words that must all appear in the file's path, case-insensitive; "
                             "for example 'truss', 'lighting', 'people', 'stage deck' or 'audio'. "
                             "Empty lists every library file.")] = "",
    limit: Annotated[int, _d("Maximum number of files to return.")] = 50,
) -> list[dict]:
    """Find Vectorworks library files (.vwx) installed on this Mac by words in their path.
    Searches the Vectorworks application libraries and the user libraries on
    disk only; nothing is sent to Vectorworks and nothing is imported. Use it
    first when a symbol (truss, fixture, people, backline) is not yet in the
    document, then vw_list_library_resources on one of the returned paths and
    vw_import_resource to bring a symbol in. Only libraries that are actually
    downloaded are found; many Vectorworks libraries are download-on-demand.
    Returns a list of {library, folder, name, path} rows."""
    return library.find_library_files(query, limit=limit)


@mcp.tool(annotations=READ)
def vw_list_library_resources(
    path: Annotated[str, _d("Absolute path of a library .vwx file, as returned by vw_list_library_files.")],
    name_contains: Annotated[str | None, _d("Keep only resources whose name contains this text, "
                                           "case-insensitive. Omitted: all resources of that type.")] = None,
    type_code: Annotated[int, _d("Vectorworks resource type: 16 = symbol definitions (includes plug-in "
                                 "styles such as truss, lighting pipe and fixture symbols), 47 = record formats.")] = 16,
    limit: Annotated[int, _d("Maximum number of names to return.")] = 500,
) -> dict:
    """List the resource names inside one library file without importing anything.
    Vectorworks reads the file's resource list; the document is not changed.
    Use it after vw_list_library_files to pick the exact symbol name for
    vw_import_resource. Returns {path, type_code, count, names: [...]}."""
    return vw("library_resources", path=path, type_code=type_code,
              name_contains=name_contains, limit=limit)


@mcp.tool(annotations=WRITE)
def vw_import_resource(
    path: Annotated[str, _d("Absolute path of the library .vwx file (from vw_list_library_files).")],
    name: Annotated[str, _d("Exact resource name inside that file (from vw_list_library_resources).")],
    new_name: Annotated[str | None, _d("Name for the imported copy when the document already has a "
                                      "resource called `name`. Omitted: imported under its own name.")] = None,
    type_code: Annotated[int, _d("Resource type: 16 = symbol definition or plug-in style (default), "
                                 "47 = record format.")] = 16,
    document: Annotated[str | None, _d(_DOCUMENT)] = None,
) -> dict:
    """Import one symbol or plug-in style from a library file into the open document.
    Goes through Vectorworks' own importer, so the resource arrives complete
    (a truss symbol brings its Braceworks record, a fixture symbol its
    Lighting Device data). Changes the document's resource list only; nothing
    is placed in the drawing. Afterwards place it with vw_insert_symbol
    (plain symbols) or the typed insert tools (truss runs, lighting devices).
    One revertible step: vw_revert_last removes the imported resource.
    Returns {name, type_code} with the name as it exists in the document."""
    app.require_document(document)
    out = vw("import_resource", path=path, name=name, type_code=type_code, new_name=new_name)
    return _journal(out, "vw_import_resource", [{"op": "resource", "name": out["name"]}])


@mcp.tool(annotations=WRITE)
def vw_create_pio(
    plugin: Annotated[str, _d("Internal plug-in name, case-sensitive: 'TrussItem', 'Lighting Device', "
                              "'Light Position Obj', ... Learn names from vw_find_objects(type='Plug-in "
                              "Object') plus vw_get_pio_parameters on an existing object.")],
    x: Annotated[float, _d(f"Insertion point x in {_UNITS}.")],
    y: Annotated[float, _d(f"Insertion point y in {_UNITS}.")],
    rotation: Annotated[float, _d("Rotation in degrees, counter-clockwise, 0 = along +x.")] = 0.0,
    parameters: Annotated[dict[str, Any] | None, _d("Parameter fields to set by exact field name, for example "
                                                   "{'Symbol': 'F34 Straight 2m', 'Name': 'T1'} for a TrussItem. "
                                                   "An unknown name aborts the call. Omitted: plug-in defaults.")] = None,
    layer: Annotated[str | None, _d(_LAYER)] = None,
    class_name: Annotated[str | None, _d(_CLASS)] = None,
    document: Annotated[str | None, _d(_DOCUMENT)] = None,
) -> dict:
    """Place one Vectorworks or Spotlight plug-in object by its internal name and set its parameters.
    The general-purpose way to create a plug-in object when no typed tool
    fits; prefer vw_insert_truss_run, vw_insert_lighting_devices,
    vw_insert_stage_decks and the other insert tools where they exist, since
    those know the objects' quirks. The object is created and regenerated with
    the given parameters; nothing else in the document is touched. Unknown
    parameter names abort the call and nothing is placed. One revertible step.
    Returns the new object's summary as vw_find_objects lists objects ({uuid,
    type, name, layer, class, bbox...}) plus class; read the resulting fields
    with vw_get_pio_parameters."""
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
def vw_get_pio_parameters(
    uuid: Annotated[str, _d("UUID of a plug-in object, from vw_find_objects, vw_get_selection or an insert tool's result.")],
) -> dict:
    """Read every parameter field of one plug-in object with its current value.
    Works for truss, lighting devices, stage decks, hoists and any other
    plug-in object; also tells you the plug-in's internal name, which is what
    vw_create_pio needs. Reads only. Returns {plugin, fields: {field: value}}."""
    return vw("pio_parameters", uuid=uuid)


@mcp.tool(annotations=WRITE)
def vw_set_pio_parameters(
    uuid: Annotated[str, _d("UUID of the plug-in object to change.")],
    values: Annotated[dict[str, Any], _d("Fields to set, by exact field name as vw_get_pio_parameters lists "
                                         "them, with their new values. One unknown name changes nothing.")],
    document: Annotated[str | None, _d(_DOCUMENT)] = None,
) -> dict:
    """Change parameter fields of one plug-in object by field name and regenerate it.
    Use it for objects that have no typed editor; for Lighting Devices prefer
    vw_set_lighting_device_fields, which also handles addresses and read-back.
    All-or-nothing: an unknown field name changes nothing. One revertible
    step: vw_revert_last restores the previous values. Returns {uuid, plugin,
    after: {field: value}} re-read after the regeneration, so values Vectorworks
    rejected show their actual state."""
    app.require_document(document)
    out = vw("set_pio_parameters", uuid=uuid, values=values)
    ops = [{"op": "fields", "uuid": uuid, "record": out["record"], "before": out["before"]}]
    _journal(out, "vw_set_pio_parameters", ops)
    return {"uuid": uuid, "plugin": out["record"], "after": vw("get_record", uuid=uuid, record=out["record"])}


@mcp.tool(annotations=WRITE)
def vw_create_layer(
    name: Annotated[str, _d("Name of the new layer. Fails if a layer of that name exists.")],
    kind: Annotated[Literal["design", "sheet"], _d("'design' for a model/drawing layer, 'sheet' for a "
                                                  "presentation sheet layer.")] = "design",
    scale: Annotated[float | None, _d("Design layers only: scale denominator, for example 48 for "
                                      "1/4\" = 1', 100 for 1:100. Omitted: the document's default.")] = None,
    activate: Annotated[bool, _d("True makes the new layer the active layer. Default False keeps "
                                 "the user's active layer.")] = False,
    document: Annotated[str | None, _d(_DOCUMENT)] = None,
) -> dict:
    """Create a design layer or a sheet layer in the open document.
    Adds the layer only; nothing is drawn on it. For a sheet with a viewport
    and title block use vw_create_sheet instead. The user's active layer stays
    active unless activate=True. One revertible step: vw_revert_last deletes
    the layer. Returns {name, kind, active}."""
    app.require_document(document)
    out = vw("create_layer", name=name, kind=kind, scale=scale, activate=activate)
    return _journal(out, "vw_create_layer", [{"op": "layer", "name": name}])


@mcp.tool(annotations=WRITE)
def vw_create_class(
    name: Annotated[str, _d("Class name; use '-' for hierarchy, for example 'Lighting-Truss'. "
                            "Fails if the class exists.")],
    document: Annotated[str | None, _d(_DOCUMENT)] = None,
) -> dict:
    """Create one class in the open document with default attributes.
    For a whole consistent class set with colours and line weights use
    vw_apply_class_standard instead. The active class is left unchanged and
    no object is moved into the new class (pass class_name= to the insert
    tools, or vw_set_record). One revertible step: vw_revert_last deletes the
    class. Returns {name}."""
    app.require_document(document)
    out = vw("create_class", name=name)
    return _journal(out, "vw_create_class", [{"op": "class", "name": name}])


@mcp.tool(annotations=WRITE)
def vw_apply_class_standard(
    standard: Annotated[str, _d("Name of the bundled class standard. 'spotlight' (the only one today) "
                                "defines Lighting-Instruments / -Labels / -Positions / -Focus Points / "
                                "-Cables, Rigging-Truss / -Hoists, Stage-Decks / -Steps, Soft Goods, "
                                "Audio, Video, Scenery, People, Venue-Architecture / -Seating, Notes, "
                                "Dimensions.")] = "spotlight",
    only: Annotated[list[str] | None, _d("Limit the work to these class names or name prefixes, for "
                                         "example ['Lighting', 'Rigging-Truss']. Omitted: the whole standard.")] = None,
    overwrite: Annotated[bool, _d("True restyles classes that already exist (pen, fill, line weight; "
                                  "recorded for revert). Default False leaves existing classes alone.")] = False,
    document: Annotated[str | None, _d(_DOCUMENT)] = None,
) -> dict:
    """Give the document a consistent set of Spotlight classes with colours and line weights.
    Use it once per show file so plots look tidy and layers can be filtered;
    for a single ad-hoc class use vw_create_class. Missing classes are created
    and styled; existing ones are left alone unless overwrite=True. No object
    changes class: afterwards pass class_name= to the insert tools or use
    vw_set_record. One revertible step (created classes are deleted, restyled
    ones restored). Returns {standard, created: [...], restyled: [...],
    unchanged: [...], note?}."""
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
    name: Annotated[str, _d("Name of the new sheet layer. Fails if a layer of that name exists.")],
    layers: Annotated[list[str], _d("Design layer names the viewport shows; at least one.")],
    scale: Annotated[float, _d("Viewport scale denominator: 48 = 1/4\" = 1'-0\", 96 = 1/8\", 50 or 100 "
                               "for metric. Must be positive.")] = 48,
    hide_classes: Annotated[list[str] | None, _d("Class names hidden in this viewport only, for example "
                                                 "['Notes', 'Lighting-Focus Points']. Omitted: all classes visible.")] = None,
    title: Annotated[str | None, _d("Sheet title written into the title block's 'Sheet Title' field. "
                                    "Any of title, sheet_number or project adds a Title Block Border.")] = None,
    sheet_number: Annotated[str | None, _d("Sheet number written into the title block's 'Sheet Number' field.")] = None,
    project: Annotated[str | None, _d("Project name written into the title block's 'Project Name' field.")] = None,
    document: Annotated[str | None, _d(_DOCUMENT)] = None,
) -> dict:
    """Create a presentation sheet: a sheet layer with one Top/Plan viewport of chosen design layers and an optional title block.
    Use it to make a printable plot page; vw_create_layer makes a bare layer
    only. The viewport shows `layers` at 1:`scale` with `hide_classes` hidden
    in that viewport. With title, sheet_number or project, a Title Block
    Border is placed at the sheet origin and those fields written where the
    title block style has them. The user's active layer is restored. One
    revertible step: vw_revert_last deletes the sheet with its viewport and
    title block. Returns {sheet, viewport (uuid), title_block: {uuid, fields_set,
    fields_unknown, fields_available}?, title_block_error?}. To look at it, the
    user switches to the sheet and you call vw_screenshot, or use
    vw_render_layers for a picture."""
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
def vw_delete_objects(
    uuids: Annotated[list[str], _d("UUIDs of the objects to delete, from vw_find_objects, vw_get_selection "
                                   "or a tool result. At least one; one unknown UUID deletes nothing.")],
    document: Annotated[str | None, _d(_DOCUMENT)] = None,
) -> dict:
    """Permanently delete objects by UUID; the one write that vw_revert_last cannot undo.
    Only Cmd-Z inside Vectorworks can bring them back, and the deletion also
    blocks reverting earlier journaled edits, so confirm with the user before
    calling it. To undo something a tool placed, use vw_revert_last instead
    of deleting by hand. All-or-nothing: if any UUID is unknown nothing is
    deleted. Returns {deleted: n}."""
    app.require_document(document)
    if not uuids:
        raise ToolError("no uuids given")
    out = vw("delete_objects", uuids=uuids)
    return _journal(out, "vw_delete_objects", None)


@mcp.tool(annotations=WRITE)
def vw_move_objects(
    uuids: Annotated[list[str], _d("UUIDs of the objects to move; at least one. One unknown UUID moves nothing.")],
    dx: Annotated[float, _d(f"Offset along x in {_UNITS}.")] = 0.0,
    dy: Annotated[float, _d(f"Offset along y in {_UNITS}.")] = 0.0,
    dz: Annotated[float, _d(f"Offset along z in {_UNITS}, for 3D objects. 0 keeps the height.")] = 0.0,
    document: Annotated[str | None, _d(_DOCUMENT)] = None,
) -> dict:
    """Move objects by an offset, keeping their rotation and everything else.
    All-or-nothing on unknown UUIDs. One revertible step: vw_revert_last moves
    them back (a plug-in regeneration between move and revert can leave an
    object off by a fraction of a unit). Returns {moved: n}."""
    app.require_document(document)
    if not uuids:
        raise ToolError("no uuids given")
    out = vw("move_objects", uuids=uuids, dx=dx, dy=dy, dz=dz)
    ops = [{"op": "move", "uuid": u, "dx": dx, "dy": dy, "dz": dz} for u in uuids]
    return _journal(out, "vw_move_objects", ops)


@mcp.tool(annotations=WRITE)
def vw_set_view(
    view: Annotated[Literal["top_plan", "top", "bottom", "front", "back", "left", "right",
                            "iso", "iso_right", "iso_left"] | None,
                    _d("View to switch to: 'top_plan' (2D plan), the orthogonal 3D views 'top', 'bottom', "
                       "'front', 'back', 'left', 'right', or the isometrics 'iso', 'iso_right', 'iso_left'. "
                       "Omitted: the view is left as it is.")] = None,
    fit: Annotated[bool, _d("True zooms so every object on visible layers fits the window.")] = False,
) -> dict:
    """Change the drawing view or zoom to fit, typically before vw_screenshot.
    Changes how the user sees the document, not the document itself, so it is
    not journaled and vw_revert_last does not undo it. For a view-independent
    picture use vw_render_layers instead. Returns {view, fit}."""
    return vw("set_view", view=view, fit=fit)


@mcp.tool(annotations=WRITE)
def vw_insert_truss_run(
    symbol: Annotated[str, _d("Name of a truss symbol already in the document (vw_list_symbols), or in "
                              "the library file given as library_path.")],
    x: Annotated[float, _d(f"Start point x of the run in {_UNITS} (the first piece begins here).")],
    y: Annotated[float, _d(f"Start point y of the run in {_UNITS}.")],
    count: Annotated[int, _d("Number of pieces placed end to end; at least 1.")],
    rotation: Annotated[float, _d("Direction of the run in degrees: 0 = along +x, 90 = along +y.")] = 0.0,
    z: Annotated[float, _d(f"Height of the truss centre line in {_UNITS}.")] = 0.0,
    position_name: Annotated[str | None, _d("Spotlight position name written into every piece, so lighting "
                                            "devices can refer to the run. Omitted: left empty.")] = None,
    layer: Annotated[str | None, _d(_LAYER)] = None,
    class_name: Annotated[str | None, _d(_CLASS)] = None,
    library_path: Annotated[str | None, _d("Library .vwx path (vw_list_library_files) to import the symbol "
                                           "from first, when it is not in the document yet.")] = None,
    document: Annotated[str | None, _d(_DOCUMENT)] = None,
) -> dict:
    """Place a straight run of truss pieces end to end, linked into one truss system, the way Spotlight's Insert Truss tool does.
    Creates `count` TrussItem objects on the symbol's length centres from
    (x, y) along `rotation`, dimensions, weight and type from the symbol's
    Braceworks record, chained into a new truss system. Corners and towers
    are not supported yet; for a single odd piece use vw_create_pio with
    'TrussItem'. All-or-nothing; one revertible step removes the whole run
    (and the import, if any). Returns {system, piece_length, total_length,
    imported, pieces: [{uuid, bbox}], class?}; check with vw_list_truss."""
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
def vw_list_truss(
    system: Annotated[str | None, _d("Only this truss system, by its Braceworks name such as 'T2'. "
                                     "Omitted: every system.")] = None,
    layer: Annotated[str | None, _d("Only truss on this design layer. Omitted: all layers.")] = None,
) -> dict:
    """Inventory of the truss in the document, grouped by truss system in chain order.
    Reads only. Each system lists its pieces in order along the chain with
    count, total length and weight, symbols, position names, each piece's 3D
    centre and the run's plan bounding box (document units, independent of
    the current view); `linked` is False when a run's pieces are not chained.
    Returns {runs: [{system, count, total_length, total_weight_kg, positions,
    symbols, linked, bbox, pieces: [{uuid, symbol, length, center, class,
    layer}]}], total_pieces, total_length}."""
    return vw("list_truss", system=system, layer=layer)


@mcp.tool(annotations=WRITE)
def vw_insert_lighting_devices(
    symbol: Annotated[str, _d("Name of a fixture symbol already in the document (vw_list_symbols), or in "
                              "the library file given as library_path.")],
    x: Annotated[float, _d(f"First fixture's x in {_UNITS}.")],
    y: Annotated[float, _d(f"First fixture's y in {_UNITS}.")],
    count: Annotated[int, _d("How many fixtures to hang in a row; at least 1.")] = 1,
    spacing: Annotated[float, _d(f"Distance between fixtures in {_UNITS}, measured along `rotation`. "
                                 "0 with count > 1 stacks them on one point.")] = 0.0,
    rotation: Annotated[float, _d("Direction of the row in degrees: 0 = along +x, 90 = along +y.")] = 0.0,
    position: Annotated[str | None, _d("Spotlight Position name to hang them on, as listed by "
                                       "vw_list_positions; the fixtures are raised to that position's height "
                                       "unless z is given. Omitted: no position, height z or 0.")] = None,
    z: Annotated[float | None, _d(f"Explicit hanging height in {_UNITS}. Omitted: the position's height.")] = None,
    start_unit: Annotated[int | None, _d("Unit Number of the first fixture; following ones add unit_step. "
                                         "None leaves Unit Number empty.")] = 1,
    unit_step: Annotated[int, _d("Increment of the Unit Number from one fixture to the next.")] = 1,
    channel: Annotated[int | None, _d("Channel of the first fixture; following ones add channel_step. "
                                      "Omitted: Channel left empty.")] = None,
    channel_step: Annotated[int, _d("Increment of the Channel from one fixture to the next.")] = 1,
    purpose: Annotated[str | None, _d(_PURPOSE)] = None,
    layer: Annotated[str | None, _d(_LAYER)] = None,
    class_name: Annotated[str | None, _d(_CLASS)] = None,
    library_path: Annotated[str | None, _d("Library .vwx path (vw_list_library_files) to import the symbol "
                                           "from first, when it is not in the document yet.")] = None,
    document: Annotated[str | None, _d(_DOCUMENT)] = None,
) -> dict:
    """Hang a row of lighting fixtures as real Spotlight Lighting Devices with position, unit numbers, channels and purpose set.
    Places the symbol `count` times from (x, y) along `rotation`, `spacing`
    apart, and converts each to a Lighting Device the way Spotlight's
    insertion tool does, so Inst Type, wattage, DMX footprint and GDTF data
    come from the symbol. To change fixtures that already exist use
    vw_set_lighting_device_fields; to place a plain (non-fixture) symbol use
    vw_insert_symbol. All-or-nothing; one revertible step removes them all.
    Fields are re-read after Spotlight's reset: trust the returned values, and
    anything Spotlight overrode is listed under not_applied. Returns
    {devices: [{uuid, unit, inst_type, Position, Unit Number, Channel, Purpose,
    Inst Type}], imported, z, class?, not_applied?}."""
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


_STRUCTURE = ("Leg style of each deck: 'Legs-Basic', 'Legs-Braced', 'Folding', 'Deck Only', "
              "'Border' or 'Simple'.")
_DECK_CORNER = ("Platform corner {axis} in {units}: each deck extends +width along `rotation` and "
                "+depth at 90 degrees from it, so at rotation 0 the platform fills x..x+width*columns, "
                "y..y+depth*rows.")


@mcp.tool(annotations=WRITE)
def vw_insert_stage_decks(
    width: Annotated[float, _d(f"Width of one deck in {_UNITS}, measured along `rotation`.")],
    depth: Annotated[float, _d(f"Depth of one deck in {_UNITS}, across `rotation`.")],
    height: Annotated[float, _d(f"Deck top height above the floor in {_UNITS}.")],
    x: Annotated[float, _d(_DECK_CORNER.format(axis="x", units=_UNITS))],
    y: Annotated[float, _d(_DECK_CORNER.format(axis="y", units=_UNITS))],
    columns: Annotated[int, _d("Number of decks along `rotation`; at least 1.")] = 1,
    rows: Annotated[int, _d("Number of decks across; at least 1.")] = 1,
    rotation: Annotated[float, _d("Platform direction in degrees: 0 = width along +x, 90 = along +y.")] = 0.0,
    structure: Annotated[Literal["Legs-Basic", "Legs-Braced", "Folding", "Deck Only", "Border", "Simple"],
                         _d(_STRUCTURE)] = "Legs-Basic",
    purpose: Annotated[str | None, _d(_PURPOSE)] = None,
    position: Annotated[str | None, _d(_POSITION)] = None,
    layer: Annotated[str | None, _d(_LAYER)] = None,
    class_name: Annotated[str | None, _d(_CLASS)] = None,
    document: Annotated[str | None, _d(_DOCUMENT)] = None,
) -> dict:
    """Build a platform from Spotlight Stage Deck objects tiled edge to edge in a grid.
    Creates `columns` x `rows` rectangular decks of `width` x `depth` at
    `height`, starting at corner (x, y). For a platform with a flight of
    steps in one call use vw_insert_platform; for the steps alone
    vw_insert_stage_steps. All-or-nothing; one revertible step removes the
    whole platform. The geometry is read back after creation. Returns
    {count, footprint: {width, depth}, decks: [{uuid, center: [x, y, z],
    size: [w, d, h]}], class?}."""
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


_STEP_KIND = ("Stage Steps type: 'Self-Adjusting' (rental unit with a fixed stringer, shallow pitch "
              "on low stages), 'Frame Free-Standing', 'Solid Free-Standing', 'Open Free-Standing' or "
              "'Simple' (compact flight).")


@mcp.tool(annotations=WRITE)
def vw_insert_platform(
    width: Annotated[float, _d(f"Width of one deck in {_UNITS}, measured along `rotation`.")],
    depth: Annotated[float, _d(f"Depth of one deck in {_UNITS}, across `rotation`.")],
    height: Annotated[float, _d(f"Deck top height above the floor in {_UNITS}; also the stage height the steps descend.")],
    x: Annotated[float, _d(_DECK_CORNER.format(axis="x", units=_UNITS))],
    y: Annotated[float, _d(_DECK_CORNER.format(axis="y", units=_UNITS))],
    columns: Annotated[int, _d("Number of decks along `rotation`; at least 1.")] = 1,
    rows: Annotated[int, _d("Number of decks across; at least 1.")] = 1,
    rotation: Annotated[float, _d("Platform direction in degrees: 0 = width along +x, 90 = along +y.")] = 0.0,
    steps_on: Annotated[Literal["front", "back", "left", "right"] | None,
                        _d("Edge that gets the flight of steps, in the platform's own frame: 'front' is "
                           "the edge through (x, y) along `rotation`, 'back' the opposite edge, 'left' the "
                           "edge through (x, y) across, 'right' the opposite. Omitted: decks only.")] = None,
    step_count: Annotated[int | None, _d("Number of steps in the flight. Omitted: about one per 8 inches of height.")] = None,
    tread_width: Annotated[float | None, _d(f"Width of the flight in {_UNITS}. Omitted: the plug-in default.")] = None,
    step_kind: Annotated[Literal["Self-Adjusting", "Frame Free-Standing", "Solid Free-Standing", "Open Free-Standing", "Simple"],
                         _d(_STEP_KIND)] = "Self-Adjusting",
    rails: Annotated[bool, _d("True adds a handrail on both sides of the steps.")] = False,
    structure: Annotated[Literal["Legs-Basic", "Legs-Braced", "Folding", "Deck Only", "Border", "Simple"],
                         _d(_STRUCTURE)] = "Legs-Basic",
    purpose: Annotated[str | None, _d(_PURPOSE + " Applied to decks and steps.")] = None,
    position: Annotated[str | None, _d(_POSITION + " Applied to decks and steps.")] = None,
    layer: Annotated[str | None, _d(_LAYER)] = None,
    class_name: Annotated[str | None, _d(_CLASS)] = None,
    document: Annotated[str | None, _d(_DOCUMENT)] = None,
) -> dict:
    """Build a platform of Stage Decks together with one flight of Stage Steps on a chosen edge, as one revertible step.
    The decks are laid out exactly as vw_insert_stage_decks does; the flight
    is centred on the `steps_on` edge and descends away from the platform. Use
    vw_insert_stage_decks or vw_insert_stage_steps alone when only one part is
    wanted. All document units. One vw_revert_last removes decks and steps
    together. Returns {decks: [{uuid, center, size}], footprint, steps: {uuid,
    steps, center, size}?, class?} with geometry read back after creation."""
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
def vw_insert_band(
    members: Annotated[list[dict[str, Any]], _d("One entry per person or instrument: {'symbol': name of a "
                                                 "symbol in the document, 'x': ..., 'y': ... (document units), "
                                                 "optional 'z', 'rotation' in degrees (default 0) and 'name' "
                                                 "for the label (default: the symbol name)}. At least one.")],
    layer: Annotated[str | None, _d(_LAYER)] = None,
    class_name: Annotated[str | None, _d(_CLASS + " Applied to symbols and labels.")] = None,
    label: Annotated[bool, _d("True adds a centred text label with each member's name below the symbol.")] = True,
    label_offset_mm: Annotated[float, _d("Distance in millimetres from the symbol's insertion point down to the label.")] = 500,
    document: Annotated[str | None, _d(_DOCUMENT)] = None,
) -> dict:
    """Place a band or crew on stage: people or backline symbols at given points, each with a name label.
    The symbols must already be in the document (vw_list_symbols); bring them
    in first with vw_list_library_resources and vw_import_resource. For a
    single symbol without a label use vw_insert_symbol. All-or-nothing; one
    revertible step removes symbols and labels together. Returns {members:
    [{uuid, label_uuid, ...}], class?}."""
    if not members:
        raise ToolError("members: give at least one {symbol, x, y}")
    clean = []
    for i, m in enumerate(members):
        if not m.get("symbol") or "x" not in m or "y" not in m:
            raise ToolError(f"member {i}: needs symbol, x and y: {m!r}")
        clean.append({"symbol": m["symbol"], "x": m["x"], "y": m["y"], "rotation": m.get("rotation", 0),
                      "name": m.get("name") or m["symbol"], "z": m.get("z")})
    app.require_document(document)
    out = vw("insert_band", members=clean, layer=layer, label=label, label_offset_mm=label_offset_mm)
    uuids = [u for r in out["members"] for u in (r["uuid"], r.get("label_uuid")) if u]
    out = _journal(out, "vw_insert_band", [{"op": "created", "uuid": u} for u in uuids])
    if class_name:  # second job: see vw_create_pio
        vw("set_objects_class", uuids=uuids, cls=class_name)
        out["class"] = class_name
    return out


_EDGE_X = (f"x of the top centre of the flight on the stage edge, in {_UNITS}.")
_EDGE_Y = (f"y of the top centre of the flight on the stage edge, in {_UNITS}.")
_EDGE_ROT = ("Direction in degrees. At 0 the stage is on the +y side and the object descends toward -y; "
             "rotate with the platform, for example 90 for a platform that extends toward -x.")


@mcp.tool(annotations=WRITE)
def vw_insert_stage_ramp(
    x: Annotated[float, _d(_EDGE_X.replace("flight", "ramp"))],
    y: Annotated[float, _d(_EDGE_Y.replace("flight", "ramp"))],
    stage_height: Annotated[float, _d(f"Height of the stage edge the ramp descends from, in {_UNITS}.")],
    rotation: Annotated[float, _d(_EDGE_ROT)] = 0.0,
    tread_width: Annotated[float | None, _d(f"Width of the ramp in {_UNITS}. Omitted: the plug-in default.")] = None,
    ramp_length: Annotated[float | None, _d(f"Length of the ramp measured along the slope, in {_UNITS}. "
                                            "Give this or pitch_angle; omitted with no angle: the plug-in default.")] = None,
    pitch_angle: Annotated[float | None, _d("Slope of the ramp in degrees, as an alternative to ramp_length.")] = None,
    kind: Annotated[Literal["Legs", "Solid", "Simple"], _d("Ramp construction: 'Legs', 'Solid' or 'Simple'.")] = "Legs",
    rail_left: Annotated[bool, _d("True adds a handrail on the left side (seen going down).")] = False,
    rail_right: Annotated[bool, _d("True adds a handrail on the right side.")] = False,
    arrow: Annotated[bool, _d("True draws the plug-in's 'down' arrow in plan view.")] = False,
    purpose: Annotated[str | None, _d(_PURPOSE)] = None,
    position: Annotated[str | None, _d(_POSITION)] = None,
    layer: Annotated[str | None, _d(_LAYER)] = None,
    class_name: Annotated[str | None, _d(_CLASS)] = None,
    document: Annotated[str | None, _d(_DOCUMENT)] = None,
) -> dict:
    """Place a Spotlight Stage Ramp descending from a stage edge.
    Same placement convention as vw_insert_stage_steps: (x, y) is the top
    centre on the edge, the ramp runs away from the stage along `rotation`.
    One revertible step; the geometry is read back after creation. Returns
    {uuid, center: [x, y, z], size: [w, l, h], class?} (the plan length is
    size[1] at rotation 0)."""
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
    points: Annotated[list[list[float]], _d(f"Path of the run as [[x, y], [x, y], ...] in {_UNITS}; at least "
                                            "two points, an open polyline.")],
    height: Annotated[float, _d(f"Height of the curtain or border in {_UNITS}.")],
    function: Annotated[Literal["Curtain", "Truss Border", "Pipe-and-Drape"],
                        _d("What the run is: 'Curtain', 'Truss Border' or 'Pipe-and-Drape'.")] = "Curtain",
    opening_width: Annotated[float | None, _d(f"Curtains only: width of the opening in {_UNITS}. Omitted: no opening.")] = None,
    open_from: Annotated[str | None, _d("Curtains only: where the opening is, as the plug-in's popup text, "
                                        "for example 'Center'. Omitted: the plug-in default.")] = None,
    traveler: Annotated[bool, _d("True marks the curtain as a traveler.")] = False,
    add_pipe: Annotated[bool, _d("True draws the hanging pipe.")] = False,
    add_track: Annotated[bool, _d("True draws the curtain track.")] = False,
    purpose: Annotated[str | None, _d(_PURPOSE)] = None,
    position: Annotated[str | None, _d(_POSITION)] = None,
    layer: Annotated[str | None, _d(_LAYER)] = None,
    class_name: Annotated[str | None, _d(_CLASS)] = None,
    document: Annotated[str | None, _d(_DOCUMENT)] = None,
) -> dict:
    """Place a Spotlight Soft Goods run (curtain, truss border or pipe-and-drape) along a path of points.
    Creates one Soft Goods object on the open polyline through `points`,
    `height` tall, with the optional opening and hardware. One revertible step
    removes it with its path. The geometry is read back after creation.
    Returns {uuid, center: [x, y, z], size: [w, d, h], path_length, class?}."""
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
    x: Annotated[float, _d(_EDGE_X)],
    y: Annotated[float, _d(_EDGE_Y)],
    stage_height: Annotated[float, _d(f"Height of the stage edge the steps descend from, in {_UNITS}.")],
    rotation: Annotated[float, _d(_EDGE_ROT)] = 0.0,
    tread_width: Annotated[float | None, _d(f"Width of the flight in {_UNITS}. Omitted: the plug-in default.")] = None,
    steps: Annotated[int | None, _d("Number of steps. Omitted: about one per 8 inches of stage height.")] = None,
    kind: Annotated[Literal["Self-Adjusting", "Frame Free-Standing", "Solid Free-Standing", "Open Free-Standing", "Simple"],
                    _d(_STEP_KIND)] = "Self-Adjusting",
    rail_left: Annotated[bool, _d("True adds a handrail on the left side (seen going down).")] = False,
    rail_right: Annotated[bool, _d("True adds a handrail on the right side.")] = False,
    stringer_length: Annotated[float | None, _d(f"'Self-Adjusting' only: stringer length in {_UNITS}. "
                                                "Omitted: 6 ft, so a low flight lies at a shallow pitch.")] = None,
    purpose: Annotated[str | None, _d(_PURPOSE)] = None,
    position: Annotated[str | None, _d(_POSITION)] = None,
    layer: Annotated[str | None, _d(_LAYER)] = None,
    class_name: Annotated[str | None, _d(_CLASS)] = None,
    document: Annotated[str | None, _d(_DOCUMENT)] = None,
) -> dict:
    """Place a flight of Spotlight Stage Steps descending from a stage edge.
    (x, y) is the top centre of the flight on the edge and the flight runs
    away from the stage along `rotation`. For decks and steps in one call use
    vw_insert_platform; for a ramp vw_insert_stage_ramp. The default
    'Self-Adjusting' kind is a rental unit with a fixed stringer, so a low
    flight lies at a shallow pitch; 'Simple' gives a compact flight. One
    revertible step; the geometry is read back after creation. Returns
    {uuid, steps, center: [x, y, z], size: [w, l, h], class?}."""
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
