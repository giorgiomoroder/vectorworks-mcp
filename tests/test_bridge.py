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


def test_root_comes_from_home_file_beside_the_bridge(tmp_path, fake_vs, monkeypatch):
    other = tmp_path / "vwmcp-2027"
    monkeypatch.setattr(bridge, "HOME_FILE", str(tmp_path / "vwmcp_home.txt"))
    assert bridge.configured_root() == bridge.DEFAULT_ROOT
    (tmp_path / "vwmcp_home.txt").write_text(str(other) + "\n")
    assert bridge.configured_root() == str(other)
    write_job(other, "h1", "'from 2027'")
    assert bridge.run_pending(vs_module=fake_vs) == 1
    assert read_result(other, "h1")["value"] == "from 2027"
    (tmp_path / "vwmcp_home.txt").write_text("~/.vwmcp-x\n")
    assert bridge.configured_root().endswith("/.vwmcp-x") and "~" not in bridge.configured_root()


# ---------------------------------------------------------------- checked vs

import types

import pytest


def _fn(doc, impl=None):
    f = impl or (lambda *a: ("called", a))
    f.__doc__ = doc
    return f


@pytest.fixture
def typed_vs():
    """A fake vs whose functions carry Vectorworks-style docstrings, so that
    load_tables keeps them (the live parameter count must match the table)."""
    vs = types.ModuleType("vs")
    vs.GetFName = _fn("Definition:\n  vs.GetFName()", lambda: "Plot.vwx")
    vs.Rect = _fn("Definition:\n  vs.Rect(p1, p2)")
    vs.SetRField = _fn("Definition:\n  vs.SetRField(h, record, field, value)")
    vs.ColorIndexToRGB = _fn("Definition:\n  vs.ColorIndexToRGB(color)")
    vs.ForEachObject = _fn("Definition:\n  vs.ForEachObject(callback, c)")
    vs.UprString = _fn("Definition:\n  vs.UprString(str)")
    vs.EditProperties = _fn("Definition:\n  vs.EditProperties(h)")
    vs.HMove = _fn("Definition:\n  vs.HMove(h, xOffset, yOffset)")
    vs.calls = []
    return vs


@pytest.fixture
def tables(tmp_path, monkeypatch):
    types_json = {"f": {
        "Rect": {"t": "PP", "a": "p1:POINT, p2:POINT"},
        "SetRField": {"t": "HSSS", "a": "h:HANDLE, record:STRING, field:STRING, value:STRING"},
        "ColorIndexToRGB": {"t": "I", "a": "color:INTEGER"},
        "ForEachObject": {"t": "FS", "a": "callback:PROCEDURE, c:CRITERIA"},
        "HMove": {"t": "HRR", "a": "h:HANDLE, xOffset:REAL, yOffset:REAL"},
        "GetFName": {"t": "", "a": ""}}}
    safety = {"crash": ["UprString"], "hang": [], "document_level": [], "interactive": ["EditProperties"],
              "arg_check": {}}
    (tmp_path / "vs_types.json").write_text(json.dumps(types_json))
    (tmp_path / "vs_safety.json").write_text(json.dumps(safety))
    monkeypatch.setattr(bridge, "_HERE", str(tmp_path))
    bridge._CACHE["tables"] = None
    return tmp_path


def test_check_args_accepts_point_as_tuple_or_two_numbers():
    assert bridge.check_args("PP", ((0, 0), (10, 5))) is None
    assert bridge.check_args("PP", (0, 0, 10, 5)) is None
    assert bridge.check_args("PP", ((0, 0, 1), (1, 1))) is None  # 3-tuples pass (3D points)
    assert "parameter 2 (POINT) needs a tuple or 2 numbers" in bridge.check_args("PP", ((0, 0),))
    assert "too few" in bridge.check_args("HRR", (None, 1))
    assert "too many" in bridge.check_args("PP", ((0, 0), (1, 1), (2, 2)))


def test_check_args_catches_wrong_types():
    assert "got text" in bridge.check_args("HRR", ("not a handle", 1, 2))
    assert "got text" in bridge.check_args("I", ("7",))
    assert "one tuple" in bridge.check_args("C", (1, 2, 3))
    assert bridge.check_args("C", ((1, 2, 3),)) is None
    assert bridge.check_args("I", ((1, 2),)) is not None  # a tuple for one integer
    assert "callable" in bridge.check_args("FS", ("x", "T=1"))


def test_proxy_refuses_bad_call_before_vectorworks_sees_it(root, typed_vs, tables):
    write_job(root, "c1", "vs.ColorIndexToRGB((1000, 2000, 3000))")
    bridge.run_pending(root, vs_module=typed_vs)
    res = read_result(root, "c1")
    assert res["ok"] is False
    assert "VSArgumentError" in res["error"]
    assert "vs.ColorIndexToRGB(color:INTEGER)" in res["error"]


def test_proxy_passes_good_calls_through(root, typed_vs, tables):
    write_job(root, "c2", "vs.Rect((0, 0), (10, 5))\nvs.Rect(0, 0, 10, 5)\nvs.GetFName()")
    bridge.run_pending(root, vs_module=typed_vs)
    res = read_result(root, "c2")
    assert res["ok"] is True and res["value"] == "Plot.vwx"


def test_proxy_only_checks_functions_whose_live_signature_matches(root, typed_vs, tables):
    typed_vs.Rect = _fn("Definition:\n  vs.Rect(p1, p2, extra)")  # a future Vectorworks
    bridge._CACHE["tables"] = None
    write_job(root, "c3", "vs.Rect('anything', 'goes', 1)")
    bridge.run_pending(root, vs_module=typed_vs)
    assert read_result(root, "c3")["ok"] is True


def test_proxy_refuses_known_crashers_and_dialog_openers(root, typed_vs, tables):
    write_job(root, "c4", "vs.UprString('abc')")
    bridge.run_pending(root, vs_module=typed_vs)
    res = read_result(root, "c4")
    assert res["ok"] is False and "VSUnsafeError" in res["error"] and "crash" in res["error"]
    write_job(root, "c5", "vs.EditProperties(None)")
    bridge.run_pending(root, vs_module=typed_vs)
    assert "dialog" in read_result(root, "c5")["error"]
    write_job(root, "c6", "vs.EditProperties(None)", allow_dialogs=True)
    bridge.run_pending(root, vs_module=typed_vs)
    assert read_result(root, "c6")["ok"] is True


def test_check_can_be_switched_off_per_job(root, typed_vs, tables):
    write_job(root, "c7", "vs.ColorIndexToRGB((1, 2, 3))", check=False)
    bridge.run_pending(root, vs_module=typed_vs)
    assert read_result(root, "c7")["ok"] is True


def test_proxied_callback_is_unwrapped_for_vectorworks(root, typed_vs, tables):
    seen = {}
    typed_vs.ForEachObject = _fn("Definition:\n  vs.ForEachObject(callback, c)",
                                 lambda cb, c: seen.setdefault("cb", cb))
    typed_vs.SetSelect = _fn("Definition:\n  vs.SetSelect(h)", lambda h: None)  # named parameter: no *args
    bridge._CACHE["tables"] = None
    write_job(root, "c8", "vs.ForEachObject(vs.SetSelect, 'T=RECT')")
    bridge.run_pending(root, vs_module=typed_vs)
    assert read_result(root, "c8")["ok"] is True
    assert seen["cb"] is typed_vs.SetSelect  # the real built-in, not our wrapper


def test_import_vs_inside_the_job_gets_the_proxy_too(root, typed_vs, tables):
    write_job(root, "c10", "import vs as v2\nv2.ColorIndexToRGB((1, 2, 3))")
    bridge.run_pending(root, vs_module=typed_vs)
    assert "VSArgumentError" in read_result(root, "c10")["error"]


def test_missing_tables_mean_no_checking(root, typed_vs, monkeypatch, tmp_path):
    monkeypatch.setattr(bridge, "_HERE", str(tmp_path / "nowhere"))
    bridge._CACHE["tables"] = None
    write_job(root, "c9", "vs.ColorIndexToRGB((1, 2, 3))")
    bridge.run_pending(root, vs_module=typed_vs)
    assert read_result(root, "c9")["ok"] is True


def test_bridge_version_is_0_2_0():
    assert bridge.BRIDGE_VERSION == "0.2.0"


# ------------------------------------------------- document guard, libraries


def test_document_guard_refuses_another_document_before_running(root, fake_vs):
    fake_vs.GetFPathName = lambda: "/Users/m/Plot.vwx"
    write_job(root, "d1", "vs.calls.append('ran')", document={"name": "visit-bushwick v2027"})
    bridge.run_pending(root, vs_module=fake_vs)
    res = read_result(root, "d1")
    assert res["ok"] is False and res["never_ran"] is True
    assert res["error"].startswith("WrongDocument:")
    assert "Plot.vwx" in res["error"] and fake_vs.calls == []


def test_document_guard_matches_case_and_extension_insensitively(root, fake_vs):
    fake_vs.GetFPathName = lambda: "/Users/m/Plot.vwx"
    write_job(root, "d2", "vs.calls.append('ran')", document={"name": "plot"})
    bridge.run_pending(root, vs_module=fake_vs)
    assert read_result(root, "d2")["ok"] is True and fake_vs.calls == ["ran"]


def test_document_guard_prefers_the_path_when_both_sides_have_one(root, fake_vs):
    fake_vs.GetFPathName = lambda: "/Users/m/shows/Plot.vwx"
    write_job(root, "d3", "1", document={"name": "Plot", "path": "/Users/m/other/Plot.vwx"})
    bridge.run_pending(root, vs_module=fake_vs)
    assert read_result(root, "d3")["never_ran"] is True


def test_helper_library_is_compiled_once_per_session(root, fake_vs, tmp_path):
    src = "def helper():\n    return 'lib'\n"
    sha = bridge.hashlib.sha256(src.encode("utf-8")).hexdigest()
    lib = tmp_path / f"{sha}.py"
    lib.write_text(src)
    ref = {"name": "vwlib", "sha": sha, "path": str(lib)}
    bridge._CACHE["libs"].clear()
    write_job(root, "l1", "helper()", libs=[ref])
    bridge.run_pending(root, vs_module=fake_vs)
    assert read_result(root, "l1")["value"] == "lib"
    lib.unlink()  # cached: the file is not needed any more this session
    write_job(root, "l2", "helper()", libs=[ref])
    bridge.run_pending(root, vs_module=fake_vs)
    assert read_result(root, "l2")["value"] == "lib"


def test_helper_library_with_wrong_checksum_is_refused(root, fake_vs, tmp_path):
    lib = tmp_path / "x.py"
    lib.write_text("def helper(): return 1\n")
    write_job(root, "l3", "helper()", libs=[{"name": "vwlib", "sha": "0" * 64, "path": str(lib)}])
    bridge.run_pending(root, vs_module=fake_vs)
    assert "checksum" in read_result(root, "l3")["error"]


def test_result_carries_claimed_at(root, fake_vs):
    write_job(root, "t1", "1")
    bridge.run_pending(root, vs_module=fake_vs)
    assert read_result(root, "t1")["claimed_at"] > 0
