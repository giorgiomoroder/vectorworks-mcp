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


def test_exec_file_runs_script_and_is_revertible(vs, tmp_path):
    script = tmp_path / "draw.py"
    script.write_text("vs.Rect(0, 1, 1, 0)\n'drawn'", encoding="utf-8")
    out = server.vw_exec_file(str(script))
    assert out["value"] == "drawn" and out["created"] == 1
    server.vw_revert_last()
    assert vs.objects == ["pre-1", "pre-2"]


def test_exec_file_missing_path_is_a_tool_error(tmp_path):
    from mcp.server.mcpserver.exceptions import ToolError

    with pytest.raises(ToolError, match="Can't read"):
        server.vw_exec_file(str(tmp_path / "nope.py"))


