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
    for k, v in values.items():
        vs.SetRField(h, record, k, _str(v))
    if vs.GetTypeN(h) == 86:
        vs.ResetObject(h)
    return get_record(uuid, record)


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
        if _is_nil(vs.GetLayerByName(layer)):
            raise LookupError("no layer named %r" % layer)
        vs.Layer(layer)
    vs.Symbol(name, (x, y), rotation)
    h = vs.LNewObj()
    if cls:
        vs.SetClass(h, cls)
    if z is not None:
        vs.Move3DObj(h, 0, 0, z - vs.GetSymLoc3D(h)[2])
    return obj_info(h)
