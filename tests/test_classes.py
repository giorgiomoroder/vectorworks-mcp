"""Class standards: data file, validation and the apply plan (pure)."""

import pytest

from vwmcp import classes


def test_spotlight_standard_loads_and_is_valid():
    spec = classes.load("spotlight")
    names = [c["name"] for c in spec]
    assert len(names) >= 12 and len(set(names)) == len(names)
    assert "Lighting-Instruments" in names and "Rigging-Truss" in names
    for c in spec:
        assert len(c["pen"]) == 3 and all(0 <= v <= 255 for v in c["pen"])
        assert c["fill"] is None or (len(c["fill"]) == 3 and all(0 <= v <= 255 for v in c["fill"]))
        assert 1 <= c["line_weight"] <= 100  # mils
        assert c["description"]


def test_unknown_standard_lists_the_known_ones():
    with pytest.raises(KeyError, match="spotlight"):
        classes.load("nope")
    assert classes.standards() == ["spotlight"]


def test_plan_creates_missing_and_leaves_existing_alone_by_default():
    spec = [{"name": "A", "pen": [255, 0, 0], "fill": None, "line_weight": 5, "description": "a"},
            {"name": "B", "pen": [0, 0, 255], "fill": [200, 200, 200], "line_weight": 10, "description": "b"}]
    existing = {"B": {"exists": True, "pen": [0, 0, 0], "fill": None, "line_weight": 5}}
    plan = classes.plan(spec, existing)
    assert [c["name"] for c in plan["create"]] == ["A"]
    assert plan["restyle"] == []
    assert plan["unchanged"] == ["B"]


def test_plan_overwrite_restyles_existing_classes_that_differ():
    spec = [{"name": "B", "pen": [0, 0, 255], "fill": [200, 200, 200], "line_weight": 10, "description": "b"},
            {"name": "C", "pen": [1, 2, 3], "fill": None, "line_weight": 7, "description": "c"}]
    existing = {"B": {"exists": True, "pen": [0, 0, 0], "fill": None, "line_weight": 5},
                "C": {"exists": True, "pen": [1, 2, 3], "fill": None, "line_weight": 7}}
    plan = classes.plan(spec, existing, overwrite=True)
    assert [c["name"] for c in plan["restyle"]] == ["B"]
    assert plan["unchanged"] == ["C"]


def test_plan_only_filters_by_exact_name_or_prefix():
    spec = classes.load("spotlight")
    plan = classes.plan(spec, {}, only=["Lighting-Instruments", "Stage"])
    names = [c["name"] for c in plan["create"]]
    assert "Lighting-Instruments" in names
    assert all(n == "Lighting-Instruments" or n.startswith("Stage") for n in names)
    assert len(names) > 1
    with pytest.raises(KeyError, match="Nope"):
        classes.plan(spec, {}, only=["Nope"])
