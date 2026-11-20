"""The two data tables shipped beside the bridge (see NOTICE for their origin)."""

import ast
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "src" / "vwmcp" / "data"
BRIDGE = Path(__file__).resolve().parents[1] / "vw-plugin" / "vwmcp" / "vwmcp_bridge.py"


def test_vs_types_table_has_codes_and_params():
    d = json.loads((DATA / "vs_types.json").read_text(encoding="utf-8"))
    assert "Keystone" in d["_meta"]["source"]
    f = d["f"]
    assert len(f) > 3000
    assert f["Rect"] == {"t": "PP", "a": "p1:POINT, p2:POINT"}
    assert f["SetRField"]["t"] == "HSSS"
    assert all(set(e["t"]) <= set("HRIBSPQVCF") for e in f.values())
    assert all("t" in e and "a" in e for e in f.values())


def test_vs_safety_table_lists_the_known_crashers():
    d = json.loads((DATA / "vs_safety.json").read_text(encoding="utf-8"))
    assert "stevenmorgan94" in d["source"]
    assert "UprString" in d["crash"] and "TBB_AttachRecords" in d["crash"]
    assert "RetrieveOpenGLPrefs" in d["hang"]
    assert "ProgressDlgYield" in d["document_level"]
    assert "EditProperties" in d["interactive"]
    assert d["arg_check"]["ApplyLightInfoRecord"] == ["wrong-object-type:crash"]
    assert not (set(d["crash"]) & set(d["interactive"]))


def test_bridge_stays_python_3_9():
    # Vectorworks 2026 embeds Python 3.9.2: no match statements, no X | Y types.
    ast.parse(BRIDGE.read_text(encoding="utf-8"), str(BRIDGE), feature_version=(3, 9))
