import pytest

from vwmcp.client import TriggerError
from vwmcp.trigger import MacTrigger, parse_etime


class FakeProc:
    def __init__(self, done=True):
        self.done = done

    def poll(self):
        return 0 if self.done else None


def make(root, uptime, procs=None):
    procs = [] if procs is None else procs

    def spawn(args):
        procs.append(args)
        return FakeProc(done=False)

    return MacTrigger(root, app="Vectorworks 2026", uptime=lambda: uptime, spawn=spawn), procs


def test_refuses_when_vectorworks_not_running(root):
    t, procs = make(root, uptime=None)
    with pytest.raises(TriggerError, match="not running"):
        t()
    assert procs == []


def test_refuses_while_vectorworks_is_still_starting(root):
    # Scripts sent during launch crash Vectorworks 2026.
    t, procs = make(root, uptime=5)
    with pytest.raises(TriggerError, match="starting"):
        t()
    assert procs == []


def test_sends_menu_command_via_vectorscript_file(root):
    t, procs = make(root, uptime=600)
    t()
    (args,) = procs
    assert args[0] == "osascript"
    joined = " ".join(args)
    assert 'tell application "Vectorworks 2026" to run VectorScript' in joined
    vss = (root / "trigger.vss").read_text()
    assert "DoMenuTextByName('MCP Run Job', 0)" in vss


def test_will_not_stack_events_while_previous_is_stuck(root):
    t, procs = make(root, uptime=600)
    t()
    with pytest.raises(TriggerError, match="dialog"):
        t()
    assert len(procs) == 1


@pytest.mark.parametrize(
    "text,secs", [("00:07", 7), ("12:34", 754), ("01:00:00", 3600), ("2-00:00:01", 172801)]
)
def test_parse_etime(text, secs):
    assert parse_etime(text) == secs
