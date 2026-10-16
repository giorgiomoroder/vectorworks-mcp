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

    t = MacTrigger(root, app="Vectorworks 2026", uptime=lambda: uptime, spawn=spawn,
                   busy_grace=0.05, poll_interval=0.001)
    return t, procs


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


class SlowProc:
    """Finishes after a few polls, like osascript returning just after the result lands."""

    def __init__(self, polls_until_done=3):
        self.left = polls_until_done

    def poll(self):
        self.left -= 1
        return 0 if self.left <= 0 else None


def test_waits_briefly_for_previous_event_to_finish(root):
    procs = []
    t = MacTrigger(root, uptime=lambda: 600, spawn=lambda a: procs.append(a) or SlowProc(),
                   busy_grace=1.0, poll_interval=0.001)
    t()
    t()  # previous proc finishes within the grace period
    assert len(procs) == 2
