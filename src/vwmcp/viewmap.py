"""Map screenshot pixels to drawing coordinates and back.

The numbers come from one small job in Vectorworks (`vwlib.view_mapping`):
the view centre in drawing units, and where that point plus one unit along
x and along y land on screen (`vs.ModelPt2DToScreenPt`). That gives pixels
per drawing unit and the centre's screen position without guessing dpi,
zoom or the Retina factor. The captured PNG may be smaller than the window
(`max_width`), so the image scale is read from the PNG header.

Only exact in Top/Plan (an orthogonal projection of the screen plane); in a
3D view the mapping is flagged and still returned for the screen plane.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path


def png_size(path: Path) -> tuple[int, int]:
    head = Path(path).read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError(f"{path}: not a PNG file")
    return struct.unpack(">II", head[16:24])


@dataclass(frozen=True)
class Mapping:
    origin_x: float          # drawing x at image pixel (0, 0)
    origin_y: float
    units_per_pixel: float   # drawing units per image pixel (x and y, isotropic)
    image_size: tuple[int, int]
    warning: str = ""
    units: str = ""

    @classmethod
    def from_view(cls, view: dict, window: dict, image_size: tuple[int, int], units: str = "") -> "Mapping":
        cx, cy = view["center"]
        sx, sy = view["center_screen"]
        ux, uy = view["unit_x_screen"]
        vx, vy = view["unit_y_screen"]
        px_per_unit = ux - sx            # screen px for +1 unit of x
        py_per_unit = vy - sy            # screen px for +1 unit of y (negative: screen y grows downward)
        if abs(px_per_unit) < 1e-9 or abs(py_per_unit) < 1e-9:
            raise ValueError("view mapping is degenerate (zoom or projection gave no pixel size)")
        scale = image_size[0] / float(window["width"])  # image px per screen px
        upp = 1.0 / (abs(px_per_unit) * scale)
        # image pixel of the view centre
        icx = (sx - window["x"]) * scale
        icy = (sy - window["y"]) * scale
        origin_x = cx - icx * upp
        origin_y = cy + icy * upp  # image y down = drawing y down
        warning = "" if view.get("top_plan", True) else (
            "View is not Top/Plan: the mapping is for the screen plane only (projection %s)."
            % view.get("projection"))
        return cls(origin_x, origin_y, upp, tuple(image_size), warning, units)

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
