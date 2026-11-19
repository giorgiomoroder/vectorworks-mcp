# Helper library executed INSIDE Vectorworks (embedded Python 3.9).
#
# The server sends this file's source as a prelude with every tool job, so
# the installed bridge never has to change when tools do. Keep it 3.9-
# compatible: no match statements, no `X | Y` type unions, stdlib only.
# `vs` is injected by the bridge.

TYPE_NAMES = {
    2: "Line", 3: "Rectangle", 4: "Oval", 5: "Polygon", 6: "Arc", 10: "Text",
    11: "Group", 15: "Symbol", 16: "Symbol Definition", 21: "Polyline",
    31: "Layer", 86: "Plug-in Object", 92: "Symbol Folder",
}
TYPE_CODES = dict((v.lower(), k) for k, v in TYPE_NAMES.items())


def _str(x):
    return "" if x is None else str(x)


def _is_nil(h):
    return h is None or str(h) == "0"


def obj_name(h):
    # GetName returns "none" for unnamed objects. An object really named
    # "none" is the one GetObject finds (which may otherwise hit class None).
    nm = _str(vs.GetName(h))
    if nm == "none" and str(vs.GetObject(nm)) != str(h):
        return ""
    return nm


def h_uuid(h):
    return vs.GetObjectUuid(h)


def handle(uuid):
    h = vs.GetObjectByUuid(uuid)
    if _is_nil(h):
        raise LookupError("no object with uuid %s" % uuid)
    return h


def pio_name(h):
    """Plug-in object name (e.g. 'Lighting Device'), or ''."""
    if vs.GetTypeN(h) != 86:
        return ""
    rec = vs.GetParametricRecord(h)
    return "" if _is_nil(rec) else _str(vs.GetName(rec))


def record_names(h):
    return [_str(vs.GetName(vs.GetRecord(h, i))) for i in range(1, vs.NumRecords(h) + 1)]


def obj_info(h):
    t = vs.GetTypeN(h)
    (x1, y1), (x2, y2) = vs.GetBBox(h)
    info = {
        "uuid": h_uuid(h),
        "type": TYPE_NAMES.get(t, "Type %d" % t),
        "type_code": t,
        "name": obj_name(h),
        "class": _str(vs.GetClass(h)),
        "layer": _str(vs.GetLName(vs.GetLayer(h))),
        "bbox": [[x1, y1], [x2, y2]],
        "records": record_names(h),
    }
    if t == 15:
        info["symbol"] = _str(vs.GetSymName(h))
    if t == 86:
        info["plugin"] = pio_name(h)
    return info


def all_objects(criteria="(ALL)"):
    found = []
    vs.ForEachObject(found.append, criteria)
    return found


def matches(h, cls=None, layer=None, type_=None, plugin=None, record=None,
            field=None, value=None, name=None):
    if cls is not None and _str(vs.GetClass(h)) != cls:
        return False
    if layer is not None and _str(vs.GetLName(vs.GetLayer(h))) != layer:
        return False
    if type_ is not None:
        want = TYPE_CODES.get(str(type_).lower(), type_)
        if vs.GetTypeN(h) != want:
            return False
    if plugin is not None and pio_name(h) != plugin:
        return False
    if name is not None and obj_name(h) != name:
        return False
    if record is not None:
        if record not in record_names(h) and pio_name(h) != record:
            return False
        if field is not None and value is not None:
            if _str(vs.GetRField(h, record, field)) != _str(value):
                return False
    return True


# ---- document -------------------------------------------------------------

def list_layers():
    out = []
    layer = vs.FLayer()
    while not _is_nil(layer):
        out.append({
            "name": _str(vs.GetLName(layer)),
            "kind": "sheet" if vs.GetObjectVariableInt(layer, 154) == 2 else "design",
            "visibility": vs.GetObjectVariableInt(layer, 153),
            "active": _str(vs.GetLName(layer)) == _str(vs.GetLName(vs.ActLayer())),
        })
        layer = vs.NextLayer(layer)
    return out


def list_classes(name_contains=None):
    names = [_str(vs.ClassList(i)) for i in range(1, vs.ClassNum() + 1)]
    if name_contains:
        needle = name_contains.lower()
        names = [n for n in names if needle in n.lower()]
    return names


def document_info():
    units = vs.GetUnits()
    return {
        "name": _str(vs.GetFName()),
        "path": _str(vs.GetFPathName()),
        "units": {"display_name": units[4].strip() or units[4], "area_name": units[5].strip()},
        "active_layer": _str(vs.GetLName(vs.ActLayer())),
        "active_class": _str(vs.ActiveClass()),
        "layer_count": vs.NumLayers(),
        "class_count": vs.ClassNum(),
        "selection_count": vs.NumSelectedObjects(),
    }


def get_selection(limit=500):
    out = []
    h = vs.FSActLayer()
    while not _is_nil(h) and len(out) < limit:
        out.append(obj_info(h))
        h = vs.NextSObj(h)
    return out


def find_objects(cls=None, layer=None, type_=None, plugin=None, record=None,
                 field=None, value=None, name=None, limit=500):
    out = []
    for h in all_objects():
        if matches(h, cls, layer, type_, plugin, record, field, value, name):
            out.append(obj_info(h))
            if len(out) >= limit:
                break
    return out


# ---- records ----------------------------------------------------------------

def _record_handle(h, record):
    if pio_name(h) == record:
        return vs.GetParametricRecord(h)
    for i in range(1, vs.NumRecords(h) + 1):
        rec = vs.GetRecord(h, i)
        if _str(vs.GetName(rec)) == record:
            return rec
    raise LookupError("object has no record %r (has %r)" % (record, record_names(h)))


def get_record(uuid, record):
    h = handle(uuid)
    rec = _record_handle(h, record)
    fields = {}
    for i in range(1, vs.NumFields(rec) + 1):
        fname = _str(vs.GetFldName(rec, i))
        fields[fname] = _str(vs.GetRField(h, record, fname))
    return fields


def set_record(uuid, record, values):
    h = handle(uuid)
    rec = _record_handle(h, record)
    known = set(_str(vs.GetFldName(rec, i)) for i in range(1, vs.NumFields(rec) + 1))
    unknown = [k for k in values if k not in known]
    if unknown:
        raise KeyError("unknown field(s) %r on record %r" % (unknown, record))
    before = dict((k, _str(vs.GetRField(h, record, k))) for k in values)
    _write_fields(h, record, values)
    return {"document": current_document(), "before": before}


def _write_fields(h, record, values):
    if record == LD:
        values = _address_fields(h, values)
    for k, v in values.items():
        vs.SetRField(h, record, k, _str(v))
    if vs.GetTypeN(h) == 86:
        vs.ResetObject(h)


def current_document():
    return _str(vs.GetFName())


def revert(ops):
    """Undo journaled tool calls: restore fields, delete created objects,
    move objects back, remove created layers/classes/resources."""
    restored, deleted, moved, missing = 0, 0, 0, []
    for op in ops:
        kind = op["op"]
        if kind == "layer_created":  # vw_duplicate_layer
            kind = "layer"
        if kind == "layer":
            h = vs.GetLayerByName(op["name"])
        elif kind == "class":
            h = op["name"] if op["name"] in list_classes() else None
        elif kind == "resource":
            h = vs.GetObject(op["name"])
        else:
            h = vs.GetObjectByUuid(op["uuid"])
        if _is_nil(h):
            missing.append(op.get("uuid") or op.get("name"))
            continue
        if kind == "vertices":
            b = op["before"]
            _apply_vertices(h, b["points"], b.get("vertex_types"), b.get("arc_radii"))
            restored += 1
        elif kind == "fields":
            _write_fields(h, op["record"], op["before"])
            restored += 1
        elif kind == "created" or kind == "layer" or kind == "resource":
            vs.DelObject(h)
            deleted += 1
        elif kind == "class":
            vs.DelClass(op["name"])
            deleted += 1
        elif kind == "move":
            _move(h, -op["dx"], -op["dy"], -op.get("dz", 0.0))
            moved += 1
    return {"document": current_document(), "restored": restored, "deleted": deleted,
            "moved": moved, "missing": missing}


# ---- symbols ------------------------------------------------------------------

def list_symbols(name_contains=None, folder=None, limit=1000):
    out = []

    def walk(h, path):
        while not _is_nil(h) and len(out) < limit:
            t = vs.GetTypeN(h)
            nm = _str(vs.GetName(h))
            if t == 92:
                walk(vs.FInFolder(h), path + [nm])
            elif t == 16:
                fpath = "/".join(path)
                if (not name_contains or name_contains.lower() in nm.lower()) and \
                        (not folder or folder.lower() in fpath.lower()):
                    out.append({"name": nm, "folder": fpath})
            h = vs.NextSymDef(h)

    walk(vs.FSymDef(), [])
    return out


def insert_symbol(name, x, y, z=None, layer=None, cls=None, rotation=0.0):
    if _is_nil(vs.GetObject(name)):
        raise LookupError("no symbol definition named %r" % name)
    if layer:
        _activate_layer(layer)
    vs.Symbol(name, (x, y), rotation)
    h = vs.LNewObj()
    if cls:
        vs.SetClass(h, cls)
    if z is not None:
        vs.Move3DObj(h, 0, 0, z - vs.GetSymLoc3D(h)[2])
    info = obj_info(h)
    info["document"] = current_document()
    return info


# ---- Spotlight ------------------------------------------------------------------

LD = "Lighting Device"
LD_FIELDS = [
    "Unit Number", "Channel", "Dimmer", "Universe", "DMX Address", "UniverseAddress",
    "Absolute Address", "Num Channels", "Purpose", "Position", "Inst Type", "Wattage",
    "Color", "Template", "Template2", "Focus", "Circuit Number", "Circuit Name",
    "Mark", "Symbol Name", "Fixture Mode", "GDTF Fixture Name", "Device Type",
    "User Field 1", "User Field 2", "User Field 3", "User Field 4", "User Field 5",
    "User Field 6",
]
# Plug-in name -> parameter holding the position's name.
POSITION_PLUGINS = {
    "Light Position Obj": "Position Name",
    "Lighting Pipe": "Name",
    "Lighting Pipe Ladder": "Name",
    "Hanging Position": "Position Name",
    "TrussItem": "PositionName",  # VW 2026 truss objects (internal name)
    "Truss": "Name",
}


def _natural(s):
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s or "")]


def lighting_devices():
    return all_objects("(PON='%s')" % LD)


def ld_row(h, fields):
    row = {"uuid": h_uuid(h), "layer": _str(vs.GetLName(vs.GetLayer(h))),
           "class": _str(vs.GetClass(h))}
    for f in fields:
        row[f] = _str(vs.GetRField(h, LD, f))
    return row


def ld_field_names():
    devs = lighting_devices()
    if not devs:
        return []
    rec = vs.GetParametricRecord(devs[0])
    return [_str(vs.GetFldName(rec, i)) for i in range(1, vs.NumFields(rec) + 1)]


def list_lighting_devices(fields=None, position=None, layer=None, limit=5000):
    fields = fields or LD_FIELDS
    keyed = []
    for h in lighting_devices():
        pos = _str(vs.GetRField(h, LD, "Position"))
        if position is not None and pos != position:
            continue
        if layer is not None and _str(vs.GetLName(vs.GetLayer(h))) != layer:
            continue
        unit = _str(vs.GetRField(h, LD, "Unit Number"))
        keyed.append(((_natural(pos), _natural(unit)), ld_row(h, fields)))
    keyed.sort(key=lambda kr: kr[0])
    return [row for _, row in keyed[:limit]]


def _resolve_devices(selectors):
    """Map each selector to exactly one device handle, or raise before any edit."""
    by_uuid, by_pos_unit, by_unit, by_chan = {}, {}, {}, {}
    for h in lighting_devices():
        u = h_uuid(h)
        pos = _str(vs.GetRField(h, LD, "Position"))
        unit = _str(vs.GetRField(h, LD, "Unit Number"))
        by_uuid[u] = h
        by_pos_unit.setdefault((pos, unit), []).append(h)
        by_unit.setdefault(unit, []).append(h)
        by_chan.setdefault(_str(vs.GetRField(h, LD, "Channel")), []).append(h)
    out, errors = [], []
    for i, sel in enumerate(selectors):
        if sel.get("uuid"):
            hs = [by_uuid[sel["uuid"]]] if sel["uuid"] in by_uuid else []
            label = "uuid %s" % sel["uuid"]
        elif sel.get("unit_number") is not None and sel.get("position") is not None:
            hs = by_pos_unit.get((sel["position"], str(sel["unit_number"])), [])
            label = "%s unit %s" % (sel["position"], sel["unit_number"])
        elif sel.get("unit_number") is not None:
            hs = by_unit.get(str(sel["unit_number"]), [])
            label = "unit %s (add position: unit numbers repeat per position)" % sel["unit_number"]
        elif sel.get("channel") is not None:
            hs = by_chan.get(str(sel["channel"]), [])
            label = "channel %s" % sel["channel"]
        else:
            errors.append("update %d: needs uuid, unit_number(+position) or channel" % i)
            continue
        if len(hs) != 1:
            errors.append("update %d: %s matches %d devices" % (i, label, len(hs)))
        else:
            out.append(hs[0])
    if errors:
        raise LookupError("; ".join(errors))
    return out


def _address_fields(h, fields):
    """Spotlight rebuilds Universe/DMX Address from UniverseAddress on reset, so
    route split-address edits through UniverseAddress."""
    fields = dict(fields)
    if ("Universe" in fields or "DMX Address" in fields) and "UniverseAddress" not in fields:
        uni = _str(fields.pop("Universe", vs.GetRField(h, LD, "Universe")))
        addr = _str(fields.pop("DMX Address", vs.GetRField(h, LD, "DMX Address")))
        fields["UniverseAddress"] = "%s/%s" % (uni, addr)
    return fields


def set_lighting_device_fields(updates):
    """updates: [{selector keys..., "fields": {name: value}}]. All-or-nothing:
    every selector and field name is validated before anything changes.
    Values are re-read by the server afterwards (resets apply at script end)."""
    handles = _resolve_devices(updates)
    known = set(ld_field_names())
    bad = sorted(set(k for u in updates for k in u["fields"]) - known)
    if bad:
        raise KeyError("unknown Lighting Device field(s): %r" % bad)
    done = []
    for h, u in zip(handles, updates):
        before = dict((k, _str(vs.GetRField(h, LD, k))) for k in u["fields"])
        _write_fields(h, LD, u["fields"])
        done.append({"uuid": h_uuid(h), "before": before})
    return {"document": current_document(), "devices": done}


def read_devices(uuids, fields):
    return [ld_row(handle(u), fields) for u in uuids]


def list_positions(include_devices=True):
    devices = {}
    for h in lighting_devices():
        devices.setdefault(_str(vs.GetRField(h, LD, "Position")), []).append(
            ld_row(h, ["Unit Number", "Channel", "Inst Type", "Purpose"]))
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
            "unassigned_device_count": len(devices.get("", [])),
            "device_positions_without_object": orphans}


# ---- layers, classes, views, move, delete -------------------------------------
# Calls marked (vwx) follow vicquick/vwx-mcp (MIT). Live-tested here on
# Vectorworks 2026 (31.7) 2026-11-17; see docs/vs-notes.md "Drawing tools".

def _activate_layer(name):
    """Make a layer active. VW 2026 (31.7) has no SetActiveLayerN, so this is
    vs.Layer(name), which vwx-mcp found hazardous from palette/timer contexts;
    from our menu command it worked live (2026-11-17)."""
    h = vs.GetLayerByName(name)
    if _is_nil(h):
        raise LookupError("no layer named %r" % name)
    fn = getattr(vs, "SetActiveLayerN", None)
    if fn is not None:
        fn(h)
    else:
        vs.Layer(name)


def create_layer(name, kind="design", scale=None, activate=False):
    if not _is_nil(vs.GetLayerByName(name)):
        raise ValueError("layer %r already exists" % name)
    prev = _str(vs.GetLName(vs.ActLayer()))
    h = vs.CreateLayer(name, 2 if kind == "sheet" else 1)  # (vwx) 1 design, 2 sheet
    if _is_nil(h):
        raise RuntimeError("CreateLayer did not create %r" % name)
    if scale is not None and kind != "sheet":
        vs.SetLScale(h, float(scale))
    if not activate and prev:
        _activate_layer(prev)  # CreateLayer leaves the new layer active
    return {"document": current_document(), "name": name, "kind": kind,
            "active": activate or not prev}


def create_class(name):
    if name in list_classes():
        raise ValueError("class %r already exists" % name)
    prev = _str(vs.ActiveClass())
    vs.NameClass(name)  # (vwx) creates the class, and makes it active
    if prev:
        vs.NameClass(prev)
    return {"document": current_document(), "name": name}


def _handles(uuids):
    """All handles, or a LookupError naming every missing uuid (nothing touched)."""
    hs, missing = [], []
    for u in uuids:
        h = vs.GetObjectByUuid(u)
        (missing if _is_nil(h) else hs).append(u if _is_nil(h) else h)
    if missing:
        raise LookupError("no object with uuid(s) %s" % ", ".join(missing))
    return hs


def delete_objects(uuids):
    hs = _handles(uuids)
    for h in hs:
        vs.DelObject(h)
    return {"document": current_document(), "deleted": len(hs)}


def set_objects_class(uuids, cls):
    """Assign a class to existing objects; returns their previous classes."""
    if cls not in list_classes():
        raise LookupError("no class named %r" % cls)
    hs = _handles(uuids)
    before = [_str(vs.GetClass(h)) for h in hs]
    for h in hs:
        vs.SetClass(h, cls)
    return {"document": current_document(), "before": before}


def move_objects(uuids, dx=0.0, dy=0.0, dz=0.0):
    hs = _handles(uuids)
    for h in hs:
        _move(h, dx, dy, dz)
    return {"document": current_document(), "moved": len(hs)}


def _move(h, dx, dy, dz):
    if dz:
        vs.Move3DObj(h, dx, dy, dz)
    else:
        vs.HMove(h, dx, dy)


# (camera direction, up vector); the target is the origin. (vwx)
VIEWS = {
    "top": ((0, 0, 1), (0, 1, 0)), "bottom": ((0, 0, -1), (0, -1, 0)),
    "front": ((0, -1, 0), (0, 0, 1)), "back": ((0, 1, 0), (0, 0, 1)),
    "right": ((1, 0, 0), (0, 0, 1)), "left": ((-1, 0, 0), (0, 0, 1)),
    "iso": ((1, -1, 1), (0, 0, 1)), "iso_right": ((1, -1, 1), (0, 0, 1)),
    "iso_left": ((-1, -1, 1), (0, 0, 1)),
}


def set_view(view=None, fit=False):
    if view == "top_plan":
        vs.DoMenuTextByName("Standard Views", 1)  # live-tested (vs-notes)
    elif view:
        if view not in VIEWS:
            raise ValueError("unknown view %r (use top_plan, %s)" % (view, ", ".join(VIEWS)))
        loc, up = VIEWS[view]
        vs.SetViewVector(loc, (0, 0, 0), up)
    if fit:
        vs.DoMenuTextByName("Fit To Objects", 0)  # (vwx) VW 2026 has no ZoomToSel
    vs.ReDrawAll()
    return {"view": view, "fit": fit}


# ---- libraries and resources ------------------------------------------------------
# Type codes for BuildResourceList: 16 symbol definition (also plug-in styles,
# which are symbol definitions wrapping one plug-in object), 47 record format.

def _resource_names(list_id, count):
    return [_str(vs.GetNameFromResourceList(list_id, i)) for i in range(1, count + 1)]


def library_resources(path, type_code=16, name_contains=None, limit=500):
    import os
    if not os.path.isfile(path):
        raise LookupError("no file at %s" % path)
    list_id, n = vs.BuildResourceListN(type_code, path)  # (vwx)
    names = _resource_names(list_id, n)
    if name_contains:
        needle = name_contains.lower()
        names = [nm for nm in names if needle in nm.lower()]
    return {"path": path, "type_code": type_code, "count": len(names), "names": names[:limit]}


def import_resource(path, name, type_code=16, new_name=None):
    """Import one resource from a library file via Vectorworks' own importer
    (plug-in style data travels with it). (vwx)"""
    import os
    if not os.path.isfile(path):
        raise LookupError("no file at %s" % path)
    final = new_name or name
    if not _is_nil(vs.GetObject(final)):
        raise ValueError("a resource named %r is already in the document" % final)
    list_id, n = vs.BuildResourceListN(type_code, path)
    names = _resource_names(list_id, n)
    if name not in names:
        raise LookupError("%r is not in %s (has %d resources of type %d)"
                          % (name, path, n, type_code))
    existing = vs.GetObject(name)
    tmp = None
    if not _is_nil(existing):  # importing a copy under new_name: park the local one
        tmp = name + "__vwmcp_tmp"
        vs.SetName(existing, tmp)
    try:
        fn = getattr(vs, "ImportResourceToCurrentFile", None)  # (listID, index) in VW 2026
        if fn is not None:
            h = fn(list_id, names.index(name) + 1)
        else:
            h = vs.ImportResToCurFileN(list_id, names.index(name) + 1, lambda *a: 0)
        if _is_nil(h):
            raise RuntimeError("resource import returned nothing for %r" % name)
        if new_name:
            vs.SetName(h, new_name)
    finally:
        if tmp is not None:
            vs.SetName(existing, name)
    return {"document": current_document(), "name": _str(vs.GetName(h)),
            "type_code": vs.GetTypeN(h)}


# ---- plug-in objects --------------------------------------------------------------

def create_pio(plugin, x, y, rotation=0.0, parameters=None, layer=None):
    """Place a plug-in object by its internal name ('Lighting Device',
    'TrussItem', 'Light Position Obj', ...) and set parameters by field name."""
    if layer:
        _activate_layer(layer)
    fn = getattr(vs, "CreateCustomObjectN", None)
    if fn is not None:
        h = fn(plugin, (x, y), rotation, False)  # False: no preferences dialog
    else:
        h = vs.CreateCustomObject(plugin, (x, y), rotation)
    if _is_nil(h):
        raise LookupError("plug-in %r is not available in this document" % plugin)
    try:
        if parameters:
            set_record(h_uuid(h), pio_name(h) or plugin, parameters)
    except Exception:
        vs.DelObject(h)
        raise
    # `cls` is NOT applied here: a new plug-in object's first regeneration (at the
    # end of this job) resets its class. Callers assign it in a second job
    # (set_objects_class); live finding 2026-11-17.
    info = obj_info(h)
    info["document"] = current_document()
    return info


def pio_parameters(uuid):
    h = handle(uuid)
    rec = pio_name(h)
    if not rec:
        raise TypeError("object %s is not a plug-in object" % uuid)
    return {"plugin": rec, "fields": get_record(uuid, rec)}


def set_pio_parameters(uuid, values):
    rec = pio_name(handle(uuid))
    if not rec:
        raise TypeError("object %s is not a plug-in object" % uuid)
    out = set_record(uuid, rec, values)
    out["record"] = rec
    return out


# ---- tracked raw Python (vw_exec_python) ---------------------------------------

def _jsonable(value):
    import json
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)


def _uuid_parents():
    """uuid -> parent uuid for every object ForEachObject reaches."""
    out = {}

    def add(h):
        u = vs.GetObjectUuid(h)
        if u:
            p = vs.GetParent(h)
            out[u] = "" if _is_nil(p) else _str(vs.GetObjectUuid(p))

    vs.ForEachObject(add, "(ALL)")
    return out


def exec_tracked(code, track=True):
    """Run user code like the bridge does (last expression or `result` is the
    value) and report which objects it created, so they can be reverted.
    Errors are returned, not raised, so a script that fails halfway still
    reports what it already drew."""
    import ast
    import traceback
    before = _uuid_parents() if track else None
    scope = {"vs": vs, "__name__": "__vwmcp_user__"}
    value, error, tb = None, None, None
    try:
        tree = ast.parse(code, "<vw_exec_python>", "exec")
        last = None
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last = ast.Expression(tree.body.pop().value)
        exec(compile(tree, "<vw_exec_python>", "exec"), scope)
        if last is not None:
            value = eval(compile(last, "<vw_exec_python>", "eval"), scope)
        if "result" in scope:
            value = scope["result"]
    except BaseException as e:  # noqa: BLE001 - report, never crash Vectorworks
        error = "%s: %s" % (type(e).__name__, e)
        tb = traceback.format_exc()
    out = {"value": _jsonable(value), "error": error, "traceback": tb,
           "document": current_document()}
    if track:
        after = _uuid_parents()
        new = set(after) - set(before)
        # Keep only top-level new objects: deleting a new group removes its contents.
        out["created"] = sorted(u for u in new if after[u] not in new)
        out["deleted_existing"] = len(set(before) - set(after))
    return out


# ---- truss runs ------------------------------------------------------------------
# Mirrors what Spotlight's Insert Truss tool leaves behind (read live 2026-11-17):
# TrussItem plug-in objects, centre-based, one per symbol length, linked through
# C_START_UUID, dimensions copied from the symbol's BrxTrussItemRecord (mm),
# height in the 3D location, grouped by TrussSystem / TrussLine.

BRX = "BrxTrussItemRecord"


def _mm_to_doc():
    """Document units per millimetre (GetUnits()[3] is units per inch)."""
    return float(vs.GetUnits()[3]) / 25.4


def _truss_record(symbol):
    sd = vs.GetObject(symbol)
    if _is_nil(sd):
        raise LookupError("no symbol %r in the document (vw_import_resource it first)" % symbol)
    if BRX not in record_names(sd):
        raise ValueError("%r has no %s record; it is not a Braceworks truss symbol" % (symbol, BRX))
    f = lambda k: _str(vs.GetRField(sd, BRX, k))  # noqa: E731
    return {"name": f("Name"), "type": f("Type"), "item_type": f("ItemType") or "Line",
            "length_mm": float(f("Length") or 0), "height_mm": float(f("Height") or 0),
            "width_mm": float(f("Width") or 0), "section": f("Section"),
            "connection": f("Connection"), "weight_kg": float(f("Weight") or 0)}


def _next_truss_system():
    used = set()

    def each(h):
        rec = vs.GetParametricRecord(h)
        if not _is_nil(rec) and _str(vs.GetName(rec)) == "TrussItem":
            used.add(_str(vs.GetRField(h, "TrussItem", "TrussSystem")))

    vs.ForEachObject(each, "(T=86)")
    n = 0
    while "T%d" % n in used:
        n += 1
    return "T%d" % n


def insert_truss_run(symbol, x, y, count, rotation=0.0, z=0.0, position_name=None,
                     layer=None, truss_system=None, library_path=None):
    """Place `count` straight truss pieces end to end from (x, y), heading along
    `rotation` degrees, centres at height z. All-or-nothing."""
    import math
    if count < 1:
        raise ValueError("count must be at least 1")
    imported = None
    if _is_nil(vs.GetObject(symbol)) and library_path:
        imported = import_resource(library_path, symbol)["name"]
    rec = _truss_record(symbol)
    if rec["length_mm"] <= 0:
        raise ValueError("%s on %r has no Length" % (BRX, symbol))
    length = rec["length_mm"] * _mm_to_doc()
    if layer:
        _activate_layer(layer)
    system = truss_system or _next_truss_system()
    rad = math.radians(rotation)
    dx, dy = math.cos(rad), math.sin(rad)
    created, prev = [], ""
    try:
        for i in range(count):
            along = length * (0.5 + i)
            h = vs.CreateCustomObjectN("TrussItem", (x + dx * along, y + dy * along), rotation, False)
            if _is_nil(h):
                raise RuntimeError("TrussItem plug-in did not create a piece")
            created.append(h)
            params = {
                "Symbol": symbol, "Name": rec["name"], "Type": rec["type"],
                "ItemType": rec["item_type"], "CrossSection": rec["section"],
                "ConnectionIdent": rec["connection"],
                "Length": "%gmm" % rec["length_mm"], "Height": "%gmm" % rec["height_mm"],
                "Width": "%gmm" % rec["width_mm"],
                "TrussSystem": system, "TrussLine": "1", "TrussSystemLineIdent": system + "-1",
                "C_START_UUID": prev, "PositionName": position_name or "",
            }
            if rec["weight_kg"]:
                params["Weight"] = "%g" % (rec["weight_kg"] * 1000)  # grams, as Insert Truss stores it
                params["Distributed weight"] = "%g" % (rec["weight_kg"] / (rec["length_mm"] / 1000.0))
            _write_fields(h, "TrussItem", params)  # class: see create_pio, applied in a 2nd job
            if z:
                vs.Move3DObj(h, 0, 0, z)
            prev = h_uuid(h)
    except Exception:
        for h in created:
            vs.DelObject(h)
        if imported:
            vs.DelObject(vs.GetObject(imported))
        raise
    pieces = [obj_info(h) for h in created]
    return {"document": current_document(), "system": system, "piece_length": length,
            "total_length": length * count, "imported": imported,
            "pieces": [{"uuid": p["uuid"], "bbox": p["bbox"]} for p in pieces]}


def _dim_to_doc(text):
    """A dimension field as read back in document units; 0 for blank. VW 2026
    returns feet-inches docs' dimension fields as feet in exponent notation
    ("8.000000000000002e00'", live 2026-11-17); mm, m, inches and 9'10" forms
    are accepted too."""
    import re
    t = _str(text).strip().replace(",", "")
    if not t:
        return 0.0
    per_inch = float(vs.GetUnits()[3])
    m = re.match(r"^(-?[\d.]+(?:[eE][+-]?\d+)?)\s*(mm|cm|m|in|\"|ft|')?$", t)
    if m:
        v, unit = float(m.group(1)), m.group(2)
        if unit == "mm":
            return v * per_inch / 25.4
        if unit == "cm":
            return v * per_inch / 2.54
        if unit == "m":
            return v * per_inch / 0.0254
        if unit in ("in", '"'):
            return v * per_inch
        if unit in ("ft", "'"):
            return v * 12 * per_inch
        return v
    m = re.match(r"^(-?)(\d+)'\s*(?:(\d+(?:\.\d+)?)(?:\s*(\d+)/(\d+))?\"?)?$", t)
    if m:
        sign = -1 if m.group(1) else 1
        inches = int(m.group(2)) * 12 + float(m.group(3) or 0)
        if m.group(4):
            inches += float(m.group(4)) / float(m.group(5))
        return sign * inches * per_inch
    raise ValueError("cannot read dimension %r" % t)


def list_truss(system=None, layer=None):
    """TrussItem objects grouped by TrussSystem, each run ordered along its
    C_START_UUID chain, with lengths in document units."""
    items = []

    def each(h):
        if pio_name(h) != "TrussItem":
            return
        if layer and _str(vs.GetLName(vs.GetLayer(h))) != layer:
            return
        f = lambda k: _str(vs.GetRField(h, "TrussItem", k))  # noqa: E731
        sysname = f("TrussSystem")
        if system and sysname != system:
            return
        info = obj_info(h)
        ext = _extent3d(h) or {"center": [None, None, None], "size": [0, 0, 0]}
        items.append({"uuid": info["uuid"], "system": sysname, "symbol": f("Symbol"),
                      "type": f("Type"), "item_type": f("ItemType"),
                      "length": _dim_to_doc(f("Length")),
                      "weight_kg": float(f("Weight") or 0) / 1000.0,
                      "position": f("PositionName"), "previous": f("C_START_UUID"),
                      "class": info["class"], "layer": info["layer"],
                      "center": ext["center"], "size": ext["size"]})

    vs.ForEachObject(each, "(T=86)")
    groups = {}
    for it in items:
        groups.setdefault(it["system"], []).append(it)
    runs = []
    for name in sorted(groups, key=_natural):
        pieces = groups[name]
        # order along the chain: starts are pieces nobody points back to
        by_uuid = dict((p["uuid"], p) for p in pieces)
        nexts = dict((p["previous"], p["uuid"]) for p in pieces if p["previous"] in by_uuid)
        ordered, seen = [], set()
        for start in [p for p in pieces if p["previous"] not in by_uuid]:
            u = start["uuid"]
            while u and u in by_uuid and u not in seen:
                seen.add(u)
                ordered.append(by_uuid[u])
                u = nexts.get(u)
        ordered += [p for p in pieces if p["uuid"] not in seen]  # loops / broken links
        xs = [p["center"][0] + s * p["size"][0] / 2.0 for p in ordered for s in (-1, 1)
              if p["center"][0] is not None]
        ys = [p["center"][1] + s * p["size"][1] / 2.0 for p in ordered for s in (-1, 1)
              if p["center"][1] is not None]
        runs.append({"system": name, "count": len(ordered),
                     "total_length": sum(p["length"] for p in ordered),
                     "total_weight_kg": sum(p["weight_kg"] for p in ordered),
                     "positions": sorted(set(p["position"] for p in ordered if p["position"])),
                     "symbols": sorted(set(p["symbol"] for p in ordered if p["symbol"])),
                     "linked": all(p["previous"] in by_uuid for p in ordered[1:]) if ordered else True,
                     "bbox": [[min(xs), min(ys)], [max(xs), max(ys)]] if xs else None,
                     "pieces": [dict((k, p[k]) for k in ("uuid", "symbol", "length", "center", "class", "layer"))
                                for p in ordered]})
    return {"document": current_document(), "runs": runs,
            "total_pieces": len(items), "total_length": sum(p["length"] for p in items)}


# ---- lighting devices -------------------------------------------------------------
# A Lighting Device is made the way Spotlight's insertion tool does it (live
# 2026-11-17): place the fixture symbol, select it, run the "Convert to
# Instrument" menu command. A bare CreateCustomObjectN("Lighting Device") gets
# no geometry and no Light Info Record data. See docs/vs-notes.md.

CONVERT_MENU = "Convert to Instrument"


def _selected_uuids():
    out = []
    h = vs.FSActLayer()
    while not _is_nil(h):
        out.append(h_uuid(h))
        h = vs.NextSObj(h)
    return out


def _select_only(handles):
    vs.DSelectAll()
    for h in handles:
        vs.SetSelect(h)


def _restore_selection(uuids):
    vs.DSelectAll()
    for u in uuids:
        h = vs.GetObjectByUuid(u)
        if not _is_nil(h):
            vs.SetSelect(h)


def position_height(position):
    """z of the named position (Light Position Obj, truss, pipe...), or None."""
    found = []

    def each(h):
        if found:
            return
        rec = vs.GetParametricRecord(h)
        if _is_nil(rec):
            return
        plugin = _str(vs.GetName(rec))
        field = POSITION_PLUGINS.get(plugin)
        if field and _str(vs.GetRField(h, plugin, field)) == position:
            found.append(vs.GetSymLoc3D(h)[2])

    vs.ForEachObject(each, "(T=86)")
    return found[0] if found else None


def insert_lighting_devices(symbol, x, y, count, spacing=0.0, rotation=0.0, z=None,
                            position=None, start_unit=1, unit_step=1, channel=None,
                            channel_step=1, purpose=None, layer=None, library_path=None):
    """Hang `count` fixtures of `symbol` along `rotation` from (x, y), `spacing`
    apart, converted to Lighting Devices and filled in. All-or-nothing."""
    import math
    if count < 1:
        raise ValueError("count must be at least 1")
    imported = None
    if _is_nil(vs.GetObject(symbol)) and library_path:
        imported = import_resource(library_path, symbol)["name"]
    if _is_nil(vs.GetObject(symbol)):
        raise LookupError("no symbol %r in the document (vw_import_resource it first)" % symbol)
    if z is None and position:
        z = position_height(position)
    if layer:
        _activate_layer(layer)
    previous = _selected_uuids()
    rad = math.radians(rotation)
    dx, dy = math.cos(rad), math.sin(rad)
    placed = []
    try:
        for i in range(count):
            vs.Symbol(symbol, (x + dx * spacing * i, y + dy * spacing * i), rotation)
            placed.append(vs.LNewObj())
        _select_only(placed)
        vs.DoMenuTextByName(CONVERT_MENU, 0)
        devices = []
        h = vs.FSActLayer()
        while not _is_nil(h):
            if pio_name(h) == LD:
                devices.append(h)
            h = vs.NextSObj(h)
        if len(devices) != count:
            raise RuntimeError("%r converted %d of %d symbols into Lighting Devices; is %r "
                               "a fixture symbol with a Light Info Record?"
                               % (CONVERT_MENU, len(devices), count, symbol))
        placed = devices  # the symbols are gone; these are what to delete on failure
        for i, h in enumerate(devices):
            fields = {}
            if position:
                fields["Position"] = position
            if start_unit is not None:
                fields["Unit Number"] = str(start_unit + unit_step * i)
            if channel is not None:
                fields["Channel"] = str(channel + channel_step * i)
            if purpose:
                fields["Purpose"] = purpose
            if fields:
                _write_fields(h, LD, fields)
            if z:
                vs.Move3DObj(h, 0, 0, z - vs.GetSymLoc3D(h)[2])
    except Exception:
        for h in placed:
            if not _is_nil(h):
                vs.DelObject(h)
        if imported:
            vs.DelObject(vs.GetObject(imported))
        _restore_selection(previous)
        raise
    _restore_selection(previous)
    return {"document": current_document(), "imported": imported, "z": z,
            "devices": [{"uuid": h_uuid(h), "unit": _str(vs.GetRField(h, LD, "Unit Number")),
                         "inst_type": _str(vs.GetRField(h, LD, "Inst Type"))} for h in devices]}


# ---- stage decks ------------------------------------------------------------------
# Spotlight's Stage Deck plug-in (internal name "Stage Deck", Plug-ins/Stage
# Deck.vso). Dimension fields take unit strings; we write millimetres like
# the truss helper. Field names come from the .vso string table.

DECK = "Stage Deck"
DECK_STRUCTURES = ["Legs-Basic", "Legs-Braced", "Folding", "Deck Only", "Border", "Simple"]


def _doc_to_mm(value):
    return float(value) / _mm_to_doc()


def _extent3d(h):
    """Centre and size of an object's 3D extents, view-independent (GetBBox is
    projected in 3D views; live 2026-11-17)."""
    if not hasattr(vs, "Get3DCntr"):
        return None
    (cx, cy), cz = vs.Get3DCntr(h)
    dy, dx, dz = vs.Get3DInfo(h)  # returns (y extent, x extent, z extent) on a deck
    return {"center": [cx, cy, cz], "size": [dx, dy, dz]}


def insert_stage_decks(width, depth, height, x, y, columns=1, rows=1, rotation=0.0,
                       structure="Legs-Basic", purpose=None, position=None, layer=None):
    """Tile `columns` x `rows` Stage Deck objects of width x depth (document
    units) at `height`. (x, y) is the first deck's insertion corner (a deck
    extends +width along `rotation` degrees and +depth at +90 from it; live
    2026-11-17); columns continue along rotation, rows across. All-or-nothing."""
    import math
    if columns < 1 or rows < 1:
        raise ValueError("columns and rows must be at least 1")
    if width <= 0 or depth <= 0:
        raise ValueError("width and depth must be positive")
    if structure not in DECK_STRUCTURES:
        raise ValueError("structure must be one of %s" % ", ".join(DECK_STRUCTURES))
    if layer:
        _activate_layer(layer)
    rad = math.radians(rotation)
    ax, ay = math.cos(rad), math.sin(rad)      # along a row of columns
    bx, by = -math.sin(rad), math.cos(rad)     # across rows
    params = {"DeckShape": "Rectangular", "Width": "%gmm" % _doc_to_mm(width),
              "Depth": "%gmm" % _doc_to_mm(depth), "Height": "%gmm" % _doc_to_mm(height),
              "StgStyle": structure}
    if purpose:
        params["Purpose"] = purpose
    if position:
        params["Position"] = position
    created = []
    try:
        for r in range(rows):
            for c in range(columns):
                cx = x + ax * width * c + bx * depth * r
                cy = y + ay * width * c + by * depth * r
                h = vs.CreateCustomObjectN(DECK, (cx, cy), rotation, False)
                if _is_nil(h):
                    raise RuntimeError("Stage Deck plug-in did not create an object")
                created.append(h)
                _write_fields(h, DECK, params)  # class: see create_pio, applied in a 2nd job
    except Exception:
        for h in created:
            vs.DelObject(h)
        raise
    return {"document": current_document(), "count": len(created),
            "footprint": {"width": width * columns, "depth": depth * rows},
            "decks": [{"uuid": h_uuid(h)} for h in created]}


def object_extents(uuids):
    """3D centre and size per object (a second job after creation: a new
    plug-in object has no geometry until the creating job ends)."""
    return [dict(uuid=u, **(_extent3d(handle(u)) or {})) for u in uuids]


# ---- stage steps ------------------------------------------------------------------
# Spotlight's Stage Steps plug-in (live 2026-11-17): inserted at the top centre
# of the flight, at the stage edge; at rotation 0 the flight is Treadwidth
# wide centred on x and descends in -y. Field names from the .vso string table.

STEPS = "Stage Steps"
STEPS_TYPES = ["Self-Adjusting", "Frame Free-Standing", "Solid Free-Standing",
               "Open Free-Standing", "Simple"]


def insert_stage_steps(x, y, stage_height, rotation=0.0, tread_width=None, steps=None,
                       kind="Self-Adjusting", rail_left=False, rail_right=False,
                       stringer_length=None, purpose=None, position=None, layer=None):
    """One flight of Stage Steps down from a stage edge at (x, y) (top centre
    of the flight), descending away from the stage at rotation-90 degrees
    (rotation 0: stage is +y, steps go -y). Dimensions in document units."""
    if stage_height <= 0:
        raise ValueError("stage_height must be positive")
    if kind not in STEPS_TYPES:
        raise ValueError("kind must be one of %s" % ", ".join(STEPS_TYPES))
    if steps is None:
        # ~8" rise like the plug-in's default (TreadRiseVar 200mm), at least one step
        steps = max(1, int(round(_doc_to_mm(stage_height) / 200.0)))
    if steps < 1:
        raise ValueError("steps must be at least 1")
    if layer:
        _activate_layer(layer)
    params = {"Type": kind, "BuildMethod": "Stage height and number of steps",
              "Stageheight": "%gmm" % _doc_to_mm(stage_height), "StepTotal": str(steps),
              "RailLeft": "True" if rail_left else "False",
              "RailRight": "True" if rail_right else "False"}
    if tread_width:
        params["Treadwidth"] = "%gmm" % _doc_to_mm(tread_width)
    if stringer_length:  # Self-Adjusting units have a fixed stringer (default 6 ft)
        params["StringerLength"] = "%gmm" % _doc_to_mm(stringer_length)
    if purpose:
        params["Purpose"] = purpose
    if position:
        params["Position"] = position
    h = vs.CreateCustomObjectN(STEPS, (x, y), rotation, False)
    if _is_nil(h):
        raise RuntimeError("Stage Steps plug-in did not create an object")
    try:
        _write_fields(h, STEPS, params)  # class: see create_pio, applied in a 2nd job
    except Exception:
        vs.DelObject(h)
        raise
    return {"document": current_document(), "uuid": h_uuid(h), "steps": steps}


# ---- geometry export (read-back) -----------------------------------------------

def _pt(p, nd):
    return [round(p[0], nd), round(p[1], nd)]


def _geom(h, t, nd):
    """Exact geometry for the common 2D types. vs.GetBBox depends on the plan
    rotation of the view, so it is only used as a last resort."""
    import math
    g = {}
    if t == 2:
        g["points"] = [_pt(vs.GetSegPt1(h), nd), _pt(vs.GetSegPt2(h), nd)]
    elif t in (5, 21):
        n = vs.GetVertNum(h)
        if t == 5:
            g["points"] = [_pt(vs.GetPolyPt(h, i), nd) for i in range(1, n + 1)]
        else:
            pts, kinds, radii = [], [], []
            for i in range(1, n + 1):
                p, kind, radius = vs.GetPolylineVertex(h, i)
                pts.append(_pt(p, nd))
                kinds.append(kind)
                radii.append(round(radius, nd))
            g["points"] = pts
            if any(kinds):
                g["vertex_types"] = kinds  # 0 corner, 1 bezier, 2 cubic, 3 arc, 4 radius
                g["arc_radii"] = radii
        try:
            g["closed"] = bool(vs.IsPolyClosed(h))
        except Exception:  # noqa: BLE001 - optional
            pass
    elif t == 6:
        c = vs.HCenter(h)
        p1, p2 = vs.GetSegPt1(h), vs.GetSegPt2(h)
        start, sweep = vs.GetArc(h)
        g.update({"center": _pt(c, nd), "radius": round(math.hypot(p1[0] - c[0], p1[1] - c[1]), nd),
                  "start_angle": round(start, 6), "sweep": round(sweep, 6),
                  "points": [_pt(p1, nd), _pt(p2, nd)]})
    elif t == 10:
        origin, angle, mirrored = vs.GetTextOrientation(h)
        g.update({"text": _str(vs.GetText(h)), "origin": _pt(origin, nd), "angle": round(angle, 6),
                  "size_raw": vs.GetTextSize(h, 0), "just": vs.GetTextJust(h)})  # unit unclear
    elif t == 63:
        g.update({"text": _str(vs.GetDimText(h)), "center": _pt(vs.HCenter(h), nd)})
    else:
        (x1, y1), (x2, y2) = vs.GetBBox(h)
        g.update({"center": _pt(vs.HCenter(h), nd),
                  "bbox_view": [_pt((min(x1, x2), min(y1, y2)), nd), _pt((max(x1, x2), max(y1, y2)), nd)]})
    return g


def _hex(color):
    return "#%02x%02x%02x" % tuple(int(v) >> 8 for v in color[:3])


def _attrs(h):
    """Fill and pen as the object is drawn, and whether they follow its class.
    fill pattern: 0 none, 1 solid background color, 2 solid foreground color,
    other values are patterns / hatches. pen weight in mils (4 = 0.1 mm),
    pen style 0 = no line, 2 = solid, negative = a dash style."""
    return {
        "fill": {
            "pattern": vs.GetFPat(h), "back": _hex(vs.GetFillBack(h)), "fore": _hex(vs.GetFillFore(h)),
            "by_class": {"pattern": bool(vs.IsFPatByClass(h)), "color": bool(vs.IsFillColorByClass(h))},
        },
        "pen": {
            "color": _hex(vs.GetPenFore(h)), "weight": vs.GetLW(h), "style": vs.GetLSN(h),
            "by_class": {"color": bool(vs.IsPenColorByClass(h)), "weight": bool(vs.IsLWByClass(h)),
                         "style": bool(vs.IsLSByClass(h))},
        },
    }


def export_geometry(layer=None, classes=None, limit=20000, digits=4, attributes=True):
    """All objects of one layer (default: active) with exact 2D geometry,
    descending into groups. Plug-in objects (chain dimensions, doors...)
    are reported as one entry with their center. attributes: add fill and
    pen of every object ("attrs")."""
    lay = vs.ActLayer() if not layer else vs.GetLayerByName(layer)
    if _is_nil(lay):
        raise LookupError("no layer named %r" % layer)
    want = set(classes) if classes else None
    out, truncated = [], [False]

    def walk(h, group):
        while not _is_nil(h):
            if len(out) >= limit:
                truncated[0] = True
                return
            t = vs.GetTypeN(h)
            if t == 11:
                walk(vs.FInGroup(h), group + [h_uuid(h)])
            else:
                cls = _str(vs.GetClass(h))
                if want is None or cls in want:
                    e = {"uuid": h_uuid(h), "type": TYPE_NAMES.get(t, "Type %d" % t),
                         "type_code": t, "class": cls}
                    if group:
                        e["group"] = group[-1]
                    if t == 86:
                        e["plugin"] = pio_name(h)
                    e.update(_geom(h, t, digits))
                    if attributes:
                        e["attrs"] = _attrs(h)
                    out.append(e)
            h = vs.NextObj(h)

    walk(vs.FInLayer(lay), [])
    return {"document": current_document(), "layer": _str(vs.GetLName(lay)),
            "objects": out, "truncated": truncated[0]}


# ---- layers ---------------------------------------------------------------------

VISIBILITY = {"visible": 0, "hidden": -1, "gray": 2}


def _layer_names():
    out = []
    layer = vs.FLayer()
    while not _is_nil(layer):
        out.append(_str(vs.GetLName(layer)))
        layer = vs.NextLayer(layer)
    return out


def _pair_uuids(a, b, out):
    """uuid of an object -> uuid of its duplicate, walking groups in parallel."""
    out[h_uuid(a)] = h_uuid(b)
    if vs.GetTypeN(a) == 11 and vs.GetTypeN(b) == 11:
        x, y = vs.FInGroup(a), vs.FInGroup(b)
        while not _is_nil(x) and not _is_nil(y):
            _pair_uuids(x, y, out)
            x, y = vs.NextObj(x), vs.NextObj(y)


def _move_layer_next_to(layer, name, source):
    """Step `layer` through the stack until it sits right after `source` in
    list order. HMoveBackward / HMoveForward on a layer handle move it one
    or more places; the direction is taken from what the first step did."""
    def gap():
        names = _layer_names()
        return names.index(name) - names.index(source)

    start = gap()
    if start == 1:
        return
    vs.HMoveBackward(layer, False)
    backward_lowers = gap() < start
    for _ in range(4 * len(_layer_names())):
        g = gap()
        if g == 1:
            return
        lower = g > 1
        if lower == backward_lowers:
            vs.HMoveBackward(layer, False)
        else:
            vs.HMoveForward(layer, False)
        if gap() == g:
            return  # stuck (e.g. sheet layers in between): leave it there


def duplicate_layer(source, name, visibility=None, uuid_map=False):
    """Copy a design layer with all its objects: same scale, placed right
    after the source in the layer list. visibility: "visible", "hidden",
    "gray" or None (same as the source has now). The active layer stays
    active. uuid_map: also return {source object uuid: copy uuid}."""
    src = vs.GetLayerByName(source)
    if _is_nil(src):
        raise LookupError("no layer named %r" % source)
    if vs.GetObjectVariableInt(src, 154) == 2:
        raise ValueError("%r is a sheet layer; only design layers can be duplicated" % source)
    if not _is_nil(vs.GetLayerByName(name)):
        raise ValueError("a layer named %r already exists" % name)
    if visibility is not None and visibility not in VISIBILITY:
        raise ValueError("visibility must be one of %r or None" % sorted(VISIBILITY))
    active = _str(vs.GetLName(vs.ActLayer()))
    originals = []
    h = vs.FInLayer(src)
    while not _is_nil(h):
        originals.append(h)
        h = vs.NextObj(h)
    new = vs.CreateLayer(name, 1)
    vs.SetLScale(new, vs.GetLScale(src))
    mapping, copied = {}, 0
    for h in originals:
        d = vs.CreateDuplicateObject(h, new)
        if _is_nil(d):
            continue
        copied += 1
        if uuid_map:
            _pair_uuids(h, d, mapping)
    vis = vs.GetObjectVariableInt(src, 153) if visibility is None else VISIBILITY[visibility]
    vs.SetObjectVariableInt(new, 153, vis)
    _move_layer_next_to(new, name, source)
    _activate_layer(active)
    names = _layer_names()
    out = {"document": current_document(), "layer": name, "source": source,
           "objects": copied, "source_objects": len(originals), "scale": vs.GetLScale(new),
           "visibility": vis, "after_source": names.index(name) - names.index(source) == 1}
    if uuid_map:
        out["uuid_map"] = mapping
    return out


# ---- polygon / polyline vertices ------------------------------------------------

def _vertices(h):
    t = vs.GetTypeN(h)
    n = vs.GetVertNum(h)
    if t == 5:
        return {"points": [list(vs.GetPolyPt(h, i)) for i in range(1, n + 1)]}
    pts, kinds, radii = [], [], []
    for i in range(1, n + 1):
        p, kind, radius = vs.GetPolylineVertex(h, i)
        pts.append(list(p))
        kinds.append(kind)
        radii.append(radius)
    return {"points": pts, "vertex_types": kinds, "arc_radii": radii}


def _apply_vertices(h, points, vertex_types=None, arc_radii=None):
    """Make the vertex list of a polygon (type 5) or polyline (type 21) equal
    to `points`. SetPolyPt silently does nothing on polylines, so those go
    through SetPolylineVertex."""
    n = vs.GetVertNum(h)
    while n > len(points):
        vs.DelVertex(h, n)
        n -= 1
    while n < len(points):
        vs.InsertVertex(h, points[0][0], points[0][1], n, 0, 0)
        n += 1
    polyline = vs.GetTypeN(h) == 21
    for i, p in enumerate(points):
        if polyline:
            kind = vertex_types[i] if vertex_types else 0
            radius = arc_radii[i] if arc_radii else 0
            vs.SetPolylineVertex(h, i + 1, (p[0], p[1]), kind, radius, True)
        else:
            vs.SetPolyPt(h, i + 1, p[0], p[1])
    vs.ResetBBox(h)


def _shoelace(points):
    n = len(points)
    return abs(sum(points[i][0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * points[i][1]
                   for i in range(n))) / 2.0


def set_vertices(uuid, points, vertex_types=None, arc_radii=None):
    """Replace all vertices of a polygon or polyline. Re-reads them afterwards
    and reports whether every point arrived ("applied")."""
    h = handle(uuid)
    t = vs.GetTypeN(h)
    if t not in (5, 21):
        raise TypeError("%s is a %s; only polygons and polylines have editable vertices"
                        % (uuid, TYPE_NAMES.get(t, "Type %d" % t)))
    if len(points) < 2:
        raise ValueError("need at least 2 points")
    for name, extra in (("vertex_types", vertex_types), ("arc_radii", arc_radii)):
        if extra is not None and len(extra) != len(points):
            raise ValueError("%s must have one entry per point" % name)
    if t == 5 and vertex_types and any(vertex_types):
        raise ValueError("curved vertices need a polyline; this object is a polygon")
    before = _vertices(h)
    _apply_vertices(h, points, vertex_types, arc_radii)
    after = _vertices(h)["points"]
    applied = len(after) == len(points) and all(
        abs(a[0] - p[0]) < 1e-6 and abs(a[1] - p[1]) < 1e-6 for a, p in zip(after, points))
    return {"document": current_document(), "uuid": uuid,
            "type": TYPE_NAMES.get(vs.GetTypeN(h), "Type %d" % vs.GetTypeN(h)),
            "before": before, "points": after, "applied": applied,
            "area_before": _shoelace(before["points"]), "area": _shoelace(after),
            "closed": bool(vs.IsPolyClosed(h))}
