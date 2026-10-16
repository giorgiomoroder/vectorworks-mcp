import json
import threading

import pytest
import vwmcp_bridge

from vwmcp.client import Bridge, BridgeTimeout, TriggerError


class FakeExecutor:
    """Plays the Vectorworks side: each trigger runs the real bridge code."""

    def __init__(self, root, vs_module, delay=0.0):
        self.root, self.vs, self.delay, self.triggers = root, vs_module, delay, 0

    def __call__(self):
        self.triggers += 1
        run = lambda: vwmcp_bridge.run_pending(self.root, vs_module=self.vs)
        threading.Timer(self.delay, run).start()


def make_bridge(root, trigger, **kw):
    return Bridge(root=root, trigger=trigger, poll_interval=0.01, **kw)


def test_round_trip_returns_value_and_stdout(root, fake_vs):
    b = make_bridge(root, FakeExecutor(root, fake_vs))
    res = b.run("print('hi')\nvs.GetFName()")
    assert res["ok"] and res["value"] == "Plot.vwx" and res["stdout"] == "hi\n"


def test_job_ids_sort_in_submission_order(root, fake_vs):
    b = make_bridge(root, lambda: None, timeout=0.05)
    ids = [b._new_job_id() for _ in range(50)]
    assert ids == sorted(ids) and len(set(ids)) == 50


def test_timeout_when_vectorworks_never_claims_job(root, fake_vs):
    b = make_bridge(root, lambda: None, timeout=0.1)
    with pytest.raises(BridgeTimeout) as e:
        b.run("1")
    assert "MCP Run Job" in str(e.value)
    # An unclaimed job must not linger and run later by surprise.
    assert list((root / "jobs").glob("*.json")) == []


def test_timeout_is_logged_with_timestamp(root, fake_vs):
    b = make_bridge(root, lambda: None, timeout=0.05)
    with pytest.raises(BridgeTimeout):
        b.run("1")
    log = (root / "vwmcp.log").read_text()
    assert "timeout" in log.lower() and log[:4].isdigit()


def test_slow_job_that_was_claimed_is_waited_for(root, fake_vs):
    b = make_bridge(root, FakeExecutor(root, fake_vs, delay=0.15), timeout=1)
    assert b.run("41 + 1")["value"] == 42


def test_trigger_failure_surfaces_as_error_and_removes_job(root, fake_vs):
    def broken():
        raise TriggerError("Vectorworks 2026 is not running")

    b = make_bridge(root, broken)
    with pytest.raises(TriggerError):
        b.run("1")
    assert list((root / "jobs").glob("*.json")) == []
    assert "not running" in (root / "vwmcp.log").read_text()


def test_result_file_is_consumed(root, fake_vs):
    b = make_bridge(root, FakeExecutor(root, fake_vs))
    b.run("1")
    assert list((root / "results").glob("*.json")) == []


def test_job_carries_ttl_so_stale_jobs_never_run(root, fake_vs):
    seen = {}

    def peek():
        job = next((root / "jobs").glob("*.json"))
        seen.update(json.loads(job.read_text()))
        vwmcp_bridge.run_pending(root, vs_module=fake_vs)

    make_bridge(root, peek, timeout=5).run("1")
    assert seen["ttl"] == 5
