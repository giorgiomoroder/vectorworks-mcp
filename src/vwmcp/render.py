"""Draw exported layer geometry to a PNG, without the screen.

`vw_export_geometry` gives exact 2D geometry and attributes; this module
rasterizes it with the standard library only (no Pillow), so a drawing can
be checked visually even when the Vectorworks window shows something else.
It is a check picture, not a plot: curved polyline vertices are drawn as
corners, hatches and patterns are not filled, dash styles are solid, and
texts are only marked at their origin.
"""

from __future__ import annotations

import math
import struct
import zlib

WHITE = (255, 255, 255)
TEXT_MARK = (200, 0, 160)
BOX_GRAY = (150, 150, 150)


class Canvas:
    """RGB pixel buffer with antialiased lines and even-odd polygon fill."""

    def __init__(self, width: int, height: int, background: tuple[int, int, int] = WHITE):
        self.w, self.h = int(width), int(height)
        self.buf = bytearray(bytes(background) * (self.w * self.h))

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        i = (y * self.w + x) * 3
        return tuple(self.buf[i:i + 3])

    def _blend(self, x: int, y: int, color, alpha: float) -> None:
        if 0 <= x < self.w and 0 <= y < self.h and alpha > 0:
            i = (y * self.w + x) * 3
            a = min(alpha, 1.0)
            for k in range(3):
                self.buf[i + k] = int(self.buf[i + k] * (1 - a) + color[k] * a + 0.5)

    def _wu(self, x0: float, y0: float, x1: float, y1: float, color) -> None:
        steep = abs(y1 - y0) > abs(x1 - x0)
        if steep:
            x0, y0, x1, y1 = y0, x0, y1, x1
        if x0 > x1:
            x0, x1, y0, y1 = x1, x0, y1, y0
        dx = x1 - x0
        grad = (y1 - y0) / dx if dx else 0.0
        limit = self.h if steep else self.w
        xa, xb = max(int(math.floor(x0)), 0), min(int(math.ceil(x1)), limit - 1)
        y = y0 + grad * (xa - x0)
        for x in range(xa, xb + 1):
            yi = int(math.floor(y))
            frac = y - yi
            if steep:
                self._blend(yi, x, color, 1 - frac)
                self._blend(yi + 1, x, color, frac)
            else:
                self._blend(x, yi, color, 1 - frac)
                self._blend(x, yi + 1, color, frac)
            y += grad

    def line(self, x0: float, y0: float, x1: float, y1: float, color, width: int = 1) -> None:
        if max(x0, x1) < -2 or max(y0, y1) < -2 or min(x0, x1) > self.w + 2 or min(y0, y1) > self.h + 2:
            return
        length = math.hypot(x1 - x0, y1 - y0)
        if width <= 1 or length == 0:
            self._wu(x0, y0, x1, y1, color)
            return
        nx, ny = -(y1 - y0) / length * width / 2, (x1 - x0) / length * width / 2
        quad = [(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)]
        self.fill(quad, color)
        for (ax, ay), (bx, by) in zip(quad, quad[1:] + quad[:1]):
            self._wu(ax, ay, bx, by, color)

    def fill(self, points, color) -> None:
        """Even-odd scanline fill of one closed ring (pixel centers)."""
        if len(points) < 3:
            return
        ys = [p[1] for p in points]
        row = bytes(color)
        n = len(points)
        for y in range(max(int(math.ceil(min(ys) - 0.5)), 0), min(int(math.floor(max(ys) - 0.5)), self.h - 1) + 1):
            yc = y + 0.5
            xs = []
            for i in range(n):
                (ax, ay), (bx, by) = points[i], points[(i + 1) % n]
                if (ay <= yc) != (by <= yc):
                    xs.append(ax + (yc - ay) * (bx - ax) / (by - ay))
            xs.sort()
            for a, b in zip(xs[0::2], xs[1::2]):
                xa, xb = max(int(math.ceil(a - 0.5)), 0), min(int(math.floor(b - 0.5)), self.w - 1)
                if xb >= xa:
                    i = (y * self.w + xa) * 3
                    self.buf[i:i + (xb - xa + 1) * 3] = row * (xb - xa + 1)

    def png(self) -> bytes:
        stride = self.w * 3
        raw = b"".join(b"\x00" + bytes(self.buf[r * stride:(r + 1) * stride]) for r in range(self.h))

        def chunk(tag: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

        head = struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0)
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def _rgb(hex_color: str | None, default=(0, 0, 0)) -> tuple[int, int, int]:
    try:
        h = hex_color.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (AttributeError, ValueError, IndexError):
        return default


def arc_points(center, radius: float, start: float, sweep: float) -> list[list[float]]:
    """Polyline along an arc (angles in degrees, counterclockwise from +x)."""
    steps = max(int(abs(sweep) / 6) + 1, 2)
    return [[center[0] + radius * math.cos(math.radians(start + sweep * i / steps)),
             center[1] + radius * math.sin(math.radians(start + sweep * i / steps))]
            for i in range(steps + 1)]


def outline(obj: dict) -> tuple[list[list[float]], bool] | None:
    """World-space path of one exported object and whether it is closed."""
    t = obj.get("type")
    if t == "Arc" and "center" in obj and obj.get("radius"):
        sweep = obj.get("sweep", 360.0)
        return arc_points(obj["center"], obj["radius"], obj.get("start_angle", 0.0), sweep), abs(sweep) >= 360
    pts = obj.get("points")
    if pts and len(pts) >= 2:
        return pts, bool(obj.get("closed")) and len(pts) > 2
    box = obj.get("bbox_view")
    if box:
        (x0, y0), (x1, y1) = box
        if t == "Oval":
            cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, abs(x1 - x0) / 2, abs(y1 - y0) / 2
            return [[cx + rx * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a))]
                    for a in range(0, 360, 8)], True
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], True
    return None


def extent(layers: list[dict]) -> list[float] | None:
    xs, ys = [], []
    for data in layers:
        for obj in data["objects"]:
            path = outline(obj)
            for p in (path[0] if path else []):
                xs.append(p[0])
                ys.append(p[1])
            if "origin" in obj:
                xs.append(obj["origin"][0])
                ys.append(obj["origin"][1])
    return [min(xs), min(ys), max(xs), max(ys)] if xs else None


def _pen_width(weight) -> int:
    try:
        w = float(weight)
    except (TypeError, ValueError):
        return 1
    return 1 if w < 10 else 2 if w < 20 else 3


def render(layers: list[dict], bbox: list[float] | None = None, max_size: int = 1600,
           fills: bool = True) -> tuple[bytes, dict]:
    """PNG of the exported layers (drawn in the given order) and what it shows.

    bbox: [x_min, y_min, x_max, y_max] in document units; default: everything.
    All fills are painted first and all lines on top, so translucent area
    polygons can't hide linework (object opacity is not exported).
    """
    if bbox is None:
        full = extent(layers)
        if full is None:
            raise ValueError("nothing to draw: the layers have no geometry")
        mx, my = (full[2] - full[0]) * 0.03 or 1.0, (full[3] - full[1]) * 0.03 or 1.0
        bbox = [full[0] - mx, full[1] - my, full[2] + mx, full[3] + my]
    x0, y0, x1, y1 = bbox
    if not (x1 > x0 and y1 > y0):
        raise ValueError("bbox must be [x_min, y_min, x_max, y_max] with positive size")
    scale = max_size / max(x1 - x0, y1 - y0)
    width, height = max(int(round((x1 - x0) * scale)), 1), max(int(round((y1 - y0) * scale)), 1)
    cv = Canvas(width, height)

    def px(p):
        return (p[0] - x0) * scale, (y1 - p[1]) * scale

    drawn = texts = 0
    paths = []
    for data in layers:
        for obj in data["objects"]:
            if obj.get("type") == "Text" and "origin" in obj:
                paths.append(("text", obj, None, False))
                continue
            path = outline(obj)
            if path:
                paths.append(("path", obj, [px(p) for p in path[0]], path[1]))
    if fills:
        for kind, obj, pts, closed in paths:
            fill = (obj.get("attrs") or {}).get("fill") or {}
            if kind == "path" and closed and fill.get("pattern") in (1, 2):
                cv.fill(pts, _rgb(fill.get("back" if fill["pattern"] == 1 else "fore"), WHITE))
    for kind, obj, pts, closed in paths:
        if kind == "text":
            cx, cy = px(obj["origin"])
            cv.line(cx - 4, cy, cx + 4, cy, TEXT_MARK)
            cv.line(cx, cy - 4, cx, cy + 4, TEXT_MARK)
            texts += 1
            continue
        pen = (obj.get("attrs") or {}).get("pen") or {}
        if pen.get("style") == 0:
            continue
        boxed = "points" not in obj and obj.get("type") not in ("Rectangle", "Oval", "Arc", "Rounded Rectangle")
        color = BOX_GRAY if boxed else _rgb(pen.get("color"))
        w = 1 if boxed else _pen_width(pen.get("weight"))
        segs = list(zip(pts, pts[1:] + pts[:1])) if closed else list(zip(pts, pts[1:]))
        for (ax, ay), (bx, by) in segs:
            cv.line(ax, ay, bx, by, color, w)
        drawn += 1
    info = {"bbox": [x0, y0, x1, y1], "size": [width, height], "pixels_per_unit": scale,
            "objects_drawn": drawn, "texts_marked": texts,
            "layers": [d.get("layer") for d in layers]}
    return cv.png(), info
