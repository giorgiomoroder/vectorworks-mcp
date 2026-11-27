# Windows trigger: notes from other projects' in-app listeners

Status (2026-11-27): implemented as `vwmcp_bridge.listen()` (menu command
**MCP Listen**) and live-tested on Windows 11, Vectorworks 2027 (32.1.0,
German UI, Spotlight). See "Live findings 2026-11-27" at the end. The
research sections below were read from public code, not run.

## The problem

On macOS the server pokes Vectorworks with one Apple Event (`run
VectorScript` calling `DoMenuTextByName('MCP Run Job')`). Windows has no
equivalent, so today the user runs **MCP Run Job** by hand for each request.

## What the pure-Python projects do

Two projects run a Python listener *inside* Vectorworks and reached the same
answer: a **modal layout dialog with a timer** is the only pure-Python context
that can both stay alive and safely call `vs.*`.

**edmacovaz/rt-vectorworks-mcp** (`vw_mcp/listener.py`, VW 2026, macOS):

```python
dialog_id = vs.CreateLayout("VW MCP Session", False, "Stop", "")
vs.CreateStaticText(dialog_id, 4, "Agent session on 127.0.0.1:9877", 48)
vs.CreateStaticText(dialog_id, 5, "Agent drives VW while this is open; close to hand it back.", 56)
vs.SetFirstLayoutItem(dialog_id, 4)
vs.SetBelowItem(dialog_id, 4, 5, 0, 0)

def handler(item, data):
    if item == 12255:                      # SetupDialogC: dialog just opened
        vs.RegisterDialogForTimerEvents(dialog_id, 50)   # tick every 50 ms
        pump()
        return
    if item in (1, 2):                     # OK ("Stop") / Cancel: end session
        return
    pump()                                 # timer tick (or any other event)

try:
    vs.RunLayoutDialog(dialog_id, handler)
finally:
    vs.DeregisterDialogFromTimerEvents(dialog_id)
```

`pump()` does one non-blocking `select()` on a loopback TCP socket, reads
newline-delimited JSON, dispatches, replies. Their tools are read-only so far,
so this proves the *lifecycle*, not writes. They call the non-modal modes
"freeze or can't schedule" and name a native C++ bridge as the upgrade path.

**BhaveshY/vectorworks-mcp** (`legacy/vw_listener.py`, VW 2024/2025,
Windows; 0.3.0, later replaced by a native plug-in): same dialog pattern,
default mode `dialog`, `VW_MCP_DIALOG_TIMER_MS=50`. Their docstring records
why the alternatives were demoted to "transport-only diagnostics":

- `background` (Python thread): "real CAD handlers can deadlock outside that
  script context".
- `win_timer` (`user32.SetTimer` via ctypes, Windows only): same deadlock.
- `foreground` (busy loop in the script): "can monopolize the Vectorworks UI".

So: timer-driven modal dialog = safe `vs` context, including writes in their
case (their 20 tools draw walls, doors, slabs through it). The cost is that
the user cannot edit while the dialog is open; it is explicit turn-taking.

**vicquick/vwx-mcp** avoids the dialog with a native C++ palette (100 ms
timer; reads through an `OnIdle` notification, writes by calling the Python
menu command via `ISDK::DoMenuName` from a message-only window). That is the
non-modal answer, but it needs the SDK and a compiler per Vectorworks
version. Its macOS path is still the TCP dialog bridge.

## Proposed design for vwmcp

Keep the file protocol; add a second menu command, **MCP Listen**, whose
script opens the modal dialog above and, on every timer tick, calls
`vwmcp_bridge.run_pending()` (which already drains `~/.vwmcp/jobs`). No
sockets, no new wire format, and the existing bridge file stays the executor.

- Server side: on Windows the trigger becomes a no-op (`manual_trigger`),
  because the listener polls. The timeout message should say "run MCP Listen".
  On macOS the same command could be offered as an alternative to the
  AppleScript hop for people who prefer an explicit session.
- Dialog text: the job folder, a counter of jobs run, "Close to stop".
- Tick interval 100 ms is plenty for a file poll (`os.listdir` of a tiny folder).
- Resolved: a write done from a timer event inside the dialog is a regular
  undo step. Ctrl+Z removed it (see the live findings).
- Resolved: `vs.SetupDialogC` is not exposed in the 2027 Python API table, so
  the constant 12255 is used.

Historical, superseded by Live findings 2026-11-27: first live test (macOS, throwaway doc, user watching): open the dialog, send
`vw_ping` with the trigger disabled, confirm the result lands; then one
`vw_set_record` and Cmd-Z.

## Live findings 2026-11-27

Setup: Windows 11, Vectorworks 2027 (`vs` reports 32.1.0, build 885363),
German UI, Spotlight, embedded Python 3.14. Bridge 0.2.1 unchanged. Blank
document "Ohne Titel 1".

1. Listener closed: `vw_ping` failed after 15.0 s with the Windows message
   naming "MCP Listen".
2. Listener open: `vw_ping` answered in 0.1 s. The dialog shows "Jobs run: N".
3. `vw_document_info`, `vw_list_layers` and `vw_list_classes` returned correct
   results.
4. `vw_create_layer` was visible at once and `vw_revert_last` removed it. A
   second layer was left in place, then Stop and Ctrl+Z in Vectorworks: Ctrl+Z
   removed it. Observation: one layer created from a tick was undone with
   Ctrl+Z after Stop.
5. 50 consecutive `vw_ping` took 5.5 s with 0 failures. Vectorworks' Stop
   button stayed responsive. Stop ended the session cleanly (the counter
   showed the 62 jobs sent). Reopening MCP Listen worked and answered again.
6. `vw_exec_python("1/0")` returned the ZeroDivisionError as a result and the
   session continued.
7. Vectorworks keeps the imported `vwmcp_bridge` module in memory for the whole
   session. After `vwmcp install-plugin` overwrote the bridge file, reopening
   MCP Listen still ran the old code; only a Vectorworks restart loaded the
   new file. (CLAUDE.md and the CHANGELOG already say to restart Vectorworks
   once after a bridge update; this confirms it for the Windows listener.)
8. Exceptions that escape a timer-dialog callback do not kill the dialog.
   Vectorworks appends each traceback to
   `%APPDATA%\Nemetschek\Vectorworks\2027\ErrorOut.txt` and shows them in a
   "Script-Fehler" (Script Errors) dialog when the listener dialog closes. If
   the dialog shows "Script-Fehler", look in `ErrorOut.txt`. With the
   unhardened handler, a job file held open by another process made
   `os.replace` in `_claim_oldest` raise `PermissionError [WinError 32]` on
   every tick (about 30 tracebacks in 3 s); the job ran as soon as the file
   was released. With the hardened handler (after the restart), the same fault
   produced no `ErrorOut.txt` growth and the job ran after release: the
   handler caught it. The label then lost the error count, which the
   previous commit fixes.

Setup frictions:

- Pasting the two-line script into the Plug-in Manager editor (Extras >
  Plug-ins > Plug-in-Manager > Neu > Befehl, Sprache Python) collapsed it into
  one line with a space, which gave a SyntaxError on first run. The one-liner
  `from vwmcp import vwmcp_bridge; vwmcp_bridge.listen()` works and is what
  `MENU_SCRIPT_LISTEN` now says. A command made by hand appears under the
  category Scripts in the workspace editor (Run Job is under Miscellaneous).
  The bundled `MCP Run Job.vsm` copied by `install-plugin` did load. The
  bundled `MCP Listen.vsm` is the file Vectorworks wrote on this machine; a
  copy of it on another machine is expected to load (the category travels
  inside the file) but is not confirmed.
- Standard Vectorworks workspaces are read-only. The workspace has to be
  duplicated before the commands can be dragged into the Tools (Extras) menu.

Handler hardening (commit e9b5cfd): an exception from the handler's own
plumbing (claim, makedirs, result write, label update) is caught, counted and
shown in the label as "Jobs run: N, errors: M (last: ...)". It is unit-tested
with fault injection at `_claim_oldest`. See findings 7 and 8 for the live run.

Still open: `vw_screenshot`, `vw_list_documents`, `vw_switch_document` and
`vw_open_document` are macOS-only (the ping result said "Switching documents
is only available on macOS"). Windows
users keep the modal dialog open for the whole session (explicit
turn-taking). A non-modal trigger would need a native plug-in.
