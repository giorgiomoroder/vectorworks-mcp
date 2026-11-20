"""Channel hookup import: spreadsheet rows -> vw_set_lighting_device_fields updates."""

import pytest

from vwmcp import hookup

KNOWN = ["Unit Number", "Channel", "Position", "Purpose", "Color", "UniverseAddress",
         "Universe", "DMX Address", "Dimmer", "Focus", "User Field 1"]


def test_read_csv_with_bom_and_header(tmp_path):
    p = tmp_path / "hookup.csv"
    p.write_text("﻿Channel,Purpose,Color\n1,Front wash,R02\n2,,\n", encoding="utf-8")
    assert hookup.read_table(p) == [
        {"Channel": "1", "Purpose": "Front wash", "Color": "R02"},
        {"Channel": "2", "Purpose": "", "Color": ""},
    ]


def test_read_tsv_by_extension(tmp_path):
    p = tmp_path / "hookup.tsv"
    p.write_text("Channel\tPurpose\n1\tFront, warm\n", encoding="utf-8")
    assert hookup.read_table(p) == [{"Channel": "1", "Purpose": "Front, warm"}]


def test_read_table_rejects_unknown_extension(tmp_path):
    p = tmp_path / "hookup.xlsx"
    p.write_bytes(b"PK")
    with pytest.raises(ValueError, match="csv"):
        hookup.read_table(p)


def test_plan_by_channel_maps_known_headers_case_insensitively():
    rows = [{"channel": "101", "purpose": "Key", "COLOR": "L201", "Notes": "x"}]
    plan = hookup.plan_updates(rows, key="channel", known_fields=KNOWN)
    assert plan["updates"] == [{"channel": "101", "fields": {"Purpose": "Key", "Color": "L201"}}]
    assert plan["ignored"] == ["Notes"]
    assert plan["skipped_rows"] == 0


def test_plan_address_aliases_go_to_universe_address():
    for header in ("Address", "Addr", "DMX"):
        plan = hookup.plan_updates([{"Channel": "1", header: "2/101"}], key="channel", known_fields=KNOWN)
        assert plan["updates"][0]["fields"] == {"UniverseAddress": "2/101"}, header


def test_plan_universe_and_dmx_columns_are_passed_through():
    rows = [{"Channel": "1", "Universe": "2", "DMX Address": "101"}]
    plan = hookup.plan_updates(rows, key="channel", known_fields=KNOWN)
    assert plan["updates"][0]["fields"] == {"Universe": "2", "DMX Address": "101"}


def test_plan_by_position_and_unit():
    rows = [{"Position": "1E", "Unit": "3", "Channel": "7"}]
    plan = hookup.plan_updates(rows, key="position+unit_number", known_fields=KNOWN)
    assert plan["updates"] == [{"position": "1E", "unit_number": "3", "fields": {"Channel": "7"}}]


def test_plan_skips_rows_with_empty_key_and_empty_values():
    rows = [{"Channel": "", "Purpose": "x"}, {"Channel": "5", "Purpose": ""}, {"Channel": "6", "Purpose": "y"}]
    plan = hookup.plan_updates(rows, key="channel", known_fields=KNOWN)
    assert plan["updates"] == [{"channel": "6", "fields": {"Purpose": "y"}}]
    assert plan["skipped_rows"] == 2


def test_plan_explicit_column_map_wins():
    rows = [{"Ch": "1", "What": "Key"}]
    plan = hookup.plan_updates(rows, key="channel", known_fields=KNOWN,
                               column_map={"Ch": "Channel", "What": "Purpose"})
    assert plan["updates"] == [{"channel": "1", "fields": {"Purpose": "Key"}}]


def test_plan_key_column_missing_is_an_error():
    with pytest.raises(ValueError, match="Channel"):
        hookup.plan_updates([{"Purpose": "x"}], key="channel", known_fields=KNOWN)


def test_plan_unknown_key():
    with pytest.raises(ValueError, match="key"):
        hookup.plan_updates([{"Channel": "1"}], key="serial", known_fields=KNOWN)
