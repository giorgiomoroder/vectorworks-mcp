"""Screenshot pixel <-> drawing coordinates (pure math over numbers read live)."""

import struct
import zlib

import pytest

from vwmcp import viewmap


def png_bytes(width, height):
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
    return b"\x89PNG\r\n\x1a\n" + chunk


def test_png_size_reads_the_header(tmp_path):
    p = tmp_path / "a.png"
    p.write_bytes(png_bytes(640, 480))
    assert viewmap.png_size(p) == (640, 480)
    (tmp_path / "b.png").write_bytes(b"nope")
    with pytest.raises(ValueError):
        viewmap.png_size(tmp_path / "b.png")


VIEW = {"center": [10.0, 20.0], "center_screen": [500.0, 400.0],
        "unit_x_screen": [600.0, 400.0], "unit_y_screen": [500.0, 300.0],
        "zoom": 100.0, "layer_scale": 48.0, "projection": 6, "top_plan": True}
WINDOW = {"x": 100.0, "y": 50.0, "width": 1000.0, "height": 800.0}


def test_mapping_round_trips_center_and_unit_vectors():
    m = viewmap.Mapping.from_view(VIEW, WINDOW, image_size=(500, 400))
    assert m.to_pixel(10, 20) == (200.0, 175.0)
    assert m.to_world(200, 175) == (10.0, 20.0)
    assert m.to_world(250, 175) == (11.0, 20.0)   # +50 px right = +1 unit x
    assert m.to_world(200, 125) == (10.0, 21.0)   # 50 px up = +1 unit y
    assert m.units_per_pixel == pytest.approx(0.02)


def test_mapping_dict_is_self_describing_and_rebuildable():
    m = viewmap.Mapping.from_view(VIEW, WINDOW, image_size=(500, 400))
    d = m.as_dict()
    assert d["image_size"] == [500, 400] and d["units_per_pixel"] == pytest.approx(0.02)
    assert d["image_center_world"] == [pytest.approx(11.0), pytest.approx(19.5)]  # image centre (250,200) is 50 px right, 25 px below the view centre
    again = viewmap.Mapping.from_dict(d)
    assert again.to_world(250, 175) == (11.0, 20.0)


def test_mapping_warns_when_not_top_plan():
    m = viewmap.Mapping.from_view({**VIEW, "top_plan": False, "projection": 0}, WINDOW, (500, 400))
    assert "Top/Plan" in m.warning
    assert viewmap.Mapping.from_view(VIEW, WINDOW, (500, 400)).warning == ""


def test_mapping_rejects_degenerate_view():
    bad = {**VIEW, "unit_x_screen": VIEW["center_screen"]}
    with pytest.raises(ValueError, match="zoom"):
        viewmap.Mapping.from_view(bad, WINDOW, (500, 400))
