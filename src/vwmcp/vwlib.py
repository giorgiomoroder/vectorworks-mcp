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


def _keep_selection(fn):
    """Run an insert helper without changing the user's selection: new plug-in
    objects come in selected (live 2026-11-20: Object Info showed the three
    platform parts), which would surprise a user working in the document."""
    def wrapped(*args, **kwargs):
        before = _selected_uuids()
        try:
            return fn(*args, **kwargs)
        finally:
            _restore_selection(before)
    wrapped.__name__ = fn.__name__
    wrapped.__doc__ = fn.__doc__
    return wrapped


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


def _resolve_record(h, record):
    """record None means the plug-in object's own parameter record."""
    if record:
        return record
    name = pio_name(h)
    if not name:
        raise TypeError("object is not a plug-in object; give the record name (has %r)" % record_names(h))
    return name


def get_record(uuid, record=None):
    h = handle(uuid)
    record = _resolve_record(h, record)
    rec = _record_handle(h, record)
    fields = {}
    for i in range(1, vs.NumFields(rec) + 1):
        fname = _str(vs.GetFldName(rec, i))
        fields[fname] = _str(vs.GetRField(h, record, fname))
    return fields


def record_fields(uuid, record=None):
    """{"record": name, "fields": {...}}: the record name resolved (a plug-in's
    parameters when record is None)."""
    record = _resolve_record(handle(uuid), record)
    return {"record": record, "fields": get_record(uuid, record)}


def set_record(uuid, record, values):
    h = handle(uuid)
    record = _resolve_record(h, record)
    rec = _record_handle(h, record)
    known = set(_str(vs.GetFldName(rec, i)) for i in range(1, vs.NumFields(rec) + 1))
    unknown = [k for k in values if k not in known]
    if unknown:
        raise KeyError("unknown field(s) %r on record %r" % (unknown, record))
    before = dict((k, _str(vs.GetRField(h, record, k))) for k in values)
    _write_fields(h, record, values)
    return {"document": current_document(), "record": record, "before": before}


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
        elif kind == "class" or kind == "class_attrs":
            h = op["name"] if op["name"] in list_classes() else None
        elif kind == "resource":
            h = vs.GetObject(op["name"])
        elif kind == "layer_renamed":
            h = vs.GetLayerByName(op["new_name"])
        elif kind == "class_renamed":
            h = op["new_name"] if op["new_name"] in list_classes() else None
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
        elif kind == "class_attrs":
            _set_class_attrs(op["name"], op["before"])
            restored += 1
        elif kind == "move":
            _move(h, -op["dx"], -op["dy"], -op.get("dz", 0.0))
            moved += 1
        elif kind == "rotate":
            vs.HRotate(h, (op["cx"], op["cy"]), -op["angle"])
            moved += 1
        elif kind == "layer_renamed":
            vs.SetName(h, op["name"])
            restored += 1
        elif kind == "class_renamed":
            vs.RenameClass(op["new_name"], op["name"])
            restored += 1
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


@_keep_selection
def insert_band(members, layer=None, label=True, label_offset_mm=500.0, label_size_pt=None):
    """Place people/backline symbols with an optional name label under each:
    members = [{"symbol", "x", "y", "rotation", "name", "z"}]. Symbols must be
    in the document (import them first). Labels are plain text objects,
    centred, `label_offset_mm` below the insertion point. All-or-nothing.
    Not run live yet (2026-11-20): TextJust/TextSize set the state for the
    next CreateText, as the VectorScript reference says."""
    created, out = [], []
    try:
        for m in members:
            info = insert_symbol(m["symbol"], m["x"], m["y"], z=m.get("z"), layer=layer,
                                 rotation=m.get("rotation", 0.0))
            created.append(handle(info["uuid"]))
            row = {"name": m.get("name") or m["symbol"], "symbol": m["symbol"],
                   "uuid": info["uuid"], "label_uuid": None}
            if label and row["name"]:
                vs.TextJust(2)  # centre
                if label_size_pt:
                    vs.TextSize(float(label_size_pt))
                vs.TextOrigin((m["x"], m["y"] - label_offset_mm * _mm_to_doc()))
                vs.CreateText(row["name"])
                t = vs.LNewObj()
                if not _is_nil(t):
                    created.append(t)
                    row["label_uuid"] = h_uuid(t)
            out.append(row)
    except Exception:
        for h in created:
            vs.DelObject(h)
        raise
    return {"document": current_document(), "members": out}


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


MVR_FIELDS = [
    "Unit Number", "Channel", "Position", "Inst Type", "Symbol Name", "Fixture Mode",
    "GDTF Fixture Mode", "GDTF Fixture Name", "GDTF Fixture Type ID", "Fixture ID",
    "UniverseAddress", "Absolute Address", "Num Channels", "Device Type",
]


def mvr_data():
    """Everything the MVR pre-flight (server-side `mvr.run_checks`) looks at:
    device rows with the MVR-relevant fields this document has, the names of the
    position objects, and the symbol type of every fixture symbol in use
    (vs.GetSymbolType: 0 2D only, 1 3D, 2 hybrid; live 2026-11-20 on the
    Bobby Lee plot: field names FixtureID, GDTF Fixture Mode, GDTF Fixture
    Type ID exist in VW 2026)."""
    known = set(ld_field_names())
    fields = [f for f in MVR_FIELDS if f in known]
    rows = [ld_row(h, fields) for h in lighting_devices()]
    positions = [p["name"] for p in list_positions(include_devices=False)["positions"]]
    symbols = {}
    for name in sorted(set(r.get("Symbol Name", "") for r in rows) - set([""])):
        sd = vs.GetObject(name)
        if not _is_nil(sd) and vs.GetTypeN(sd) == 16:
            symbols[name] = {"type": vs.GetSymbolType(sd)}
    return {"document": current_document(), "fields": fields, "devices": rows,
            "positions": positions, "symbols": symbols}


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


def _rgb255(color):
    """0-255 RGB from what the class colour getters return. Live 2026-11-20
    (VW 2026): GetClPenFore / GetClFillFore return an (r, g, b) tuple with
    0-65535 components in Python, not a colour index; an index is converted."""
    if isinstance(color, (tuple, list)):
        r, g, b = color
    else:
        r, g, b = vs.ColorIndexToRGB(color)
    return [int(round(v / 257.0)) for v in (r, g, b)]


def _color_index(rgb):
    return vs.RGBToColorIndex(*[int(v) * 257 for v in rgb])


def class_attrs(names):
    """Pen/fill colour (RGB 0-255), fill pattern, line weight (mils) and
    use-graphic flag of classes, keyed by name; {"exists": False} for unknown
    ones. Live 2026-11-20 on VW 2026: GetClFPat 0 means 'no fill'."""
    have = set(list_classes())
    out = {}
    for n in names:
        if n not in have:
            out[n] = {"exists": False}
            continue
        pat = vs.GetClFPat(n)
        out[n] = {"exists": True, "pen": _rgb255(vs.GetClPenFore(n)),
                  "fill": _rgb255(vs.GetClFillFore(n)) if pat else None,
                  "fill_pattern": pat, "line_weight": vs.GetClLW(n),
                  "use_graphic": bool(vs.GetClUseGraphic(n))}
    return out


def _set_class_attrs(name, spec):
    """spec: pen [r,g,b] 0-255, fill [r,g,b] or None, line_weight mils;
    optional fill_pattern / use_graphic (used by revert)."""
    vs.SetClPenFore(name, _color_index(spec["pen"]))
    if spec.get("fill") is not None:
        vs.SetClFillFore(name, _color_index(spec["fill"]))
        vs.SetClFPat(name, spec.get("fill_pattern") or 1)  # 1 = solid
    else:
        vs.SetClFPat(name, 0)  # 0 = no fill
    vs.SetClLW(name, int(spec["line_weight"]))
    vs.SetClUseGraphic(name, bool(spec.get("use_graphic", True)))


def apply_class_attrs(create, restyle):
    """Create the `create` classes (keeping the user's active class) and style
    both lists. Returns what the revert needs: created names, before-attrs of
    the restyled ones."""
    prev = _str(vs.ActiveClass())
    before = class_attrs([c["name"] for c in restyle])
    created = []
    try:
        for c in create:
            vs.NameClass(c["name"])  # creates and activates (vs-notes)
            actual = _str(vs.ActiveClass())
            created.append(actual)
            if actual != c["name"]:
                # Live 2026-11-25 (VW 2027): a class cannot share its name with a
                # record format ("Soft Goods" once that plug-in was used), so
                # Vectorworks quietly made "Soft Goods-2".
                raise ValueError("class %r could not be created under that name (Vectorworks made %r: "
                                 "the name is taken, usually by a record format); nothing changed"
                                 % (c["name"], actual))
        if created and prev:
            vs.NameClass(prev)
        for c in create + restyle:
            _set_class_attrs(c["name"], c)
    except Exception:
        if prev:
            vs.NameClass(prev)
        for n in created:  # all-or-nothing: a refused call must not leave new classes
            if n in list_classes():
                vs.DelClass(n)
        for n, attrs in before.items():
            if attrs.get("exists"):
                _set_class_attrs(n, attrs)
        raise
    return {"document": current_document(), "created": created,
            "restyled": [c["name"] for c in restyle], "before": before}


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


def _layer_objects(layer_h):
    """Handles of the objects on a layer (FInLayer / NextObj)."""
    out, h = [], vs.FInLayer(layer_h)
    while not _is_nil(h):
        out.append(h)
        h = vs.NextObj(h)
    return out


def rename_layer(name, new_name):
    """Rename a layer (objects stay). Revert op: layer_renamed."""
    h = vs.GetLayerByName(name)
    if _is_nil(h):
        raise LookupError("no layer named %r" % name)
    if not new_name or new_name == name:
        raise ValueError("new_name must differ from name")
    if not _is_nil(vs.GetLayerByName(new_name)):
        raise ValueError("layer %r already exists" % new_name)
    vs.SetName(h, new_name)
    actual = _str(vs.GetLName(h))
    if actual != new_name:
        raise RuntimeError("Vectorworks named the layer %r, not %r" % (actual, new_name))
    return {"document": current_document(), "name": name, "new_name": actual}


def delete_layer(name, force=False):
    """Delete a layer; refuses while objects are on it unless force (they go
    with it and cannot be restored). The only layer cannot be deleted."""
    h = vs.GetLayerByName(name)
    if _is_nil(h):
        raise LookupError("no layer named %r" % name)
    layers = list_layers()
    if len(layers) < 2:
        raise ValueError("%r is the only layer; a document needs one" % name)
    n = len(_layer_objects(h))
    if n and not force:
        raise ValueError("layer %r holds %d object(s); pass force=True to delete them with it" % (name, n))
    active = _str(vs.GetLName(vs.ActLayer()))
    if active == name:  # the active layer cannot go: activate another design layer first
        other = next((l["name"] for l in layers if l["name"] != name and l["kind"] == "design"), None) \
            or next(l["name"] for l in layers if l["name"] != name)
        _activate_layer(other)
    vs.DelObject(h)
    if not _is_nil(vs.GetLayerByName(name)):
        raise RuntimeError("Vectorworks did not delete layer %r" % name)
    return {"document": current_document(), "name": name, "objects_deleted": n}


def _class_object_count(name):
    n = 0
    layer = vs.FLayer()
    while not _is_nil(layer):
        for h in _layer_objects(layer):
            if _str(vs.GetClass(h)) == name:
                n += 1
        layer = vs.NextLayer(layer)
    return n


def rename_class(name, new_name):
    """Rename a class; its objects follow. Revert op: class_renamed."""
    if name not in list_classes():
        raise LookupError("no class named %r" % name)
    if name in ("None", "Dimension"):
        raise ValueError("%r is a built-in class and cannot be renamed" % name)
    if not new_name or new_name == name:
        raise ValueError("new_name must differ from name")
    if new_name in list_classes():
        raise ValueError("class %r already exists" % new_name)
    vs.RenameClass(name, new_name)
    if new_name not in list_classes():
        raise RuntimeError("Vectorworks did not rename class %r" % name)
    return {"document": current_document(), "name": name, "new_name": new_name}


def delete_class(name, force=False):
    """Delete a class; refuses while objects use it unless force (Vectorworks
    moves them to None). Built-in classes cannot be deleted."""
    if name not in list_classes():
        raise LookupError("no class named %r" % name)
    if name in ("None", "Dimension"):
        raise ValueError("%r is a built-in class and cannot be deleted" % name)
    n = _class_object_count(name)
    if n and not force:
        raise ValueError("class %r is used by %d object(s); pass force=True to delete it anyway "
                         "(they move to class None)" % (name, n))
    if _str(vs.ActiveClass()) == name:
        vs.NameClass("None")
    vs.DelClass(name)
    if name in list_classes():
        raise RuntimeError("Vectorworks did not delete class %r" % name)
    return {"document": current_document(), "name": name, "objects_moved_to_none": n}


def _plan_center(h):
    ext = _extent3d(h)
    if ext and ext.get("center"):
        return ext["center"][0], ext["center"][1]
    (x1, y1), (x2, y2) = vs.GetBBox(h)
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def rotate_objects(uuids, angle, center=None):
    """Rotate objects in plan by `angle` degrees (counter-clockwise) about
    `center` (x, y), or about the centre of their combined extents."""
    hs = _handles(uuids)
    if center is None:
        cs = [_plan_center(h) for h in hs]
        center = (sum(c[0] for c in cs) / len(cs), sum(c[1] for c in cs) / len(cs))
    cx, cy = float(center[0]), float(center[1])
    for h in hs:
        vs.HRotate(h, (cx, cy), float(angle))
    return {"document": current_document(), "rotated": len(hs), "center": [cx, cy], "angle": float(angle)}


def duplicate_objects(uuids, dx=0.0, dy=0.0, dz=0.0):
    """Copy objects, offset by (dx, dy, dz). All-or-nothing. Returns the new
    objects' uuids in the order of `uuids`."""
    hs = _handles(uuids)
    made = []
    try:
        for h in hs:
            d = vs.HDuplicate(h, dx, dy)
            if _is_nil(d):
                raise RuntimeError("HDuplicate returned nothing for %s" % h_uuid(h))
            if dz:
                vs.Move3DObj(d, 0, 0, dz)
            made.append(d)
    except Exception:
        for d in made:
            vs.DelObject(d)
        raise
    return {"document": current_document(), "created": [h_uuid(d) for d in made]}


def save_document(path=None):
    """Save the active document in place (File > Save, no dialog when it has
    a file), or under `path` with VSave. An unsaved document needs `path`."""
    current = _str(vs.GetFPathName())
    if path:
        vs.VSave(path)
        return {"document": current_document(), "path": _str(vs.GetFPathName()), "saved_as": path}
    if not current:
        raise ValueError("this document has never been saved; pass path= (Save would open a dialog)")
    vs.DoMenuTextByName("Save", 0)
    return {"document": current_document(), "path": current, "saved_as": None}


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


# ---- sheet layers --------------------------------------------------------------
# Live 2026-11-20 (VW 2026): CreateVP on the active sheet layer, object
# variable 1003 = viewport scale (read back 48.0), 1000 = 6 in Top/Plan.

TITLE_BLOCK = "Title Block Border"
VP_SCALE = 1003


def _attached_records(h):
    """{record name: [field names]} of every record attached to an object."""
    out = {}
    for i in range(1, vs.NumRecords(h) + 1):
        rec = vs.GetRecord(h, i)
        out[_str(vs.GetName(rec))] = [_str(vs.GetFldName(rec, j)) for j in range(1, vs.NumFields(rec) + 1)]
    return out


def create_sheet(name, layers, scale=48.0, hide_classes=None, title_block=None):
    """A sheet layer with one viewport showing the given design layers at
    1:`scale` (Top/Plan, the viewport default), classes in `hide_classes`
    hidden in it, and optionally a Title Block Border whose parameters
    `title_block` ({field: value}) are written to the attached data records
    ("Sheet Title", "Sheet Number" in Title Block Sheet Data, "Project Name"
    in Title Block Project Data). The user's active layer is restored at the end. Deleting the sheet layer
    (revert) removes the viewport and title block with it."""
    kinds = dict((l["name"], l["kind"]) for l in list_layers())
    missing = [l for l in layers if l not in kinds]
    if missing:
        raise LookupError("no such design layer(s): %s" % ", ".join(missing))
    not_design = [l for l in layers if kinds[l] != "design"]
    if not_design:
        raise ValueError("not design layers: %s" % ", ".join(not_design))
    prev = _str(vs.GetLName(vs.ActLayer()))
    create_layer(name, "sheet", activate=True)  # sheet stays active for CreateVP
    sheet = vs.GetLayerByName(name)
    try:
        vp = vs.CreateVP(sheet)
        if _is_nil(vp):
            raise RuntimeError("CreateVP returned nothing on sheet %r" % name)
        for lname, kind in kinds.items():
            if kind != "design":
                continue
            vs.SetVPLayerVisibility(vp, vs.GetLayerByName(lname), 0 if lname in layers else -1)
        for cls in hide_classes or []:
            vs.SetVPClassVisibility(vp, cls, -1)
        vs.SetObjectVariableReal(vp, VP_SCALE, float(scale))
        vs.UpdateVP(vp)
        out = {"document": current_document(), "sheet": name, "viewport": h_uuid(vp),
               "scale": float(scale), "layers_shown": list(layers), "title_block": None}
        if title_block is not None:
            tb = vs.CreateCustomObjectN(TITLE_BLOCK, (0, 0), 0, False)
            if _is_nil(tb):
                out["title_block_error"] = "%r plug-in did not create an object" % TITLE_BLOCK
            else:
                out["title_block"] = set_title_block_fields(h_uuid(tb), title_block)
    finally:
        if prev:
            _activate_layer(prev)
    return out


def set_title_block_fields(uuid, fields):
    """Write title block data. Live 2026-11-20: title/number/project are
    fields of the attached records "Title Block Sheet Data" / "Title Block
    Project Data", not plug-in parameters; each field goes to the record that
    has it. Live 2026-11-25 (VW 2027): those records are attached only after
    the creating job ends, so the tool calls this again in a follow-up job
    when fields_available comes back empty."""
    tb = handle(uuid)
    where = {}
    for rec, names in _attached_records(tb).items():
        if rec == TITLE_BLOCK:
            continue
        for f in names:
            where.setdefault(f, rec)
    done = []
    for k, v in fields.items():
        if k in where:
            vs.SetRField(tb, where[k], k, _str(v))
            done.append(k)
    if done:
        vs.ResetObject(tb)
    return {"uuid": uuid, "fields_set": sorted(done),
            "fields_unknown": sorted(set(fields) - set(done)), "fields_available": sorted(where)}


# ---- view mapping (for screenshots) ---------------------------------------------
# Live 2026-11-20 (VW 2026): GetProjection(ActLayer()) is 6 in Top/Plan;
# ModelPt2DToScreenPt returns model coordinates unchanged, so the server maps
# pixels from zoom, layer scale and the display density instead (viewmap.py).

TOP_PLAN_PROJECTIONS = (6,)


def view_mapping():
    """View centre, zoom (percent), layer scale and units per inch of the
    active layer, for the server's screenshot mapping."""
    cx, cy = vs.GetVCenter()
    layer = vs.ActLayer()
    proj = vs.GetProjection(layer)
    units = vs.GetUnits()
    return {"center": [cx, cy], "zoom": vs.GetZoom(), "layer_scale": vs.GetLScale(layer),
            "units_per_inch": float(units[3]), "projection": proj,
            "top_plan": proj in TOP_PLAN_PROJECTIONS, "units": (units[4] or "").strip(),
            "layer": _str(vs.GetLName(layer))}


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
    before = _symdef_names()
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
    final = _str(vs.GetName(h))
    # Nested symbols (a hoist's hook parts, a fixture's clamp) arrive with the
    # import and stay behind when the main symbol is deleted (live 2026-11-25).
    also = sorted(n for n in _symdef_names() - before if n != final)
    return {"document": current_document(), "name": final,
            "type_code": vs.GetTypeN(h), "also": also}


def _symdef_names():
    return {s["name"] for s in list_symbols(limit=10 ** 7)}


def _delete_resources(names):
    for n in names:
        h = vs.GetObject(n)
        if not _is_nil(h):
            vs.DelObject(h)


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
    length_mm = float(f("Length") or 0)
    if not length_mm and "Truss Record" in record_names(sd):
        # base plates and spindles (live 2026-11-21): Length only in the Truss Record, as "6mm"
        length_mm = _dim_to_mm(_str(vs.GetRField(sd, "Truss Record", "Length")))
    return {"name": f("Name"), "type": f("Type"), "item_type": f("ItemType") or "Line",
            "length_mm": length_mm, "height_mm": float(f("Height") or 0),
            "width_mm": float(f("Width") or 0), "section": f("Section"),
            "connection": f("Connection"), "weight_kg": float(f("Weight") or 0),
            # corners (live 2026-11-21): the piece's local frame has the incoming
            # face ("Low") at the origin along +x; "Center X" is what it takes
            # from each leg; the outgoing face centre is the Bottom point.
            "corner_type": f("CornerType"), "center_mm": float(f("Center X") or 0),
            "bottom_mm": (float(f("Bottom X") or 0), float(f("Bottom Y") or 0)),
            "bottom_valid": f("Bottom Valid") == "True",
            # where the symbol's origin sits relative to its start (Low) face:
            # (0, 0) for the F34 library pieces (live 2026-11-21), so the
            # insertion point is the start, not the centre.
            "low_mm": (float(f("Low X") or 0), float(f("Low Y") or 0))}


def _insertion_for_low(rec, low_pt, heading_deg):
    """Insertion point that puts the piece's Low (start) face at low_pt."""
    import math
    lx, ly = rec["low_mm"][0] * _mm_to_doc(), rec["low_mm"][1] * _mm_to_doc()
    r = math.radians(heading_deg)
    return (low_pt[0] - (lx * math.cos(r) - ly * math.sin(r)),
            low_pt[1] - (lx * math.sin(r) + ly * math.cos(r)))


def _truss_params(rec, symbol, system, prev, position_name, vertical=False):
    params = {
        "Symbol": symbol, "Name": rec["name"], "Type": rec["type"],
        "ItemType": rec["item_type"], "CrossSection": rec["section"],
        "ConnectionIdent": rec["connection"],
        "Length": "%gmm" % rec["length_mm"], "Height": "%gmm" % rec["height_mm"],
        "Width": "%gmm" % rec["width_mm"],
        "TrussSystem": system, "TrussLine": "1", "TrussSystemLineIdent": system + "-1",
        "C_START_UUID": prev, "PositionName": position_name or "",
    }
    if rec["item_type"] == "Corner" and rec["corner_type"]:
        params["CornerType"] = rec["corner_type"]
    if vertical:
        params["Vertical"] = "True"  # stands the piece up on its insertion point (live 2026-11-21)
    if rec["weight_kg"]:
        params["Weight"] = "%g" % (rec["weight_kg"] * 1000)  # grams, as Insert Truss stores it
        if rec["length_mm"]:
            params["Distributed weight"] = "%g" % (rec["weight_kg"] / (rec["length_mm"] / 1000.0))
    return params


def _place_truss_item(rec, symbol, pt, rotation, z, system, prev, position_name, vertical=False):
    h = vs.CreateCustomObjectN("TrussItem", pt, rotation, False)
    if _is_nil(h):
        raise RuntimeError("TrussItem plug-in did not create a piece")
    _write_fields(h, "TrussItem", _truss_params(rec, symbol, system, prev, position_name, vertical))
    if z:
        vs.Move3DObj(h, 0, 0, z)
    return h


@_keep_selection
def insert_truss_path(straight, corner, path, z=0.0, position_name=None, layer=None,
                      truss_system=None, library_path=None, fit="start"):
    """Straight pieces along every leg of `path` (document units) with a
    corner piece at every interior vertex, all chained into one system.
    Each leg takes whole pieces; the leftover `gap` sits at the leg's end
    (fit "start"), its start ("end") or is split between both ("center").
    All-or-nothing."""
    import math
    if len(path) < 2:
        raise ValueError("path needs at least two points")
    if fit not in ("start", "center", "end"):
        raise ValueError("fit must be start, center or end")
    imported, also = [], []
    for sym in (straight, corner):
        if _is_nil(vs.GetObject(sym)) and library_path:
            r = import_resource(library_path, sym)
            imported.append(r["name"])
            also.extend(r["also"])
    srec, crec = _truss_record(straight), _truss_record(corner)
    if srec["length_mm"] <= 0:
        raise ValueError("%s on %r has no Length" % (BRX, straight))
    if crec["item_type"] != "Corner" or not crec["bottom_valid"]:
        raise ValueError("%r is not a corner piece (ItemType %r)" % (corner, crec["item_type"]))
    to_doc = _mm_to_doc()
    piece = srec["length_mm"] * to_doc
    take = crec["center_mm"] * to_doc  # what the corner takes from each leg at a vertex
    bx, by = crec["bottom_mm"]
    turn_deg = math.degrees(math.atan2(by, bx - crec["center_mm"]))  # negative: the piece turns right
    pts = [(float(x), float(y)) for x, y in path]
    legs = []
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        length = math.hypot(x1 - x0, y1 - y0)
        if length <= 0:
            raise ValueError("path points %d and %d coincide" % (i, i + 1))
        legs.append({"heading": math.degrees(math.atan2(y1 - y0, x1 - x0)), "length": length})
    turns = []
    for i in range(len(legs) - 1):
        d = (legs[i + 1]["heading"] - legs[i]["heading"] + 180) % 360 - 180
        if abs(abs(d) - abs(turn_deg)) > 1.0:
            raise ValueError("the path turns %.1f degrees at point %d but %r turns %.0f degrees"
                             % (d, i + 1, corner, abs(turn_deg)))
        turns.append("left" if d > 0 else "right")
    for i, leg in enumerate(legs):
        leg["available"] = leg["length"] - (take if i > 0 else 0) - (take if i < len(legs) - 1 else 0)
        if leg["available"] < piece:
            raise ValueError("leg %d is too short for one %s piece after the corners (%.1f available)"
                             % (i + 1, straight, leg["available"]))
    if layer:
        _activate_layer(layer)
    system = truss_system or _next_truss_system()
    created, prev = [], ""
    out_legs = []
    try:
        for i, leg in enumerate(legs):
            rad = math.radians(leg["heading"])
            ux, uy = math.cos(rad), math.sin(rad)
            sx, sy = pts[i]
            if i > 0:
                sx, sy = sx + ux * take, sy + uy * take
            n = int(leg["available"] // piece + 1e-9)
            slack = leg["available"] - piece * n
            if fit != "start":
                shift = slack / 2.0 if fit == "center" else slack
                sx, sy = sx + ux * shift, sy + uy * shift
            for k in range(n):
                along = piece * k
                pt = _insertion_for_low(srec, (sx + ux * along, sy + uy * along), leg["heading"])
                h = _place_truss_item(srec, straight, pt, leg["heading"], z, system, prev, position_name)
                created.append(h)
                prev = h_uuid(h)
            end = (sx + ux * piece * n, sy + uy * piece * n)
            out_legs.append({"pieces": n, "length": leg["length"], "gap": slack,
                             "turn": turns[i] if i < len(turns) else None})
            if i < len(turns):
                vx, vy = pts[i + 1]
                if turns[i] == "right":
                    # enter through the Low face at the leg's end, heading along the leg
                    rot = leg["heading"]
                    pt = _insertion_for_low(crec, (vx - ux * take, vy - uy * take), rot)
                else:
                    # enter through the Bottom face, leave through Low: rotate so local +y is the heading
                    rot = leg["heading"] - 90.0
                    rr = math.radians(rot)
                    lx, ly = take, -take
                    low_x = vx + math.cos(math.radians(legs[i + 1]["heading"])) * take
                    low_y = vy + math.sin(math.radians(legs[i + 1]["heading"])) * take
                    pt = _insertion_for_low(crec, (low_x, low_y), rot)
                    # check: Bottom = Low + R(rot)(take, -take) must be the incoming leg's end
                    bxw = low_x + lx * math.cos(rr) - ly * math.sin(rr)
                    byw = low_y + lx * math.sin(rr) + ly * math.cos(rr)
                    if math.hypot(bxw - (vx - ux * take), byw - (vy - uy * take)) > 1e-6 * max(1.0, take):
                        raise RuntimeError("corner geometry does not close at point %d" % (i + 1))
                h = _place_truss_item(crec, corner, pt, rot, z, system, prev, position_name)
                created.append(h)
                prev = h_uuid(h)
    except Exception:
        for h in created:
            vs.DelObject(h)
        _delete_resources(imported + also)
        raise
    return {"document": current_document(), "system": system, "piece_length": piece,
            "straights": sum(leg["pieces"] for leg in out_legs), "corners": len(turns),
            "legs": out_legs, "imported": imported, "imported_also": also,
            "items": [{"uuid": h_uuid(h)} for h in created]}


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


@_keep_selection
def insert_truss_run(symbol, x, y, count, rotation=0.0, z=0.0, position_name=None,
                     layer=None, truss_system=None, library_path=None,
                     vertical=False, base_symbol=None, top_symbol=None):
    """Place `count` straight truss pieces end to end from (x, y), heading along
    `rotation` degrees, raised by z. vertical: stack them upward from (x, y, z)
    instead (a tower), optionally on a base plate symbol and under a top
    piece (spindle), each a TrussItem of its own. All-or-nothing."""
    import math
    if count < 1:
        raise ValueError("count must be at least 1")
    imported, also = None, []
    if _is_nil(vs.GetObject(symbol)) and library_path:
        r = import_resource(library_path, symbol)
        imported, also = r["name"], r["also"]
    rec = _truss_record(symbol)
    if rec["length_mm"] <= 0:
        raise ValueError("%s on %r has no Length" % (BRX, symbol))
    length = rec["length_mm"] * _mm_to_doc()
    if layer:
        _activate_layer(layer)
    system = truss_system or _next_truss_system()
    if vertical:
        return _insert_tower(symbol, rec, x, y, count, z, position_name, system, base_symbol, top_symbol,
                             imported, also)
    rad = math.radians(rotation)
    dx, dy = math.cos(rad), math.sin(rad)
    created, prev = [], ""
    try:
        for i in range(count):
            along = length * i  # the piece's start face lands here
            pt = _insertion_for_low(rec, (x + dx * along, y + dy * along), rotation)
            h = _place_truss_item(rec, symbol, pt, rotation, z, system, prev, position_name)  # class: 2nd job
            created.append(h)
            prev = h_uuid(h)
    except Exception:
        for h in created:
            vs.DelObject(h)
        _delete_resources(([imported] if imported else []) + also)
        raise
    pieces = [obj_info(h) for h in created]
    return {"document": current_document(), "system": system, "piece_length": length,
            "total_length": length * count, "imported": imported, "imported_also": also, "vertical": False,
            "pieces": [{"uuid": p["uuid"], "bbox": p["bbox"]} for p in pieces]}


def _insert_tower(symbol, rec, x, y, count, z, position_name, system, base_symbol, top_symbol, imported,
                  also=()):
    """Vertical pieces stacked at (x, y) from z: base plate, `count` straights,
    top piece; every piece's Low face sits on the previous piece's end."""
    to_doc = _mm_to_doc()
    stack = []
    if base_symbol:
        stack.append((base_symbol, _truss_record(base_symbol)))
    stack += [(symbol, rec)] * count
    if top_symbol:
        stack.append((top_symbol, _truss_record(top_symbol)))
    created, prev, level = [], "", z
    rows = []
    # A straight lies along +x with its cross-section at z 0..Height; rotating it
    # -90 degrees about y through its foot stands it up with the section at
    # x -Height..0. Base plates and spindles are centred at x = +Height/2, so
    # the standing pieces are placed one truss height along +x to share that
    # footprint (live 2026-11-21: Michael's zoomed capture showed the spindle
    # beside the column before this).
    shift = rec["height_mm"] * to_doc
    try:
        for sym, r in stack:
            pt = (x + shift, y) if r is rec else (x, y)
            h = _place_truss_item(r, sym, pt, 0.0, level, system, prev, position_name, vertical=True)
            created.append(h)
            if r is rec:
                # Vertical=True is bookkeeping only; the rotation stands the piece up
                # (seen by Michael) and survives the reset.
                vs.Set3DRot(h, 0, -90, 0, pt[0], pt[1], level)
                vs.ResetObject(h)
            prev = h_uuid(h)
            rows.append({"uuid": prev, "symbol": sym, "z": level})
            level += r["length_mm"] * to_doc
    except Exception:
        for h in created:
            vs.DelObject(h)
        _delete_resources(([imported] if imported else []) + list(also))
        raise
    return {"document": current_document(), "system": system, "piece_length": rec["length_mm"] * to_doc,
            "total_length": rec["length_mm"] * to_doc * count, "total_height": level - z,
            "imported": imported, "imported_also": list(also), "vertical": True, "pieces": rows}


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


def _dim_to_mm(text):
    """A dimension string ("12 m", "39'4\"", "15000 mm", or a number in
    document units) as millimetres."""
    return _dim_to_doc(text) / _mm_to_doc()


HOIST = "BrxHoist"
HOIST_DATA = "HoistObjectData"


def _hoist_symbol_data(symbol):
    """The hoist symbol's HoistObjectData record (what the Hoist tool copies
    into a new BrxHoist; read live 2026-11-21 on VW 2026)."""
    sd = vs.GetObject(symbol)
    if _is_nil(sd):
        raise LookupError("no symbol %r in the document (vw_import_resource it first)" % symbol)
    if HOIST_DATA not in record_names(sd):
        raise ValueError("%r has no %s record; it is not a hoist symbol" % (symbol, HOIST_DATA))
    f = lambda k: _str(vs.GetRField(sd, HOIST_DATA, k))  # noqa: E731
    return {"Capacity": f("Capacity"), "ChainWt": f("ChainWt"), "HoistWt": f("HoistWt"),
            "Voltage": f("Voltage"), "Phasing": f("Phasing"), "Speed": f("Speed"),
            "MotorHeight": f("MotorHeight"), "Connector": f("Connector"),
            "ControlType": f("Control Type"), "MaxChainLength": f("ChainLength"),
            "Function": f("Function"), "direction": f("Motor up or down")}


@_keep_selection
def insert_hoists(symbol, points, height_mm, ids, location=None, function=None,
                  hoist_pos="up", layer=None, notes=None):
    """One BrxHoist per point (document units), hook at height_mm above the
    low point, data copied from the symbol's HoistObjectData. All-or-nothing."""
    data = _hoist_symbol_data(symbol)
    if layer:
        _activate_layer(layer)
    created = []
    try:
        for (x, y), hid in zip(points, ids):
            h = vs.CreateCustomObjectN(HOIST, (x, y), 0, False)
            if _is_nil(h):
                raise RuntimeError("%s plug-in did not create a hoist" % HOIST)
            created.append(h)
            params = {
                "HoistID": hid, "HoistName": symbol, "SymbolUsed": symbol,
                "Location": location or "", "Function": function or data["Function"],
                "HoistPos": "Hoist Down" if hoist_pos == "down" else "Hoist Up",
                "DistanceFromLow": "%g" % height_mm,
            }
            for k in ("Capacity", "ChainWt", "HoistWt", "Voltage", "Phasing", "Speed",
                      "MotorHeight", "Connector", "ControlType"):
                if data[k]:
                    params[k] = data[k]
            if data["MaxChainLength"]:  # a dimension field: document units (live 2026-11-21)
                params["MaxChainLength"] = "%g" % (float(data["MaxChainLength"]) * _mm_to_doc())
            if notes:
                params["Notes"] = notes
            _write_fields(h, HOIST, params)  # class: see create_pio, applied in a 2nd job
    except Exception:
        for h in created:
            vs.DelObject(h)
        raise
    rows = []
    for h, hid in zip(created, ids):
        x, y = vs.GetSymLoc(h)
        rows.append({"uuid": h_uuid(h), "id": hid, "x": x, "y": y})
    # Derived fields (hook height, chain, weight) only exist after the reset,
    # which runs when this job ends: read them with list_hoists.
    return {"document": current_document(), "symbol": symbol, "count": len(rows), "hoists": rows}


def list_hoists(location=None, layer=None):
    """Every BrxHoist with the fields rigging paperwork needs."""
    rows = []

    def each(h):
        if pio_name(h) != HOIST:
            return
        f = lambda k: _str(vs.GetRField(h, HOIST, k))  # noqa: E731
        info = obj_info(h)
        if layer and info["layer"] != layer:
            return
        if location is not None and f("Location").casefold() != location.casefold():
            return
        x, y = vs.GetSymLoc(h)  # the insertion point (the bbox centre is off: live 2026-11-21)
        rows.append({
            "uuid": info["uuid"], "id": f("HoistID"), "symbol": f("HoistName"),
            "location": f("Location"), "function": f("Function"),
            "direction": "down" if "Down" in f("HoistPos") else "up",
            "capacity_kg": float(f("Capacity") or 0) / 1000.0,
            "hook_height_mm": float(f("DistanceFromLow") or 0),
            "hook_height": f("HiHook_formated"),
            "weight_with_chain": f("WeightWithChain_formated"),
            "truss_system_top": f("TrussSysTop"), "truss_system_bottom": f("TrussSysBottom"),
            "notes": f("Notes"), "class": info["class"], "layer": info["layer"],
            "x": x, "y": y,
        })

    vs.ForEachObject(each, "(T=86)")
    rows.sort(key=lambda r: (r["location"], r["id"]))
    return {"count": len(rows), "total_capacity_kg": sum(r["capacity_kg"] for r in rows), "hoists": rows}


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
    imported, also = None, []
    if _is_nil(vs.GetObject(symbol)) and library_path:
        r = import_resource(library_path, symbol)
        imported, also = r["name"], r["also"]
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
        _delete_resources(([imported] if imported else []) + also)
        _restore_selection(previous)
        raise
    _restore_selection(previous)
    return {"document": current_document(), "imported": imported, "imported_also": also, "z": z,
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


@_keep_selection
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


def refresh_objects(uuids):
    """Reset new plug-in objects and repaint. Live 2026-11-25 (VW 2027): a
    plug-in object created by a job has its geometry at the end of that job
    but is not painted until a ResetObject in a LATER job; ReDrawAll alone in
    a later job does not paint it either. Missing objects are skipped."""
    n = 0
    for u in uuids:
        h = vs.GetObjectByUuid(u)
        if not _is_nil(h) and vs.GetTypeN(h) == 86:
            vs.ResetObject(h)
            n += 1
    vs.ReDrawAll()
    return {"reset": n}


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


@_keep_selection
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


@_keep_selection
def insert_platform(width, depth, height, x, y, columns=1, rows=1, rotation=0.0,
                    structure="Legs-Basic", purpose=None, position=None, layer=None, steps=None):
    """Decks (insert_stage_decks) plus, if `steps` is given, one flight of
    Stage Steps at steps["x"], steps["y"], steps["rotation"] (the server
    computes the edge midpoint) with the other insert_stage_steps keys.
    All-or-nothing: a failing flight removes the decks again."""
    decks = insert_stage_decks(width, depth, height, x, y, columns=columns, rows=rows,
                               rotation=rotation, structure=structure, purpose=purpose,
                               position=position, layer=layer)
    flight = None
    if steps:
        try:
            flight = insert_stage_steps(steps["x"], steps["y"], height, rotation=steps["rotation"],
                                        tread_width=steps.get("tread_width"), steps=steps.get("steps"),
                                        kind=steps.get("kind", "Self-Adjusting"),
                                        rail_left=steps.get("rail_left", False),
                                        rail_right=steps.get("rail_right", False),
                                        purpose=purpose, position=position, layer=layer)
        except Exception:
            for d in decks["decks"]:
                vs.DelObject(handle(d["uuid"]))
            raise
        flight.pop("document", None)
    return {"document": decks["document"], "decks": decks["decks"], "footprint": decks["footprint"],
            "steps": flight}


RAMP = "Stage Ramp"
RAMP_TYPES = ["Legs", "Solid", "Simple"]


@_keep_selection
def insert_stage_ramp(x, y, stage_height, rotation=0.0, tread_width=None, ramp_length=None,
                      pitch_angle=None, kind="Legs", rail_left=False, rail_right=False,
                      arrow=False, purpose=None, position=None, layer=None):
    """One Stage Ramp down from a stage edge at (x, y) (top centre of the
    ramp), descending away from the stage like Stage Steps (rotation 0:
    stage is +y, ramp goes -y). Give ramp_length (along the slope) or
    pitch_angle (degrees); dimensions in document units."""
    if stage_height <= 0:
        raise ValueError("stage_height must be positive")
    if kind not in RAMP_TYPES:
        raise ValueError("kind must be one of %s" % ", ".join(RAMP_TYPES))
    if (ramp_length is None) == (pitch_angle is None):
        raise ValueError("give either ramp_length or pitch_angle")
    if ramp_length is not None and ramp_length <= stage_height:
        raise ValueError("ramp_length must be longer than stage_height")
    if pitch_angle is not None and not 0 < pitch_angle < 90:
        raise ValueError("pitch_angle must be between 0 and 90 degrees")
    if layer:
        _activate_layer(layer)
    params = {"Type": kind, "Stageheight": "%gmm" % _doc_to_mm(stage_height),
              "RailLeft": "True" if rail_left else "False",
              "RailRight": "True" if rail_right else "False",
              "DrawArrow": "Down" if arrow else "None"}
    if ramp_length is not None:
        params["BuildMethod"] = "Ramp Length"
        params["RampLength"] = "%gmm" % _doc_to_mm(ramp_length)
    else:
        params["BuildMethod"] = "Pitch Angle"
        params["PitchAngVar"] = "%g" % pitch_angle
    if tread_width:
        params["Treadwidth"] = "%gmm" % _doc_to_mm(tread_width)
    if purpose:
        params["Purpose"] = purpose
    if position:
        params["Position"] = position
    h = vs.CreateCustomObjectN(RAMP, (x, y), rotation, False)
    if _is_nil(h):
        raise RuntimeError("Stage Ramp plug-in did not create an object")
    try:
        _write_fields(h, RAMP, params)  # class: see create_pio, applied in a 2nd job
    except Exception:
        vs.DelObject(h)
        raise
    return {"document": current_document(), "uuid": h_uuid(h)}


# ---- soft goods ------------------------------------------------------------------
# Spotlight's Soft Goods plug-in is a *path* object: a curtain, truss border
# or pipe-and-drape run along a polyline. Field names and popup choices from
# the .vso string table (vs-notes "Parameter names"); creation call not yet
# run live (2026-11-20).

SOFT_GOODS = "Soft Goods"
SOFT_GOODS_FUNCTIONS = ["Curtain", "Truss Border", "Pipe-and-Drape"]


def _open_polyline(points):
    """An open polyline through `points` ([x, y] pairs, document units)."""
    vs.OpenPoly()
    try:
        vs.BeginPoly()
        for x, y in points:
            vs.AddPoint((x, y))
        vs.EndPoly()
    finally:
        vs.ClosePoly()  # back to the default for later polys
    h = vs.LNewObj()
    if _is_nil(h):
        raise RuntimeError("could not create the path polyline")
    return h


@_keep_selection
def insert_soft_goods(points, height, function="Curtain", opening_width=None, open_from=None,
                      traveler=False, add_pipe=False, add_track=False, purpose=None,
                      position=None, layer=None):
    """A Soft Goods run (curtain, truss border or pipe-and-drape) along the
    open polyline through `points` (at least two [x, y], document units),
    `height` tall. The path polyline becomes the plug-in's path."""
    if len(points) < 2:
        raise ValueError("points needs at least two [x, y] pairs")
    if height <= 0:
        raise ValueError("height must be positive")
    if function not in SOFT_GOODS_FUNCTIONS:
        raise ValueError("function must be one of %s" % ", ".join(SOFT_GOODS_FUNCTIONS))
    if opening_width is not None and opening_width <= 0:
        raise ValueError("opening_width must be positive")
    if layer:
        _activate_layer(layer)
    params = {"GdsFunct": function, "CurtHeight": "%gmm" % _doc_to_mm(height),
              "Traveler": "True" if traveler else "False",
              "AddPipe": "True" if add_pipe else "False",
              "AddTrack": "True" if add_track else "False"}
    if opening_width is not None:
        params["OpenWidth"] = "%gmm" % _doc_to_mm(opening_width)
    if open_from:
        params["OpenFrom"] = open_from
    if purpose:
        params["Purpose"] = purpose
    if position:
        params["Position"] = position
    # Live 2026-11-20: CreateCustomObjectPath opened the plug-in's "Object
    # Preferences" dialog (no showPref flag), holding the job until the user
    # clicked OK; the path was consumed and the height applied. So create the
    # object silently with CreateCustomObjectN(..., False) and attach the path.
    h = vs.CreateCustomObjectN(SOFT_GOODS, (points[0][0], points[0][1]), 0, False)
    if _is_nil(h):
        raise RuntimeError("Soft Goods plug-in did not create an object")
    try:
        path = _open_polyline(points)
        vs.SetCustomObjectPath(h, path)
        _write_fields(h, SOFT_GOODS, params)  # class: see create_pio, applied in a 2nd job
    except Exception:
        vs.DelObject(h)
        raise
    length = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        length += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    return {"document": current_document(), "uuid": h_uuid(h), "path_length": length}


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
