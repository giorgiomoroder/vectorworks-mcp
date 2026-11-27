# Vectorworks MCP

<!-- mcp-name: io.github.giorgiomoroder/vectorworks-mcp -->

> **Beta.** Tested on Vectorworks 2026 (Update 3, English) and 2027 (32.1,
> English and German) with Spotlight. Windows works through the MCP Listen
> window and was tested on 2027 German only. Other versions and languages may
> not work yet. Save
> your file before asking for edits, and please
> [report what you find](https://github.com/giorgiomoroder/vectorworks-mcp/issues/new/choose).
> Working under an NDA? Read [Your drawing data](#your-drawing-data-and-ndas) first.

Let Claude work inside your open Vectorworks drawing, on a Mac, with nothing
to compile. Spotlight first: read and bulk-edit Lighting Devices, check
hanging positions, pull paperwork, place symbols, look at the drawing through
a screenshot, and run any Vectorworks Python when you need more.

- **Mac-native.** Pure Python, no C++ SDK, no compiling. One-line installer.
  The Mac is the primary platform here, not a fallback.
- **Spotlight-first.** Channels, addresses, purposes, colors, gobos, positions,
  paperwork. Validated on a real 216-device plot.
- **Safe edits.** Bulk edits are validated before anything changes, address
  edits are re-read and report what Spotlight overrode, and `vw_revert_last`
  undoes exactly the last thing Claude did.
- **Sees its work.** `vw_screenshot` returns the document window as an image,
  so Claude can check what it drew, or show you which dialog is in the way.
- **Runs where Vectorworks allows writes.** Every call runs through a menu
  command on Vectorworks' main thread, the only context we found that doesn't
  crash on writes. Vectorworks stays usable between calls.

> Example asks, once it's set up:
> - "List every device on the 1E with its channel and color."
> - "Which devices have no position? Which position names have no position object?"
> - "Renumber channels on FOH TRUSS 101 to 127 in unit-number order."
> - "Move FOH TRUSS units 1–6 to universe 2, starting at address 1."
> - "Give me a channel hookup as CSV on my Desktop."
> - "Find Global Truss F34 in the library and hang a 30-foot run upstage at 14 feet, position name US TRUSS."
> - "Hang eight MAC Ones on US TRUSS at 18-inch centres, units 1 to 8, channels 101 up, purpose Wash."
> - "Show me the drawing." / "Undo that last change."

---

## Install (about 10 minutes, macOS)

You need: Vectorworks 2026, and [Claude Desktop](https://claude.ai/download)
and/or [Claude Code](https://claude.com/claude-code).

### 1. Run the installer (2 minutes)

Open **Terminal** (Applications > Utilities) and paste:

```bash
curl -LsSf https://raw.githubusercontent.com/giorgiomoroder/vectorworks-mcp/main/scripts/install-macos.sh | bash
```

It installs [uv](https://docs.astral.sh/uv/) if needed, copies the small
bridge script and the "MCP Run Job" menu command into your Vectorworks
Plug-ins folder (`~/Library/Application Support/Vectorworks/2026/Plug-ins/`),
and adds Vectorworks to Claude Desktop and Claude Code. Your existing Claude Desktop
settings are kept (a backup is saved next to them).

### 2. Put "MCP Run Job" in a menu (once, 1 minute)

Claude reaches into Vectorworks through one menu command. The installer
already placed the command file; Vectorworks loads it at startup, so if
Vectorworks was running during the install, quit and reopen it. Then:

1. **Tools ▸ Workspaces ▸ Edit Current Workspace…** ▸ **Menus** tab. Find
   **MCP Run Job** in the left list (under *Miscellaneous*) and drag it into
   any menu on the right, e.g. **Tools**. Click **OK**.

Test it: choose **Tools ▸ MCP Run Job**. Nothing visible happens, and no
error appears. That's correct; there's no work queued yet.

<details>
<summary>Prefer to make the command yourself?</summary>

**Tools ▸ Plug-ins ▸ Plug-in Manager…** ▸ **Custom Plug-ins** ▸ **New…**,
type **Command**, name it exactly `MCP Run Job`, then **Edit Script…**,
**Language: Python**, and paste:

```python
from vwmcp import vwmcp_bridge
vwmcp_bridge.run_pending()
```

</details>

### 3. Restart Claude and say hello (1 minute)

Quit and reopen Claude Desktop. With a drawing open in Vectorworks, ask:

> Ping Vectorworks.

The first time, macOS asks whether Claude may control Vectorworks.
Click **Allow**. You should get back your Vectorworks version and the name
of your open drawing.

If that fails, run the self-check in Terminal; it looks at the bridge, both
Claude configs, the Vectorworks process and the runtime folder without
touching Vectorworks:

```bash
uvx --from git+https://github.com/giorgiomoroder/vectorworks-mcp vwmcp doctor
```

---

### Alternative: Claude Desktop extension (one file)

Download `vectorworks-mcp-<version>.mcpb` from the
[releases](https://github.com/giorgiomoroder/vectorworks-mcp/releases) (or
build it: `uv run python scripts/build-mcpb.py`), double-click it, and
Claude Desktop installs the server with its own Python (via `uv`). Set the
Vectorworks version when asked. Then say "check the Vectorworks MCP setup":
`vw_doctor(fix=True)` installs the bridge into your Plug-ins folder, and the
only manual step left is step 2 above (drag "MCP Run Job" into a menu) plus a
Vectorworks restart. Claude Code users keep using the installer script.

## Tools

| Tool | What it does |
|---|---|
| `vw_ping` | Bridge alive? Vectorworks version, open document, bridge version check |
| `vw_document_info` | Units, active layer/class, counts, selection size |
| `vw_list_layers`, `vw_list_classes` | Layers (design/sheet, visibility) and classes |
| `vw_get_selection` | Selected objects: type, name, class, layer, bbox, records |
| `vw_find_objects` | Find by class, layer, type, plug-in, record field value, name |
| `vw_get_record`, `vw_set_record` | Read/write record fields or plug-in parameters |
| `vw_list_symbols`, `vw_insert_symbol` | Symbol definitions by name/folder; place one at x, y(, z) |
| `vw_list_lighting_devices` | Every Lighting Device: unit, channel, address, purpose, position, type, color, gobo, focus… |
| `vw_set_lighting_device_fields` | Bulk edit by position + unit number, channel, or uuid |
| `vw_list_positions` | Positions with their devices, plus unassigned devices and orphan position names |
| `vw_lighting_device_report` | Paperwork export (CSV or JSON), naturally sorted |
| `vw_mvr_check` | MVR export pre-flight: devices without GDTF fixture or mode, missing or duplicate Fixture IDs, unpatched or overlapping DMX addresses, loose positions, 2D-only symbols. Read-only; the export itself stays in the File menu |
| `vw_import_hookup` | Channel hookup from a spreadsheet export (.csv/.tsv): rows matched by channel or position + unit, columns written as device fields; dry run first, then one revertible step |
| `vw_lightwright_snapshot` | Every Lighting Device as Spotlight's Lightwright Data Exchange last exported it (the XML next to the saved file): works even while a dialog blocks the other tools |
| `vw_lightwright_patch` | Change device fields through that exchange file (Lightwright-style sparse patch, applied when Vectorworks regains focus); dry run by default, guarded against the known ways to damage a plot, revertible; the full export is copied to `~/.vwmcp/lightwright/` first |
| `vw_list_library` | Browse the Vectorworks and user libraries on disk (lighting, truss, people, stage decks), or list the symbols inside one library file |
| `vw_import_resource` | Import one symbol or plug-in style from a library file into the document |
| `vw_insert_truss_run` | A straight truss run from a library symbol: pieces end to end at a trim height, linked into a Braceworks system, named position |
| `vw_insert_truss_run` with `vertical=True` | A ground-support tower: base plate, pieces stood on end, spindle on top |
| `vw_insert_truss_path` | A truss shape (L, U, rectangle) from straights and matching corner pieces along a polyline, one linked system |
| `vw_list_truss` | Truss inventory: runs grouped by system, pieces in order, total length and weight, broken links flagged |
| `vw_insert_hoists`, `vw_list_hoists` | Place Spotlight hoists at points with ID, location, function and hook height, data copied from the hoist symbol; rigging inventory with capacities |
| `vw_insert_stage_decks` | Build a platform or riser from Spotlight Stage Deck objects: columns x rows of a deck size at a height, leg style, purpose |
| `vw_insert_platform` | Platform and steps in one call: decks plus a flight of Stage Steps centred on a chosen edge, rails, class; one revertible step |
| `vw_insert_stage_ramp` | A Stage Ramp down from a stage edge, by ramp length or pitch angle, with rails and a down arrow; revertible |
| `vw_insert_stage_steps` | A flight of Spotlight Stage Steps down from a stage edge: height, step count, rails, purpose |
| `vw_insert_soft_goods` | A Soft Goods run (curtain, truss border, pipe-and-drape) along a polyline: height, opening, traveler, pipe/track; revertible (not yet run live) |
| `vw_insert_band` | Band members, crew or backline from people/backline symbols at positions, each with a name label; one revertible step (not yet run live; needs the People/Audio libraries downloaded once) |
| `vw_insert_lighting_devices` | Hang fixtures from a fixture symbol on a position at a spacing, as real Lighting Devices with unit numbers, channels, purpose; verified after insert |
| `vw_create_pio` | Place a plug-in object (TrussItem, Lighting Device, positions…) by its parameter names; read and edit its parameters with `vw_get_record` / `vw_set_record` |
| `vw_apply_class_standard` | A tidy class set with colours and line weights (Lighting-*, Rigging-*, Stage-*, Soft Goods, Audio, Video, Scenery, People, Venue-*, Notes): creates what is missing, optionally restyles the rest; revertible |
| `vw_create_sheet` | A sheet layer with a viewport of chosen design layers at a scale, classes hidden in it, optional title block with sheet title/number/project; revertible (not yet run live) |
| `vw_create_layer`, `vw_create_class`, `vw_move_objects`, `vw_delete_objects` | Document housekeeping; all but delete are revertible |
| `vw_rename_layer`, `vw_delete_layer`, `vw_rename_class`, `vw_delete_class`, `vw_rotate_objects`, `vw_duplicate_objects` | Layer and class lifecycle, rotate and copy; renames, rotations and copies are revertible, deletes refuse while anything is on the layer or in the class |
| `vw_set_view` | Top/Plan, standard 3D views, fit to objects (e.g. before a screenshot) |
| `vw_list_documents` / `vw_switch_document` / `vw_open_document` / `vw_save_document` | List the open documents (tabs included), bring a saved one to the front, open a .vwx from disk, File > Save (AppleScript and a menu command, no extra permission). Write tools take an optional `document=` and refuse if another document is active |
| `vw_export_geometry` | Exact 2D geometry of a layer (lines, polygons, arcs, texts, dimensions) as JSON, inline or written to a file; with fill and pen of every object and whether they follow the class |
| `vw_render_layers` | Picture of any design layers drawn from their real geometry (optionally a zoomed area), independent of the screen; no Screen Recording needed |
| `vw_duplicate_layer` | Copy a design layer with its objects next to the original (same scale, visibility as the source by default); can return the uuid mapping; revertible |
| `vw_set_vertices` | Replace the vertices of a polygon or polyline, with read-back check and area before/after; revertible |
| `vw_revert_last` | Undo exactly the last Claude edit in this drawing (repeatable), including objects a `vw_exec_python` call created |
| `vw_exec_python` | Run any Vectorworks Python (`vs.*`), given as code or as a script file path, and get stdout, value, traceback; records created objects for revert; optional timeout |
| `vw_lint` | Check Python for Vectorworks without running it: syntax, wrong `vs.*` argument counts, deprecated calls, and functions a published safety sweep found to crash or hang Vectorworks or to open a dialog. `vw_exec_python` runs this check first |
| `vw_screenshot` | The document window as an image (plus window geometry and any dialog or open menu in front); works even while a dialog blocks the bridge; `mapping=True` adds the pixel-to-drawing-coordinates mapping |
| `vw_point_to_world` | Drawing x, y of a pixel in the last mapped screenshot (Top/Plan), no job |
| `vw_doctor` | Setup check from inside Claude: bridge, menu command file, Claude configs, process, stale files, log; `fix=True` reinstalls a missing bridge |
| `vw_vs_lookup` | Search the `vs.*` API of *your* Vectorworks, with signatures |

## Skill: recipes for Claude

`skills/vectorworks-spotlight/SKILL.md` teaches Claude the session-start
document check, the safety rules and step-by-step recipes (hang fixtures,
hookup import, MVR pre-flight, platforms, troubleshooting). Claude Code:
copy the folder into `~/.claude/skills/`. Claude Desktop: paste the file's
text into a project's instructions.

## Your drawing data and NDAs

**What leaves your Mac:** whatever Claude reads from your drawing, plus
whatever you type, is sent to Anthropic as part of your Claude conversation.
That includes fixture lists, channel and address data, position and layer
names, venue and show names, and anything else the tools return. The
`.vwx` file itself is never uploaded, but Claude can read most of what's in
it if you ask.

**What stays local:** the bridge runs entirely on your Mac. Requests and
results pass through `~/.vwmcp/`, and nothing in this project sends data
anywhere except through your Claude app.

**If a project is under NDA or a client confidentiality clause:**

- Check whether your agreement allows project data to be processed by a
  third-party AI service. Many NDAs don't address it, and some forbid it.
  When in doubt, ask the client or producer first.
- Your Claude plan and privacy settings govern how Anthropic stores
  conversations and whether they may be used for model training. Review them
  at [claude.ai/settings](https://claude.ai/settings) and in
  [Anthropic's privacy policy](https://www.anthropic.com/legal/privacy).
  Team and Enterprise plans have different terms from personal plans.
- Limit what Claude sees: ask about one position or layer rather than the
  whole drawing, and prefer report tools that return only the columns you
  need.
- Don't use it on a confidential drawing if you can't share that drawing's
  contents with Anthropic.

## Good to know

- **Undo.** Vectorworks lumps back-to-back Claude edits into a single
  Cmd-Z, so Cmd-Z may undo several of them at once (never your own work).
  To undo exactly one Claude edit, ask Claude to "undo that" (`vw_revert_last`).
  This works for all typed edit tools and deletes the objects a raw Python
  call (`vw_exec_python`) created, even if the script stopped halfway.
  What raw Python changed on existing objects (moves, attributes,
  deletions) can only be undone with Cmd-Z.
- **Bulk edits are all-or-nothing.** If any device in a bulk edit can't be
  found or any field name is wrong, nothing changes. Unit numbers repeat per
  position, so give the position too.
- **Addresses.** Spotlight treats *UniverseAddress* (e.g. `2/101`) as the
  source of truth. Edits to Universe or DMX Address are applied through it
  automatically, and the tool re-reads each device afterwards and reports
  anything Spotlight overrode.
- **No more "Script Errors" boxes (bridge 0.2).** Inside Vectorworks every
  `vs.*` call Claude makes is checked first against a signature table
  (argument count and types) and a safety table of functions known to crash
  or hang Vectorworks or to open a dialog. A bad call comes back to Claude as
  an error instead of a modal window you have to click away while nothing
  else can run. Dialog-opening functions need `allow_dialogs=True` on purpose.
- **Alerts and open menus block Claude.** If a system alert (such as "Script
  Errors"), a plug-in's Object Preferences dialog or a right-click menu is
  open, Claude's request waits 15 seconds, is cancelled (it will not run
  later by surprise) and Claude is told why. Close it and ask again;
  `vw_screenshot` can tell Claude what is in the way. Vectorworks' own
  dialogs (Preferences, About) do not block; jobs run underneath them.
- **Right document, every time.** A write names its document, and the bridge
  checks that name inside Vectorworks right before running each job, so a
  document switched in between is refused rather than drawn into.
- **Just launched, or no document open?** Claude waits until Vectorworks has
  been open ~30 seconds, and refuses to send anything while only the start
  screen shows. Scripts sent in either state can crash Vectorworks.
- **Log file.** Bridge errors and timeouts are logged to `~/.vwmcp/vwmcp.log`;
  `vwmcp doctor` summarizes them.
- **Screenshots** need Screen Recording permission for the app running the
  server (Claude Desktop, or Terminal for Claude Code). The last ten captures
  are kept in `~/.vwmcp/screenshots/`.

## Troubleshooting

When reporting a problem, please use the
[bug report form](https://github.com/giorgiomoroder/vectorworks-mcp/issues/new/choose).

| Symptom | Fix |
|---|---|
| Anything, first step | `uvx --from git+https://github.com/giorgiomoroder/vectorworks-mcp vwmcp doctor` (add `--fix` to clear stale job files). Ask Claude for a screenshot to see what Vectorworks is showing. |
| "did not pick up the job" | Open a drawing, close any dialog or open menu (a right-click menu counts), and check **MCP Run Job** is in a menu (step 2, part 4). Run it once by hand; it should do nothing silently. |
| "is not running" / "still starting" | Open Vectorworks and wait a few seconds. |
| A "Script Errors" window in Vectorworks | Should be rare since bridge 0.2 (calls are checked first). Click OK; ask Claude to run `vw_doctor`: an old bridge or missing check tables beside it are the usual cause, and `vw_doctor(fix=True)` reinstalls them (then restart Vectorworks once so it loads the new bridge). |
| "No document is open (only the start screen)" | Open a drawing. Jobs sent to the start screen crash Vectorworks, so Claude refuses them. |
| Nothing works and you don't know why | Ask Claude to "check the Vectorworks MCP setup" (`vw_doctor`; with fix it reinstalls a missing bridge). It never touches Vectorworks itself. |
| `vw_ping` warns about bridge version | Re-run the installer (or `uvx --from git+https://github.com/giorgiomoroder/vectorworks-mcp vwmcp install-plugin`). |
| Nothing happens, no macOS permission prompt | System Settings ▸ Privacy & Security ▸ Automation: allow Claude (or Terminal) to control Vectorworks 2026. |
| `vwmcp doctor` says several Vectorworks versions are installed | Run the installer once per version you use (`VW_VERSION=2027 bash install-macos.sh`); each server entry then names its version. |
| `vw_ping` warns the Vectorworks version is untested | It may work; save first, check results, and please open an issue either way. |
| Different Vectorworks version | `VW_VERSION=2025 bash install-macos.sh`: installs the bridge for that version and registers a server with `VWMCP_VW_VERSION` set. Only 2026 is tested. |
| Two versions at once (e.g. 2026 and 2027) | Run the installer once per version. Each gets its own server (`vectorworks`, `vectorworks-2027`), job folder and journal; see `docs/claude-config.md`. |

## Manual configuration

See [docs/claude-config.md](docs/claude-config.md) for the Claude Desktop and
Claude Code config blocks, and the environment variables.

## How it works

```
Claude ──MCP──▶ vwmcp server ──writes──▶ ~/.vwmcp/jobs/<id>.json
                     │
                     └─AppleScript: run VectorScript "DoMenuTextByName('MCP Run Job')"
                                          │
Vectorworks ◀────────────────────────────┘
  MCP Run Job ▶ vwmcp_bridge.run_pending(): exec job with `vs` in scope
              ▶ ~/.vwmcp/results/<id>.json ──▶ server ──▶ Claude
```

The in-app bridge is a ~120-line "dumb executor" and rarely changes. All
logic, including the helper library run inside Vectorworks, is sent from the
server with each request. Details and the reasons for this design are in
[docs/architecture.md](docs/architecture.md); `vs.*` findings are in [docs/vs-notes.md](docs/vs-notes.md).

## Windows

Live-tested on Windows 11 with Vectorworks 2027 (32.1.0, German UI). Other
Windows setups are untested.

Windows has no automatic trigger. Instead you open **MCP Listen** in
Vectorworks, and it runs Claude's requests while its window is open.

1. Install [uv](https://docs.astral.sh/uv/) (`scripts/install-windows.ps1`
   does it if needed). Then run `powershell -ExecutionPolicy Bypass -File
   scripts/install-windows.ps1 -VwVersion 2027`, or by hand:
   `uvx --from git+https://github.com/giorgiomoroder/vectorworks-mcp vwmcp install-plugin --vw-version 2027`.
   This copies the bridge to `%APPDATA%\Nemetschek\Vectorworks\2027\Plug-ins\vwmcp\`
   and places `MCP Run Job.vsm` and `MCP Listen.vsm` next to it.
2. Claude Desktop: `install-windows.ps1` writes its config and sets
   `VWMCP_VW_VERSION` from `-VwVersion`. Claude Code:
   `claude mcp add -s user vectorworks -e VWMCP_VW_VERSION=2027 -- uv run --directory <path-to-checkout> vwmcp`.
3. Once only: standard Vectorworks workspaces are read-only. Duplicate one,
   then drag **MCP Run Job** (Miscellaneous) and **MCP Listen** (Scripts)
   into a menu such as Tools.
4. Each session: open **MCP Listen** before asking Claude. The window shows
   "Jobs run: N". Press **Stop** when you want to edit yourself, then open it
   again for the next request. Claude's edits are regular undo steps, so
   **Ctrl+Z** works.

If MCP Listen is closed, a request fails after about 15 seconds with a message
naming it. The copied `MCP Run Job.vsm` loaded on the tested machine. `MCP Listen.vsm` is
the file Vectorworks wrote there when the command was created by hand. A copy
of it on another machine is expected to work and to appear under Scripts, but
is not confirmed. If it is missing, create the command in the Plug-in Manager
yourself. The script must be the one line `from vwmcp import
vwmcp_bridge; vwmcp_bridge.listen()`. Pasting two lines collapsed them into
one in the editor and gave a SyntaxError.

macOS only for now: `vw_screenshot`, `vw_list_documents`, `vw_switch_document`
and `vw_open_document`. The `vw_doctor` tests expect `/bin/sh`. A trigger that
needs no open window would require a native plug-in.

## Development

```bash
uv sync
uv run pytest            # bridge round-trips with a fake Vectorworks
uv run vwmcp             # run the server on stdio
```

Code sent into Vectorworks (`src/vwmcp/vwlib.py`, `vw-plugin/`) must stay
**Python 3.9**-compatible: that's what Vectorworks 2026 embeds.

Nothing from the Vectorworks install (stubs, SDK headers, libraries, sample
files) is included. Bring your own licensed Vectorworks.

## How this compares (November 2026)

Several Vectorworks MCP servers appeared during 2026. This one is the
Mac-native, Spotlight-focused option with the smallest install. The others,
as of this writing:

| Project | Platform | Bridge into Vectorworks | Focus |
|---|---|---|---|
| [vicquick/vwx-mcp](https://github.com/vicquick/vwx-mcp) | Windows (macOS through an older TCP dialog bridge) | File IPC, native C++ palette, Python menu command | 248 general tools: BIM, GIS, 2D/3D modeling, worksheets |
| [SRVR-JOE/showcad-mcp](https://github.com/SRVR-JOE/showcad-mcp) | Windows (fork of vwx-mcp) | Same | ConnectCAD and Spotlight, scaffold stage |
| [BhaveshY/vectorworks-mcp](https://github.com/BhaveshY/vectorworks-mcp) | Windows, VW 2024/2025 | TCP, prebuilt native SDK plug-in | Architecture: walls, doors, slabs, roofs, exports, screenshots |
| [chronista-club/vectorworks-mcp](https://github.com/chronista-club/vectorworks-mcp) (was mako-357) and [upipibi/claude-vectorworks-mcp](https://github.com/upipibi/claude-vectorworks-mcp) | macOS | Unix socket from a C++ SDK plug-in you compile | 6 generic tools; SDK calls off the main thread can crash the document |
| [edmacovaz/rt-vectorworks-mcp](https://github.com/edmacovaz/rt-vectorworks-mcp) | macOS | Python modal dialog, TCP | Read-only, architecture template extraction |
| [seraphinernst4/vectorworks-2d-mcp](https://github.com/seraphinernst4/vectorworks-2d-mcp) ("Keystone", a fork of this project) | macOS, German VW 2026 | Same job folder; triggers Python over VectorScript without a menu command; type-checked `vs` proxy | Exact 2D architecture drawing, geometry checks and repair, DWG import clean-up, room planning |
| [MattA-Official/vwmcp](https://github.com/MattA-Official/vwmcp) | Windows, VW 2026/2027 | Single Rust .exe, file IPC, keyboard shortcut posted to Vectorworks | 12 general tools, well documented |
| [stevenmorgan94/vw-mcp](https://github.com/stevenmorgan94/vw-mcp) | macOS, VW 2027 | C++ library plug-in, loopback HTTP, Node relay | 4 tools; published a safety sweep of ~2,800 `vs.*` calls (safe / opens a dialog / crashes) |
| [Gribiche64/vectorworks-bridge](https://github.com/Gribiche64/vectorworks-bridge) | macOS | No plug-in: reads and patches Spotlight's Lightwright Data Exchange XML | Fixture data and field edits for Lighting Devices only; dormant since 2026-09 |

What is different here:

- **Nothing to compile, no SDK.** The in-app part is a 120-line Python file.
- **Main-thread writes.** Every call runs inside a Vectorworks menu command.
  vwx-mcp reached the same conclusion independently; the C++ socket bridges
  warn that their writes can crash or corrupt the document.
- **Undo.** `vw_revert_last` reverts one call at a time and write tools
  verify what was applied. No other project documents an undo story.
- **Spotlight.** Lighting devices, positions and paperwork as typed tools,
  tested on a real plot, rather than generic geometry.

If you draw buildings on Windows, vwx-mcp has far more tools. If you draw
exact 2D architecture on a German Mac, Keystone (built on this code) goes
much deeper there. If you need ConnectCAD, watch showcad-mcp. This project
is also listed on [Glama](https://glama.ai/mcp/servers/giorgiomoroder/vectorworks-mcp).

## License

MIT
