"""Platform composite: where a flight of Stage Steps goes on a platform edge.

The platform (see vwlib.insert_stage_decks) has its corner at (x, y), extends
width*columns along `rotation` degrees and depth*rows at rotation + 90. Edges
are named in the platform's own frame: "front" is the low-y edge (y_local 0),
"back" the far edge, "left" x_local 0, "right" the far x edge. The steps
object (vwlib.insert_stage_steps) is inserted at the top centre of the
flight on the edge and, at its rotation 0, has the stage on its +y side and
descends toward -y; so its rotation is the direction that points *into* the
platform minus 90.
"""

from __future__ import annotations

import math

EDGES = ("front", "back", "left", "right")


def step_origin(x: float, y: float, width: float, depth: float, columns: int, rows: int,
                rotation: float, edge: str) -> tuple[float, float, float]:
    """(step_x, step_y, step_rotation) for the middle of `edge`."""
    if edge not in EDGES:
        raise ValueError(f"edge must be one of {', '.join(EDGES)}, not {edge!r}")
    w, d = width * columns, depth * rows
    # midpoint in the platform frame, and the steps' rotation in that frame
    local = {
        "front": ((w / 2.0, 0.0), 0.0),      # stage at +y: steps rotation 0
        "back": ((w / 2.0, d), 180.0),        # stage at -y
        "left": ((0.0, d / 2.0), 270.0),      # stage at +x: steps +y must point +x
        "right": ((w, d / 2.0), 90.0),        # stage at -x
    }
    (lx, ly), lrot = local[edge]
    rad = math.radians(rotation)
    sx = x + lx * math.cos(rad) - ly * math.sin(rad)
    sy = y + lx * math.sin(rad) + ly * math.cos(rad)
    return sx, sy, (lrot + rotation) % 360.0
