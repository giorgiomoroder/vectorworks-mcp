import threading
from pathlib import Path

import pytest
import vwmcp_bridge

from vwmcp import app
from vwmcp.tools import generic as server
from vwmcp.client import Bridge


class Runner:
    def __init__(self, root, vs):
        self.root, self.vs = root, vs

    def __call__(self):
        threading.Thread(
            target=vwmcp_bridge.run_pending, args=(self.root,), kwargs={"vs_module": self.vs}
        ).start()


@pytest.fixture
def vs(fake_vs):
    def GetRField(h, record, field):
        """Returns string description of a record field value. Definition: vs.GetRField(h, record, field)"""

    fake_vs.GetRField = GetRField
    fake_vs.GetVersionEx = lambda: (31, 3, 0, 1, 846827)
    # Minimal document: objects are uuid strings, all top-level.
    fake_vs.objects = ["pre-1", "pre-2"]
    fake_vs.ForEachObject = lambda fn, criteria: [fn(h) for h in list(fake_vs.objects)]
    fake_vs.GetObjectUuid = lambda h: h
    fake_vs.GetParent = lambda h: 0
    fake_vs.GetObjectByUuid = lambda u: u if u in fake_vs.objects else 0
    fake_vs.GetFName = lambda: "Plot.vwx"

    def Rect(*args):
        fake_vs.objects.append(f"new-{len(fake_vs.objects)}")

    def DelObject(h):
        fake_vs.objects.remove(h)

    fake_vs.Rect, fake_vs.DelObject = Rect, DelObject
    return fake_vs


@pytest.fixture(autouse=True)
def bridge(root, vs, monkeypatch):
    b = Bridge(root=root, trigger=Runner(root, vs), poll_interval=0.01, timeout=2)
    monkeypatch.setattr(app, "get_bridge", lambda: b)
    return b


@pytest.fixture(autouse=True)
def no_applescript(monkeypatch):
    """vw_ping lists the open documents with AppleScript; never run it in tests."""
    from vwmcp import documents

    monkeypatch.setattr(documents, "list_documents",
                        lambda: {"documents": ["Plot.vwx", "Other.vwx"], "active": "Plot.vwx", "paths": {}})


@pytest.fixture(autouse=True)
def journal(tmp_path, monkeypatch):
    from vwmcp.journal import Journal

    j = Journal(tmp_path / "journal.jsonl")
    monkeypatch.setattr(app, "get_journal", lambda: j)
    return j


def test_exec_python_returns_value_stdout_and_no_error():
    out = server.vw_exec_python("print('x')\n6*7")
    assert out == {"ok": True, "value": 42, "stdout": "x\n", "error": None,
                   "traceback": None, "created": 0, "revertable": False}


def test_exec_python_read_only_skips_tracking():
    out = server.vw_exec_python("print('x')\n6*7", modifies_document=False)
    assert out == {"ok": True, "value": 42, "stdout": "x\n", "error": None, "traceback": None}


def test_exec_python_reports_errors_instead_of_raising():
    out = server.vw_exec_python("raise ValueError('bad seat')")
    assert out["ok"] is False and "bad seat" in out["error"] and "ValueError" in out["traceback"]


def test_exec_python_result_variable_wins():
    assert server.vw_exec_python("result = {'a': 1}\n5")["value"] == {"a": 1}


def test_exec_python_records_created_objects_and_revert_deletes_them(vs):
    out = server.vw_exec_python("vs.Rect(0, 0, 1, 1)\nvs.Rect(1, 1, 2, 2)")
    assert out["created"] == 2 and out["revertable"] is True
    rev = server.vw_revert_last()
    assert rev["reverted_tool"] == "vw_exec_python" and rev["deleted"] == 2
    assert vs.objects == ["pre-1", "pre-2"]


def test_exec_python_failing_halfway_still_revertable(vs):
    out = server.vw_exec_python("vs.Rect(0, 0, 1, 1)\nraise RuntimeError('oops')")
    assert out["ok"] is False and out["created"] == 1
    server.vw_revert_last()
    assert vs.objects == ["pre-1", "pre-2"]


def test_exec_python_warns_when_existing_objects_deleted(vs):
    out = server.vw_exec_python("vs.DelObject('pre-1')\nvs.Rect(0, 0, 1, 1)")
    assert out["created"] == 1 and "1 pre-existing" in out["warning"]


def test_exec_python_without_created_objects_is_a_revert_barrier():
    from mcp.server.mcpserver.exceptions import ToolError

    server.vw_exec_python("x = 1")
    with pytest.raises(ToolError, match="can't be reverted"):
        server.vw_revert_last()


def test_exec_python_nested_new_objects_are_not_listed_twice(vs):
    # A new group containing new objects: only the group is recorded.
    vs.GetParent = lambda h: "new-2" if h == "new-3" else 0
    out = server.vw_exec_python("vs.Rect(0, 0, 1, 1)\nvs.Rect(0, 0, 1, 1)")
    assert out["created"] == 1


def test_ping_reports_versions_and_document():
    out = server.vw_ping()
    assert out["document"] == "Plot.vwx"
    assert out["vectorworks_version"] == "31.3.0"
    assert out["bridge_version"] == app.EXPECTED_BRIDGE_VERSION
    assert "warning" not in out


def test_ping_warns_on_bridge_version_mismatch(monkeypatch):
    monkeypatch.setattr(app, "EXPECTED_BRIDGE_VERSION", "9.9.9")
    out = server.vw_ping()
    assert "9.9.9" in out["warning"] and "install" in out["warning"]


def test_vs_lookup_searches_names_and_docs():
    out = server.vw_vs_lookup("record field")
    assert out[0]["name"] == "GetRField"
    assert "Definition" in out[0]["doc"]


def test_packaged_bridge_matches_repo_copy():
    repo = Path(__file__).resolve().parents[1] / "vw-plugin" / "vwmcp" / "vwmcp_bridge.py"
    assert app.bundled_bridge_source() == repo.read_text()
    assert f'BRIDGE_VERSION = "{app.EXPECTED_BRIDGE_VERSION}"' in repo.read_text()


def test_ping_warns_on_untested_vectorworks_version(vs):
    vs.GetVersionEx = lambda: (30, 4, 0, 1, 800000)  # Vectorworks 2025
    out = server.vw_ping()
    assert "2026" in out["warning"] and "30.4.0" in out["warning"]


def test_ping_combines_warnings(vs, monkeypatch):
    vs.GetVersionEx = lambda: (30, 4, 0, 1, 800000)
    monkeypatch.setattr(app, "EXPECTED_BRIDGE_VERSION", "9.9.9")
    out = server.vw_ping()
    assert "9.9.9" in out["warning"] and "2026" in out["warning"]


def test_exec_python_runs_a_script_file_and_is_revertible(vs, tmp_path):
    # vw_exec_file was folded into vw_exec_python(path=...) (2026-11-21).
    script = tmp_path / "draw.py"
    script.write_text("vs.Rect(0, 1, 1, 0)\n'drawn'", encoding="utf-8")
    out = server.vw_exec_python(path=str(script))
    assert out["value"] == "drawn" and out["created"] == 1
    server.vw_revert_last()
    assert vs.objects == ["pre-1", "pre-2"]


def test_exec_python_needs_exactly_one_of_code_and_path(tmp_path):
    from mcp.server.mcpserver.exceptions import ToolError

    with pytest.raises(ToolError, match="Can't read"):
        server.vw_exec_python(path=str(tmp_path / "nope.py"))
    with pytest.raises(ToolError, match="either code or path"):
        server.vw_exec_python()
    with pytest.raises(ToolError, match="either code or path"):
        server.vw_exec_python(code="1", path=str(tmp_path / "x.py"))




def test_ping_lists_open_documents():
    out = server.vw_ping()
    assert out["documents"] == ["Plot.vwx", "Other.vwx"]
    assert out["document"] == "Plot.vwx"


def test_ping_document_listing_failure_is_soft(monkeypatch):
    from vwmcp import documents

    def boom():
        raise documents.DocumentsError("osascript failed")

    monkeypatch.setattr(documents, "list_documents", boom)
    out = server.vw_ping()
    assert "documents" not in out
    assert "osascript failed" in out["documents_error"]
    assert out["document"] == "Plot.vwx"


def test_instructions_tell_claude_to_check_documents_first():
    assert "vw_list_documents" in app.INSTRUCTIONS
    assert "document=" in app.INSTRUCTIONS


# ---- vw_doctor ------------------------------------------------------------------

def _checks(bridge_ok=True):
    from vwmcp.doctor import Check

    return [Check("version", True, "Vectorworks 2026"),
            Check("bridge", bridge_ok, "0.1.0 at /x" if bridge_ok else "not installed at /x",
                  "" if bridge_ok else "Run the installer again, or: vwmcp install-plugin"),
            Check("vectorworks", None, "not running")]


def test_doctor_reports_checks_without_fixing(monkeypatch):
    from vwmcp import doctor

    seen = {}

    def fake_run(**kw):
        seen.update(kw)
        return _checks(bridge_ok=False)

    monkeypatch.setattr(doctor, "run_checks", fake_run)
    out = server.vw_doctor()
    assert seen["fix"] is False
    assert out["ok"] is False
    assert out["checks"][1] == {"name": "bridge", "ok": False, "detail": "not installed at /x",
                                "fix": "Run the installer again, or: vwmcp install-plugin"}
    assert out["checks"][2]["ok"] is None
    assert "installed" not in out
    assert "fix=True" in out["next_step"]


def test_doctor_fix_installs_missing_bridge(monkeypatch, tmp_path):
    from vwmcp import doctor, install

    calls = []
    monkeypatch.setattr(doctor, "run_checks", lambda **kw: (calls.append(("run", kw["fix"])) or _checks(bridge_ok=False)) if not calls else _checks(True))
    monkeypatch.setattr(install, "plugin_dir", lambda version: tmp_path / "Plug-ins" / "vwmcp")
    monkeypatch.setattr(install, "install_plugin", lambda target, home=None: calls.append(("install", target, home)) or "Installed")
    out = server.vw_doctor(fix=True)
    assert calls[0] == ("run", True)
    assert calls[1][0] == "install" and calls[1][1] == tmp_path / "Plug-ins" / "vwmcp"
    assert calls[1][2] == app.get_bridge().root
    assert out["installed"] == "Installed"
    assert out["ok"] is True  # re-checked after the install
    assert install.MENU_STEP in out["next_step"]


def test_doctor_fix_does_not_install_when_bridge_is_fine(monkeypatch):
    from vwmcp import doctor, install

    monkeypatch.setattr(doctor, "run_checks", lambda **kw: _checks(True))
    monkeypatch.setattr(install, "install_plugin", lambda *a, **k: pytest.fail("must not install"))
    out = server.vw_doctor(fix=True)
    assert out["ok"] is True and "installed" not in out


# ---- screenshot mapping -------------------------------------------------------

def _fake_capture(tmp_path):
    import struct, zlib
    from vwmcp import screenshot as ss

    ihdr = struct.pack(">IIBBBBB", 500, 400, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr
           + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr)))
    path = tmp_path / "shot.png"
    path.write_bytes(png)
    window = ss.Window(id=1, title="Plot.vwx", layer=0, x=100, y=50, width=1000, height=800)
    return lambda **kw: (path, window, [])


def test_screenshot_with_mapping_adds_world_coordinates(monkeypatch, tmp_path):
    import json
    from vwmcp import screenshot as ss

    from vwmcp import viewmap

    monkeypatch.setattr(ss, "screenshot", _fake_capture(tmp_path))
    monkeypatch.setattr(viewmap, "canvas_bbox", lambda path: (50, 40, 450, 360))  # centre (250, 200)
    monkeypatch.setattr(viewmap, "display_points_per_inch", lambda: 96.0)
    monkeypatch.setattr(server, "vw", lambda fn, **kw: {
        "center": [10.0, 20.0], "zoom": 100.0, "layer_scale": 48.0, "units_per_inch": 1.0,
        "projection": 6, "top_plan": True, "units": '"'})
    out = server.vw_screenshot(mapping=True)
    meta = json.loads(out[1].text)
    # image 500 px for a 1000 pt window: 0.5 px/pt; 96 ppi * 0.5 / 48 = 1 px per inch
    assert meta["mapping"]["units_per_pixel"] == pytest.approx(1.0)
    assert meta["mapping"]["image_center_world"] == [pytest.approx(10.0), pytest.approx(20.0)]
    # the pure follow-up uses the last mapping
    assert server.vw_point_to_world(260, 190) == {"x": 20.0, "y": 30.0, "units": '"'}


def test_screenshot_mapping_failure_is_soft(monkeypatch, tmp_path):
    import json
    from mcp.server.mcpserver.exceptions import ToolError
    from vwmcp import screenshot as ss

    monkeypatch.setattr(ss, "screenshot", _fake_capture(tmp_path))

    def boom(fn, **kw):
        raise ToolError("Vectorworks has not answered")

    monkeypatch.setattr(server, "vw", boom)
    monkeypatch.setattr(server, "_LAST_MAPPING", None)
    out = server.vw_screenshot(mapping=True)
    meta = json.loads(out[1].text)
    assert "mapping" not in meta and "not answered" in meta["mapping_error"]
    with pytest.raises(ToolError, match="mapping=True"):
        server.vw_point_to_world(1, 1)


# ------------------------------------------------- document guard, allow_dialogs

from mcp.server.mcpserver.exceptions import ToolError


@pytest.fixture
def bridge_with_fake(bridge, vs):
    return bridge, vs


@pytest.fixture(autouse=True)
def clear_document_guard():
    """Tests set app.DOCUMENT in the main thread's context; never let it leak."""
    yield
    app.DOCUMENT.set(None)


def test_require_document_guards_every_later_call_in_the_request(bridge_with_fake):
    bridge, fake_vs = bridge_with_fake
    fake_vs.GetFPathName = lambda: "/x/Plot.vwx"
    bridge.run("1")  # learn the version
    app.require_document("Plot")  # matches: no error, sets the guard
    assert app.DOCUMENT.get() == {"name": "Plot"}
    assert app.vw("current_document") == "Plot.vwx"
    # another document: the pre-check refuses with a ToolError naming both
    with pytest.raises(ToolError, match="Plot.vwx"):
        app.require_document("Other")


def test_require_document_without_pre_check_fails_inside_the_job(bridge_with_fake):
    bridge, fake_vs = bridge_with_fake
    fake_vs.GetFPathName = lambda: "/x/Plot.vwx"
    bridge.run("1")
    app.DOCUMENT.set({"name": "Other"})  # as if the user switched after the pre-check
    with pytest.raises(ToolError, match="not 'Other'"):
        app.vw("current_document")


def test_exec_python_can_allow_dialogs(bridge_with_fake, monkeypatch):
    bridge, fake_vs = bridge_with_fake
    seen = {}

    def fake_run(code, **kw):
        seen.update(kw)
        return {"ok": True, "stdout": "", "value": {"created": [], "document": "Plot.vwx",
                                                   "value": None, "stdout": ""}}

    monkeypatch.setattr(bridge, "run", fake_run)
    server.vw_exec_python("vs.EditProperties(None)", allow_dialogs=True)  # tracked path (exec_tracked)
    assert seen["allow_dialogs"] is True
    seen.clear()
    server.vw_exec_python("1", modifies_document=False, allow_dialogs=True)  # raw path (_run_raw)
    assert seen["allow_dialogs"] is True
