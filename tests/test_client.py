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
    b = make_bridge(root, lambda: None, claim_timeout=0.1)
    with pytest.raises(BridgeTimeout) as e:
        b.run("1")
    assert "MCP Run Job" in str(e.value)
    # An unclaimed job must not linger and run later by surprise.
    assert list((root / "jobs").glob("*.json")) == []


def test_timeout_is_logged_with_timestamp(root, fake_vs):
    b = make_bridge(root, lambda: None, claim_timeout=0.05)
    with pytest.raises(BridgeTimeout):
        b.run("1")
    log = (root / "vwmcp.log").read_text()
    assert "cancelled" in log.lower() and log[:4].isdigit()


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

    make_bridge(root, peek, claim_timeout=5).run("1")
    assert seen["ttl"] == 65  # claim timeout + a generous margin: never refuse a job we still wait for


# ------------------------------------------ claim phase, cancel, liveness, libs

import os
import time

from vwmcp.client import BridgeError, WrongDocument


class CountingTrigger:
    def __init__(self):
        self.fired = 0
        self.alive = True

    def __call__(self):
        self.fired += 1

    def in_flight(self):
        return False

    def target_alive(self):
        return self.alive


def test_unclaimed_job_is_cancelled_by_rename_and_never_ran(root, fake_vs):
    b = make_bridge(root, lambda: None, claim_timeout=0.1, timeout=5)
    with pytest.raises(BridgeTimeout) as e:
        b.run("1")
    assert e.value.never_ran is True
    assert list((root / "jobs").glob("*.json")) == []
    assert len(list((root / "jobs").glob("*.cancelled"))) == 1
    # a bridge arriving late finds nothing to run
    assert vwmcp_bridge.run_pending(root, vs_module=fake_vs) == 0


def test_trigger_is_refired_while_unclaimed(root, fake_vs):
    t = CountingTrigger()
    b = make_bridge(root, t, claim_timeout=0.3, timeout=1)
    b.retrigger_after = 0.05
    with pytest.raises(BridgeTimeout):
        b.run("1")
    assert t.fired >= 3


def test_claimed_job_waits_for_result_beyond_claim_timeout(root, fake_vs):
    # claimed at once, result after 0.3 s: claim_timeout 0.1 must not cut it off
    class SlowExecutor(FakeExecutor):
        def __call__(self):
            self.triggers += 1

            def run():
                claimed = vwmcp_bridge._claim_oldest(str(self.root / "jobs"))
                time.sleep(0.3)
                os.replace(claimed, claimed[: -len(".running")] + ".json")  # put it back, then run it
                vwmcp_bridge.run_pending(self.root, vs_module=self.vs)

            threading.Thread(target=run).start()

    b = make_bridge(root, SlowExecutor(root, fake_vs), claim_timeout=0.1, timeout=2)
    assert b.run("2")["value"] == 2


def test_result_timeout_message_says_vectorworks_is_still_working(root, fake_vs):
    class ClaimOnly:
        def __call__(self):
            vwmcp_bridge._claim_oldest(str(root / "jobs"))

    b = make_bridge(root, ClaimOnly(), claim_timeout=0.5, timeout=0.1)
    with pytest.raises(BridgeTimeout, match="still working"):
        b.run("1")


def test_stops_waiting_when_vectorworks_is_gone(root, fake_vs):
    class ClaimThenDie(CountingTrigger):
        def __call__(self):
            self.fired += 1
            vwmcp_bridge._claim_oldest(str(root / "jobs"))
            self.alive = False

    b = make_bridge(root, ClaimThenDie(), claim_timeout=0.5, timeout=5)
    b.alive_every = 0.02
    with pytest.raises(BridgeError, match="quit or restarted"):
        b.run("1")


def test_wrong_document_result_raises_wrong_document(root, fake_vs):
    fake_vs.GetFPathName = lambda: "/x/Plot.vwx"
    b = make_bridge(root, FakeExecutor(root, fake_vs))
    with pytest.raises(WrongDocument) as e:
        b.run("1", document={"name": "Other"})
    assert e.value.never_ran is True and "Plot" in str(e.value)


def test_lib_ref_writes_the_library_once_and_bridge_version_is_learned(root, fake_vs):
    b = make_bridge(root, FakeExecutor(root, fake_vs))
    assert b.supports_libs() is False  # version unknown before the first result
    b.run("1")
    assert b.bridge_version == vwmcp_bridge.BRIDGE_VERSION and b.supports_libs() is True
    ref = b.lib_ref("vwlib", "def helper():\n    return 7\n")
    assert (root / "lib" / f"{ref['sha']}.py").is_file()
    same = b.lib_ref("vwlib", "def helper():\n    return 7\n")
    assert same == ref and len(list((root / "lib").glob("*.py"))) == 1
    assert b.run("helper()", libs=[ref])["value"] == 7


def test_housekeep_removes_old_leftovers(root, fake_vs):
    b = make_bridge(root, lambda: None)
    (root / "jobs").mkdir(parents=True)
    (root / "results").mkdir(parents=True)
    old = root / "jobs" / "x.cancelled"
    old.write_text("{}")
    fresh = root / "results" / "y.json"
    fresh.write_text("{}")
    assert b.housekeep(now=time.time() + 7200) == 2  # both older than an hour at that time
    assert not old.exists() and not fresh.exists()
