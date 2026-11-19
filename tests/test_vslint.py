"""Tests for the pre-flight linter (vs.* signatures from the bundled API table)."""

from pathlib import Path

import pytest

from vwmcp import vslint
from vwmcp.tools import generic as server
from test_server import bridge, journal, vs  # noqa: F401  (fixtures)

ROOT = Path(__file__).resolve().parents[1]


def _msgs(code):
    r = vslint.lint(code)
    return [e["message"] for e in r["errors"]], [w["message"] for w in r["warnings"]]


def test_syntax_error_is_caught():
    errors, _ = _msgs("x = (1,\nprint(x")
    assert errors and errors[0].startswith("SyntaxError")


def test_wrong_argument_count():
    errors, _ = _msgs("vs.SetWallStyle(w, 'W1')")
    assert "vs.SetWallStyle takes 4 argument(s), got 2" in errors[0]


def test_points_as_tuple_or_numbers():
    assert _msgs("vs.Wall((0, 0), (1, 0))") == ([], [])
    assert _msgs("vs.MoveTo(0, 0); vs.LineTo(1, 0)") == ([], [])
    assert _msgs("vs.Locus(0, 0)") == ([], [])


def test_deprecated_call_is_an_error():
    errors, _ = _msgs("s = vs.GetLS(h)")
    assert "deprecated" in errors[0] and "GetLSN" in errors[0]


def test_unknown_name_is_a_warning_and_aliases():
    errors, warnings = _msgs("import vs as v\nv.NoSuchCall(1)")
    assert errors == [] and "NoSuchCall" in warnings[0]


@pytest.mark.parametrize("rel", ["src/vwmcp/vwlib.py", "vw-plugin/vwmcp/vwmcp_bridge.py"])
def test_code_we_send_to_vectorworks_is_clean(rel):
    report = vslint.lint((ROOT / rel).read_text(encoding="utf-8"), rel)
    assert report["errors"] == [], vslint.format_report(report, rel)


def test_exec_python_refuses_before_sending(bridge):
    with pytest.raises(Exception) as e:
        server.vw_exec_python("vs.SetWallStyle(w, 'W1')")
    assert "Not sent to Vectorworks" in str(e.value)


def test_vw_lint_tool(tmp_path):
    f = tmp_path / "s.py"
    f.write_text("vs.Rect((0,0))\n", encoding="utf-8")
    out = server.vw_lint(path=str(f))
    assert out["ok"] is False and "vs.Rect" in out["errors"][0]["message"]


def test_build_table_from_docstrings():
    from vwmcp import vslint

    docs = {
        "GetLS": "Deprecated - will generate error. Use GetLSN instead. Definition: INTEGER = vs.GetLS(h)",
        "GetBBox": "Returns the bounding box ... on the screen plane. Definition: (p1, p2) = vs.GetBBox(h)",
        "Poly": "Draws a polygon with specified vertices.",
        "ActLayer": "Returns a handle to the active layer. Definition: HANDLE = vs.ActLayer()",
        "OldThing": "Deprecated - will generate error.",
    }
    t = vslint.build_table(docs, "2027 (32.1.1)")
    assert t["signatures"] == {"GetBBox": ["h"], "ActLayer": []}
    assert t["deprecated"] == {"GetLS": "GetLSN", "OldThing": ""}
    assert t["known_without_signature"] == ["Poly"]
    assert t["vectorworks"] == "2027 (32.1.1)"


def test_exec_python_is_linted_before_sending(monkeypatch):
    import pytest
    from mcp.server.mcpserver.exceptions import ToolError

    from vwmcp import app
    from vwmcp.tools import generic

    sent = []
    monkeypatch.setattr(app, "vw", lambda fn, **kw: None)
    monkeypatch.setattr(generic, "_run_raw", lambda code, timeout=None: sent.append(code) or {"ok": True, "value": 1})
    with pytest.raises(ToolError, match="Script Errors"):
        generic.vw_exec_python("vs.GetLS(h)", modifies_document=False)
    with pytest.raises(ToolError, match="SyntaxError"):
        generic.vw_exec_python("def (:", modifies_document=False)
    assert sent == []
    out = generic.vw_exec_python("vs.NoSuchThing(1)", modifies_document=False)
    assert out["ok"] and out["lint_warnings"] and "NoSuchThing" in out["lint_warnings"][0]
    generic.vw_exec_python("vs.GetLS(h)", modifies_document=False, lint=False)
    assert sent[-1] == "vs.GetLS(h)"


def test_vw_lint_tool_reports(tmp_path):
    from vwmcp.tools import generic

    assert generic.vw_lint(code="vs.ActLayer()")["ok"]
    bad = tmp_path / "s.py"
    bad.write_text("vs.ActLayer(1)\n")
    rep = generic.vw_lint(path=str(bad))
    assert not rep["ok"] and rep["errors"][0]["line"] == 1
