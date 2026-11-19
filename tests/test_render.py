import struct
import zlib

import pytest

from vwmcp import render


def decode(png):
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", png[16:24])
    pos, idat = 8, b""
    while pos < len(png):
        n, tag = struct.unpack(">I", png[pos:pos + 4])[0], png[pos + 4:pos + 8]
        if tag == b"IDAT":
            idat += png[pos + 8:pos + 8 + n]
        pos += 12 + n
    raw = zlib.decompress(idat)
    rows = [raw[r * (w * 3 + 1) + 1:(r + 1) * (w * 3 + 1)] for r in range(h)]
    return w, h, lambda x, y: tuple(rows[y][x * 3:x * 3 + 3])


def test_canvas_png_roundtrip_and_line():
    cv = render.Canvas(20, 10)
    cv.line(2, 5, 17, 5, (0, 0, 0))
    w, h, px = decode(cv.png())
    assert (w, h) == (20, 10)
    assert px(10, 5) == (0, 0, 0) and px(10, 1) == (255, 255, 255)


def test_fill_is_even_odd_and_clipped():
    cv = render.Canvas(10, 10)
    cv.fill([(-5, 2), (5, 2), (5, 8), (-5, 8)], (221, 0, 0))
    assert cv.pixel(2, 5) == (221, 0, 0) and cv.pixel(7, 5) == (255, 255, 255)


def test_arc_points_follow_vectorworks_angles():
    pts = render.arc_points([0, 0], 2.0, 90.0, 90.0)
    assert pts[0] == pytest.approx([0, 2]) and pts[-1] == pytest.approx([-2, 0])


def test_outline_of_rectangle_uses_bbox_and_arc_uses_center():
    assert render.outline({"type": "Rectangle", "bbox_view": [[0, 0], [2, 1]]}) == (
        [[0, 0], [2, 0], [2, 1], [0, 1]], True)
    path, closed = render.outline({"type": "Arc", "center": [0, 0], "radius": 1, "start_angle": 0, "sweep": 30})
    assert not closed and path[0] == pytest.approx([1, 0])


LAYER = {"layer": "plan", "objects": [
    {"type": "Polygon", "closed": True, "points": [[0, 0], [10, 0], [10, 10], [0, 10]],
     "attrs": {"fill": {"pattern": 1, "back": "#dd0000", "fore": "#000000"},
               "pen": {"color": "#0000ff", "weight": 4, "style": 2}}},
    {"type": "Line", "points": [[0, 5], [10, 5]], "attrs": {"pen": {"color": "#000000", "weight": 4, "style": 2}}},
    {"type": "Text", "origin": [5, 8], "text": "Room"},
]}


def test_render_draws_fill_below_lines_and_reports_view():
    png, info = render.render([LAYER], bbox=[0, 0, 10, 10], max_size=100)
    w, h, px = decode(png)
    assert (w, h) == (100, 100) and info["pixels_per_unit"] == 10
    assert px(30, 20) == (221, 0, 0)          # solid fill
    assert px(50, 50) == (0, 0, 0)            # the line at y=5 lies on top of the fill
    assert info["objects_drawn"] == 2 and info["texts_marked"] == 1


def test_render_without_fills_and_default_bbox_has_margin():
    png, info = render.render([LAYER], max_size=200, fills=False)
    _, _, px = decode(png)
    assert px(100, 60) == (255, 255, 255)
    assert info["bbox"][0] < 0 and info["bbox"][2] > 10


def test_render_rejects_empty_and_bad_bbox():
    with pytest.raises(ValueError):
        render.render([{"layer": "x", "objects": []}])
    with pytest.raises(ValueError):
        render.render([LAYER], bbox=[5, 5, 5, 9])
