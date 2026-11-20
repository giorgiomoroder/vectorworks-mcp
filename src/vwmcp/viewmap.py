"""Map screenshot pixels to drawing coordinates and back.

Calibrated live on 2026-11-20 (VW 2026): Vectorworks' zoom is relative to the
display's physical pixel density (100 % = true size on screen), so

    pixels per drawing unit = points_per_inch * image_px_per_point
                              * zoom / 100 / (layer_scale * units_per_inch)

and the view centre (`vs.GetVCenter`) sits at the centre of the white
drawing area, which is found in the capture itself (the UI around it is
darker). `vs.ModelPt2DToScreenPt` does not help: it returns model
coordinates unchanged in Top/Plan. Exact in Top/Plan only; a 3D view gets a
warning and a screen-plane mapping.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


def png_size(path: Path) -> tuple[int, int]:
    head = Path(path).read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError(f"{path}: not a PNG file")
    return struct.unpack(">II", head[16:24])


def display_points_per_inch() -> float:
    """Physical density of the main display in points per inch (macOS,
    CoreGraphics). 127.5 on the 2026-11-20 MacBook. Vectorworks' 100 % zoom is
    one paper inch per physical inch, so this is the key to the mapping."""
    if sys.platform != "darwin":
        raise ValueError("display density is only read on macOS")
    cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))

    class CGSize(ctypes.Structure):
        _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]

    cg.CGMainDisplayID.restype = ctypes.c_uint32
    cg.CGDisplayScreenSize.restype = CGSize
    cg.CGDisplayScreenSize.argtypes = [ctypes.c_uint32]
    cg.CGDisplayPixelsWide.restype = ctypes.c_size_t
    cg.CGDisplayPixelsWide.argtypes = [ctypes.c_uint32]
    d = cg.CGMainDisplayID()
    mm = cg.CGDisplayScreenSize(d).width
    if mm <= 0:
        raise ValueError("display size unknown")
    return cg.CGDisplayPixelsWide(d) / (mm / 25.4)


def canvas_bbox_bmp(path: Path, step: int = 8, white: int = 240, frac: float = 0.6) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) of the large near-white area in a 24/32-bit
    BMP (as `sips -s format bmp` writes). Columns/rows are sampled every
    `step` pixels; a column or row belongs to the canvas when more than `frac`
    of its samples are white. Drawn lines are sparse and do not matter."""
    data = Path(path).read_bytes()
    if data[:2] != b"BM":
        raise ValueError(f"{path}: not a BMP file")
    offset = struct.unpack_from("<I", data, 10)[0]
    width, height = struct.unpack_from("<ii", data, 18)
    bpp = struct.unpack_from("<H", data, 28)[0]
    if bpp not in (24, 32):
        raise ValueError(f"{path}: {bpp}-bit BMP not supported")
    top_down = height < 0
    height = abs(height)
    bytes_px = bpp // 8
    stride = (width * bytes_px + 3) // 4 * 4

    def is_white(x: int, y: int) -> bool:
        row = y if top_down else height - 1 - y
        i = offset + row * stride + x * bytes_px
        b, g, r = data[i], data[i + 1], data[i + 2]
        return r > white and g > white and b > white

    xs = range(0, width, step)
    ys = range(0, height, step)
    col_ok = [sum(is_white(x, y) for y in ys) / len(ys) > frac for x in xs]
    row_ok = [sum(is_white(x, y) for x in xs) / len(xs) > frac for y in ys]
    cols = [x for x, ok in zip(xs, col_ok) if ok]
    rows = [y for y, ok in zip(ys, row_ok) if ok]
    if len(cols) < 3 or len(rows) < 3:
        raise ValueError("no white drawing area found in the capture (is a document window showing?)")
    return cols[0], rows[0], cols[-1], rows[-1]


def canvas_bbox(png_path: Path, step: int = 8) -> tuple[int, int, int, int]:
    """Canvas of a PNG capture, via a temporary BMP made with sips (macOS)."""
    with tempfile.TemporaryDirectory() as tmp:
        bmp = Path(tmp) / "capture.bmp"
        res = subprocess.run(["sips", "-s", "format", "bmp", str(png_path), "--out", str(bmp)],
                             capture_output=True, text=True)
        if res.returncode != 0 or not bmp.exists():
            raise ValueError("sips could not convert the capture: " + (res.stderr or "").strip())
        return canvas_bbox_bmp(bmp, step=step)


@dataclass(frozen=True)
class Mapping:
    origin_x: float          # drawing x at image pixel (0, 0)
    origin_y: float
    units_per_pixel: float   # drawing units per image pixel (isotropic)
    image_size: tuple[int, int]
    warning: str = ""
    units: str = ""

    @classmethod
    def from_view(cls, view: dict, window: dict, image_size: tuple[int, int],
                  canvas: tuple[float, float, float, float], points_per_inch: float) -> "Mapping":
        cx, cy = view["center"]
        px_per_point = image_size[0] / float(window["width"])
        ppi_image = points_per_inch * px_per_point
        px_per_unit = ppi_image * (view["zoom"] / 100.0) / (view["layer_scale"] * view.get("units_per_inch", 1.0))
        if px_per_unit <= 0:
            raise ValueError("zoom or scale gave no pixel size")
        upp = 1.0 / px_per_unit
        icx = (canvas[0] + canvas[2]) / 2.0
        icy = (canvas[1] + canvas[3]) / 2.0
        origin_x = cx - icx * upp
        origin_y = cy + icy * upp
        warning = "" if view.get("top_plan", True) else (
            "View is not Top/Plan: the mapping is for the screen plane only (projection %s)."
            % view.get("projection"))
        return cls(origin_x, origin_y, upp, tuple(image_size), warning, view.get("units", ""))

    @classmethod
    def from_dict(cls, d: dict) -> "Mapping":
        return cls(d["origin"][0], d["origin"][1], d["units_per_pixel"], tuple(d["image_size"]),
                   d.get("warning", ""), d.get("units", ""))

    def to_world(self, px: float, py: float) -> tuple[float, float]:
        return (round(self.origin_x + px * self.units_per_pixel, 6),
                round(self.origin_y - py * self.units_per_pixel, 6))

    def to_pixel(self, x: float, y: float) -> tuple[float, float]:
        return (round((x - self.origin_x) / self.units_per_pixel, 3),
                round((self.origin_y - y) / self.units_per_pixel, 3))

    def as_dict(self) -> dict:
        w, h = self.image_size
        cxw = self.to_world(w / 2.0, h / 2.0)
        d = {
            "origin": [self.origin_x, self.origin_y],
            "units_per_pixel": self.units_per_pixel,
            "image_size": [w, h],
            "image_center_world": [cxw[0], cxw[1]],
            "units": self.units,
            "how": "world = origin + (px, -py) * units_per_pixel; vw_point_to_world does it",
        }
        if self.warning:
            d["warning"] = self.warning
        return d
