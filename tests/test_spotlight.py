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
