"""Screenshot pixel <-> drawing coordinates.

Numbers below are the live calibration of 2026-11-20 (VW 2026, MacBook display
127.5 points/inch, window 1728 pt wide captured at 3456 px): zoom 201.24 % on a
1:48 layer gave 10.69 px per drawing inch; the view centre (48, 30) sat at the
centre of the white drawing area, pixel (1609, 1122)."""

import struct

import pytest

from vwmcp import viewmap

VIEW = {"center": [48.0, 30.0], "zoom": 201.24064171122993, "layer_scale": 48.0,
        "units_per_inch": 1.0, "projection": 6, "top_plan": True, "units": '"'}
WINDOW = {"x": 0.0, "y": 33.0, "width": 1728.0, "height": 978.0}
CANVAS = (361, 337, 2857, 1907)   # white drawing area in the 3456 x 1956 capture
IMAGE = (3456, 1956)
PPI = 127.5


def mapping():
    return viewmap.Mapping.from_view(VIEW, WINDOW, IMAGE, canvas=CANVAS, points_per_inch=PPI)


def test_pixels_per_unit_from_display_density_zoom_and_scale():
    m = mapping()
    assert 1 / m.units_per_pixel == pytest.approx(10.69, abs=0.01)


def test_view_centre_maps_to_canvas_centre():
    m = mapping()
    assert m.to_pixel(48, 30) == (pytest.approx(1609.0), pytest.approx(1122.0))
    x, y = m.to_world(1609, 1122)
    assert (x, y) == (pytest.approx(48.0), pytest.approx(30.0))


def test_known_deck_corner_lands_where_it_was_measured():
    # deck (0..96, 0..96): top-left corner measured at about (1096, 416)
    m = mapping()
    px, py = m.to_pixel(0, 96)
    assert px == pytest.approx(1096, abs=2) and py == pytest.approx(416, abs=2)


def test_metric_document_uses_units_per_inch():
    view = {**VIEW, "units_per_inch": 25.4}   # millimetre document: GetUnits()[3] = 25.4 units per inch
    m = viewmap.Mapping.from_view(view, WINDOW, IMAGE, canvas=CANVAS, points_per_inch=PPI)
    assert 1 / m.units_per_pixel == pytest.approx(10.69 / 25.4, rel=1e-3)


def test_shrunk_image_scales_everything():
    m = viewmap.Mapping.from_view(VIEW, WINDOW, (1728, 978), canvas=tuple(c / 2 for c in CANVAS), points_per_inch=PPI)
    assert 1 / m.units_per_pixel == pytest.approx(10.69 / 2, abs=0.01)
    assert m.to_pixel(48, 30) == (pytest.approx(804.5), pytest.approx(561.0))


def test_dict_round_trip_and_warning():
    d = mapping().as_dict()
    assert viewmap.Mapping.from_dict(d).to_world(1609, 1122) == (pytest.approx(48.0), pytest.approx(30.0))
    assert "warning" not in d
    m = viewmap.Mapping.from_view({**VIEW, "top_plan": False, "projection": 0}, WINDOW, IMAGE, CANVAS, PPI)
    assert "Top/Plan" in m.warning


def bmp_bytes(width, height, pixels):
    """32-bit top-down BMP like `sips -s format bmp` writes; pixels[y][x] = (r, g, b)."""
    header_size = 138
    rows = b"".join(b"".join(bytes([b, g, r, 255]) for (r, g, b) in row) for row in pixels)
    head = b"BM" + struct.pack("<IHHI", header_size + len(rows), 0, 0, header_size)
    dib = struct.pack("<IiiHHIIiiII", 124, width, -height, 1, 32, 3, len(rows), 2835, 2835, 0, 0)
    dib += b"\x00" * (124 - len(dib))
    return head + dib + rows


def test_canvas_detection_finds_the_large_white_area(tmp_path):
    w, h = 40, 30
    pixels = [[(30, 30, 30)] * w for _ in range(h)]
    for y in range(5, 28):
        for x in range(8, 38):
            pixels[y][x] = (250, 250, 250)
    pixels[15][20] = (0, 0, 0)  # a drawn line must not break the detection
    p = tmp_path / "shot.bmp"
    p.write_bytes(bmp_bytes(w, h, pixels))
    assert viewmap.canvas_bbox_bmp(p, step=1) == (8, 5, 37, 27)


def test_canvas_detection_rejects_images_without_a_canvas(tmp_path):
    p = tmp_path / "dark.bmp"
    p.write_bytes(bmp_bytes(10, 10, [[(20, 20, 20)] * 10 for _ in range(10)]))
    with pytest.raises(ValueError, match="drawing area"):
        viewmap.canvas_bbox_bmp(p, step=1)
