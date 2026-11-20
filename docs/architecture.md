# Architecture and design notes

## Pieces

- **`vw-plugin/vwmcp/vwmcp_bridge.py`** (0.2.0): installed in the user
  Plug-ins folder (already on Vectorworks' `sys.path`) together with two
  tables, `vs_types.json` and `vs_safety.json` (see NOTICE). `run_pending()`
  claims the oldest job in `~/.vwmcp/jobs/` by atomic rename (`.json` →
  `.running`; the server's cancel rename to `.cancelled` wins if it came
  first), checks the job's `document` against `GetFName`/`GetFPathName`
  (`WrongDocument`, `never_ran`), `exec`s the job's helper libraries (sent by
  sha, compiled once per session) and code with a **checked `vs`** in scope:
  a `CheckedVS` proxy validates argument count and types of every `vs.*`
  call against the type table (only where the live docstring's parameter
  count agrees) and refuses functions the safety table lists as crash, hang
  or interactive (the last unless the job has `allow_dialogs`). Captures
  stdout, the last expression (or `result`), and any traceback, and writes
  `~/.vwmcp/results/<id>.json` atomically. One job per call. Version-stamped
  (`BRIDGE_VERSION`); `vw_ping` and `vw_doctor` compare it. Vectorworks
  caches the imported module: after an upgrade, restart Vectorworks once.
- **"MCP Run Job" menu command**: two lines of Python that call
  `run_pending()`. Shipped as `MCP Run Job.vsm`; the user drags it into a menu.
- **`src/vwmcp/`**: the MCP server.
  - `client.py` writes jobs, fires the trigger, waits in two phases: up to
    15 s for the claim (re-firing the trigger every 2 s while an osascript
    is not in flight; unclaimed → renamed `.cancelled`, `BridgeTimeout` with
    `never_ran`), then up to `VWMCP_TIMEOUT` (120 s) for the result, asking
    the trigger every 2 s whether Vectorworks still runs. Learns the bridge
    version from results (`supports_libs`), writes helper libraries to
    `~/.vwmcp/lib/<sha>.py` (`lib_ref`), housekeeps leftovers, and logs to
    `~/.vwmcp/vwmcp.log`. Job keys: `code`, `created`, `ttl`, `protocol`,
    optional `libs`, `check`, `document`, `allow_dialogs`.
  - `trigger.py`: macOS trigger (below); also refuses when the window list
    shows only the start screen (a job then crashes Vectorworks).
  - `vwlib.py`: helper library executed *inside* Vectorworks, sent with
    every typed tool call (inline for a 0.1 bridge, by reference from 0.2)
    so the installed bridge never needs updating for new tools.
    Must stay Python 3.9-compatible.
  - `app.py`: `DOCUMENT` contextvar set by `require_document`; `vw()` puts
    it into every job of that tool call, so the bridge re-checks the
    document right before running (the pre-check alone had a race: the user
    can switch documents between two of our jobs).
  - `journal.py`: per-call revert journal.
  - `tools/generic.py`, `tools/spotlight.py`: the MCP tools.

## Why the AppleScript → menu command hop

Vectorworks has no idle/timer callback for scripts outside of a modal dialog
(`RegisterDialogForTimerEvents` exists, but only for dialogs), so an in-app
polling loop would freeze the UI. Its AppleScript dictionary has
`run Python script` and `run VectorScript`. Findings on Vectorworks 2026
Update 3 (macOS):

| Approach | Result |
|---|---|
| `run Python script` that only reads (doc open) | works |
| `run Python script` that writes (e.g. `vs.Rect`) | **crashes Vectorworks** |
| any `run Python script` while launching / in a modal dialog | **crashes Vectorworks** |
| `run VectorScript` with a write | works |
| `run VectorScript "DoMenuTextByName('MCP Run Job', 0)"` | **works**: full document + undo context |

So the server only ever sends that one VectorScript line. Guards: refuse if
Vectorworks isn't running or launched < 30 s ago; one request in flight at
a time; a trigger still unanswered after a grace period (usually a dialog)
is reported instead of stacking more Apple Events.

## Undo

Each `MCP Run Job` run is an undo step, but Vectorworks merges consecutive
script-triggered runs: after the first run following a user action, later
runs fold into one Cmd-Z step until the user does something else.
`vs.NameUndoEvent` (even with unique names) changes neither the merging
nor the Undo menu label. Hence `journal.py`: typed write tools record
before-values (or created UUIDs) per call, stamped with the document name,
and `vw_revert_last` replays them precisely. Raw `vw_exec_python` writes
leave a barrier entry the revert won't step past silently.

## Spotlight notes

- Lighting Devices are plug-in objects `PON='Lighting Device'`; their
  parameters are read/written with `GetRField`/`SetRField` on the
  `Lighting Device` record, then `ResetObject`.
- Resets apply when the script ends, so values read back in the same job
  can be stale. Write tools re-read in a second request.
- `UniverseAddress` / `Absolute Address` are authoritative; `Universe` and
  `DMX Address` written alone are overwritten on reset.
- Position objects: `Light Position Obj` (name in `Position Name`),
  `Lighting Pipe`/`Lighting Pipe Ladder`/`Truss` (`Name`). Devices refer to
  positions by name through their `Position` field.
- `LDevice_GetParamStr` and friends exist but have undocumented signatures;
  a wrong call shows a modal "Script Errors" dialog instead of raising.
