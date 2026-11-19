import pytest
from mcp.server.mcpserver.exceptions import ToolError

from vwmcp import app
from vwmcp.journal import Journal
from vwmcp.tools import generic, spotlight


class FakeVW:
    """Records vwlib calls and returns canned values."""

    def __init__(self, document="Plot.vwx"):
        self.calls, self.document = [], document

    def __call__(self, fn, **kw):
        self.calls.append((fn, kw))
        if fn == "set_record":
            return {"document": self.document, "before": {"Note": "old"}}
        if fn == "get_record":
            return {"Note": "new"}
        if fn == "insert_symbol":
            return {"document": self.document, "uuid": "sym-1", "type": "Symbol"}
        if fn == "set_lighting_device_fields":
            return {"document": self.document, "devices": [{"uuid": "ld-1", "before": {"Channel": "5"}}]}
        if fn == "read_devices":
            return [{"uuid": "ld-1", "Channel": "101"}]
        if fn == "current_document":
            return self.document
        if fn == "revert":
            return {"document": self.document, "reverted": len(kw["ops"])}
        raise AssertionError(fn)


@pytest.fixture
def fake(tmp_path, monkeypatch):
    f = FakeVW()
    for mod in (app, generic, spotlight):
        monkeypatch.setattr(mod, "vw", f)
    monkeypatch.setattr(app, "get_journal", lambda: Journal(tmp_path / "j.jsonl"))
    monkeypatch.setattr(generic, "_run_raw", lambda code, timeout=None: {"ok": True, "value": None, "stdout": "", "error": None, "traceback": None})

    def call_result(bridge, fn, timeout=None, **kw):
        assert fn == "exec_tracked"
        created = ["r-1"] if "Rect" in kw["code"] else []
        return {"value": {"value": None, "error": None, "traceback": None, "document": f.document,
                          "created": created, "deleted_existing": 0}, "stdout": ""}

    monkeypatch.setattr(generic.calls, "call_result", call_result)
    monkeypatch.setattr(app, "get_bridge", lambda: None)
    return f


def test_set_record_then_revert_restores_before_values(fake):
    assert generic.vw_set_record("u1", "Notes", {"Note": "new"}) == {"Note": "new"}
    out = generic.vw_revert_last()
    fn, kw = fake.calls[-1]
    assert fn == "revert"
    assert kw["ops"] == [{"op": "fields", "uuid": "u1", "record": "Notes", "before": {"Note": "old"}}]
    assert out["reverted_tool"] == "vw_set_record"


def test_insert_symbol_then_revert_deletes_it(fake):
    generic.vw_insert_symbol("Source 4", 1, 2)
    generic.vw_revert_last()
    assert fake.calls[-1][1]["ops"] == [{"op": "created", "uuid": "sym-1"}]


def test_lighting_fields_revert_uses_lighting_device_record(fake):
    spotlight.vw_set_lighting_device_fields([{"uuid": "ld-1", "fields": {"Channel": "101"}}])
    generic.vw_revert_last()
    assert fake.calls[-1][1]["ops"] == [
        {"op": "fields", "uuid": "ld-1", "record": "Lighting Device", "before": {"Channel": "5"}}
    ]


def test_revert_refuses_when_active_document_changed(fake):
    generic.vw_set_record("u1", "Notes", {"Note": "new"})
    fake.document = "Other.vwx"
    with pytest.raises(ToolError, match="nothing to revert in 'Other.vwx'"):
        generic.vw_revert_last()


def test_exec_python_blocks_revert_unless_read_only(fake):
    generic.vw_set_record("u1", "Notes", {"Note": "new"})
    generic.vw_exec_python("print(1)", modifies_document=False)
    assert generic.vw_revert_last()["reverted_tool"] == "vw_set_record"

    generic.vw_set_record("u1", "Notes", {"Note": "new"})
    generic.vw_exec_python("vs.SetClass(h, 'x')")  # changes, creates nothing
    with pytest.raises(ToolError, match="vw_exec_python"):
        generic.vw_revert_last()


def test_exec_python_created_objects_are_reverted(fake):
    generic.vw_set_record("u1", "Notes", {"Note": "new"})
    generic.vw_exec_python("vs.Rect(0,0,1,1)")
    out = generic.vw_revert_last()
    assert out["reverted_tool"] == "vw_exec_python" and "pre-existing" in out["note"]
    assert fake.calls[-1][1]["ops"] == [{"op": "created", "uuid": "r-1"}]
    assert generic.vw_revert_last()["reverted_tool"] == "vw_set_record"


class LayerVW(FakeVW):
    def __call__(self, fn, **kw):
        if fn == "duplicate_layer":
            self.calls.append((fn, kw))
            return {"document": self.document, "layer": kw["name"], "source": kw["source"], "objects": 3,
                    "source_objects": 3, "scale": 100.0, "visibility": -1, "after_source": True}
        if fn == "set_vertices":
            self.calls.append((fn, kw))
            return {"document": self.document, "uuid": kw["uuid"], "type": "Polyline", "applied": True,
                    "before": {"points": [[0, 0], [1, 0], [1, 1]]}, "points": kw["points"],
                    "area_before": 0.5, "area": 1.0, "closed": True}
        return super().__call__(fn, **kw)


@pytest.fixture
def layer_fake(tmp_path, monkeypatch):
    f = LayerVW()
    for mod in (app, generic):
        monkeypatch.setattr(mod, "vw", f)
    monkeypatch.setattr(app, "get_journal", lambda: Journal(tmp_path / "j.jsonl"))
    return f


def test_duplicate_layer_is_journaled_as_layer_created(layer_fake):
    out = generic.vw_duplicate_layer("EG", "EG var2")
    assert out["layer"] == "EG var2" and "warning" not in out and "document" not in out
    assert layer_fake.calls[0] == ("duplicate_layer", {"source": "EG", "name": "EG var2",
                                                         "visibility": None, "uuid_map": False})
    generic.vw_revert_last()
    assert layer_fake.calls[-1][1]["ops"] == [{"op": "layer_created", "name": "EG var2"}]


def test_set_vertices_journals_previous_vertices_for_revert(layer_fake):
    pts = [[0, 0], [2, 0], [2, 1], [0, 1]]
    out = generic.vw_set_vertices("p1", pts)
    assert out["area"] == 1.0 and out["applied"] and "before" not in out
    generic.vw_revert_last()
    assert layer_fake.calls[-1][1]["ops"] == [
        {"op": "vertices", "uuid": "p1", "before": {"points": [[0, 0], [1, 0], [1, 1]]}}]
