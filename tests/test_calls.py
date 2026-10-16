import ast
import threading

import pytest
import vwmcp_bridge

from vwmcp import calls
from vwmcp.client import Bridge


class Runner:
    def __init__(self, root, vs):
        self.root, self.vs = root, vs

    def __call__(self):
        threading.Thread(
            target=vwmcp_bridge.run_pending, args=(self.root,), kwargs={"vs_module": self.vs}
        ).start()


@pytest.fixture
def bridge(root, fake_vs):
    return Bridge(root=root, trigger=Runner(root, fake_vs), poll_interval=0.01, timeout=2)


def test_vwlib_is_python39_compatible():
    # Vectorworks 2026 embeds Python 3.9; the prelude must parse there.
    ast.parse(calls.VWLIB_SOURCE, feature_version=(3, 9))


def test_call_runs_a_vwlib_function_with_json_args(bridge):
    assert calls.call(bridge, "_str", x=None) == ""


def test_call_passes_awkward_strings_safely(bridge):
    tricky = "O'Brien's \"FOH\" truss\n\\ end"
    assert calls.call(bridge, "_str", x=tricky) == tricky


def test_vw_side_exception_becomes_vwerror_with_traceback(bridge):
    with pytest.raises(calls.VWError) as e:
        calls.call(bridge, "handle", uuid="nope")
    assert "GetObjectByUuid" in e.value.traceback or "AttributeError" in str(e.value)
