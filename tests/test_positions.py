"""summarize_positions is executed inside Vectorworks; load vwlib with a fake vs."""
import types

from vwmcp import vwlib


def load(fake_vs):
    mod = types.ModuleType("vwlib_live")
    mod.vs = fake_vs
    exec(open(vwlib.__file__, encoding="utf-8").read(), mod.__dict__)
    return mod


def row(position, inst="Robin Forte", channel="101", address="1/1"):
    return {"Position": position, "Inst Type": inst, "Channel": channel,
            "UniverseAddress": address}


def test_summary_per_position_name(fake_vs):
    m = load(fake_vs)
    rows = [row("K C", "Roxx", "401", "14/1"), row("K C", "Roxx", "402", "14/82"),
            row("K C", "MAC Ultra", "438", "15/1"), row("K C", "MAC Ultra", "x", ""),
            row("LX 1", channel="101", address="1/1"), row("", "Hazer", "801", "21/501")]
    out = m.summarize_positions(rows, named={"LX 1"})
    assert [p["name"] for p in out] == ["K C", "LX 1"]
    kc = out[0]
    assert kc["has_object"] is False and kc["device_count"] == 4
    assert list(kc["inst_types"].items()) == [("Roxx", 2), ("MAC Ultra", 2)]
    assert kc["universes"] == [14, 15] and kc["channels"] == [401, 438] and kc["unpatched"] == 1
    lx = out[1]
    assert lx["has_object"] is True and lx["channels"] == [101, 101] and lx["universes"] == [1]


def test_zero_address_counts_as_unpatched_and_channels_can_be_none(fake_vs):
    m = load(fake_vs)
    out = m.summarize_positions([row("L 1", channel="", address="0/0")], named=set())
    assert out == [{"name": "L 1", "has_object": False, "device_count": 1,
                    "inst_types": {"Robin Forte": 1}, "universes": [], "channels": None,
                    "unpatched": 1}]


def test_names_sort_naturally(fake_vs):
    m = load(fake_vs)
    out = m.summarize_positions([row("LX 10"), row("LX 2"), row("K SL")], named=set())
    assert [p["name"] for p in out] == ["K SL", "LX 2", "LX 10"]
