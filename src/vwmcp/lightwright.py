"""Spotlight's Lightwright Data Exchange XML as a second data channel.

With Spotlight > Preferences > Lightwright > "Use automatic Lightwright Data
Exchange" on, Vectorworks writes <document>.xml next to the .vwx whenever
it loses focus (and on a full export), and watches that file for patches
stamped "Lightwright". Format decoded by Gribiche64/vectorworks-bridge
(PROTOCOL.md, MIT, May 2026, VW 2026); no plug-in involved.

Read: every Lighting Device with the exported fields, even while a dialog
blocks the bridge. Write: a sparse patch (only changed fields, Action=Update)
that Vectorworks applies 1 to 2 s after it next gains focus. Guards (from
the protocol's hard lessons): never Delete; a Symbol_Name must already be
used by a fixture in the export (an unknown one breaks fixture selection in
the whole drawing, irreversibly); a type change must carry Wattage (it is
not updated by Vectorworks). A revert is the inverse patch, built from the
envelope saved in the journal (after an apply the file on disk is the
patch, not the export).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from vwmcp.client import DEFAULT_ROOT

# Full exports are copied here before a patch overwrites them (the file beside
# the document holds the patch, then Vectorworks' acknowledgement, until the
# next full export).
BACKUP_DIR = DEFAULT_ROOT / "lightwright"

META = {"Action", "TimeStamp", "AppStamp", "UID", "Lightwright_ID", "Use_Legend", "Accessories"}
# Written by every export whatever the field list says (the protocol's type-swap fields).
ALWAYS_WRITABLE = {"Symbol_Name", "Inst_Type", "Wattage"}
HINT = ("Turn on the exchange in Spotlight Preferences: Spotlight > Preferences > Lightwright, "
        "'Use automatic Lightwright Data Exchange' with 'Perform a full export' checked once. "
        "Save, then click into another app and back: Vectorworks writes <document>.xml next "
        "to the .vwx.")


ACK_HINT = ("The exchange file holds no fixtures: Vectorworks acknowledged the last patch "
            "and has not re-exported (live 2026-11-20: it writes back only the field list). "
            "For a fresh snapshot redo the full export (Spotlight > Preferences > Lightwright, "
            "'Perform a full export'), or read the drawing with vw_list_lighting_devices.")


class PatchError(ValueError):
    pass


def record_field(tag: str) -> str:
    """The Lighting Device record field behind an exchange tag
    (Unit_Number -> 'Unit Number', Inst_Type -> 'Inst Type', Template2 stays)."""
    return tag.replace("_", " ")


def is_acknowledgement(snapshot: dict) -> bool:
    """True for the file Vectorworks writes back after consuming a patch:
    a field list and an empty <InstrumentData>."""
    return not snapshot["fixtures"]


def find_xml(doc_path: str | None) -> Path | None:
    """The exchange file for a saved document: <stem>.xml beside it (any
    case) that is a Lightwright export (<SLData>)."""
    if not doc_path:
        return None
    p = Path(doc_path)
    if not p.parent.is_dir():
        return None
    # Scan the folder (rather than test <stem>.xml directly) so the name comes
    # back as it is on disk, whatever the filesystem's case sensitivity.
    for other in sorted(p.parent.glob("*.xml"), key=lambda q: q.name != p.stem + ".xml"):
        if other.stem.casefold() != p.stem.casefold():
            continue
        try:
            head = other.read_text(encoding="utf-8", errors="replace")[:400]
        except OSError:
            continue
        if "<SLData>" in head:
            return other
    return None


def parse(path: Path) -> dict:
    """{"path", "exported", "vw_version", "vw_build", "fields", "fixtures"}:
    one row per top-level fixture with its exported fields (accessories are
    counted, not listed)."""
    root = ET.parse(path).getroot()
    efl = root.find("ExportFieldList")
    fields = [c.tag for c in efl if c.tag not in ("AppStamp", "TimeStamp")] if efl is not None else []
    data = root.find("InstrumentData")
    if data is None:
        raise PatchError(f"{path.name} has no <InstrumentData>")
    fixtures = []
    for el in data:
        if not el.tag.startswith("UID_"):
            continue
        row = {"uid": (el.findtext("UID") or el.tag[4:].replace("_", ".")).strip(),
               "lightwright_id": (el.findtext("Lightwright_ID") or "").strip()}
        acc = el.find("Accessories")
        row["accessories"] = sum(1 for c in acc if c.tag.startswith("UID_")) if acc is not None else 0
        for c in el:
            if c.tag not in META:
                row[c.tag] = (c.text or "").strip()
        fixtures.append(row)
    return {"path": str(path), "exported": (efl.findtext("TimeStamp") if efl is not None else "") or "",
            "vw_version": data.findtext("VWVersion") or "", "vw_build": data.findtext("VWBuild") or "",
            "fields": fields, "fixtures": fixtures}


def _block(text: str, tag: str) -> str:
    m = re.search(rf"<{tag}\b.*?</{tag}>", text, re.S)
    if not m:
        raise PatchError(f"the export has no <{tag}>")
    return m.group(0)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def uid_tag(uid: str) -> str:
    return "UID_" + uid.replace(".", "_")


def envelope_of(xml_text: str, snapshot: dict) -> dict:
    """What a patch needs besides the changes: the export's field list and
    Vectorworks version (kept in the journal for the revert)."""
    return {"export_field_list": _block(xml_text, "ExportFieldList"),
            "vw_version": snapshot.get("vw_version") or "3150", "vw_build": snapshot.get("vw_build") or "0"}


def render_patch(envelope: dict, changes: list[dict], now: str | None = None) -> str:
    """The patch text for changes [{"uid", "lightwright_id", "fields"}]; no
    guards (see build_patch for those)."""
    stamp = now or utc_now()
    blocks = []
    for ch in changes:
        uid = ch["uid"]
        lines = [f"    <{uid_tag(uid)}>"]
        for name, value in ch["fields"].items():
            lines.append(f"      <{name} />" if value is None else f"      <{name}>{escape(str(value))}</{name}>")
        lines += [f"      <Lightwright_ID>{escape(ch.get('lightwright_id') or '')}</Lightwright_ID>",
                  f"      <UID>{uid}</UID>", "      <AppStamp>Lightwright</AppStamp>",
                  f"      <TimeStamp>{stamp}</TimeStamp>", "      <Action>Update</Action>",
                  f"    </{uid_tag(uid)}>"]
        blocks.append("\n".join(lines))
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>', "<SLData>",
        "  <Inventory>", "    <AppStamp>Lightwright</AppStamp>", "  </Inventory>",
        "  " + envelope["export_field_list"],
        "  <InstrumentData>", "    <AppStamp>Lightwright</AppStamp>",
        f"    <VWVersion>{envelope['vw_version']}</VWVersion>",
        f"    <VWBuild>{envelope['vw_build']}</VWBuild>", "    <AutoRot2D>false</AutoRot2D>",
        *blocks, "  </InstrumentData>", "</SLData>", ""])


def check_changes(snapshot: dict, changes: list[dict]) -> list[dict]:
    """Validate changes [{"uid", "fields"}] against the export; return them
    completed with lightwright_id (and Use_Legend on a type change)."""
    if not changes:
        raise PatchError("no changes")
    by_uid = {f["uid"]: f for f in snapshot["fixtures"]}
    writable = set(snapshot["fields"]) | ALWAYS_WRITABLE
    in_use = {f.get("Symbol_Name") for f in snapshot["fixtures"] if f.get("Symbol_Name")}
    out = []
    for ch in changes:
        uid, fields = ch.get("uid", ""), dict(ch.get("fields") or {})
        if uid not in by_uid:
            if is_acknowledgement(snapshot):
                raise PatchError(ACK_HINT)
            raise PatchError(f"unknown fixture UID {uid!r} (not in the export)")
        if not fields:
            raise PatchError(f'no fields for {uid}: each change is {{"uid": ..., "fields": {{name: value}}}}')
        if "Action" in fields:
            raise PatchError("Action is set by the patch (Update); Delete is refused on purpose")
        for name in fields:
            if name in META:
                raise PatchError(f"{name} is protocol metadata, not a fixture field")
            if name not in writable:
                raise PatchError(f"{name!r} is not in the export field list; add it in Spotlight "
                                 "Preferences > Lightwright, or use vw_set_lighting_device_fields")
        sym = fields.get("Symbol_Name")
        if sym and sym not in in_use:
            raise PatchError(f"Symbol_Name {sym!r}: no fixture uses it in this drawing yet. An unknown "
                             "symbol breaks fixture selection for the whole drawing (irreversibly). "
                             "Place one fixture of that type first.")
        if "Inst_Type" in fields and "Wattage" not in fields:
            raise PatchError("a type change (Inst_Type) must set Wattage too: Vectorworks keeps the old one")
        if "Inst_Type" in fields:
            fields.setdefault("Use_Legend", None)
        out.append({"uid": uid, "lightwright_id": by_uid[uid].get("lightwright_id", ""), "fields": fields})
    return out


def build_patch(xml_text: str, snapshot: dict, changes: list[dict], now: str | None = None) -> str:
    """Lightwright-style sparse patch for `changes` ([{"uid", "fields": {...}}])
    against the export the XML was parsed into. Raises PatchError on
    anything the protocol says not to do."""
    return render_patch(envelope_of(xml_text, snapshot), check_changes(snapshot, changes), now)


def inverse_changes(snapshot: dict, changes: list[dict], live: dict | None = None) -> list[dict]:
    """The changes that would restore the previous values (for revert): the
    drawing's current values where `live` ({uid: {field: value}}) has them,
    else the export's (which can be stale: live 2026-11-20 an export said
    channel 999 where the drawing had 901)."""
    by_uid = {f["uid"]: f for f in snapshot["fixtures"]}
    live = live or {}
    out = []
    for ch in changes:
        prev = {**by_uid.get(ch["uid"], {}), **live.get(ch["uid"], {})}
        out.append({"uid": ch["uid"],
                    "fields": {k: prev.get(k, "") for k in ch["fields"] if k != "Use_Legend"}})
    return out


def revert_op(path: Path, xml_text: str, snapshot: dict, changes: list[dict],
              live: dict | None = None) -> dict:
    """Journal op that reverts `changes` later without re-reading the file
    (which by then holds the patch): inverse changes with their
    Lightwright_IDs plus the envelope."""
    by_uid = {f["uid"]: f for f in snapshot["fixtures"]}
    inverse = inverse_changes(snapshot, changes, live)
    for ch in inverse:
        ch["lightwright_id"] = by_uid.get(ch["uid"], {}).get("lightwright_id", "")
        if "Inst_Type" in ch["fields"]:
            ch["fields"]["Use_Legend"] = None
    return {"op": "lightwright", "path": str(path), "envelope": envelope_of(xml_text, snapshot),
            "changes": inverse}


def backup_export(path: Path, text: str, folder: Path) -> Path:
    """Copy the full export's text to folder/<stem>-<UTC stamp>.xml before a
    patch overwrites the file; returns the copy's path."""
    folder.mkdir(parents=True, exist_ok=True)
    stamp = utc_now()
    out = folder / f"{path.stem}-{stamp}.xml"
    n = 1
    while out.exists():
        n += 1
        out = folder / f"{path.stem}-{stamp}-{n}.xml"
    out.write_text(text, encoding="utf-8")
    return out


def write_patch(path: Path, patch: str) -> None:
    """Overwrite the exchange file in place (no rename: Vectorworks watches
    this path with FSEvents)."""
    path.write_text(patch, encoding="utf-8")
