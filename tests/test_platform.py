"""Platform composite: where the steps go for a given platform edge (pure math)."""

import pytest

from vwmcp import platform


def approx(pair):
    return (pytest.approx(pair[0], abs=1e-9), pytest.approx(pair[1], abs=1e-9))


# a 2 x 1 platform of 4x8 decks at (10, 20): spans x 10..18, y 20..28 at rotation 0
P = dict(x=10, y=20, width=4, depth=8, columns=2, rows=1, rotation=0)


def test_front_edge_is_the_low_y_edge_steps_descend_away():
    sx, sy, rot = platform.step_origin(edge="front", **P)
    assert (sx, sy) == approx((14, 20)) and rot == pytest.approx(0)


def test_back_edge():
    sx, sy, rot = platform.step_origin(edge="back", **P)
    assert (sx, sy) == approx((14, 28)) and rot == pytest.approx(180)


def test_left_and_right_edges():
    assert platform.step_origin(edge="left", **P)[:2] == approx((10, 24))
    assert platform.step_origin(edge="left", **P)[2] == pytest.approx(270)
    assert platform.step_origin(edge="right", **P)[:2] == approx((18, 24))
    assert platform.step_origin(edge="right", **P)[2] == pytest.approx(90)


def test_rotation_turns_edge_and_steps_together():
    # platform rotated 90: extends +y from the corner (width along +y), depth toward -x
    sx, sy, rot = platform.step_origin(edge="front", **{**P, "rotation": 90})
    assert (sx, sy) == approx((10, 24)) and rot == pytest.approx(90)


def test_unknown_edge():
    with pytest.raises(ValueError, match="front"):
        platform.step_origin(edge="top", **P)
