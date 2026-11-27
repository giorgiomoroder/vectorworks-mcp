"""MVR export pre-flight: pure checks over Lighting Device rows (no Vectorworks)."""

from vwmcp import mvr

ALL_FIELDS = [
    "Unit Number", "Channel", "Position", "Inst Type", "Symbol Name", "Fixture Mode",
    "GDTF Fixture Name", "GDTF Fixture Type ID", "Fixture ID", "UniverseAddress",
    "Absolute Address", "Num Channels",
]


def device(uuid="u1", unit="1", channel="1", position="FOH", symbol="MAC One",
           mode="Standard", gdtf="Martin@MAC One", fixture_id="1", address="1/1",
           absolute="1", channels="16"):
    return {
        "uuid": uuid, "Unit Number": unit, "Channel": channel, "Position": position,
        "Inst Type": "MAC One", "Symbol Name": symbol, "Fixture Mode": mode,
        "GDTF Fixture Name": gdtf, "GDTF Fixture Type ID": "12" if gdtf else "0",
        "Fixture ID": fixture_id, "UniverseAddress": address,
        "Absolute Address": absolute, "Num Channels": channels,
    }


def data(devices, fields=None, positions=("FOH",), symbols=None):
    return {
        "fields": list(fields or ALL_FIELDS),
        "devices": devices,
        "positions": list(positions),
        "symbols": symbols if symbols is not None else {"MAC One": {"type": 2}},
    }


def checks(out):
    return {i["check"] for i in out["issues"]}


def issue(out, check):
    (found,) = [i for i in out["issues"] if i["check"] == check]
    return found


def test_clean_plot_is_ok():
    out = mvr.run_checks(data([device()]))
    assert out["ok"] is True
    assert out["issues"] == []
    assert out["device_count"] == 1


def test_parse_address():
    assert mvr.parse_address("2/101") == (2, 101)
    assert mvr.parse_address(" 1 / 1 ") == (1, 1)
    assert mvr.parse_address("") is None
    assert mvr.parse_address("0/0") is None
    assert mvr.parse_address("abc") is None


def test_missing_gdtf_is_an_error():
    out = mvr.run_checks(data([device(gdtf="")]))
    assert out["ok"] is False
    i = issue(out, "no_gdtf")
    assert i["severity"] == "error"
    assert i["devices"] == [{"uuid": "u1", "position": "FOH", "unit": "1", "channel": "1"}]


def test_missing_mode_is_an_error():
    out = mvr.run_checks(data([device(mode="")]))
    assert issue(out, "no_mode")["severity"] == "error"


def test_missing_fixture_id():
    out = mvr.run_checks(data([device(fixture_id="")]))
    assert issue(out, "no_fixture_id")["severity"] == "error"


def test_duplicate_fixture_id_lists_both_devices_once():
    out = mvr.run_checks(data([device(uuid="a", fixture_id="7"), device(uuid="b", unit="2", channel="2", fixture_id="7", address="1/17", absolute="17")]))
    i = issue(out, "duplicate_fixture_id")
    assert i["severity"] == "error"
    assert [d["uuid"] for d in i["devices"]] == ["a", "b"]
    assert "7" in i["message"]


def test_unpatched_variants():
    rows = [device(uuid="a", address="", absolute="0"),
            device(uuid="b", unit="2", channel="2", address="0/0", absolute="0", fixture_id="2"),
            device(uuid="c", unit="3", channel="3", address="1/33", absolute="33", fixture_id="3")]
    out = mvr.run_checks(data(rows))
    assert [d["uuid"] for d in issue(out, "unpatched")["devices"]] == ["a", "b"]


def test_overlapping_footprints_in_one_universe():
    rows = [device(uuid="a", address="1/1", absolute="1", channels="16"),
            device(uuid="b", unit="2", channel="2", fixture_id="2", address="1/10", absolute="10", channels="16"),
            device(uuid="c", unit="3", channel="3", fixture_id="3", address="2/10", absolute="522", channels="16")]
    out = mvr.run_checks(data(rows))
    i = issue(out, "address_overlap")
    assert i["severity"] == "error"
    assert [d["uuid"] for d in i["devices"]] == ["a", "b"]
    assert "1/1" in i["message"] and "1/10" in i["message"]


def test_footprint_past_512_is_flagged():
    out = mvr.run_checks(data([device(address="1/500", absolute="500", channels="16")]))
    assert "address_past_512" in checks(out)


def test_position_without_object_and_device_without_position_are_warnings():
    rows = [device(uuid="a", position="Nowhere"), device(uuid="b", unit="2", channel="2", fixture_id="2", position="", address="1/17", absolute="17")]
    out = mvr.run_checks(data(rows, positions=["FOH"]))
    assert issue(out, "position_without_object")["severity"] == "warning"
    assert "Nowhere" in issue(out, "position_without_object")["message"]
    assert [d["uuid"] for d in issue(out, "no_position")["devices"]] == ["b"]
    assert out["ok"] is True  # warnings alone don't fail the check


def test_2d_only_symbol_is_a_warning():
    out = mvr.run_checks(data([device()], symbols={"MAC One": {"type": 0}}))
    i = issue(out, "symbol_without_3d")
    assert i["severity"] == "warning"
    assert "MAC One" in i["message"]


def test_symbol_missing_from_document():
    out = mvr.run_checks(data([device(symbol="Ghost")], symbols={}))
    assert "symbol_missing" in checks(out)


def test_missing_field_skips_its_check_and_reports_once():
    fields = [f for f in ALL_FIELDS if f != "Fixture ID"]
    rows = [{k: v for k, v in device().items() if k != "Fixture ID"}]
    out = mvr.run_checks(data(rows, fields=fields))
    i = issue(out, "field_missing")
    assert "Fixture ID" in i["message"]
    assert "no_fixture_id" not in checks(out)
    assert "duplicate_fixture_id" not in checks(out)


def test_summary_counts_devices_per_check():
    rows = [device(uuid="a", mode=""), device(uuid="b", unit="2", channel="2", fixture_id="2", gdtf="", address="1/17", absolute="17")]
    out = mvr.run_checks(data(rows))
    assert out["summary"] == {"no_gdtf": 1, "no_mode": 1}


def test_fixtureid_is_the_fixture_type_not_an_id():
    # Live 2026-11-20: the BL plot (VW 2026) has "FixtureID" = "Astera AX5" etc.
    fields = [f for f in ALL_FIELDS if f != "Fixture ID"] + ["FixtureID"]
    rows = [{**{k: v for k, v in device(uuid="a").items() if k != "Fixture ID"}, "FixtureID": "Astera AX5"},
            {**{k: v for k, v in device(uuid="b", unit="2", channel="2", address="1/17", absolute="17").items()
                if k != "Fixture ID"}, "FixtureID": "Astera AX5"}]
    out = mvr.run_checks(data(rows, fields=fields))
    assert "duplicate_fixture_id" not in checks(out) and "no_fixture_id" not in checks(out)
    assert "Fixture ID" in issue(out, "field_missing")["message"]


def test_gdtf_fixture_mode_is_preferred_and_only_checked_with_a_gdtf_fixture():
    fields = ALL_FIELDS + ["GDTF Fixture Mode"]
    rows = [{**device(uuid="a"), "GDTF Fixture Mode": ""},                       # GDTF set, no GDTF mode
            {**device(uuid="b", unit="2", channel="2", fixture_id="2", address="1/17", absolute="17", gdtf="", mode=""),
             "GDTF Fixture Mode": ""}]                                          # no GDTF at all
    out = mvr.run_checks(data(rows, fields=fields))
    assert [d["uuid"] for d in issue(out, "no_mode")["devices"]] == ["a"]
    assert [d["uuid"] for d in issue(out, "no_gdtf")["devices"]] == ["b"]


def test_identical_addresses_are_a_shared_address_warning_not_an_overlap():
    rows = [device(uuid="a", address="1/207", absolute="207", channels="1"),
            device(uuid="b", unit="2", channel="2", fixture_id="2", address="1/207", absolute="207", channels="1"),
            device(uuid="c", unit="3", channel="3", fixture_id="3", address="2/311", absolute="823", channels="21"),
            device(uuid="d", unit="4", channel="4", fixture_id="4", address="2/330", absolute="842", channels="21")]
    out = mvr.run_checks(data(rows))
    shared = issue(out, "address_shared")
    assert shared["severity"] == "warning" and [x["uuid"] for x in shared["devices"]] == ["a", "b"]
    overlap = issue(out, "address_overlap")
    assert overlap["severity"] == "error" and [x["uuid"] for x in overlap["devices"]] == ["c", "d"]


def test_gdtf_name_typed_but_not_linked_is_an_error():
    # Live 2026-11-21: writing 'GDTF Fixture Name' / 'GDTF Fixture Mode' as text
    # links nothing (type id stays 0, channel count unchanged); the link is made
    # in the Object Info palette's GDTF chooser.
    linked = device(uuid="a")
    typed = {**device(uuid="b"), "GDTF Fixture Type ID": "0"}
    blank = device(uuid="c", gdtf="")
    out = mvr.run_checks(data([linked, typed, blank]))
    i = issue(out, "gdtf_unlinked")
    assert i["severity"] == "error" and [d["uuid"] for d in i["devices"]] == ["b"]
    assert "Object Info" in i["message"]
    assert [d["uuid"] for d in issue(out, "no_gdtf")["devices"]] == ["c"]
    # without the type id field (older documents) the check is skipped, not fired
    out2 = mvr.run_checks(data([typed], fields=[f for f in ALL_FIELDS if f != "GDTF Fixture Type ID"]))
    assert "gdtf_unlinked" not in checks(out2)


def test_gdtf_type_id_never_populated_skips_the_unlinked_check():
    # Live 2026-11-27 (Vectorworks 2027 32.1.0, German, Windows): every linked
    # device had 'GDTF Fixture Type ID' == "0" while carrying a real GDTF mode
    # and channel count. With no non-zero id anywhere, the id says nothing.
    rows = [{**device(uuid=u), "GDTF Fixture Type ID": "0"} for u in ("a", "b", "c")]
    out = mvr.run_checks(data(rows))
    assert "gdtf_unlinked" not in checks(out)
    note = issue(out, "field_unused")
    assert note["severity"] == "warning" and note["devices"] == []
    assert "GDTF Fixture Type ID" in note["message"] and "skipped" in note["message"]
    assert out["summary"].get("gdtf_unlinked", 0) == 0
    assert "field_unused" not in out["summary"]
    assert "field_unused" not in checks(mvr.run_checks(data([])))
    # one non-zero id in the document: the macOS rule applies again
    rows[0]["GDTF Fixture Type ID"] = "12"
    out2 = mvr.run_checks(data(rows))
    assert [d["uuid"] for d in issue(out2, "gdtf_unlinked")["devices"]] == ["b", "c"]
    assert "field_unused" not in checks(out2)
