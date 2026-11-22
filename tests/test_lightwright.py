"""Lightwright Data Exchange XML: reading the export, building guarded patches."""

import pytest

from vwmcp import lightwright as lw

SAMPLE = """<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<SLData>
  <ExportFieldList>
    <AppStamp>Vectorworks</AppStamp>
    <TimeStamp>20260101120000</TimeStamp>
    <Absolute_Address>Absolute Address</Absolute_Address>
    <Inst_Type>Instrument Type</Inst_Type>
    <Unit_Number>Unit Number</Unit_Number>
    <Color>Color</Color>
    <Channel>Channel</Channel>
    <Position>Position</Position>
    <Wattage>Wattage</Wattage>
    <Purpose>Purpose</Purpose>
  </ExportFieldList>
  <InstrumentData>
    <Action>Entire Plot</Action>
    <AppStamp>Vectorworks</AppStamp>
    <VWVersion>3150</VWVersion>
    <VWBuild>862586</VWBuild>
    <AutoRot2D>false</AutoRot2D>
    <UID_1001_1_1_0_0>
      <Action>Update</Action>
      <TimeStamp>20260101120000</TimeStamp>
      <AppStamp>Vectorworks</AppStamp>
      <UID>1001.1.1.0.0</UID>
      <Lightwright_ID>155226:2C4:1C:1:Vecto</Lightwright_ID>
      <Device_Type>Moving Light</Device_Type>
      <Symbol_Name>Ayrton EagleStrike</Symbol_Name>
      <Layer>Lighting</Layer>
      <Absolute_Address>1</Absolute_Address>
      <Inst_Type>Ayrton EagleStrike</Inst_Type>
      <Unit_Number>1</Unit_Number>
      <Color />
      <Channel>101</Channel>
      <Position>LX 1</Position>
      <Wattage>700 W</Wattage>
      <Purpose />
      <X_Location_mm>1000</X_Location_mm>
      <Accessories>
        <UID_1001_1_1_1_1><Device_Type>Static Accessory</Device_Type></UID_1001_1_1_1_1>
      </Accessories>
    </UID_1001_1_1_0_0>
    <UID_1002_1_1_0_0>
      <Action>Update</Action>
      <UID>1002.1.1.0.0</UID>
      <Lightwright_ID>155226:2C4:1C:2:Vecto</Lightwright_ID>
      <Device_Type>Light</Device_Type>
      <Symbol_Name>Source Four 26deg</Symbol_Name>
      <Inst_Type>Source Four 26deg</Inst_Type>
      <Unit_Number>2</Unit_Number>
      <Channel>102</Channel>
      <Position>LX 1</Position>
      <Wattage>750 W</Wattage>
    </UID_1002_1_1_0_0>
  </InstrumentData>
</SLData>
"""


@pytest.fixture
def xml(tmp_path):
    p = tmp_path / "Plot.xml"
    p.write_text(SAMPLE, encoding="utf-8")
    (tmp_path / "Plot.vwx").write_bytes(b"")
    return p


def test_find_xml_next_to_the_document(xml, tmp_path):
    assert lw.find_xml(str(tmp_path / "Plot.vwx")) == xml
    assert lw.find_xml(str(tmp_path / "Other.vwx")) is None
    assert lw.find_xml("") is None


def test_find_xml_accepts_a_differently_cased_name_with_sldata(tmp_path):
    (tmp_path / "show.vwx").write_bytes(b"")
    (tmp_path / "SHOW.xml").write_text(SAMPLE, encoding="utf-8")
    (tmp_path / "notes.xml").write_text("<notes/>", encoding="utf-8")
    assert lw.find_xml(str(tmp_path / "show.vwx")) == tmp_path / "SHOW.xml"


def test_parse_reads_fields_and_skips_accessories(xml):
    snap = lw.parse(xml)
    assert snap["exported"] == "20260101120000" and snap["vw_version"] == "3150"
    assert snap["fields"][:2] == ["Absolute_Address", "Inst_Type"]
    assert len(snap["fixtures"]) == 2
    f = snap["fixtures"][0]
    assert f["uid"] == "1001.1.1.0.0" and f["Channel"] == "101" and f["Color"] == ""
    assert f["lightwright_id"] == "155226:2C4:1C:1:Vecto"
    assert f["accessories"] == 1 and "X_Location_mm" in f and "Accessories" not in f


def test_build_patch_emits_only_the_changed_fields_with_the_metadata(xml):
    snap = lw.parse(xml)
    patch = lw.build_patch(xml.read_text(), snap, [{"uid": "1001.1.1.0.0", "fields": {"Channel": "201"}}],
                           now="20260102030405")
    assert patch.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<Inventory>" in patch and patch.count("<AppStamp>Lightwright</AppStamp>") == 3
    assert "<ExportFieldList>" in patch and "<Absolute_Address>Absolute Address</Absolute_Address>" in patch
    assert "<VWVersion>3150</VWVersion>" in patch and "<VWBuild>862586</VWBuild>" in patch
    block = patch[patch.index("<UID_1001_1_1_0_0>"):patch.index("</UID_1001_1_1_0_0>")]
    assert "<Channel>201</Channel>" in block and "<Position>" not in block
    assert "<Lightwright_ID>155226:2C4:1C:1:Vecto</Lightwright_ID>" in block
    assert "<UID>1001.1.1.0.0</UID>" in block and "<Action>Update</Action>" in block
    assert "<TimeStamp>20260102030405</TimeStamp>" in block
    assert "UID_1002" not in patch


def test_build_patch_guards(xml):
    snap = lw.parse(xml)
    text = xml.read_text()
    with pytest.raises(lw.PatchError, match="not in the export"):
        lw.build_patch(text, snap, [{"uid": "1001.1.1.0.0", "fields": {"User_Field_1": "x"}}])
    with pytest.raises(lw.PatchError, match="unknown fixture"):
        lw.build_patch(text, snap, [{"uid": "9.9.9.9.9", "fields": {"Channel": "1"}}])
    with pytest.raises(lw.PatchError, match="Delete"):
        lw.build_patch(text, snap, [{"uid": "1001.1.1.0.0", "fields": {"Action": "Delete"}}])
    with pytest.raises(lw.PatchError, match="metadata"):
        lw.build_patch(text, snap, [{"uid": "1001.1.1.0.0", "fields": {"UID": "2"}}])
    with pytest.raises(lw.PatchError, match="no changes"):
        lw.build_patch(text, snap, [])
    # a type swap needs a Symbol_Name some fixture already uses, and a Wattage
    with pytest.raises(lw.PatchError, match="no fixture uses"):
        lw.build_patch(text, snap, [{"uid": "1001.1.1.0.0", "fields": {
            "Inst_Type": "Robe", "Symbol_Name": "Robe", "Wattage": "1 W"}}])
    with pytest.raises(lw.PatchError, match="Wattage"):
        lw.build_patch(text, snap, [{"uid": "1001.1.1.0.0", "fields": {
            "Inst_Type": "Source Four 26deg", "Symbol_Name": "Source Four 26deg"}}])
    ok = lw.build_patch(text, snap, [{"uid": "1001.1.1.0.0", "fields": {
        "Inst_Type": "Source Four 26deg", "Symbol_Name": "Source Four 26deg", "Wattage": "750 W"}}])
    assert "<Use_Legend />" in ok


def test_inverse_changes_restore_previous_values(xml):
    snap = lw.parse(xml)
    changes = [{"uid": "1001.1.1.0.0", "fields": {"Channel": "201", "Purpose": "Key"}}]
    assert lw.inverse_changes(snap, changes) == [{"uid": "1001.1.1.0.0", "fields": {"Channel": "101", "Purpose": ""}}]


def test_revert_patch_is_built_from_the_journaled_envelope_not_the_patched_file(xml):
    # After an apply the file on disk is the sparse patch; the revert must not need it.
    snap = lw.parse(xml)
    changes = [{"uid": "1001.1.1.0.0", "fields": {
        "Inst_Type": "Source Four 26deg", "Symbol_Name": "Source Four 26deg", "Wattage": "750 W"}}]
    op = lw.revert_op(xml, xml.read_text(), snap, changes)
    assert op["op"] == "lightwright" and op["path"] == str(xml)
    assert op["changes"][0]["fields"]["Symbol_Name"] == "Ayrton EagleStrike"
    patch = lw.render_patch(op["envelope"], op["changes"], now="20260102030405")
    assert "<Symbol_Name>Ayrton EagleStrike</Symbol_Name>" in patch and "<Wattage>700 W</Wattage>" in patch
    assert "<Lightwright_ID>155226:2C4:1C:1:Vecto</Lightwright_ID>" in patch
    assert "<ExportFieldList>" in patch


def test_values_are_xml_escaped(xml):
    snap = lw.parse(xml)
    patch = lw.build_patch(xml.read_text(), snap, [{"uid": "1001.1.1.0.0", "fields": {"Purpose": "R&J <act 2>"}}])
    assert "<Purpose>R&amp;J &lt;act 2&gt;</Purpose>" in patch


# Live 2026-11-20 (VW 2026 31.7): after consuming a patch Vectorworks writes
# back only this: the field list and an empty <InstrumentData>.
ACK = """<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<SLData>
  <Inventory>
    <AppStamp>Lightwright</AppStamp>
  </Inventory>
  <ExportFieldList>
    <AppStamp>Vectorworks</AppStamp>
    <TimeStamp>20251208162056</TimeStamp>
    <Channel>Channel</Channel>
  </ExportFieldList>
  <InstrumentData>
    <AppStamp>Vectorworks</AppStamp>
    <VWVersion>3120</VWVersion>
    <VWBuild>841021</VWBuild>
    <AutoRot2D>true</AutoRot2D>
    </InstrumentData>
</SLData>
"""


def test_inverse_prefers_live_values_over_the_export(xml):
    sample_snapshot = lw.parse(xml)
    changes = [{"uid": "1001.1.1.0.0", "fields": {"Channel": "5", "Color": "R02"}}]
    live = {"1001.1.1.0.0": {"Channel": "901"}}  # the export said 101: it was stale
    (inv,) = lw.inverse_changes(sample_snapshot, changes, live=live)
    assert inv["fields"] == {"Channel": "901", "Color": ""}


def test_backup_export_keeps_the_full_file(tmp_path):
    xml = tmp_path / "Plot.xml"
    xml.write_text(SAMPLE)
    out = lw.backup_export(xml, SAMPLE, tmp_path / "backups")
    assert out.parent == tmp_path / "backups" and out.name.startswith("Plot-") and out.suffix == ".xml"
    assert out.read_text() == SAMPLE


def test_missing_fields_error_shows_the_expected_shape(xml):
    sample_snapshot = lw.parse(xml)
    with pytest.raises(lw.PatchError, match='"fields"'):
        lw.check_changes(sample_snapshot, [{"uid": "1001.1.1.0.0", "Channel": "5"}])


def test_acknowledgement_file_parses_empty_and_patch_explains(tmp_path):
    xml = tmp_path / "Plot.xml"
    xml.write_text(ACK)
    snap = lw.parse(xml)
    assert snap["fixtures"] == [] and lw.is_acknowledgement(snap) is True
    with pytest.raises(lw.PatchError, match="full export"):
        lw.check_changes(snap, [{"uid": "1001.1.1.0.0", "fields": {"Channel": "5"}}])


def test_record_field_name_from_xml_tag():
    assert lw.record_field("Unit_Number") == "Unit Number"
    assert lw.record_field("Inst_Type") == "Inst Type"
    assert lw.record_field("Template2") == "Template2"
    assert lw.record_field("User_Field_6") == "User Field 6"
