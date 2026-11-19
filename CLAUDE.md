# vectorworks-mcp: guide for Claude Code sessions

Mac-native MCP server for Vectorworks, Spotlight-first, pure Python.
Public repo: https://github.com/giorgiomoroder/vectorworks-mcp (MIT).
Status: **v0.1.0 beta**, tested only on Vectorworks 2026 (Update 3 and 31.7; English,
Spotlight) on macOS. Read `docs/architecture.md` and `docs/vs-notes.md`
before changing anything that touches Vectorworks.

## Layout

- `vw-plugin/vwmcp/vwmcp_bridge.py`: in-app executor (~120 lines). Installed to
  `~/Library/Application Support/Vectorworks/2026/Plug-ins/vwmcp/`. Run by the
  user-created **MCP Run Job** menu command (`from vwmcp import vwmcp_bridge;
  vwmcp_bridge.run_pending()`). Bump `BRIDGE_VERSION` and
  `app.EXPECTED_BRIDGE_VERSION` together whenever the job/result format changes.
- `src/vwmcp/config.py`: `VWMCP_VW_VERSION` (default 2026) → app name, Plug-ins
  and Libraries folders. One server per Vectorworks version; a second version
  gets its own server, `VWMCP_HOME` and bridge (`install-plugin --home`, which
  writes `vwmcp_home.txt` beside the bridge). See docs/claude-config.md.
- `src/vwmcp/client.py`: job folder protocol (`~/.vwmcp/jobs`, `results`), timeout + withdrawal, log.
- `src/vwmcp/trigger.py`: macOS trigger: `osascript` → `run VectorScript` →
  `DoMenuTextByName('MCP Run Job', 0)`. Guards: not running, launched <30 s,
  previous Apple Event still pending after 10 s grace (= a dialog is open).
- `src/vwmcp/vwlib.py`: helper library executed **inside** Vectorworks, sent with every
  typed tool call. **Must stay Python 3.9** (VW 2026 embeds 3.9.2): no `match`,
  no `X | Y`, stdlib only. `tests/test_calls.py` parses it with `feature_version=(3, 9)`.
- `src/vwmcp/journal.py`: per-call revert journal (`~/.vwmcp/journal.jsonl`).
- `src/vwmcp/tools/generic.py`, `tools/spotlight.py`, `tools/drawing.py`: MCP tools
  (mcp 2.x `MCPServer`, the renamed FastMCP). `app.py` holds the server, `vw()`
  helper, annotations. `drawing.py` (2026-11-17): libraries, plug-in objects,
  layers/classes, move/delete, view; live-tested the same day (vs-notes
  "Drawing tools").
- `src/vwmcp/library.py`: finds library `.vwx` files on disk (app + user folders).
- `src/vwmcp/install.py` + `server.py`: `vwmcp` (stdio server), `vwmcp install-plugin`,
  `vwmcp doctor [--fix]` (`doctor.py`: bridge version, Claude configs, VW process,
  stale job/result files, log summary; never touches Vectorworks).
- `src/vwmcp/screenshot.py`: `vw_screenshot`. CoreGraphics window list via ctypes +
  `screencapture -l <id>` + `sips`. No Apple Event, so it works while a dialog blocks.
- `scripts/install-macos.sh`: one-line installer (uv, bridge, Claude Desktop + Code config).
  `scripts/install-windows.ps1` is experimental and untested.

## Hard rules (learned by crashing the user's Vectorworks)

- **Never** send `run Python script` over AppleScript. Writes, or any call during
  launch / a modal dialog, segfault Vectorworks 2026. The only Apple Event the
  server sends is the VectorScript menu hop.
- **Never** poll Vectorworks in a loop with probes. Announce each live test to the
  user, send one call at a time, and keep VectorScript in a file (shell quoting
  broke it once).
- The VW process is `…/Vectorworks 2026.app/Contents/MacOS/Vectorworks`; check
  crash reports in `~/Library/Logs/DiagnosticReports/` (`Vectorworks-*.ips`)
  as ground truth for crashes.
- A wrong `vs.*` signature shows a modal **Script Errors** dialog instead of
  raising; the user must click OK before anything else runs. An open
  right-click menu blocks jobs the same way; `vw_screenshot` lists what is
  in front (`in_front`) without touching the app. Check signatures
  with `vw_vs_lookup` (live docstrings) first.
- `vs.GetBBox` is projected in 3D views; use `vwlib._extent3d` (`Get3DCntr` /
  `Get3DInfo`) for geometry that must not depend on the user's current view.
- `vs.Layer(name)` is the only layer-activation call in VW 2026 (no
  `SetActiveLayerN`). Fine from the menu command (live 2026-11-17); vwx-mcp saw
  hangs from palette/timer contexts. Always go through `vwlib._activate_layer`.
- Vectorworks merges consecutive scripted runs of MCP Run Job into one Cmd-Z.
  Per-call undo is `vw_revert_last` (journal). Don't promise Cmd-Z granularity.
- Test writes on throwaway documents only; ask the user which files are safe.

## Development

```bash
uv sync
uv run pytest -q          # 125 tests; fake executor runs the real bridge code
uv run vwmcp              # stdio server
uv build                  # wheel must contain vwmcp/_plugin/vwmcp_bridge.py
```

- TDD for server-side logic (protocol, trigger, journal, verification, reports).
  Code that runs inside Vectorworks is validated **live** instead (a fake `vs`
  only encodes our assumptions); record findings in `docs/vs-notes.md`.
- Live checks without the MCP client: `from vwmcp.client import Bridge;
  from vwmcp.calls import call; call(Bridge(timeout=30), "document_info")`.
- Full MCP round trip: spawn `uv run --project . vwmcp` with
  `mcp.client.stdio.stdio_client` and call tools.
- Commits use the user's global git identity (giorgiomoroder). Don't push
  without the user's OK.

## Roadmap / TODO

Next: **what Michael actually draws** (stated 2026-10-16): truss, lighting
fixtures, stage parts, band members and instruments. These are mostly
Spotlight plug-in objects and library symbols, so prefer native objects over
hand-built geometry (walls/extrudes are secondary). Investigate each live
on a throwaway doc and record findings in `docs/vs-notes.md`:
- [x] **Library access** (2026-11-17, live): `vw_list_library_files` on disk,
      `vw_list_library_resources` + `vw_import_resource` (`BuildResourceListN` /
      `ImportResourceToCurrentFile`). Only locally present `.vwx` libraries are
      seen (many are download-on-demand); importing a truss symbol brings the 2D
      definition only.
- [~] **Truss.** `vw_insert_truss_run` (live 2026-11-17): straight runs from a
      library symbol, end to end at a height, dimensions/weight from the symbol's
      `BrxTrussItemRecord`, linked via `C_START_UUID`, new TrussSystem, class in a
      second job. `vw_list_truss` (live 2026-11-17) inventories runs by system
      in chain order with totals and flags broken chains. Still to do:
      corners/towers. Michael has no Braceworks licence, so the "does it
      calculate" check is off the list.
- [~] **Lighting fixtures.** `vw_insert_lighting_devices` (live 2026-11-17): fixture
      symbol → `vs.Symbol` + "Convert to Instrument" menu command → real Lighting
      Devices, hung at the position's height at a spacing, Unit/Channel/Purpose set
      and verified, class in a 2nd job, one revert. Still to do: GDTF-only
      fixtures (no symbol), auto-number by position order, accessories, and
      placing along a truss run's actual pieces (today: any point + direction).
- [~] **Stage parts.** `vw_insert_stage_decks` (live 2026-11-17): columns x
      rows of Spotlight Stage Deck objects from a corner point, size/height
      in mm strings, leg style, purpose, class in a 2nd job, extents read
      back in a follow-up job (vs-notes "Stage decks"). `vw_insert_stage_steps`
      (live 2026-11-17): a flight from a stage edge, height/steps/rails/
      stringer length. Still to do: `Stage Ramp`, soft goods (`Soft Goods` is
      a path plug-in), rails on the outer edges of a platform, round decks,
      a one-call "platform with steps" composite.
- [ ] **Band members and instruments.** Blocked on content (2026-11-17): no
      people or backline library is on this Mac (`Libraries/Visualization/People`
      is a placeholder, no backline folder, and `Libraries/defaultContent.db`,
      the local SQLite index of 622 default files, has neither). Michael has to
      download them once in the Resource Manager (Vectorworks Libraries →
      Visualization/People and Entertainment/Audio backline content); after
      that `vw_list_library_files` + `vw_insert_symbol` already place them. Then:
      a `vw_insert_band` style tool (people + backline at positions, named,
      classed) on top of that.
- [x] **`vw_screenshot`** (2026-11-17): window capture via ctypes CGWindowList
      (JXA's ObjC bridge segfaults in osascript) + `screencapture -l`. Still to do:
      an image-to-world mapping (BhaveshY's `vw_capture` returns one) so Claude can
      point at what it sees; needs view center/zoom and the drawing-area rect, live.
- [x] Generic helpers (2026-11-17, live): `vw_create_layer`/`class`,
      `vw_delete_objects` (revert barrier), `vw_move_objects`, `vw_set_view`,
      plus `vw_create_pio` / `vw_get_pio_parameters` / `vw_set_pio_parameters`.
      Journaled (revert ops: layer, class, resource, move). Known wrinkle: a
      plug-in regen between a move and its revert can shift the object ~0.5 units.
- [x] Journal raw Python better: optional "created objects" capture (diff UUIDs
      before/after) so `vw_revert_last` can delete what `vw_exec_python` drew.
- [ ] Maybe: import a 3D model file (e.g. a Blender FBX/OBJ export) as a symbol
      so custom pieces modeled elsewhere can be placed like library items.
- [ ] Lower priority: architecture drawing tools (walls via `SetComponentWidth` /
      `SetWallCornerHeights`, doors), only if venue shells are needed often.

Beta hardening:
- [ ] Gather tester reports (issue forms: bug + "works on my setup", label `compatibility`).
- [ ] Other VW versions: add majors to `app.TESTED_VW_MAJORS` only after live testing;
      `VWMCP_APP` env var covers the app name.
- [ ] Non-English VW: menu category names differ in README steps; check that
      `DoMenuTextByName` works with the English command name we create.
- [ ] Windows trigger (none today; user runs MCP Run Job by hand). Design and
      prior-art notes in `docs/windows-listener-notes.md`: a modal dialog with
      `RegisterDialogForTimerEvents` polling the jobs folder ("MCP Listen").
- [ ] `LDevice_*` functions: find real signatures (currently avoided).
- [x] Stale `~/.vwmcp/results/*.json`: `vwmcp doctor --fix` removes them (2026-11-17).
- [ ] Undo menu label: `vs.NameUndoEvent` has no visible effect; investigate.

Distribution:
- [ ] PyPI release (`vwmcp`; check the name is free), then MCP registry
      (`server.json` + `mcp-name` comment in README are ready).
- [ ] CI (GitHub Actions: `uv run pytest` on macOS + Linux).
- [ ] Stretch from the original brief: ConnectCAD signal/cable tools,
      Vision/MVR export, GDTF fixture mapping.

## Landscape (checked 2026-11-17)

Other Vectorworks MCP servers, summarized in the README's "How this compares":
vicquick/vwx-mcp (Windows, 248 tools, file IPC + native palette + menu command,
same "writes only inside a menu command" finding as ours), its ConnectCAD/Spotlight
fork SRVR-JOE/showcad-mcp, BhaveshY/vectorworks-mcp (Windows, architecture,
has screenshots with image-to-world mapping and a `doctor`), the C++ socket
pair chronista-club (ex mako-357) / upipibi, and edmacovaz/rt-vectorworks-mcp
(read-only). Our niche: Mac-native, no SDK, Spotlight, per-call revert.
Re-check `gh search repos "vectorworks mcp"` and the README list before
making positioning claims; the search misses vwx-mcp by name.

## Design decisions already made (don't relitigate)

- Transport: job folder + AppleScript→menu-command hop (user chose it after the
  direct-Python crash findings). No in-app polling loop.
- Bridge location: user Plug-ins subfolder `Plug-ins/vwmcp/` (user approved).
- `vw_undo_mark` from the brief replaced by `vw_revert_last` + journal (user approved).
- Objects are addressed by UUID (`GetObjectUuid` / `GetObjectByUuid`), never handles.
- Lighting Device address edits go through `UniverseAddress`; write tools re-read
  in a second request and report `not_applied`.
