import csv
import io

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from vwmcp.tools import spotlight


def test_verify_flags_fields_that_did_not_stick():
    requested = [{"fields": {"Channel": "101", "Universe": "2"}}]
    actual = [{"uuid": "u1", "Channel": "101", "Universe": "1"}]
    before = [{"uuid": "u1", "before": {"Channel": "5", "Universe": "1"}}]
    (out,) = spotlight.verify_updates(requested, before, actual)
    assert out["uuid"] == "u1"
    assert out["after"] == {"Channel": "101", "Universe": "1"}
    assert out["not_applied"] == {"Universe": {"requested": "2", "actual": "1"}}


def test_verify_treats_numeric_strings_loosely():
    out = spotlight.verify_updates(
        [{"fields": {"Channel": 101}}], [{"uuid": "u", "before": {}}], [{"uuid": "u", "Channel": "101"}]
    )
    assert "not_applied" not in out[0]


def test_report_csv_has_header_and_rows():
    rows = [{"uuid": "a", "Unit Number": "1", "Channel": "101", "Purpose": 'Front, "warm"'}]
    text = spotlight.format_report(rows, ["Unit Number", "Channel", "Purpose"], "csv")
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed == [["Unit Number", "Channel", "Purpose"], ["1", "101", 'Front, "warm"']]


def test_report_json_keeps_only_requested_columns():
    rows = [{"uuid": "a", "Unit Number": "1", "Channel": "101"}]
    assert spotlight.format_report(rows, ["Channel"], "json") == '[\n  {\n    "Channel": "101"\n  }\n]'


def test_report_sort_by_channel_is_numeric():
    rows = [{"Channel": "10"}, {"Channel": "9"}, {"Channel": ""}, {"Channel": "101"}]
    out = spotlight.sort_rows(rows, "Channel")
    assert [r["Channel"] for r in out] == ["9", "10", "101", ""]


# ---- vw_mvr_check -------------------------------------------------------------

def _mvr_rows():
    base = {"Position": "FOH", "Unit Number": "1", "Channel": "1", "Inst Type": "X",
            "Symbol Name": "S", "Fixture Mode": "M", "GDTF Fixture Name": "G",
            "Fixture ID": "1", "UniverseAddress": "1/1", "Absolute Address": "1",
            "Num Channels": "16"}
    return [dict(base, uuid="a"),
            dict(base, uuid="b", Position="Truss 1", Channel="2", UniverseAddress="",
                 **{"Fixture ID": "2", "Absolute Address": "0"})]


def test_mvr_check_runs_checks_on_document_data(monkeypatch):
    calls = []

    def fake_vw(fn, **kw):
        calls.append((fn, kw))
        return {"document": "Plot.vwx", "fields": list(spotlight.mvr.FIELDS),
                "devices": _mvr_rows(), "positions": ["FOH", "Truss 1"],
                "symbols": {"S": {"type": 2}}}

    monkeypatch.setattr(spotlight, "vw", fake_vw)
    out = spotlight.vw_mvr_check()
    assert calls == [("mvr_data", {})]
    assert out["document"] == "Plot.vwx"
    assert out["ok"] is False
    assert out["summary"] == {"unpatched": 1}
    assert "vw_set_lighting_device_fields" in out["next_steps"]


def test_mvr_check_position_filter(monkeypatch):
    monkeypatch.setattr(spotlight, "vw", lambda fn, **kw: {
        "document": "Plot.vwx", "fields": list(spotlight.mvr.FIELDS), "devices": _mvr_rows(),
        "positions": ["FOH", "Truss 1"], "symbols": {"S": {"type": 2}}})
    out = spotlight.vw_mvr_check(position="FOH")
    assert out["device_count"] == 1
    assert out["ok"] is True


# ---- vw_import_hookup ---------------------------------------------------------

def test_import_hookup_dry_run_plans_without_writing(tmp_path, monkeypatch):
    sheet = tmp_path / "h.csv"
    sheet.write_text("Channel,Purpose,Notes\n1,Key,hi\n", encoding="utf-8")
    calls = []

    def fake_vw(fn, **kw):
        calls.append(fn)
        assert fn == "ld_field_names"
        return ["Channel", "Purpose", "Color"]

    monkeypatch.setattr(spotlight, "vw", fake_vw)
    out = spotlight.vw_import_hookup(str(sheet))
    assert calls == ["ld_field_names"]
    assert out["dry_run"] is True
    assert out["updates"] == [{"channel": "1", "fields": {"Purpose": "Key"}}]
    assert out["ignored"] == ["Notes"]


def test_import_hookup_apply_needs_document(tmp_path, monkeypatch):
    sheet = tmp_path / "h.csv"
    sheet.write_text("Channel,Purpose\n1,Key\n", encoding="utf-8")
    monkeypatch.setattr(spotlight, "vw", lambda fn, **kw: ["Channel", "Purpose"])
    with pytest.raises(ToolError, match="document"):
        spotlight.vw_import_hookup(str(sheet), dry_run=False)


def test_import_hookup_apply_delegates_to_set_fields(tmp_path, monkeypatch):
    sheet = tmp_path / "h.csv"
    sheet.write_text("Channel,Purpose\n1,Key\n", encoding="utf-8")
    monkeypatch.setattr(spotlight, "vw", lambda fn, **kw: ["Channel", "Purpose"])
    seen = {}

    def fake_set(updates, document=None):
        seen["updates"], seen["document"] = updates, document
        return [{"uuid": "u", "after": {"Purpose": "Key"}}]

    monkeypatch.setattr(spotlight, "vw_set_lighting_device_fields", fake_set)
    out = spotlight.vw_import_hookup(str(sheet), dry_run=False, document="Plot")
    assert seen == {"updates": [{"channel": "1", "fields": {"Purpose": "Key"}}], "document": "Plot"}
    assert out["result"] == [{"uuid": "u", "after": {"Purpose": "Key"}}]
    assert out["dry_run"] is False


# ------------------------------------------------------------- Lightwright


def test_lightwright_snapshot_reports_when_the_exchange_is_off(monkeypatch, tmp_path):
    (tmp_path / "Plot.vwx").write_bytes(b"")
    monkeypatch.setattr(spotlight, "vw", lambda fn, **kw: {"name": "Plot.vwx", "path": str(tmp_path / "Plot.vwx")})
    out = spotlight.vw_lightwright_snapshot()
    assert out["available"] is False and "Spotlight Preferences" in out["hint"]


def test_lightwright_snapshot_filters_by_position_and_fields(monkeypatch, tmp_path):
    from test_lightwright import SAMPLE  # bare module name: tests/ has no __init__.py
    (tmp_path / "Plot.vwx").write_bytes(b"")
    (tmp_path / "Plot.xml").write_text(SAMPLE)
    monkeypatch.setattr(spotlight, "vw", lambda fn, **kw: {"name": "Plot.vwx", "path": str(tmp_path / "Plot.vwx")})
    out = spotlight.vw_lightwright_snapshot(position="lx 1", fields=["Channel"])
    assert out["available"] and out["count"] == 2
    assert out["fixtures"][0] == {"uid": "1001.1.1.0.0", "Channel": "101"}


def test_lightwright_patch_dry_run_writes_nothing(monkeypatch, tmp_path):
    from test_lightwright import SAMPLE
    (tmp_path / "Plot.vwx").write_bytes(b"")
    xml = tmp_path / "Plot.xml"
    xml.write_text(SAMPLE)
    monkeypatch.setattr(spotlight, "vw", lambda fn, **kw: {"name": "Plot.vwx", "path": str(tmp_path / "Plot.vwx")})
    monkeypatch.setattr(spotlight.app, "require_document", lambda d: None)
    out = spotlight.vw_lightwright_patch([{"uid": "1001.1.1.0.0", "fields": {"Channel": "5"}}])
    assert out["dry_run"] is True and "<Channel>5</Channel>" in out["patch"]
    assert xml.read_text() == SAMPLE


def test_lightwright_patch_apply_writes_and_journals_and_reverts(monkeypatch, tmp_path):
    from test_lightwright import SAMPLE
    from vwmcp.journal import Journal
    from vwmcp.tools import generic
    (tmp_path / "Plot.vwx").write_bytes(b"")
    xml = tmp_path / "Plot.xml"
    xml.write_text(SAMPLE)
    j = Journal(tmp_path / "journal.jsonl")
    fake_vw = lambda fn, **kw: ({"name": "Plot.vwx", "path": str(tmp_path / "Plot.vwx")}
                               if fn == "document_info" else "Plot.vwx")
    monkeypatch.setattr(spotlight, "vw", fake_vw)
    monkeypatch.setattr(generic, "vw", fake_vw)
    monkeypatch.setattr(spotlight.app, "require_document", lambda d: None)
    monkeypatch.setattr(spotlight.app, "get_journal", lambda: j)
    out = spotlight.vw_lightwright_patch([{"uid": "1001.1.1.0.0", "fields": {"Channel": "5"}}], dry_run=False)
    assert out["dry_run"] is False and "<Channel>5</Channel>" in xml.read_text()
    assert j.peek("Plot.vwx")["ops"][0]["op"] == "lightwright"
    back = generic.vw_revert_last()
    assert back["reverted_tool"] == "vw_lightwright_patch" and back["lightwright"] is True
    assert "<Channel>101</Channel>" in xml.read_text()


def test_lightwright_snapshot_explains_the_empty_acknowledgement_file(monkeypatch, tmp_path):
    from test_lightwright import ACK
    (tmp_path / "Plot.vwx").write_bytes(b"")
    (tmp_path / "Plot.xml").write_text(ACK)
    monkeypatch.setattr(spotlight, "vw", lambda fn, **kw: {"name": "Plot.vwx", "path": str(tmp_path / "Plot.vwx")})
    out = spotlight.vw_lightwright_snapshot()
    assert out["available"] and out["count"] == 0
    assert "full export" in out["hint"]


def _lightwright_apply_setup(monkeypatch, tmp_path, live_devices):
    from test_lightwright import SAMPLE
    from vwmcp.journal import Journal
    from vwmcp.tools import generic
    (tmp_path / "Plot.vwx").write_bytes(b"")
    xml = tmp_path / "Plot.xml"
    xml.write_text(SAMPLE)
    j = Journal(tmp_path / "journal.jsonl")
    calls = []

    def fake_vw(fn, **kw):
        calls.append((fn, kw))
        if fn == "document_info":
            return {"name": "Plot.vwx", "path": str(tmp_path / "Plot.vwx")}
        if fn == "list_lighting_devices":
            return live_devices
        return "Plot.vwx"

    monkeypatch.setattr(spotlight, "vw", fake_vw)
    monkeypatch.setattr(generic, "vw", fake_vw)
    monkeypatch.setattr(spotlight.app, "require_document", lambda d: None)
    monkeypatch.setattr(spotlight.app, "get_journal", lambda: j)
    monkeypatch.setattr(spotlight.lightwright, "BACKUP_DIR", tmp_path / "backups")
    return xml, j, calls, generic


def test_lightwright_patch_apply_backs_up_and_reverts_to_live_values(monkeypatch, tmp_path):
    from test_lightwright import SAMPLE
    # The export says unit 1 on LX 1 is channel 101; the drawing says 901 (stale export).
    xml, j, calls, generic = _lightwright_apply_setup(
        monkeypatch, tmp_path, [{"uuid": "u1", "Unit Number": "1", "Channel": "901"}])
    out = spotlight.vw_lightwright_patch([{"uid": "1001.1.1.0.0", "fields": {"Channel": "5"}}], dry_run=False)
    assert out["inverse_from"] == "live"
    backup = tmp_path / "backups" / out["backup"].split("/")[-1]
    assert backup.read_text() == SAMPLE
    live_calls = [kw for fn, kw in calls if fn == "list_lighting_devices"]
    assert live_calls == [{"position": "LX 1", "fields": ["Unit Number", "Channel"]}]
    generic.vw_revert_last()
    assert "<Channel>901</Channel>" in xml.read_text()


def test_lightwright_patch_falls_back_to_export_values_when_the_device_is_not_found(monkeypatch, tmp_path):
    xml, j, calls, generic = _lightwright_apply_setup(monkeypatch, tmp_path, [])
    out = spotlight.vw_lightwright_patch([{"uid": "1001.1.1.0.0", "fields": {"Channel": "5"}}], dry_run=False)
    assert out["inverse_from"] == "export" and "stale" in out["note"]
    generic.vw_revert_last()
    assert "<Channel>101</Channel>" in xml.read_text()


def test_mvr_check_position_filter_keeps_whole_document_id_decision(monkeypatch):
    base = _mvr_rows()[0]
    rows = [dict(base, uuid="a1", Position="A", **{"GDTF Fixture Type ID": "12", "Fixture ID": "1"}),
            dict(base, uuid="b1", Position="B", UniverseAddress="2/1",
                 **{"GDTF Fixture Type ID": "0", "Fixture ID": "2"}),
            dict(base, uuid="b2", Position="B", UniverseAddress="2/20",
                 **{"GDTF Fixture Type ID": "0", "Fixture ID": "3"})]
    monkeypatch.setattr(spotlight, "vw", lambda fn, **kw: {
        "document": "Plot.vwx", "devices": rows,
        "fields": list(spotlight.mvr.FIELDS) + ["GDTF Fixture Type ID"],
        "positions": ["A", "B"], "symbols": {"S": {"type": 2}}})
    out = spotlight.vw_mvr_check(position="B")
    assert out["device_count"] == 2
    found = [i for i in out["issues"] if i["check"] == "gdtf_unlinked"]
    assert [d["uuid"] for d in found[0]["devices"]] == ["b1", "b2"]
    assert all(i["check"] != "field_unused" for i in out["issues"])
