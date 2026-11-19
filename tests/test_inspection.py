import json

import pytest

from vwmcp import app
from vwmcp.tools import generic


EXPORT = {
    "document": "plan.vwx", "layer": "Ground floor", "truncated": False,
    "objects": [
        {"uuid": "a", "type": "Line", "class": "light", "points": [[0, 0], [2, 0]]},
        {"uuid": "b", "type": "Polygon", "class": "bold", "points": [[0, 0], [1, 3], [-1, 1]]},
        {"uuid": "c", "type": "Text", "class": "light", "origin": [5, 1], "text": "Kitchen"},
    ],
}


def test_geometry_summary_counts_and_extent():
    s = generic.geometry_summary(EXPORT)
    assert s["count"] == 3
    assert s["by_type"] == {"Line": 1, "Polygon": 1, "Text": 1}
    assert s["by_class"] == {"light": 2, "bold": 1}
    assert s["extent"] == [[-1, 0], [5, 3]]


@pytest.fixture
def export_call(monkeypatch):
    seen = {}

    def call_result(bridge, fn, timeout=None, **kw):
        seen.update(fn=fn, timeout=timeout, **kw)
        return {"value": EXPORT, "stdout": ""}

    monkeypatch.setattr(generic.calls, "call_result", call_result)
    monkeypatch.setattr(app, "get_bridge", lambda: None)
    return seen


def test_export_geometry_returns_data_inline(export_call):
    assert generic.vw_export_geometry(layer="Ground floor") == EXPORT
    assert export_call["fn"] == "export_geometry" and export_call["layer"] == "Ground floor"


def test_export_geometry_writes_file_and_returns_summary(export_call, tmp_path):
    out = generic.vw_export_geometry(out_path=str(tmp_path / "sub" / "eg.json"))
    assert out["count"] == 3 and out["path"].endswith("eg.json")
    assert json.loads((tmp_path / "sub" / "eg.json").read_text()) == EXPORT


def test_export_geometry_asks_for_attributes_by_default(export_call):
    generic.vw_export_geometry()
    assert export_call["attributes"] is True
    generic.vw_export_geometry(attributes=False)
    assert export_call["attributes"] is False


def test_render_layers_exports_each_layer_and_returns_png(export_call, tmp_path):
    img = generic.vw_render_layers(layers=["Ground floor"], max_size=120, out_path=str(tmp_path / "v.png"))
    assert export_call["fn"] == "export_geometry" and export_call["attributes"] is True
    assert img.data[:8] == b"\x89PNG\r\n\x1a\n"
    assert (tmp_path / "v.png").read_bytes() == img.data
