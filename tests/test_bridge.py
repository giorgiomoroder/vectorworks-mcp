import json
import time

import vwmcp_bridge as bridge


def write_job(root, job_id, code, **extra):
    (root / "jobs").mkdir(parents=True, exist_ok=True)
    job = {"id": job_id, "code": code, "created": time.time(), **extra}
    (root / "jobs" / f"{job_id}.json").write_text(json.dumps(job))


def read_result(root, job_id):
    return json.loads((root / "results" / f"{job_id}.json").read_text())


def test_runs_code_with_vs_in_scope_and_returns_last_expression(root, fake_vs):
    write_job(root, "a1", "x = 2\nvs.GetFName() + str(x)")
    assert bridge.run_pending(root, vs_module=fake_vs) == 1
    res = read_result(root, "a1")
    assert res["ok"] is True
    assert res["value"] == "Plot.vwx2"
    assert res["bridge_version"] == bridge.BRIDGE_VERSION


def test_captures_stdout(root, fake_vs):
    write_job(root, "a2", "print('hello')\nprint('world')")
    bridge.run_pending(root, vs_module=fake_vs)
    res = read_result(root, "a2")
    assert res["stdout"] == "hello\nworld\n"
    assert res["value"] is None


def test_explicit_result_variable_wins_over_last_statement(root, fake_vs):
    write_job(root, "a3", "result = {'n': 3}\nfor i in range(2):\n    pass")
    bridge.run_pending(root, vs_module=fake_vs)
    assert read_result(root, "a3")["value"] == {"n": 3}


def test_exception_is_reported_with_traceback(root, fake_vs):
    write_job(root, "a4", "print('before')\n1/0")
    bridge.run_pending(root, vs_module=fake_vs)
    res = read_result(root, "a4")
    assert res["ok"] is False
    assert "ZeroDivisionError" in res["error"]
    assert "ZeroDivisionError" in res["traceback"]
    assert res["stdout"] == "before\n"


def test_syntax_error_is_reported(root, fake_vs):
    write_job(root, "a5", "def (:")
    bridge.run_pending(root, vs_module=fake_vs)
    res = read_result(root, "a5")
    assert res["ok"] is False
    assert "SyntaxError" in res["error"]


def test_non_json_value_falls_back_to_repr(root, fake_vs):
    write_job(root, "a6", "object()")
    bridge.run_pending(root, vs_module=fake_vs)
    assert read_result(root, "a6")["value"].startswith("<object object")


def test_runs_one_job_per_call_oldest_first(root, fake_vs):
    # One job per trigger keeps one tool call == one Vectorworks undo step.
    # Job ids start with a zero-padded timestamp, so name order == age order.
    write_job(root, "0002-new", "2")
    write_job(root, "0001-old", "1")
    assert bridge.run_pending(root, vs_module=fake_vs) == 1
    assert (root / "results" / "0001-old.json").exists()
    assert not (root / "results" / "0002-new.json").exists()
    assert (root / "jobs" / "0002-new.json").exists()


def test_job_file_is_removed_after_running(root, fake_vs):
    write_job(root, "a7", "1")
    bridge.run_pending(root, vs_module=fake_vs)
    assert list((root / "jobs").iterdir()) == []


def test_expired_job_is_not_executed(root, fake_vs):
    write_job(root, "stale", "vs.calls.append('ran')", created=time.time() - 3600, ttl=60)
    bridge.run_pending(root, vs_module=fake_vs)
    res = read_result(root, "stale")
    assert res["ok"] is False
    assert "expired" in res["error"]
    assert fake_vs.calls == []


def test_no_jobs_is_a_noop(root, fake_vs):
    assert bridge.run_pending(root, vs_module=fake_vs) == 0


def test_corrupt_job_file_does_not_wedge_the_queue(root, fake_vs):
    (root / "jobs").mkdir(parents=True)
    (root / "jobs" / "bad.json").write_text("{not json")
    bridge.run_pending(root, vs_module=fake_vs)
    res = read_result(root, "bad")
    assert res["ok"] is False
    assert list((root / "jobs").iterdir()) == []
