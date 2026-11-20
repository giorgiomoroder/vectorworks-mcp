from pathlib import Path

import pytest

from vwmcp import screenshot as ss


def win(id, title, layer=0, w=100, h=100):
    return ss.Window(id=id, title=title, layer=layer, x=0, y=0, width=w, height=h)


def test_pick_largest_normal_window_skips_palettes():
    palette = win(1, "", layer=103, w=300, h=100)
    doc = win(2, "plot.vwx", w=1728, h=978)
    small = win(3, "other.vwx", w=800, h=600)
    assert ss.pick_window([palette, small, doc]) == doc


def test_pick_by_title_substring_case_insensitive():
    a, b = win(1, "Plot A.vwx"), win(2, "Plot B.vwx")
    assert ss.pick_window([a, b], title="plot b") == b


def test_pick_reports_open_titles_when_title_not_found():
    with pytest.raises(ss.ScreenshotError, match="'Plot A.vwx'"):
        ss.pick_window([win(1, "Plot A.vwx")], title="nope")


def test_pick_fails_when_no_document_window():
    with pytest.raises(ss.ScreenshotError, match="no document window"):
        ss.pick_window([win(1, "", layer=103)])


class FakeRun:
    def __init__(self, rc=0):
        self.calls, self.rc = [], rc

    def __call__(self, args):
        self.calls.append(args)
        if args[0] == "screencapture" and self.rc == 0:
            Path(args[-1]).write_bytes(b"png")
        import subprocess

        return subprocess.CompletedProcess(args, self.rc, "", "denied" if self.rc else "")


def test_screenshot_captures_window_id_and_shrinks(tmp_path):
    run = FakeRun()
    path, window, in_front = ss.screenshot(
        root=tmp_path, windows=lambda owner: [win(42, "plot.vwx")], run=run, max_width=1200
    )
    assert in_front == []
    assert path.parent == tmp_path / "screenshots" and path.read_bytes() == b"png"
    assert run.calls[0] == ["screencapture", "-x", "-o", "-l", "42", str(path)]
    assert run.calls[1] == ["sips", "-Z", "1200", str(path)]
    assert window.id == 42


def test_screenshot_uses_app_name_as_window_owner(tmp_path):
    seen = []

    def windows(owner):
        seen.append(owner)
        return [win(1, "x.vwx")]

    ss.screenshot(app="Vectorworks 2025", root=tmp_path, windows=windows, run=FakeRun())
    assert seen == ["Vectorworks"]


def test_screenshot_failure_mentions_screen_recording(tmp_path):
    with pytest.raises(ss.ScreenshotError, match="Screen Recording"):
        ss.screenshot(root=tmp_path, windows=lambda o: [win(1, "x.vwx")], run=FakeRun(rc=1))


def test_prune_keeps_newest(tmp_path):
    for i in range(5):
        (tmp_path / f"2026010{i}-000000.png").write_bytes(b"")
    ss.prune(tmp_path, keep=2)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "20260103-000000.png",
        "20260104-000000.png",
    ]


def test_screenshot_reports_menus_and_dialogs_in_front(tmp_path):
    windows = [win(42, "plot.vwx", w=1700, h=900), win(43, "", layer=101, w=367, h=928),
               win(44, "Script Errors", layer=8, w=400, h=200)]
    _, _, in_front = ss.screenshot(root=tmp_path, windows=lambda o: windows, run=FakeRun())
    assert [(w["id"], w["kind"]) for w in in_front] == [
        (43, "popup/contextual menu"), (44, "modal dialog")]


def test_script_error_alert_is_reported_even_at_normal_window_level():
    # Live 2026-11-20: the "A Script error has occurred" alert is a 324x130
    # window titled "Vectorworks" at level 0, next to the document windows.
    alert = ss.Window(id=9, title="Vectorworks", layer=0, x=702, y=251, width=324, height=130)
    doc = win(2, "Untitled 1", w=1728, h=978)
    (found,) = ss.blocking_windows([doc, alert])
    assert found["id"] == 9 and found["kind"] == "alert (Script error: click OK in Vectorworks)"
    assert ss.pick_window([doc, alert]) == doc


def test_object_preferences_window_is_reported_as_blocking():
    # Live 2026-11-20: a plug-in's "Object Preferences" dialog (level 0) held a job.
    prefs = ss.Window(id=5, title="Object Preferences", layer=0, x=997, y=35, width=250, height=1002)
    doc = win(2, "test_mcp.vwx", w=1728, h=978)
    (found,) = ss.blocking_windows([doc, prefs])
    assert found["id"] == 5 and "Object Preferences" in found["kind"]
    assert ss.pick_window([doc, prefs]) == doc
