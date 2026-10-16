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
    return fake_vs


@pytest.fixture(autouse=True)
def bridge(root, vs, monkeypatch):
    b = Bridge(root=root, trigger=Runner(root, vs), poll_interval=0.01, timeout=2)
    monkeypatch.setattr(app, "get_bridge", lambda: b)
    return b


def test_exec_python_returns_value_stdout_and_no_error():
    out = server.vw_exec_python("print('x')\n6*7")
    assert out == {"ok": True, "value": 42, "stdout": "x\n", "error": None, "traceback": None}


def test_exec_python_reports_errors_instead_of_raising():
    out = server.vw_exec_python("raise ValueError('bad seat')")
    assert out["ok"] is False and "bad seat" in out["error"] and "ValueError" in out["traceback"]


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
