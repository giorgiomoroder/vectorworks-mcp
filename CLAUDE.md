# vectorworks-mcp: guide for Claude Code sessions

Mac-native MCP server for Vectorworks, Spotlight-first, pure Python.
Public repo: https://github.com/giorgiomoroder/vectorworks-mcp (MIT).
Status: **v0.2.1 beta**, tested on Vectorworks 2026 (Update 3 and 31.7; English,
Spotlight) and 2027 (32.1.1, English; full live pass of every insert, list,
check and revert tool on 2026-11-25, see vs-notes "Live findings
2026-11-25"; a contributor runs it on 2027 German) on macOS. Read `docs/architecture.md` and `docs/vs-notes.md`
before changing anything that touches Vectorworks.

## Layout

- `vw-plugin/vwmcp/vwmcp_bridge.py`: in-app executor (bridge 0.2.1: checked
  `vs`, document guard, repaint after every write job). Installed to
  `~/Library/Application Support/Vectorworks/2026/Plug-ins/vwmcp/`. Run by the
  user-created **MCP Run Job** menu command (`from vwmcp import vwmcp_bridge;
  vwmcp_bridge.run_pending()`). Bump `BRIDGE_VERSION` and
  `app.EXPECTED_BRIDGE_VERSION` together whenever the job/result format changes.
- `src/vwmcp/config.py`: `VWMCP_VW_VERSION` (else the year in `VWMCP_APP`, else
  the single installed version, else 2026) → app name, Plug-ins and Libraries
  folders; `TOOL_GROUPS` + `VWMCP_TOOLS_OFF` hide spotlight/stage/plan tools
  (server.py removes them after import). One server per Vectorworks version; a second version
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
- `src/vwmcp/mvr.py` (+ `vwlib.mvr_data`): `vw_mvr_check`, MVR export pre-flight;
  pure checks over device rows (2026-11-20, offline). `hookup.py`: `vw_import_hookup`,
  .csv/.tsv → `vw_set_lighting_device_fields` updates. `classes.py` +
  `data/class_standards.json`: `vw_apply_class_standard` (revert op `class_attrs`).
  `viewmap.py`: screenshot pixel ↔ drawing coordinates (`vw_screenshot(mapping=True)`,
  `vw_point_to_world`). `platform.py`: step placement for `vw_insert_platform`.
  Tool group `drawing` = class standard + `vw_create_sheet`. Lifecycle tools
  (2026-11-25, from the TDQS review, live on both versions): `vw_rename_layer`,
  `vw_delete_layer`, `vw_rename_class`, `vw_delete_class`, `vw_rotate_objects`,
  `vw_duplicate_objects`, `vw_save_document` (File > Save only: Vectorworks
  has no silent Save As, `VSave` saves a view and `SaveActiveDocument()`
  without its string argument raises the Script Errors alert). The class
  standard's soft goods class is "Scenery-Soft Goods" (a record format named
  "Soft Goods" exists once that plug-in was used, and classes cannot share
  a record's name).
- `src/vwmcp/lightwright.py` (2026-11-20, offline): `vw_lightwright_snapshot` /
  `vw_lightwright_patch`, Spotlight's Lightwright Data Exchange XML next to the
  `.vwx` (format from Gribiche64/vectorworks-bridge PROTOCOL.md): read without
  a job, sparse Update patches with the protocol's guards, revert = inverse
  patch from the journaled envelope (op `lightwright`, handled server side in
  `vw_revert_last`). Live 2026-11-20 on the Bobby Lee plot (vs-notes "Live
  findings 2026-11-21"): patch and revert land on the next click into
  Vectorworks; afterwards the file is only an acknowledgement (no fixtures)
  until the next full export; the export can be stale, so the inverse is
  journaled from live values and the full export is backed up to
  `~/.vwmcp/lightwright/`.
- `src/vwmcp/data/vs_types.json`, `vs_safety.json` + `scripts/import-vs-*.py`
  + `NOTICE`: the tables the bridge checks against (see hard rules).
  `docs/superpowers/plans/2026-11-20-safety-batch.md` is the plan; its "Live
  check" list is what the next safe session runs.
- `skills/vectorworks-spotlight/SKILL.md`: recipes for Claude (tested: every `vw_*`
  it names must exist). `scripts/build-mcpb.py` + `mcpb_main.py`: Claude Desktop
  extension bundle (MCPB 0.4, `uv` runtime, tool list generated); `vw_doctor` is the
  in-Claude setup check that also installs the bridge (`fix=True`).
- `docs/superpowers/plans/2026-11-20-roadmap-five-items.md`: the plan behind the
  2026-11-20 batch; its "Live check" lists are what the next safe session runs.
- `src/vwmcp/menu/MCP Run Job.vsm`: the menu command itself (made once in
  Michael's 2026 Plug-in Manager; a copy loads in 2026 and 2027).
  `install-plugin` places it in Plug-ins unless one is there; only the
  workspace drag stays manual. Idea from the PO4 fork.
- `src/vwmcp/install.py` + `server.py`: `vwmcp` (stdio server), `vwmcp install-plugin`,
  `vwmcp doctor [--fix]` (`doctor.py`: bridge version, Claude configs, VW process,
  stale job/result files, log summary; never touches Vectorworks).
- `src/vwmcp/documents.py`: `vw_list_documents` / `vw_switch_document` /
  `vw_open_document` via plain AppleScript (every window with its `visible`
  flag: document tabs behind the front one are invisible windows named
  `*.vwx`; `open POSIX file` opens or fronts a file, an older file comes
  back as an unsaved `<name>_v2027.vwx` copy); remembers document paths in
  `VWMCP_HOME/document_paths.json`. Write tools take `document=` and call
  `app.require_document` first (new write tools should too). Every write
  that creates objects ends with `app.refresh_objects` (a follow-up job that
  resets new plug-in objects: VW 2027 paints them only then).
- `src/vwmcp/render.py`: `vw_render_layers`, draws exported geometry to a PNG
  (pure Python, no Screen Recording needed).
- `src/vwmcp/vslint.py` + `data/vs_api_<year>.json`: pre-flight lint of Python
  sent to Vectorworks (`vw_lint`, `vwmcp lint`, `vwmcp dump-api`).
- `src/vwmcp/screenshot.py`: `vw_screenshot`. CoreGraphics window list via ctypes +
  `screencapture -l <id>` + `sips`. No Apple Event, so it works while a dialog blocks.
  Windows are matched by the full app name (two versions run side by side);
  a Script Errors alert in `in_front` carries the tail of Vectorworks'
  "Error Output" file (`error_output`), so the error can be read without
  clicking.
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
  raising; the user must click OK before anything else runs (Michael:
  "annoying", and it eats time when he does not see it). Since bridge 0.2.0
  (2026-11-20) the bridge wraps `vs` in `CheckedVS`: argument count and
  types are checked against `data/vs_types.json` (from Keystone, MIT) where
  the live docstring agrees on the parameter count, and functions listed in
  `data/vs_safety.json` (from the stevenmorgan94 sweep, MIT) as crash/hang
  are refused, interactive ones unless the job has `allow_dialogs`. Both
  tables are installed beside the bridge (`install-plugin`, `vw_doctor`
  checks). Argument *values* and handle object types are still unchecked.
  Live 2026-11-20: the colour call that opened the alert now returns
  `VSArgumentError` in 9 ms, no window. What blocks jobs is the Script
  Errors alert, a plug-in's Object Preferences dialog and a right-click
  menu held open; Vectorworks' own dialogs (About, Vectorworks Preferences)
  do **not**, jobs run underneath (live 2026-11-21). `vw_screenshot` lists
  what is in front (`in_front`) without touching the app. Functions without
  a docstring are unchecked: `vs.SaveActiveDocument()` raised the alert on
  2026-11-25 and blocked 2026 for the night. Prefer `DoMenuTextByName` for
  document commands; never call an undocumented `vs.*` function live
  without a reason to believe its signature. `vslint.py` (from
  the PO4 fork, bgst84) checks syntax, vs.* argument counts, deprecated
  calls and the safety classes before `vw_exec_python` (code or `path`)
  sends anything (also `vw_lint`, `vwmcp lint FILE`); the signature table is
  `data/vs_api_<year>.json`, refreshed with `vwmcp dump-api`.
- Jobs sent while only the start screen is open (no document) crash
  Vectorworks 2026 and 2027 (Keystone's finding). `trigger.py` refuses via
  the CoreGraphics window list (`screenshot.has_document_window`). Live
  2026-11-21: the 2026 start screen is one layer-0 window with an **empty
  title**, so "normal windows but none titled" counts as start screen when
  Screen Recording is granted (`screen_capture_allowed`), unknown otherwise.
  Refusal verified live (60 ms, nothing sent).
- Job protocol since 0.2 (client.py): 15 s claim phase, then cancel by
  renaming the job to `.cancelled` (never runs late), re-trigger every 2 s,
  `target_alive` probe, result wait `VWMCP_TIMEOUT` (120 s). Write tools
  put the document into every job (`app.DOCUMENT` contextvar set by
  `require_document`); the bridge refuses with `WrongDocument` (`never_ran`).
  After a bridge upgrade Vectorworks must be restarted once (module cache).
- `vs.GetBBox` is projected in 3D views; use `vwlib._extent3d` (`Get3DCntr` /
  `Get3DInfo`) for geometry that must not depend on the user's current view.
- `vs.Layer(name)` is the only layer-activation call in VW 2026 (no
  `SetActiveLayerN`). Fine from the menu command (live 2026-11-17); vwx-mcp saw
  hangs from palette/timer contexts. Always go through `vwlib._activate_layer`.
- Vectorworks merges consecutive scripted runs of MCP Run Job into one Cmd-Z.
  Per-call undo is `vw_revert_last` (journal). Don't promise Cmd-Z granularity.
- Test writes on throwaway documents only; ask the user which files are safe,
  and pass `document=` on every test write: Michael switches documents
  while Claude works (2026-11-19: a test ramp landed in his Visit Bushwick
  model; reverted). Start a live session with `vw_list_documents`.

## Development

```bash
uv sync
uv run pytest -q          # ~330 tests; fake executor runs the real bridge code
uv run vwmcp              # stdio server
uv build                  # wheel must contain vwmcp/_plugin/vwmcp_bridge.py
```

- Tool definitions are graded by Glama (TDQS). Before a push that touches a
  tool: `uvx tdqs lint --command "uv run --project . vwmcp" --fail-on never`
  (deterministic, no key; 2026-11-25: 0 errors, 3 heuristic warnings).
  `tests/test_tool_definitions.py` enforces a description on every parameter
  (`Annotated[..., Field(description=...)]`), 80+ character tool
  descriptions and the `vw_<verb>_<thing>` naming. The .mcpb manifest shows
  only each docstring's first sentence: keep it self-contained.
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
- [x] **Library access** (2026-11-17, live): `vw_list_library` (files on disk,
      or one file's resources) + `vw_import_resource` (`BuildResourceListN` /
      `ImportResourceToCurrentFile`). Only locally present `.vwx` libraries are
      seen (many are download-on-demand); importing a truss symbol brings the 2D
      definition only.
- [x] **Hoists** (2026-11-21, live): the current hoist is the `BrxHoist`
      plug-in; `vw_insert_hoists` / `vw_list_hoists` (vs-notes "Hoists and
      truss corners"). **Truss corners** (2026-11-21, live):
      `vw_insert_truss_path` places straights and the family's corner piece
      along a polyline; towers = `vw_insert_truss_run(vertical=True, ...)`
      (2026-11-21, live: pieces stood up with `Set3DRot`, the `Vertical`
      flag alone does nothing).
- [x] **Vectorworks 2027 pass** (2026-11-25, unattended, test docs): every
      insert/list/check tool and every revert ran on 2027; fixes in
      CHANGELOG 0.2.1. 2027 has no truss library on disk (Resource Manager
      download) and cannot read 2026 library files, so truss ran in a
      converted copy of the 2026 test doc.
- [~] **Truss.** `vw_insert_truss_run` (live 2026-11-17): straight runs from a
      library symbol, end to end at a height, dimensions/weight from the symbol's
      `BrxTrussItemRecord`, linked via `C_START_UUID`, new TrussSystem, class in a
      second job. `vw_list_truss` (live 2026-11-17) inventories runs by system
      in chain order with totals and flags broken chains. Corners: see
      Hoists above (`vw_insert_truss_path`, 2026-11-21); the F34 library
      straights are start-based, so pieces are now placed by the record's
      `Low` point. Michael has no Braceworks licence,
      so the "does it calculate" check is off the list.
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
      stringer length. `vw_insert_stage_ramp` (2026-11-19, built from the
      default object read live on 2027; not yet run live as a tool).
      `vw_insert_soft_goods` (2026-11-20, from the .vso string table:
      `GdsFunct` Curtain | Truss Border | Pipe-and-Drape, `CurtHeight`,
      `OpenFrom`, `OpenWidth`, `Traveler`, `AddPipe`, `AddTrack`; path via
      OpenPoly/BeginPoly/AddPoint/EndPoly + `CreateCustomObjectPath(name,
      path, None)`; **not run live**: whether the path is consumed and
      whether None works as the nil profile group are the first things to
      check). Still to do: `OpenFrom` popup values beyond "Center" (read
      the default object live), pipe-and-drape hardware fields,
      rails on the outer edges
      of a platform, round decks. `vw_insert_platform` (decks + steps on an edge)
      built 2026-11-20 from the live-tested helpers; not run live as a whole.
- [~] **Band members and instruments.** `vw_insert_band` built offline 2026-11-20
      (symbols + name labels; not run live). Content still blocked (2026-11-17): no
      people or backline library is on this Mac (`Libraries/Visualization/People`
      is a placeholder, no backline folder, and `Libraries/defaultContent.db`,
      the local SQLite index of 622 default files, has neither). Michael has to
      download them once in the Resource Manager (Vectorworks Libraries →
      Visualization/People and Entertainment/Audio backline content); after
      that `vw_list_library` + `vw_insert_symbol` already place them. Then:
      `vw_insert_band` places them (people + backline at positions, named, classed).
- [x] **`vw_screenshot`** (2026-11-17): window capture via ctypes CGWindowList
      (JXA's ObjC bridge segfaults in osascript) + `screencapture -l`. Image-to-world
      mapping built 2026-11-20 (`mapping=True`, `vw_point_to_world`, from
      `ModelPt2DToScreenPt`; **not run live**: coordinate space and Top/Plan
      projection code to verify, see vs-notes).
- [x] Generic helpers (2026-11-17, live): `vw_create_layer`/`class`,
      `vw_delete_objects` (revert barrier), `vw_move_objects`, `vw_set_view`,
      plus `vw_create_pio` and `vw_get_record` / `vw_set_record` (record
      omitted = the plug-in's parameters; merged 2026-11-21 from the pio tools).
      Journaled (revert ops: layer, class, resource, move). Known wrinkle: a
      plug-in regen between a move and its revert can shift the object ~0.5 units.
- [x] Journal raw Python better: optional "created objects" capture (diff UUIDs
      before/after) so `vw_revert_last` can delete what `vw_exec_python` drew.
- [ ] Maybe: import a 3D model file (e.g. a Blender FBX/OBJ export) as a symbol
      so custom pieces modeled elsewhere can be placed like library items.
- [ ] Lower priority: architecture drawing tools (walls via `SetComponentWidth` /
      `SetWallCornerHeights`, doors), only if venue shells are needed often.

2026-11-20 batch (Michael: "all five options"). Live on VW 2026 the same afternoon
(test_mcp.vwx, 2027 open beside it): class standard, sheet + title block, platform,
ramp, soft goods, band, screenshot mapping all verified and reverted (vs-notes
"Live findings 2026-11-20"). `vw_mvr_check` and `vw_import_hookup` verified on the Bobby Lee
plot the same day. Still unverified: the `.mcpb` install in Claude Desktop, hoists
(current Hoist plug-in name unknown; legacy `HoistVW` only), truss corners (record read).
- [x] a. `vw_mvr_check` (live on the Bobby Lee plot: `FixtureID` is the fixture type
      name, not an id; `GDTF Fixture Mode` separate; `GetSymbolType` 0/2 confirmed).
- [x] b. `vw_apply_class_standard`, `vw_create_sheet` (live: object variable 1003 =
      scale, title/number/project in the Title Block Sheet/Project Data records).
- [x] c. `vw_screenshot(mapping=True)` + `vw_point_to_world` (live-calibrated: display
      density x zoom / scale, view centre = centre of the white drawing area).
- [x] d. `vw_doctor`, `vw_ping` lists documents, session-start instructions,
      skill, `.mcpb` bundle (validated with the official schema; round trip over
      stdio from the unzipped bundle worked).
- [~] e. `vw_import_hookup`, `vw_insert_platform`, `vw_insert_band` (all live);
      hoists and truss corners wait for live reads. Composite inserts should restore
      the user's selection like `insert_lighting_devices` does.

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
- [x] CI (2026-11-19): `.github/workflows/tests.yml`, pytest + lint + build on macOS and Linux.
- [ ] Stretch from the original brief: ConnectCAD signal/cable tools,
      Vision/MVR export, GDTF fixture mapping.

## Landscape (checked 2026-11-20)

Other Vectorworks MCP servers, summarized in the README's "How this compares":
vicquick/vwx-mcp (Windows, 248 tools, file IPC + native palette + menu command,
same "writes only inside a menu command" finding as ours), its ConnectCAD/Spotlight
fork SRVR-JOE/showcad-mcp, BhaveshY/vectorworks-mcp (Windows, architecture,
now 10 compact tools over a compiled SDK plug-in; screenshots with
image-to-world mapping, a `doctor`, a type-checking lint), the C++ socket
pair chronista-club (ex mako-357) / upipibi, edmacovaz/rt-vectorworks-mcp
(read-only), and, found 2026-11-20 via Glama: **seraphinernst4/vectorworks-2d-mcp
"Keystone"** (a fork of this repo, German, exact 2D architecture;
menu-command-free trigger, type-checked `vs` proxy, document pin guard,
atomic job claim protocol, an update nag we must not copy),
**MattA-Official/vwmcp** (Rust, Windows, 4 stars), **stevenmorgan94/vw-mcp**
(C++ plug-in for 2027 with a published safety sweep of ~2,800 `vs.*` calls),
**Gribiche64/vectorworks-bridge** (Lightwright Data Exchange XML, no plug-in,
format decoded in its PROTOCOL.md, dormant). Details and a ranked borrow
list: `docs/landscape-2026-11-20.md`. Our niche: Mac-native, no SDK,
Spotlight, per-call revert. Listed on Glama
(glama.ai/mcp/servers/giorgiomoroder/vectorworks-mcp; claimed by Michael
2026-11-20, `glama.json` in the repo root; after a push, "Request a re-sync"
in the Admin tab). Re-check `gh search repos vectorworks mcp --sort updated`
and the README list before making positioning claims; the search misses
vwx-mcp by name.

## Design decisions already made (don't relitigate)

- Transport: job folder + AppleScript→menu-command hop (user chose it after the
  direct-Python crash findings). No in-app polling loop.
- Bridge location: user Plug-ins subfolder `Plug-ins/vwmcp/` (user approved).
- `vw_undo_mark` from the brief replaced by `vw_revert_last` + journal (user approved).
- Objects are addressed by UUID (`GetObjectUuid` / `GetObjectByUuid`), never handles.
- Lighting Device address edits go through `UniverseAddress`; write tools re-read
  in a second request and report `not_applied`.
