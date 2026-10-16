import csv
import io

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
