"""vw_list_documents / vw_switch_document (AppleScript mocked)."""

import pytest

from vwmcp import documents


@pytest.fixture
def fake_vw(monkeypatch, tmp_path):
    monkeypatch.setattr(documents, "STATE", tmp_path / "paths.json")
    saved = tmp_path / "plan.vwx"
    saved.write_text("x")
    state = {"windows": ["Ohne Titel 3", "", "Window", "plan.vwx", "Ohne Titel 3"]}

    def fake(script, *args):
        if args:  # open <path>
            name = args[0].rsplit("/", 1)[1]
            state["windows"].remove(name)
            state["windows"].insert(0, name)
            return "ok"
        return "\n".join(state["windows"])

    monkeypatch.setattr(documents, "_osascript", fake)
    return saved


def test_parse_windows_skips_helpers_and_duplicates():
    out = documents.parse_windows("A.vwx\n\nWindow\nB\nA.vwx\n")
    assert out == {"documents": ["A.vwx", "B"], "active": "A.vwx"}
    # Vectorworks 2027 lists a window named after the app before the documents
    out = documents.parse_windows("Vectorworks\nplan.vwx\nWindow\n")
    assert out == {"documents": ["plan.vwx"], "active": "plan.vwx"}


def test_switch_by_remembered_path(fake_vw):
    documents.remember("plan.vwx", str(fake_vw))
    listed = documents.list_documents()
    assert listed["documents"] == ["Ohne Titel 3", "plan.vwx"] and listed["paths"] == {"plan.vwx": str(fake_vw)}
    out = documents.switch_document("plan")
    assert out["switched"] and out["active"] == "plan.vwx" and out["previous"] == "Ohne Titel 3"
    assert documents.switch_document("plan.vwx")["switched"] is False


def test_switch_by_path_and_errors(fake_vw):
    assert documents.switch_document(str(fake_vw))["active"] == "plan.vwx"
    with pytest.raises(documents.DocumentsError, match="unsaved"):
        documents.switch_document("Ohne Titel 3")
    with pytest.raises(documents.DocumentsError, match="not open"):
        documents.switch_document("nope")


def test_write_tools_refuse_wrong_document(monkeypatch):
    from mcp.server.mcpserver.exceptions import ToolError

    from vwmcp import app
    from vwmcp.tools import generic

    monkeypatch.setattr(app, "vw", lambda fn, **kw: "zg_testfile.vwx" if fn == "current_document" else None)
    app.require_document(None)
    app.require_document("zg_testfile")          # extension optional
    app.require_document("ZG_TESTFILE.vwx")
    with pytest.raises(ToolError, match="active document is 'zg_testfile.vwx'"):
        generic.vw_exec_python("x = 1", document="uh_vorprojekt.vwx")


def test_drawing_and_spotlight_writes_refuse_wrong_document(monkeypatch):
    from mcp.server.mcpserver.exceptions import ToolError

    from vwmcp import app
    from vwmcp.tools import drawing, spotlight

    calls = []

    def fake(fn, **kw):
        calls.append(fn)
        return "zg_testfile.vwx" if fn == "current_document" else None

    monkeypatch.setattr(app, "vw", fake)
    with pytest.raises(ToolError, match="active document"):
        drawing.vw_create_layer("New", document="other.vwx")
    with pytest.raises(ToolError, match="active document"):
        spotlight.vw_set_lighting_device_fields([{"uuid": "u", "fields": {"Channel": "1"}}],
                                                document="other.vwx")
    assert calls == ["current_document", "current_document"]  # nothing else ran
