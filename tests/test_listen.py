import json
import time

import vwmcp_bridge as bridge

TIMER_TICK = 12345  # any item id that is not setup (12255), OK (1) or Cancel (2)


def write_job(root, job_id, code):
    (root / "jobs").mkdir(parents=True, exist_ok=True)
    job = {"id": job_id, "code": code, "created": time.time()}
    (root / "jobs" / f"{job_id}.json").write_text(json.dumps(job))


def add_dialog(vs, events, on_tick=None):
    """Fake layout-dialog API: RunLayoutDialog replays `events` into the handler."""
    vs.calls = []
    vs.CreateLayout = lambda *a: vs.calls.append(("CreateLayout",) + a) or 7
    vs.CreateStaticText = lambda *a: vs.calls.append(("CreateStaticText",) + a)
    vs.SetFirstLayoutItem = lambda *a: vs.calls.append(("SetFirstLayoutItem",) + a)
    vs.SetBelowItem = lambda *a: vs.calls.append(("SetBelowItem",) + a)
    vs.SetItemText = lambda *a: vs.calls.append(("SetItemText",) + a)
    vs.RegisterDialogForTimerEvents = lambda *a: vs.calls.append(("Register",) + a)
    vs.DeregisterDialogFromTimerEvents = lambda *a: vs.calls.append(("Deregister",) + a)

    def run(dialog, handler):
        vs.calls.append(("Run", dialog))
        for item in events:
            if on_tick:
                on_tick(item)
            handler(item, 0)
        return 1

    vs.RunLayoutDialog = run
    return vs


def test_timer_ticks_run_queued_jobs_until_stop(root, fake_vs):
    write_job(root, "j1", "1 + 1")
    write_job(root, "j2", "2 + 2")
    vs = add_dialog(fake_vs, [bridge.SETUP_DIALOG, TIMER_TICK, TIMER_TICK, TIMER_TICK, 1])
    assert bridge.listen(root, vs_module=vs, interval_ms=50) == 2
    assert json.loads((root / "results" / "j1.json").read_text())["value"] == 2
    assert json.loads((root / "results" / "j2.json").read_text())["value"] == 4
    assert ("Register", 7, 50) in vs.calls
    assert vs.calls[-1] == ("Deregister", 7)


def test_job_arriving_mid_session_is_picked_up(root, fake_vs):
    def drop_job_on_second_tick(item, seen=[]):
        seen.append(item)
        if len(seen) == 3:
            write_job(root, "late", "'late'")

    vs = add_dialog(fake_vs, [bridge.SETUP_DIALOG, TIMER_TICK, TIMER_TICK, TIMER_TICK, 2],
                    on_tick=drop_job_on_second_tick)
    assert bridge.listen(root, vs_module=vs) == 1
    assert json.loads((root / "results" / "late.json").read_text())["value"] == "late"


def test_stop_and_cancel_run_no_jobs(root, fake_vs):
    write_job(root, "j1", "1")
    vs = add_dialog(fake_vs, [bridge.SETUP_DIALOG, 1])
    # setup itself may drain once; a click on Stop must not run anything further
    ran = bridge.listen(root, vs_module=vs)
    assert ran <= 1
    vs2 = add_dialog(fake_vs, [2])
    write_job(root, "j2", "2")
    assert bridge.listen(root, vs_module=vs2) == 0
    assert (root / "jobs" / "j2.json").exists()


def test_failing_job_does_not_end_the_session(root, fake_vs):
    write_job(root, "bad", "1/0")
    vs = add_dialog(fake_vs, [bridge.SETUP_DIALOG, TIMER_TICK, TIMER_TICK, 1])
    assert bridge.listen(root, vs_module=vs) == 1
    write_job(root, "good", "3")
    vs = add_dialog(fake_vs, [bridge.SETUP_DIALOG, TIMER_TICK, 1])
    assert bridge.listen(root, vs_module=vs) == 1
    assert json.loads((root / "results" / "bad.json").read_text())["ok"] is False
    assert json.loads((root / "results" / "good.json").read_text())["ok"] is True


def test_counter_label_updates(root, fake_vs):
    write_job(root, "j1", "1")
    vs = add_dialog(fake_vs, [bridge.SETUP_DIALOG, TIMER_TICK, 1])
    bridge.listen(root, vs_module=vs)
    assert ("SetItemText", 7, 5, "Jobs run: 1") in vs.calls


def test_deregisters_even_when_dialog_raises(root, fake_vs):
    vs = add_dialog(fake_vs, [])

    def boom(dialog, handler):
        raise RuntimeError("dialog failed")

    vs.RunLayoutDialog = boom
    try:
        bridge.listen(root, vs_module=vs)
    except RuntimeError:
        pass
    assert vs.calls[-1] == ("Deregister", 7)
