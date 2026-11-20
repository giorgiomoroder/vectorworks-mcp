"""New drawing tools: journal ops (FakeVW) and vwlib round trips (fake vs)."""

import threading

import pytest
import vwmcp_bridge
from mcp.server.mcpserver.exceptions import ToolError

from vwmcp import app
from vwmcp.client import Bridge
from vwmcp.journal import Journal
from vwmcp.tools import drawing, generic


# ---- journal-level ------------------------------------------------------------

class FakeVW:
    def __init__(self):
        self.calls, self.document = [], "Plot.vwx"

    def __call__(self, fn, **kw):
        self.calls.append((fn, kw))
        doc = {"document": self.document}
        canned = {
            "import_resource": lambda: {**doc, "name": kw.get("new_name") or kw["name"], "type_code": 16},
            "create_pio": lambda: {**doc, "uuid": "pio-1", "type": "Plug-in Object", "plugin": kw["plugin"]},
            "set_pio_parameters": lambda: {**doc, "before": {"Channel": "1"}, "record": "Lighting Device"},
            "get_record": lambda: {"Channel": "7"},
            "create_layer": lambda: {**doc, "name": kw["name"], "kind": kw["kind"], "active": False},
            "create_class": lambda: {**doc, "name": kw["name"]},
            "delete_objects": lambda: {**doc, "deleted": len(kw["uuids"])},
            "move_objects": lambda: {**doc, "moved": len(kw["uuids"])},
            "set_view": lambda: {"view": kw["view"], "fit": kw["fit"]},
            "set_objects_class": lambda: {**doc, "before": ["None"] * len(kw["uuids"])},
            "current_document": lambda: self.document,
            "revert": lambda: {**doc, "restored": 0, "deleted": 0, "moved": 0, "missing": []},
        }
        return canned[fn]()


@pytest.fixture
def fake(tmp_path, monkeypatch):
    f = FakeVW()
    for mod in (app, generic, drawing):
        monkeypatch.setattr(mod, "vw", f)
    monkeypatch.setattr(app, "get_journal", lambda: Journal(tmp_path / "j.jsonl"))
    return f


def last_revert_ops(fake):
    fn, kw = fake.calls[-1]
    assert fn == "revert"
    return kw["ops"]


def test_import_resource_reverts_by_name(fake):
    out = drawing.vw_import_resource("/lib/Truss.vwx", "Tomcat 12", new_name="Tomcat copy")
    assert out == {"name": "Tomcat copy", "type_code": 16}
    generic.vw_revert_last()
    assert last_revert_ops(fake) == [{"op": "resource", "name": "Tomcat copy"}]


def test_create_pio_reverts_created_uuid(fake):
    out = drawing.vw_create_pio("Truss", 0, 0, parameters={"Length": "10'"})
    assert out["uuid"] == "pio-1" and "document" not in out
    assert fake.calls[0][1]["parameters"] == {"Length": "10'"}
    generic.vw_revert_last()
    assert last_revert_ops(fake) == [{"op": "created", "uuid": "pio-1"}]


def test_set_pio_parameters_reports_after_and_reverts_fields(fake):
    out = drawing.vw_set_pio_parameters("ld-1", {"Channel": "7"})
    assert out == {"uuid": "ld-1", "plugin": "Lighting Device", "after": {"Channel": "7"}}
    generic.vw_revert_last()
    assert last_revert_ops(fake) == [
        {"op": "fields", "uuid": "ld-1", "record": "Lighting Device", "before": {"Channel": "1"}}
    ]


def test_layer_and_class_revert_by_name(fake):
    drawing.vw_create_layer("Truss", scale=48)
    drawing.vw_create_class("Lighting-Truss")
    generic.vw_revert_last()
    assert last_revert_ops(fake) == [{"op": "class", "name": "Lighting-Truss"}]
    generic.vw_revert_last()
    assert last_revert_ops(fake) == [{"op": "layer", "name": "Truss"}]


def test_move_reverts_with_negated_offsets(fake):
    drawing.vw_move_objects(["a", "b"], dx=1, dy=-2, dz=3)
    generic.vw_revert_last()
    assert last_revert_ops(fake) == [
        {"op": "move", "uuid": "a", "dx": 1, "dy": -2, "dz": 3},
        {"op": "move", "uuid": "b", "dx": 1, "dy": -2, "dz": 3},
    ]


def test_delete_is_a_revert_barrier_and_needs_uuids(fake):
    with pytest.raises(ToolError, match="no uuids"):
        drawing.vw_delete_objects([])
    assert drawing.vw_delete_objects(["a"]) == {"deleted": 1}
    with pytest.raises(ToolError, match="vw_delete_objects"):
        generic.vw_revert_last()


def test_set_view_is_not_journaled(fake, tmp_path):
    assert drawing.vw_set_view("iso", fit=True) == {"view": "iso", "fit": True}
    with pytest.raises(ToolError, match="nothing to revert"):
        generic.vw_revert_last()


# ---- vwlib round trips through the real bridge with a fake vs -----------------

class FakeDoc:
    """Just enough of `vs` for the new helpers. Handles are ints."""

    def __init__(self, vs):
        self.objects = {}  # handle -> dict(type, uuid, name, class, layer, x, y, z, pio, fields)
        self.layers = {"Design-1": 1}
        self.active_layer = "Design-1"
        self.classes = ["None", "Dimension", "Truss", "Lighting-Truss"]
        self.active_class = "None"
        self.resources = {"Tomcat 12": 50}  # name -> handle (symbol defs in document)
        self.library = {"/lib/Truss.vwx": ["Tomcat 12", "Tomcat 20"]}
        self.events = []
        self.next = 100
        v = vs
        v.GetFName = lambda: "Plot.vwx"
        v.GetObjectUuid = lambda h: self.objects[h]["uuid"]
        v.GetObjectByUuid = lambda u: next((h for h, o in self.objects.items() if o["uuid"] == u), 0)
        v.GetTypeN = lambda h: self.objects[h]["type"] if h in self.objects else (16 if h in self.resources.values() else 0)
        v.GetName = lambda h: h[1] if isinstance(h, tuple) else next(
            (n for n, hh in self.resources.items() if hh == h), self.objects.get(h, {}).get("name", "none"))
        v.GetObject = lambda name: self.resources.get(name, 0)
        v.GetClass = lambda h: self.objects[h]["class"]
        v.SetClass = lambda h, c: self.objects[h].__setitem__("class", c)
        v.GetLayer = lambda h: self.layers[self.objects[h]["layer"]]
        v.GetLName = lambda lh: next(n for n, hh in self.layers.items() if hh == lh)
        v.GetBBox = lambda h: ((0, 0), (1, 1))
        v.ForEachObject = lambda fn, crit: [fn(hh) for hh in list(self.objects)]
        v.NumRecords = lambda h: 0
        v.GetParametricRecord = lambda h: ("rec", self.objects[h]["pio"]) if self.objects[h]["pio"] else 0
        v.NumFields = lambda rec: len(PIO_FIELDS[rec[1]])
        v.GetFldName = lambda rec, i: PIO_FIELDS[rec[1]][i - 1]
        v.GetRField = lambda h, rec, f: self.objects[h]["fields"].get(f, "")
        v.SetRField = lambda h, rec, f, val: self.objects[h]["fields"].__setitem__(f, val)
        v.ResetObject = lambda h: self.events.append(("reset", h))
        v.DelObject = lambda h: self._delete(h)
        v.HMove = lambda h, dx, dy: self._move(h, dx, dy, 0)
        v.Move3DObj = lambda h, dx, dy, dz: self._move(h, dx, dy, dz)
        # layers / classes
        v.GetLayerByName = lambda n: self.layers.get(n, 0)
        v.ActLayer = lambda: self.layers[self.active_layer]
        v.CreateLayer = lambda n, t: self._create_layer(n, t)
        v.SetLScale = lambda lh, s: self.events.append(("scale", lh, s))
        v.SetActiveLayerN = lambda lh: setattr(self, "active_layer", v.GetLName(lh))
        v.Layer = lambda n: self.events.append(("vs.Layer!", n))
        v.ClassNum = lambda: len(self.classes)
        v.ClassList = lambda i: self.classes[i - 1]
        v.ActiveClass = lambda: self.active_class
        v.NameClass = lambda n: (self.classes.append(n) if n not in self.classes else None) or setattr(self, "active_class", n)
        v.DelClass = lambda n: self.classes.remove(n)
        # views
        v.SetViewVector = lambda loc, target, up: self.events.append(("view", loc, up))
        v.DoMenuTextByName = lambda name, chunk: self.events.append(("menu", name))
        v.ReDrawAll = lambda: None
        # libraries
        v.BuildResourceListN = lambda t, path: ((t, path), len(self.library[path]))
        v.GetNameFromResourceList = lambda lid, i: self.library[lid[1]][i - 1]
        v.ImportResourceToCurrentFile = lambda lid, i: self._import(self.library[lid[1]][i - 1])
        v.SetName = lambda h, n: self._rename(h, n)
        # PIO creation
        v.CreateCustomObjectN = lambda name, pt, rot, pref: self._create(86, pio=name, x=pt[0], y=pt[1]) if name in PIO_FIELDS else 0
        v.Symbol = lambda name, pt, rot: self._create(15, name=name, x=pt[0], y=pt[1])
        v.LNewObj = lambda: max(self.objects)
        # path plug-ins (Soft Goods): the polyline becomes the object's path
        v.OpenPoly = lambda: self.events.append(("openpoly",))
        v.ClosePoly = lambda: self.events.append(("closepoly",))
        v.BeginPoly = lambda: setattr(self, "poly", [])
        v.AddPoint = lambda p: self.poly.append(list(p))
        v.EndPoly = lambda: self._create(21, points=self.poly, x=self.poly[0][0], y=self.poly[0][1])
        v.CreateCustomObjectPath = lambda name, path, prof: self._path_pio(name, path)
        v.SetCustomObjectPath = lambda h, path: self._set_path(h, path)

    def _create(self, t, **kw):
        h = self.next
        self.next += 1
        o = {"type": t, "uuid": "u%d" % h, "name": "none", "class": "None", "layer": self.active_layer,
             "x": 0, "y": 0, "z": 0, "pio": None, "fields": {}}
        o.update(kw)
        if o["pio"]:
            o["fields"] = {f: "" for f in PIO_FIELDS[o["pio"]]}
        self.objects[h] = o
        return h

    def _path_pio(self, name, path):
        if name not in PIO_FIELDS or path not in self.objects:
            return 0
        pts = self.objects.pop(path)["points"]
        return self._create(86, pio=name, path=pts, x=pts[0][0], y=pts[0][1])

    def _set_path(self, h, path):
        pts = self.objects.pop(path)["points"]
        self.objects[h]["path"] = pts
        return True

    def _delete(self, h):
        self.events.append(("del", h))
        self.objects.pop(h, None)
        for name, hh in list(self.resources.items()):
            if hh == h:
                del self.resources[name]
        for name, lh in list(self.layers.items()):
            if lh == h:
                del self.layers[name]

    def _move(self, h, dx, dy, dz):
        o = self.objects[h]
        o["x"] += dx; o["y"] += dy; o["z"] += dz

    def _create_layer(self, n, t):
        self.layers[n] = lh = self.next
        self.next += 1
        self.active_layer = n
        return lh

    def _import(self, name):
        h = self.next
        self.next += 1
        self.resources[name] = h
        return h

    def _rename(self, h, n):
        for name, hh in list(self.resources.items()):
            if hh == h:
                del self.resources[name]
                self.resources[n] = h


PIO_FIELDS = {"Truss": ["Length", "Truss Type"], "Lighting Device": ["Channel", "Purpose"]}


class Runner:
    def __init__(self, root, vs):
        self.root, self.vs = root, vs

    def __call__(self):
        threading.Thread(target=vwmcp_bridge.run_pending, args=(self.root,), kwargs={"vs_module": self.vs}).start()


@pytest.fixture
def doc(fake_vs, root, tmp_path, monkeypatch):
    d = FakeDoc(fake_vs)
    b = Bridge(root=root, trigger=Runner(root, fake_vs), poll_interval=0.01, timeout=2)
    monkeypatch.setattr(app, "get_bridge", lambda: b)
    monkeypatch.setattr(app, "get_journal", lambda: Journal(tmp_path / "journal.jsonl"))
    return d


def test_create_layer_restores_active_layer_without_vs_layer(doc):
    out = drawing.vw_create_layer("Truss", scale=48)
    assert out == {"name": "Truss", "kind": "design", "active": False}
    assert "Truss" in doc.layers and doc.active_layer == "Design-1"
    assert ("scale", doc.layers["Truss"], 48.0) in doc.events
    assert not any(e[0] == "vs.Layer!" for e in doc.events)
    with pytest.raises(ToolError, match="already exists"):
        drawing.vw_create_layer("Truss")
    lh = doc.layers["Truss"]
    assert generic.vw_revert_last()["deleted"] == 1
    assert ("del", lh) in doc.events and "Truss" not in doc.layers


def test_create_class_keeps_active_class_and_reverts(doc):
    drawing.vw_create_class("MCP-Test")
    assert "MCP-Test" in doc.classes and doc.active_class == "None"
    generic.vw_revert_last()
    assert "MCP-Test" not in doc.classes


def test_create_pio_sets_parameters_and_reverts(doc, tmp_path):
    out = drawing.vw_create_pio("Truss", 1, 2, parameters={"Length": "10"}, class_name="Lighting-Truss")
    h = doc.objects and max(doc.objects)
    assert out["plugin"] == "Truss" and out["class"] == "Lighting-Truss"
    assert doc.objects[h]["class"] == "Lighting-Truss"  # applied by the second job
    assert doc.objects[h]["fields"]["Length"] == "10" and ("reset", h) in doc.events
    assert drawing.vw_get_pio_parameters(out["uuid"]) == {"plugin": "Truss", "fields": {"Length": "10", "Truss Type": ""}}
    generic.vw_revert_last()
    assert h not in doc.objects


def test_create_pio_with_bad_parameter_places_nothing(doc):
    with pytest.raises(ToolError, match="unknown field"):
        drawing.vw_create_pio("Truss", 0, 0, parameters={"Lenght": "10"})
    assert doc.objects == {}


def test_create_pio_unknown_plugin(doc):
    with pytest.raises(ToolError, match="not available"):
        drawing.vw_create_pio("Flying Pig", 0, 0)


def test_create_pio_unknown_class_leaves_object_but_errors(doc):
    with pytest.raises(ToolError, match="no class named"):
        drawing.vw_create_pio("Truss", 0, 0, class_name="Nope")
    assert len(doc.objects) == 1  # created in job 1; revertable
    generic.vw_revert_last()
    assert doc.objects == {}


def test_set_pio_parameters_then_revert(doc):
    uuid = drawing.vw_create_pio("Lighting Device", 0, 0)["uuid"]
    out = drawing.vw_set_pio_parameters(uuid, {"Channel": "7"})
    assert out["after"]["Channel"] == "7"
    generic.vw_revert_last()
    h = max(doc.objects)
    assert doc.objects[h]["fields"]["Channel"] == ""


def test_move_and_revert(doc):
    a = drawing.vw_create_pio("Truss", 0, 0)["uuid"]
    b = drawing.vw_create_pio("Truss", 5, 5)["uuid"]
    assert drawing.vw_move_objects([a, b], dx=1, dy=2) == {"moved": 2}
    assert [ (o["x"], o["y"]) for o in doc.objects.values()] == [(1, 2), (6, 7)]
    drawing.vw_move_objects([a], dz=3)
    assert doc.objects[max(doc.objects) - 1]["z"] == 3
    generic.vw_revert_last()
    generic.vw_revert_last()
    assert [(o["x"], o["y"], o["z"]) for o in doc.objects.values()] == [(0, 0, 0), (5, 5, 0)]
    with pytest.raises(ToolError, match="no object with uuid"):
        drawing.vw_move_objects([a, "nope"], dx=1)
    assert doc.objects[max(doc.objects) - 1]["x"] == 0


def test_delete_is_all_or_nothing(doc):
    a = drawing.vw_create_pio("Truss", 0, 0)["uuid"]
    with pytest.raises(ToolError, match="nope"):
        drawing.vw_delete_objects([a, "nope"])
    assert len(doc.objects) == 1
    assert drawing.vw_delete_objects([a]) == {"deleted": 1}
    assert doc.objects == {}


def test_set_view_variants(doc):
    drawing.vw_set_view("iso", fit=True)
    assert ("view", [1, -1, 1], [0, 0, 1]) in [tuple(e[:1]) + tuple(list(x) for x in e[1:]) for e in doc.events]
    assert ("menu", "Fit To Objects") in doc.events
    drawing.vw_set_view("top_plan")
    assert ("menu", "Standard Views") in doc.events
    with pytest.raises(ToolError, match="unknown view"):
        drawing.vw_set_view("sideways")


def test_library_resources_and_import(doc, monkeypatch):
    import os
    monkeypatch.setattr(os.path, "isfile", lambda p: p in doc.library)
    out = drawing.vw_list_library_resources("/lib/Truss.vwx", name_contains="20")
    assert out == {"path": "/lib/Truss.vwx", "type_code": 16, "count": 1, "names": ["Tomcat 20"]}
    with pytest.raises(ToolError, match="no file"):
        drawing.vw_list_library_resources("/nope.vwx")
    imp = drawing.vw_import_resource("/lib/Truss.vwx", "Tomcat 20")
    assert imp == {"name": "Tomcat 20", "type_code": 16} and "Tomcat 20" in doc.resources
    with pytest.raises(ToolError, match="already in the document"):
        drawing.vw_import_resource("/lib/Truss.vwx", "Tomcat 12")
    copy = drawing.vw_import_resource("/lib/Truss.vwx", "Tomcat 12", new_name="Tomcat 12 (lib)")
    assert copy["name"] == "Tomcat 12 (lib)" and doc.resources["Tomcat 12"] == 50
    with pytest.raises(ToolError, match="is not in"):
        drawing.vw_import_resource("/lib/Truss.vwx", "Nope")
    generic.vw_revert_last()
    assert "Tomcat 12 (lib)" not in doc.resources and doc.resources["Tomcat 12"] == 50


# ---- truss runs ----------------------------------------------------------------

def add_truss_symbol(doc, vs, name="Global Truss F34-300 Straight", length=3000):
    h = doc._import(name)
    doc.symdef_records = getattr(doc, "symdef_records", {})
    doc.symdef_records[h] = {"BrxTrussItemRecord": {
        "Name": "F34-300", "Type": "F34", "ItemType": "Line", "Length": str(length),
        "Height": "290", "Width": "290", "Section": "F34", "Connection": "F34", "Weight": "19.05"}}
    old_rec, old_rf = vs.GetName, vs.GetRField
    vs.NumRecords = lambda hh: len(doc.symdef_records.get(hh, {}))
    vs.GetRecord = lambda hh, i: ("symrec", hh, list(doc.symdef_records[hh])[i - 1])
    vs.GetName = lambda hh: hh[2] if isinstance(hh, tuple) and hh[0] == "symrec" else old_rec(hh)
    vs.GetRField = lambda hh, rec, f: (doc.symdef_records[hh][rec].get(f, "") if hh in doc.symdef_records
                                       else old_rf(hh, rec, f))
    vs.GetUnits = lambda: (25, 3, 2, 1.0, '"', " sq ft")  # feet-inches doc: internal inch
    doc.moves3d = []
    vs.Move3DObj = lambda hh, dx, dy, dz: doc.moves3d.append((hh, dz)) or doc._move(hh, dx, dy, dz)
    PIO_FIELDS["TrussItem"] = ["Symbol", "Name", "Type", "ItemType", "CrossSection", "ConnectionIdent",
                               "Length", "Height", "Width", "TrussSystem", "TrussLine",
                               "TrussSystemLineIdent", "C_START_UUID", "PositionName",
                               "Weight", "Distributed weight"]
    return h


def test_truss_run_places_pieces_on_length_centres_linked(doc, fake_vs):
    add_truss_symbol(doc, fake_vs)
    out = drawing.vw_insert_truss_run("Global Truss F34-300 Straight", 100, 50, 3, rotation=90,
                                      z=120, position_name="US TRUSS", class_name="Truss")
    assert out["system"] == "T0" and out["piece_length"] == pytest.approx(118.11, 0.01)
    assert out["total_length"] == pytest.approx(3 * 118.11, 0.01) and len(out["pieces"]) == 3
    pcs = [o for o in doc.objects.values() if o["pio"] == "TrussItem"]
    assert [round(p["y"], 2) for p in pcs] == [109.06, 227.17, 345.28]
    assert all(p["x"] == pytest.approx(100) for p in pcs)
    assert all(p["z"] == 120 for p in pcs) and len(doc.moves3d) == 3
    f = [p["fields"] for p in pcs]
    assert f[0]["C_START_UUID"] == "" and f[1]["C_START_UUID"] == pcs[0]["uuid"] and f[2]["C_START_UUID"] == pcs[1]["uuid"]
    assert f[0]["Length"] == "3000mm" and f[0]["Height"] == "290mm" and f[0]["Type"] == "F34"
    assert f[0]["TrussSystemLineIdent"] == "T0-1" and f[0]["PositionName"] == "US TRUSS"
    assert all(p["class"] == "Truss" for p in pcs)
    assert f[0]["Weight"] == "19050" and f[0]["Distributed weight"] == "6.35"
    generic.vw_revert_last()
    assert not [o for o in doc.objects.values() if o["pio"] == "TrussItem"]


def test_truss_run_picks_next_free_system(doc, fake_vs):
    add_truss_symbol(doc, fake_vs)
    drawing.vw_insert_truss_run("Global Truss F34-300 Straight", 0, 0, 1)
    assert drawing.vw_insert_truss_run("Global Truss F34-300 Straight", 0, 500, 1)["system"] == "T1"


def test_truss_run_imports_when_given_library_path(doc, fake_vs, monkeypatch):
    import os
    monkeypatch.setattr(os.path, "isfile", lambda p: p in doc.library)
    doc.library["/lib/Truss.vwx"] = ["Global Truss F34-300 Straight"]
    real_import = doc._import

    def importing(name):
        doc._import = real_import
        h = add_truss_symbol(doc, fake_vs, name)  # library symbol carries the record
        doc._import = importing
        return h

    doc._import = importing
    out = drawing.vw_insert_truss_run("Global Truss F34-300 Straight", 0, 0, 2, library_path="/lib/Truss.vwx")
    assert out["imported"] == "Global Truss F34-300 Straight"
    generic.vw_revert_last()
    assert "Global Truss F34-300 Straight" not in doc.resources


def test_truss_run_rejects_non_truss_symbol_and_bad_count(doc, fake_vs):
    with pytest.raises(ToolError, match="import_resource"):
        drawing.vw_insert_truss_run("Nope", 0, 0, 2)
    with pytest.raises(ToolError, match="no BrxTrussItemRecord"):
        drawing.vw_insert_truss_run("Tomcat 12", 0, 0, 2)
    with pytest.raises(ToolError, match="count"):
        drawing.vw_insert_truss_run("Tomcat 12", 0, 0, 0)


def test_list_truss_groups_runs_in_chain_order(doc, fake_vs):
    add_truss_symbol(doc, fake_vs)
    doc.classes.append("Truss")
    drawing.vw_insert_truss_run("Global Truss F34-300 Straight", 0, 0, 3, position_name="US", class_name="Truss")
    drawing.vw_insert_truss_run("Global Truss F34-300 Straight", 0, 500, 1)
    fake_vs.Get3DCntr = lambda hh: ((doc.objects[hh]["x"], doc.objects[hh]["y"]), doc.objects[hh]["z"])
    fake_vs.Get3DInfo = lambda hh: (10, 118.11, 10)
    out = drawing.vw_list_truss()
    assert [r["system"] for r in out["runs"]] == ["T0", "T1"] and out["total_pieces"] == 4
    t0 = out["runs"][0]
    assert t0["count"] == 3 and t0["total_length"] == pytest.approx(3 * 118.11, 0.01)
    assert t0["total_weight_kg"] == pytest.approx(3 * 19.05) and t0["linked"] is True
    assert t0["positions"] == ["US"] and t0["symbols"] == ["Global Truss F34-300 Straight"]
    assert [round(p["length"], 1) for p in t0["pieces"]] == [118.1] * 3
    assert [round(p["center"][0], 1) for p in t0["pieces"]] == [59.1, 177.2, 295.3]
    (x0, y0), (x1, y1) = t0["bbox"]
    assert (x0, y0, x1, y1) == pytest.approx((0, -5, 354.33, 5), abs=0.1)
    pcs = [o for o in doc.objects.values() if o["pio"] == "TrussItem" and o["fields"]["TrussSystem"] == "T0"]
    assert [p["uuid"] for p in t0["pieces"]] == [o["uuid"] for o in pcs]
    assert drawing.vw_list_truss(system="T1")["runs"][0]["count"] == 1
    assert drawing.vw_list_truss(layer="nope")["runs"] == []


# ---- lighting devices ----------------------------------------------------------

LD_FIELDS = ["Symbol Name", "Inst Type", "Device Type", "Wattage", "Position", "Unit Number",
             "Channel", "Purpose", "Num Channels"]


def add_fixture_symbol(doc, vs, name="Martin Mac One"):
    h = doc._import(name)
    doc.fixtures = getattr(doc, "fixtures", set()) | {name}
    PIO_FIELDS["Lighting Device"] = LD_FIELDS
    PIO_FIELDS["Light Position Obj"] = ["Position Name"]
    doc.selected = set()
    vs.DSelectAll = lambda: doc.selected.clear()
    vs.SetSelect = lambda hh: doc.selected.add(hh)
    vs.Selected = lambda hh: hh in doc.selected
    vs.NumSelectedObjects = lambda: len(doc.selected)
    sel = lambda: sorted(h for h in doc.selected if h in doc.objects)  # noqa: E731
    vs.FSActLayer = lambda: (sel() or [0])[0]
    vs.NextSObj = lambda hh: next((s for s in sel() if s > hh), 0)
    vs.GetSymLoc3D = lambda hh: (doc.objects[hh]["x"], doc.objects[hh]["y"], doc.objects[hh]["z"])
    vs.Move3DObj = lambda hh, dx, dy, dz: doc._move(hh, dx, dy, dz)
    vs.ForEachObject = lambda fn, crit: [fn(hh) for hh in list(doc.objects)]
    doc.menus = []

    def menu(name, chunk):
        doc.menus.append(name)
        if name == "Convert to Instrument":
            for hh in list(doc.selected):
                o = doc.objects.get(hh)
                if o and o["type"] == 15 and o["name"] == name_of_fixture(doc, o):
                    o.update(type=86, pio="Lighting Device",
                             fields={f: "" for f in LD_FIELDS})
                    o["fields"].update({"Symbol Name": o["name"], "Inst Type": o["name"],
                                        "Wattage": "180 W", "Num Channels": "108"})
    vs.DoMenuTextByName = menu
    return h


def name_of_fixture(doc, o):
    return o["name"] if o["name"] in doc.fixtures else None


def add_position(doc, name, x, y, z):
    h = doc._create(86, pio="Light Position Obj", x=x, y=y, z=z)
    doc.objects[h]["fields"]["Position Name"] = name
    return h


def test_insert_lighting_devices_converts_fills_and_hangs(doc, fake_vs):
    add_fixture_symbol(doc, fake_vs)
    add_position(doc, "palm NE", 3803.6, 1991.7, 118.0)
    doc.selected = {next(iter(doc.objects))}  # user had the position selected
    out = drawing.vw_insert_lighting_devices("Martin Mac One", 3803.6, 1926.4, count=3, spacing=17,
                                             rotation=90, position="palm NE", start_unit=5, channel=101,
                                             purpose="Wash", class_name="Truss")
    devs = [o for o in doc.objects.values() if o["pio"] == "Lighting Device"]
    assert len(devs) == 3 and out["z"] == 118.0 and "Convert to Instrument" in doc.menus
    assert [round(d["y"], 1) for d in devs] == [1926.4, 1943.4, 1960.4] and all(d["z"] == 118.0 for d in devs)
    assert [d["fields"]["Unit Number"] for d in devs] == ["5", "6", "7"]
    assert [d["fields"]["Channel"] for d in devs] == ["101", "102", "103"]
    assert all(d["fields"]["Position"] == "palm NE" and d["fields"]["Purpose"] == "Wash" for d in devs)
    assert all(d["class"] == "Truss" for d in devs)
    assert out["devices"][0]["inst_type"] == "Martin Mac One" and "not_applied" not in out
    assert doc.selected == {next(iter(doc.objects))}  # user's selection restored
    generic.vw_revert_last()
    assert not [o for o in doc.objects.values() if o["pio"] == "Lighting Device"]


def test_insert_lighting_devices_reports_not_applied(doc, fake_vs):
    add_fixture_symbol(doc, fake_vs)
    real_set = fake_vs.SetRField

    def stubborn(hh, rec, f, val):  # Spotlight rejects the channel
        real_set(hh, rec, f, "" if f == "Channel" else val)
    fake_vs.SetRField = stubborn
    out = drawing.vw_insert_lighting_devices("Martin Mac One", 0, 0, count=1, channel=7)
    assert out["not_applied"] == [{"uuid": out["devices"][0]["uuid"],
                                   "not_applied": {"Channel": {"requested": "7", "actual": ""}}}]


def test_insert_lighting_devices_fails_cleanly_on_non_fixture(doc, fake_vs):
    add_fixture_symbol(doc, fake_vs)
    with pytest.raises(ToolError, match="converted 0 of 2"):
        drawing.vw_insert_lighting_devices("Tomcat 12", 0, 0, count=2, spacing=10)
    assert all(o["type"] != 15 for o in doc.objects.values())  # placed symbols removed


# ---- stage decks ----------------------------------------------------------------

DECK_FIELDS = ["DeckShape", "Width", "Depth", "Height", "StgStyle", "Purpose", "Position"]


def test_stage_decks_tile_a_platform(doc, fake_vs):
    PIO_FIELDS["Stage Deck"] = DECK_FIELDS
    fake_vs.GetUnits = lambda: (25, 3, 2, 1.0, '"', " sq ft")
    doc.classes.append("Staging")
    fake_vs.Get3DCntr = lambda hh: ((doc.objects[hh]["x"] + 48, doc.objects[hh]["y"] + 24), 18)
    fake_vs.Get3DInfo = lambda hh: (48, 96, 36)
    out = drawing.vw_insert_stage_decks(96, 48, 36, 10, 20, columns=2, rows=2, rotation=90,
                                        structure="Legs-Braced", purpose="DRUM RISER",
                                        class_name="Staging")
    assert out["count"] == 4 and out["footprint"] == {"width": 192, "depth": 96}
    assert out["decks"][0]["center"] == [58, 44, 18] and out["decks"][0]["size"] == [96, 48, 36]
    decks = [o for o in doc.objects.values() if o["pio"] == "Stage Deck"]
    # rotation 90: columns go +y, rows go -x
    assert [(round(d["x"]), round(d["y"])) for d in decks] == [(10, 20), (10, 116), (-38, 20), (-38, 116)]
    f = decks[0]["fields"]
    assert f["Width"] == "2438.4mm" and f["Depth"] == "1219.2mm" and f["Height"] == "914.4mm"
    assert f["StgStyle"] == "Legs-Braced" and f["Purpose"] == "DRUM RISER" and f["DeckShape"] == "Rectangular"
    assert all(d["class"] == "Staging" for d in decks)
    generic.vw_revert_last()
    assert not [o for o in doc.objects.values() if o["pio"] == "Stage Deck"]


def test_stage_decks_reject_bad_input(doc, fake_vs):
    PIO_FIELDS["Stage Deck"] = DECK_FIELDS
    with pytest.raises(ToolError, match="columns"):
        drawing.vw_insert_stage_decks(96, 48, 36, 0, 0, columns=0)
    with pytest.raises(ToolError, match="positive"):
        drawing.vw_insert_stage_decks(0, 48, 36, 0, 0)
    assert not [o for o in doc.objects.values() if o["pio"] == "Stage Deck"]


def test_dimension_strings_read_back_in_document_units(fake_vs):
    import types
    from vwmcp import vwlib
    src = open(vwlib.__file__).read()
    mod = types.ModuleType("vwlib_live")
    fake_vs.GetUnits = lambda: (25, 3, 2, 1.0, '"', " sq ft")  # feet-inches: internal inch
    mod.vs = fake_vs
    exec(src, mod.__dict__)
    d = mod._dim_to_doc
    assert d("3000mm") == pytest.approx(118.11, 0.001) and d("3 m") == pytest.approx(118.11, 0.001)
    assert d("118.11") == 118.11 and d('9\'10.11"') == pytest.approx(118.11) and d("9'") == 108
    assert d("4'6 1/2\"") == 54.5 and d("") == 0 and d("12in") == 12 and d("2ft") == 24
    assert d("8.000000000000002e00'") == pytest.approx(96) and d("8.333333333333333e-02'") == pytest.approx(1)
    with pytest.raises(ValueError):
        d("what")


# ---- stage steps ----------------------------------------------------------------

STEPS_FIELDS = ["Type", "BuildMethod", "Stageheight", "Treadwidth", "StepTotal", "RailLeft",
                "RailRight", "StringerLength", "Purpose", "Position"]


def test_stage_steps_default_step_count_and_fields(doc, fake_vs):
    PIO_FIELDS["Stage Steps"] = STEPS_FIELDS
    fake_vs.GetUnits = lambda: (25, 3, 2, 1.0, '"', " sq ft")
    fake_vs.Get3DCntr = lambda hh: ((doc.objects[hh]["x"], doc.objects[hh]["y"] - 20), 12)
    fake_vs.Get3DInfo = lambda hh: (40, 36, 25)
    out = drawing.vw_insert_stage_steps(100, 200, 24, rotation=90, rail_left=True, purpose="SR STEPS")
    assert out["steps"] == 3 and out["center"] == [100, 180, 12] and out["size"] == [36, 40, 25]
    o = [o for o in doc.objects.values() if o["pio"] == "Stage Steps"][0]
    f = o["fields"]
    assert f["Stageheight"] == "609.6mm" and f["StepTotal"] == "3" and f["Type"] == "Self-Adjusting"
    assert f["RailLeft"] == "True" and f["RailRight"] == "False" and f["Purpose"] == "SR STEPS"
    assert f["Treadwidth"] == "" and f["BuildMethod"] == "Stage height and number of steps"
    assert (o["x"], o["y"]) == (100, 200)
    out2 = drawing.vw_insert_stage_steps(0, 0, 48, steps=8, tread_width=48, stringer_length=96, kind="Simple")
    assert out2["steps"] == 8
    f2 = doc.objects[max(doc.objects)]["fields"]
    assert f2["Treadwidth"] == "1219.2mm" and f2["StringerLength"] == "2438.4mm" and f2["Type"] == "Simple"
    generic.vw_revert_last()
    generic.vw_revert_last()
    assert not [o for o in doc.objects.values() if o["pio"] == "Stage Steps"]


def test_stage_steps_reject_bad_height(doc, fake_vs):
    PIO_FIELDS["Stage Steps"] = STEPS_FIELDS
    with pytest.raises(ToolError, match="stage_height"):
        drawing.vw_insert_stage_steps(0, 0, 0)


# ---- stage ramp -----------------------------------------------------------------

RAMP_FIELDS = ["Type", "BuildMethod", "Stageheight", "Treadwidth", "RampLength", "PitchAngVar",
               "RailLeft", "RailRight", "DrawArrow", "Purpose", "Position"]


def test_stage_ramp_by_length_and_by_angle(doc, fake_vs):
    PIO_FIELDS["Stage Ramp"] = RAMP_FIELDS
    fake_vs.GetUnits = lambda: (25, 3, 2, 1.0, '"', " sq ft")
    fake_vs.Get3DCntr = lambda hh: ((doc.objects[hh]["x"], doc.objects[hh]["y"] - 41.6), 24)
    fake_vs.Get3DInfo = lambda hh: (83.1, 36, 48)
    out = drawing.vw_insert_stage_ramp(5000, 5000, 48, ramp_length=96, rail_right=True, arrow=True,
                                       purpose="LOAD-IN")
    assert out["center"] == [5000, 4958.4, 24] and out["size"] == [36, 83.1, 48]
    o = [o for o in doc.objects.values() if o["pio"] == "Stage Ramp"][0]
    f = o["fields"]
    assert f["BuildMethod"] == "Ramp Length" and f["RampLength"] == "2438.4mm"
    assert f["Stageheight"] == "1219.2mm" and f["Type"] == "Legs" and f["PitchAngVar"] == ""
    assert f["RailLeft"] == "False" and f["RailRight"] == "True" and f["DrawArrow"] == "Down"
    assert f["Purpose"] == "LOAD-IN" and (o["x"], o["y"]) == (5000, 5000)
    drawing.vw_insert_stage_ramp(0, 0, 24, pitch_angle=15, tread_width=48, kind="Solid")
    f2 = doc.objects[max(doc.objects)]["fields"]
    assert f2["BuildMethod"] == "Pitch Angle" and f2["PitchAngVar"] == "15" and f2["RampLength"] == ""
    assert f2["Treadwidth"] == "1219.2mm" and f2["Type"] == "Solid" and f2["DrawArrow"] == "None"
    generic.vw_revert_last()
    generic.vw_revert_last()
    assert not [o for o in doc.objects.values() if o["pio"] == "Stage Ramp"]


def test_stage_ramp_rejects_bad_input(doc, fake_vs):
    PIO_FIELDS["Stage Ramp"] = RAMP_FIELDS
    with pytest.raises(ToolError, match="either ramp_length or pitch_angle"):
        drawing.vw_insert_stage_ramp(0, 0, 24)
    with pytest.raises(ToolError, match="either ramp_length or pitch_angle"):
        drawing.vw_insert_stage_ramp(0, 0, 24, ramp_length=60, pitch_angle=10)
    with pytest.raises(ToolError, match="longer than stage_height"):
        drawing.vw_insert_stage_ramp(0, 0, 24, ramp_length=20)
    with pytest.raises(ToolError, match="stage_height"):
        drawing.vw_insert_stage_ramp(0, 0, 0, ramp_length=20)
    assert not [o for o in doc.objects.values() if o["pio"] == "Stage Ramp"]


# ---- soft goods -----------------------------------------------------------------

SOFT_FIELDS = ["GdsFunct", "CurtHeight", "OpenWidth", "OpenFrom", "Traveler", "AddPipe", "AddTrack",
               "Purpose", "Position"]


def test_soft_goods_along_a_path(doc, fake_vs):
    PIO_FIELDS["Soft Goods"] = SOFT_FIELDS
    fake_vs.GetUnits = lambda: (25, 3, 2, 1.0, '"', " sq ft")
    fake_vs.Get3DCntr = lambda hh: ((120, 50), 60)
    fake_vs.Get3DInfo = lambda hh: (100, 240, 120)
    out = drawing.vw_insert_soft_goods([[0, 0], [240, 0], [240, 100]], 120, opening_width=48,
                                       open_from="Center", traveler=True, add_track=True,
                                       purpose="US BLACKS", class_name="Truss")
    assert out["path_length"] == 340 and out["center"] == [120, 50, 60] and out["class"] == "Truss"
    o = [o for o in doc.objects.values() if o["pio"] == "Soft Goods"][0]
    assert o["path"] == [[0, 0], [240, 0], [240, 100]] and o["class"] == "Truss"
    f = o["fields"]
    assert f["GdsFunct"] == "Curtain" and f["CurtHeight"] == "3048mm" and f["OpenWidth"] == "1219.2mm"
    assert f["OpenFrom"] == "Center" and f["Traveler"] == "True" and f["AddTrack"] == "True"
    assert f["AddPipe"] == "False" and f["Purpose"] == "US BLACKS"
    assert not [o for o in doc.objects.values() if o["type"] == 21]  # the polyline was consumed
    assert ("openpoly",) in doc.events and ("closepoly",) in doc.events
    drawing.vw_insert_soft_goods([[0, 0], [0, 1000]], 96, function="Pipe-and-Drape", add_pipe=True)
    f2 = doc.objects[max(doc.objects)]["fields"]
    assert f2["GdsFunct"] == "Pipe-and-Drape" and f2["AddPipe"] == "True" and f2["OpenWidth"] == ""
    generic.vw_revert_last()
    generic.vw_revert_last()
    assert not [o for o in doc.objects.values() if o["pio"] == "Soft Goods"]


def test_soft_goods_rejects_bad_input(doc, fake_vs):
    PIO_FIELDS["Soft Goods"] = SOFT_FIELDS
    with pytest.raises(ToolError, match="at least two"):
        drawing.vw_insert_soft_goods([[0, 0]], 100)
    with pytest.raises(ToolError, match="height"):
        drawing.vw_insert_soft_goods([[0, 0], [10, 0]], 0)
    with pytest.raises(ToolError, match="opening_width"):
        drawing.vw_insert_soft_goods([[0, 0], [10, 0]], 100, opening_width=-1)
    assert not doc.events or not [e for e in doc.events if e[0] == "openpoly"]
    assert not [o for o in doc.objects.values() if o["type"] == 21]


# ---- vw_apply_class_standard ----------------------------------------------------

def test_apply_class_standard_journals_created_and_restyled(fake, monkeypatch):
    before = {"exists": True, "pen": [0, 0, 0], "fill": None, "line_weight": 5, "use_graphic": True}
    fake_attrs = {"Lighting-Instruments": before}
    calls = []

    def fake_vw(fn, **kw):
        calls.append((fn, kw))
        if fn == "class_attrs":
            return {n: fake_attrs.get(n, {"exists": False}) for n in kw["names"]}
        if fn == "apply_class_attrs":
            return {"document": "Plot.vwx", "created": [c["name"] for c in kw["create"]],
                    "restyled": [c["name"] for c in kw["restyle"]],
                    "before": {c["name"]: fake_attrs[c["name"]] for c in kw["restyle"]}}
        if fn == "current_document":
            return "Plot.vwx"
        return fake(fn, **kw)

    for mod in (app, generic, drawing):
        monkeypatch.setattr(mod, "vw", fake_vw)
    out = drawing.vw_apply_class_standard("spotlight", only=["Lighting-Instruments", "Rigging-Truss"], overwrite=True)
    assert out["created"] == ["Rigging-Truss"] and out["restyled"] == ["Lighting-Instruments"]
    generic.vw_revert_last()
    fn, kw = calls[-1]
    assert fn == "revert"
    assert {"op": "class", "name": "Rigging-Truss"} in kw["ops"]
    attrs_op = [o for o in kw["ops"] if o["op"] == "class_attrs"][0]
    assert attrs_op["name"] == "Lighting-Instruments" and attrs_op["before"] == before


def test_apply_class_standard_unknown_name(fake):
    with pytest.raises(ToolError, match="spotlight"):
        drawing.vw_apply_class_standard("nope")


# ---- vw_create_sheet -------------------------------------------------------------

def test_create_sheet_journals_the_sheet_layer(fake, monkeypatch):
    seen = {}

    def fake_vw(fn, **kw):
        if fn == "create_sheet":
            seen.update(kw)
            return {"document": "Plot.vwx", "sheet": "Sheet-1", "viewport": "vp-1", "scale": 48.0,
                    "layers_shown": ["Lighting"], "title_block": None}
        return fake(fn, **kw)

    for mod in (app, generic, drawing):
        monkeypatch.setattr(mod, "vw", fake_vw)
    out = drawing.vw_create_sheet("Sheet-1", layers=["Lighting"], scale=48, hide_classes=["Notes"],
                                  title="Light Plot", sheet_number="LX-1")
    assert seen["layers"] == ["Lighting"] and seen["hide_classes"] == ["Notes"]
    assert seen["title_block"] == {"Sheet Title": "Light Plot", "Sheet Number": "LX-1"}
    assert out["viewport"] == "vp-1"
    generic.vw_revert_last()
    assert last_revert_ops(fake) == [{"op": "layer", "name": "Sheet-1"}]


def test_create_sheet_needs_layers_and_positive_scale(fake):
    with pytest.raises(ToolError, match="layers"):
        drawing.vw_create_sheet("S", layers=[])
    with pytest.raises(ToolError, match="scale"):
        drawing.vw_create_sheet("S", layers=["L"], scale=0)


# ---- vw_insert_platform -----------------------------------------------------------

def test_insert_platform_journals_decks_and_steps_together(fake, monkeypatch):
    seen = {}

    def fake_vw(fn, **kw):
        if fn == "insert_platform":
            seen.update(kw)
            return {"document": "Plot.vwx", "decks": [{"uuid": "d1"}, {"uuid": "d2"}],
                    "steps": {"uuid": "s1", "steps": 3}, "footprint": {"width": 8, "depth": 8}}
        if fn == "object_extents":
            return [{"uuid": u, "center": [0, 0, 0], "size": [1, 1, 1]} for u in kw["uuids"]]
        return fake(fn, **kw)

    for mod in (app, generic, drawing):
        monkeypatch.setattr(mod, "vw", fake_vw)
    out = drawing.vw_insert_platform(4, 8, 2, 10, 20, columns=2, steps_on="front", step_count=3,
                                     rails=True, class_name="Stage-Decks")
    assert seen["steps"] == {"x": 10 + 4.0, "y": 20.0, "rotation": 0.0, "steps": 3, "tread_width": None,
                             "kind": "Self-Adjusting", "rail_left": True, "rail_right": True}
    assert seen["width"] == 4 and seen["columns"] == 2
    assert out["steps"]["uuid"] == "s1" and out["class"] == "Stage-Decks"
    assert ("set_objects_class", {"uuids": ["d1", "d2", "s1"], "cls": "Stage-Decks"}) in fake.calls
    generic.vw_revert_last()
    assert last_revert_ops(fake) == [{"op": "created", "uuid": "d1"}, {"op": "created", "uuid": "d2"},
                                     {"op": "created", "uuid": "s1"}]


def test_insert_platform_without_steps(fake, monkeypatch):
    def fake_vw(fn, **kw):
        if fn == "insert_platform":
            assert kw["steps"] is None
            return {"document": "Plot.vwx", "decks": [{"uuid": "d1"}], "steps": None,
                    "footprint": {"width": 4, "depth": 8}}
        if fn == "object_extents":
            return [{"uuid": u} for u in kw["uuids"]]
        return fake(fn, **kw)

    for mod in (app, generic, drawing):
        monkeypatch.setattr(mod, "vw", fake_vw)
    out = drawing.vw_insert_platform(4, 8, 2, 0, 0)
    assert out["steps"] is None and len(out["decks"]) == 1


# ---- vw_insert_band ----------------------------------------------------------------

def test_insert_band_journals_symbols_and_labels(fake, monkeypatch):
    seen = {}

    def fake_vw(fn, **kw):
        if fn == "insert_band":
            seen.update(kw)
            return {"document": "Plot.vwx", "members": [
                {"name": "Drums", "symbol": "Drummer", "uuid": "m1", "label_uuid": "t1"},
                {"name": "Bass", "symbol": "Bassist", "uuid": "m2", "label_uuid": None}]}
        return fake(fn, **kw)

    for mod in (app, generic, drawing):
        monkeypatch.setattr(mod, "vw", fake_vw)
    out = drawing.vw_insert_band([{"symbol": "Drummer", "x": 0, "y": 0, "name": "Drums"},
                                  {"symbol": "Bassist", "x": 2, "y": 0, "rotation": 90}],
                                 layer="Stage", class_name="People")
    assert seen["members"][1] == {"symbol": "Bassist", "x": 2, "y": 0, "rotation": 90, "name": "Bassist", "z": None}
    assert seen["layer"] == "Stage" and seen["label"] is True
    assert out["class"] == "People"
    assert ("set_objects_class", {"uuids": ["m1", "t1", "m2"], "cls": "People"}) in fake.calls
    generic.vw_revert_last()
    assert last_revert_ops(fake) == [{"op": "created", "uuid": "m1"}, {"op": "created", "uuid": "t1"},
                                     {"op": "created", "uuid": "m2"}]


def test_insert_band_validates_members(fake):
    with pytest.raises(ToolError, match="symbol"):
        drawing.vw_insert_band([{"x": 0, "y": 0}])
    with pytest.raises(ToolError, match="members"):
        drawing.vw_insert_band([])
