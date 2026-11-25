"""List the open Vectorworks documents and bring one to the front (macOS).

The vs.* API has no call to list or activate open documents, and switching
documents inside a running script is not safe. This module talks to
Vectorworks from outside with plain AppleScript (Automation permission, the
same one the job trigger already uses; no Accessibility permission):

- `name of every window whose visible is true` lists the open documents
  (the first document window is the active one; empty names and helper
  windows such as "Window" or, in 2027, "Vectorworks" are skipped);
- `open POSIX file <path>` brings an already open, saved document to the
  front without opening it twice (setting a window's index does not select
  a document tab, live-tested on Vectorworks 2027).

Vectorworks' AppleScript does not report a document's file, so the server
remembers the path of every document it has seen active
(document_paths.json in the server's home, ~/.vwmcp by default). Unsaved documents can't be switched to.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from vwmcp import config
from vwmcp.client import DEFAULT_ROOT

# Addressed by name, like the job trigger, so that with two Vectorworks
# versions installed each server talks to its own app (the bundle id
# "net.nemetschek.vectorworks" is shared between versions).
APP = config.DEFAULT_APP
# Non-document windows Vectorworks reports: unnamed and palette windows, and
# (2027) a window named after the app itself. Invisible windows are left out
# by the script ("Migration Progress", "Exporting MVR" exist hidden in 2027).
# Not documents: helper windows, and the non-modal dialogs seen live
# (2026-11-20: About and Preferences stay open while scripts run).
HELPER_WINDOWS = {"", "Window", "Fenster", "Vectorworks",
                  "About Vectorworks", "Vectorworks Preferences"}
STATE = DEFAULT_ROOT / "document_paths.json"

# Every window, visible or not: document tabs behind the front one are
# invisible windows (live 2026-11-25 on Vectorworks 2027: the front tab is
# visible, the others and the helper windows are not). One "name<TAB>visible"
# line per window, front to back.
LIST_SCRIPT = f'''
set out to ""
tell application "{APP}"
  repeat with w in every window
    set out to out & (name of w) & tab & (visible of w) & linefeed
  end repeat
end tell
return out
'''

OPEN_SCRIPT = f'''
on run argv
  tell application "{APP}" to open (POSIX file (item 1 of argv))
  return "ok"
end run
'''


class DocumentsError(RuntimeError):
    pass


def _osascript(script: str, *args: str) -> str:
    if sys.platform != "darwin":
        raise DocumentsError("Switching documents is only available on macOS.")
    res = subprocess.run(["osascript", "-", *args], input=script, capture_output=True, text=True, timeout=30)
    if res.returncode != 0:
        raise DocumentsError(res.stderr.strip() or "osascript failed")
    return res.stdout


def parse_windows(text: str) -> dict:
    """Window lines (front to back, "name" or "name<TAB>true|false") ->
    {"documents": [...], "active": name}. Hidden document tabs are listed
    too; the active document is the first visible one. An unsaved document
    ("Untitled 1") counts only while it is in front: hidden, it cannot be
    told from a helper window."""
    docs, active = [], None
    for line in text.splitlines():
        name, _, vis = line.partition("\t")
        name = name.strip()
        visible = vis.strip().lower() != "false"
        if name in HELPER_WINDOWS or name in docs:
            continue
        if not visible and not name.lower().endswith(".vwx"):
            continue
        docs.append(name)
        if visible and active is None:
            active = name
    if not docs:
        raise DocumentsError("No document is open in Vectorworks.")
    return {"documents": docs, "active": active or docs[0]}


def load_paths() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def remember(name: str, path: str) -> None:
    """Note where a document lives (path as Vectorworks reports it)."""
    if not name or not path or not os.path.isabs(path):
        return
    paths = load_paths()
    if paths.get(name) != path:
        paths[name] = path
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(paths, ensure_ascii=False, indent=1), encoding="utf-8")


def list_documents() -> dict:
    out = parse_windows(_osascript(LIST_SCRIPT))
    paths = load_paths()
    out["paths"] = {d: paths[d] for d in out["documents"] if d in paths and Path(paths[d]).exists()}
    return out


def _match(name: str, docs: list[str]) -> str | None:
    if name in docs:
        return name
    return next((d for d in docs if d.rsplit(".", 1)[0] == name.rsplit(".", 1)[0]), None)


def open_document(path: str, wait: float = 60.0, poll: float = 1.0) -> dict:
    """Open a .vwx file that is not open yet (`open POSIX file`, the same
    Apple Event switch_document uses) and wait until its window is in front.
    A file saved by an older Vectorworks is converted on open (the 2027
    "Migration Progress" window); nothing is saved. Returns {active, opened,
    documents, seconds}."""
    import time
    p = Path(path).expanduser()
    if not p.is_absolute() or p.suffix.lower() != ".vwx":
        raise DocumentsError(f"{path!r} is not an absolute path to a .vwx file.")
    if not p.exists():
        raise DocumentsError(f"{p} does not exist.")
    before = list_documents()
    already = _match(p.name, before["documents"])
    if already is not None:
        out = switch_document(str(p))
        out["opened"] = False
        return out
    _osascript(OPEN_SCRIPT, str(p))
    t0 = time.monotonic()
    converted = p.stem + "_v"  # an older file opens as "<name>_v2027.vwx", unsaved
    while True:
        after = parse_windows(_osascript(LIST_SCRIPT))
        target = _match(p.name, after["documents"])
        if target is None:
            target = next((d for d in after["documents"] if d.startswith(converted)), None)
        if target is not None and after["active"] == target:
            out = {"active": target, "opened": True, "documents": after["documents"],
                   "seconds": round(time.monotonic() - t0, 1)}
            if target == p.name:
                remember(target, str(p))
            else:
                out["converted"] = True
                out["note"] = (f"{p.name} was saved by an older Vectorworks; this is a converted, unsaved "
                               f"copy named {target!r}. Save As in Vectorworks to keep it.")
            return out
        if time.monotonic() - t0 > wait:
            raise DocumentsError(
                f"Asked Vectorworks to open {p.name!r}; after {wait:.0f} s the front document is "
                f"{after['active']!r} (open: {', '.join(after['documents']) or 'none'}). A dialog may be "
                "waiting in Vectorworks (vw_screenshot shows it).")
        time.sleep(poll)


def switch_document(name_or_path: str) -> dict:
    """Bring an open document to the front, by name (as listed) or by path.
    Verified afterwards by the front window's name."""
    before = list_documents()
    docs = before["documents"]
    p = Path(name_or_path).expanduser()
    if p.suffix and p.is_absolute():
        path = str(p)
        target = _match(p.name, docs)
        if target is None:
            raise DocumentsError(f"{p.name!r} is not open. Open documents: {', '.join(docs)}")
    else:
        target = _match(name_or_path, docs)
        if target is None:
            raise DocumentsError(f"{name_or_path!r} is not open. Open documents: {', '.join(docs)}")
        path = before["paths"].get(target)
    if before["active"] == target:
        return {"active": target, "switched": False, "documents": docs}
    if not path:
        raise DocumentsError(
            f"Don't know where {target!r} is saved (unsaved documents can't be switched to). Pass its "
            "full path, or bring it to the front once by hand so the path is remembered.")
    if not Path(path).exists():
        raise DocumentsError(f"{path} no longer exists.")
    _osascript(OPEN_SCRIPT, path)
    after = parse_windows(_osascript(LIST_SCRIPT))
    if after["active"] != target:
        raise DocumentsError(f"Asked Vectorworks to show {target!r}, but {after['active']!r} is still in "
                             "front. Is a dialog open in Vectorworks?")
    return {"active": target, "switched": True, "previous": before["active"], "documents": after["documents"]}
