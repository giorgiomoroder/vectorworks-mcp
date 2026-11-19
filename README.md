# Vectorworks MCP

<!-- mcp-name: io.github.giorgiomoroder/vectorworks-mcp -->

> **Beta.** Tested on Vectorworks 2026 (Update 3, English) and 2027 (32.1,
> English and German) with Spotlight on macOS only. Other versions, languages
> and Windows may not work yet. Save
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
| `vw_list_library_files`, `vw_list_library_resources` | Browse the Vectorworks and user libraries on disk (lighting, truss, people, stage decks) and list the symbols inside a file |
| `vw_import_resource` | Import one symbol or plug-in style from a library file into the document |
| `vw_insert_truss_run` | A straight truss run from a library symbol: pieces end to end at a trim height, linked into a Braceworks system, named position |
| `vw_list_truss` | Truss inventory: runs grouped by system, pieces in order, total length and weight, broken links flagged |
| `vw_insert_stage_decks` | Build a platform or riser from Spotlight Stage Deck objects: columns x rows of a deck size at a height, leg style, purpose |
| `vw_insert_stage_ramp` | A Stage Ramp down from a stage edge, by ramp length or pitch angle, with rails and a down arrow; revertible |
| `vw_insert_stage_steps` | A flight of Spotlight Stage Steps down from a stage edge: height, step count, rails, purpose |
| `vw_insert_lighting_devices` | Hang fixtures from a fixture symbol on a position at a spacing, as real Lighting Devices with unit numbers, channels, purpose; verified after insert |
| `vw_create_pio`, `vw_get_pio_parameters`, `vw_set_pio_parameters` | Place and edit plug-in objects (TrussItem, Lighting Device, positions…) by parameter name |
| `vw_create_layer`, `vw_create_class`, `vw_move_objects`, `vw_delete_objects` | Document housekeeping; all but delete are revertible |
| `vw_set_view` | Top/Plan, standard 3D views, fit to objects (e.g. before a screenshot) |
| `vw_list_documents` / `vw_switch_document` | List the open documents and bring a saved one to the front (AppleScript, no extra permission). Write tools take an optional `document=` and refuse if another document is active |
| `vw_export_geometry` | Exact 2D geometry of a layer (lines, polygons, arcs, texts, dimensions) as JSON, inline or written to a file; with fill and pen of every object and whether they follow the class |
| `vw_render_layers` | Picture of any design layers drawn from their real geometry (optionally a zoomed area), independent of the screen; no Screen Recording needed |
| `vw_duplicate_layer` | Copy a design layer with its objects next to the original (same scale, visibility as the source by default); can return the uuid mapping; revertible |
| `vw_set_vertices` | Replace the vertices of a polygon or polyline, with read-back check and area before/after; revertible |
| `vw_revert_last` | Undo exactly the last Claude edit in this drawing (repeatable), including objects a `vw_exec_python` call created |
| `vw_exec_python` | Run any Vectorworks Python (`vs.*`) and get stdout, value, traceback; records created objects for revert; optional timeout |
| `vw_exec_file` | Same as `vw_exec_python`, for a script file on the Mac |
| `vw_lint` | Check Python for Vectorworks without running it: syntax, wrong `vs.*` argument counts, deprecated calls (the things that open the blocking "Script Errors" dialog). `vw_exec_python` runs this check first |
| `vw_screenshot` | The document window as an image (plus window geometry and any dialog or open menu in front); works even while a dialog blocks the bridge |
| `vw_vs_lookup` | Search the `vs.*` API of *your* Vectorworks, with signatures |

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
- **Dialogs and open menus block Claude.** If a Vectorworks dialog, or even a
  right-click menu, is open, Claude's request waits and then times out with a
  message saying so. Close it and ask again; `vw_screenshot` can tell Claude
  what is in the way.
- **Just launched?** Claude waits until Vectorworks has been open ~30 seconds.
  Scripts sent while Vectorworks is still starting can crash it.
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
| A "Script Errors" window in Vectorworks | Usually raw Python calling a `vs` function with the wrong arguments. Click OK; ask Claude to check the signature with `vw_vs_lookup`. |
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

Experimental and untested. `scripts/install-windows.ps1` installs the bridge
and registers Claude Desktop, but there's no automatic trigger yet: run
**MCP Run Job** yourself to process each request. Contributions welcome.

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

What is different here:

- **Nothing to compile, no SDK.** The in-app part is a 120-line Python file.
- **Main-thread writes.** Every call runs inside a Vectorworks menu command.
  vwx-mcp reached the same conclusion independently; the C++ socket bridges
  warn that their writes can crash or corrupt the document.
- **Undo.** `vw_revert_last` reverts one call at a time and write tools
  verify what was applied. No other project documents an undo story.
- **Spotlight.** Lighting devices, positions and paperwork as typed tools,
  tested on a real plot, rather than generic geometry.

If you draw buildings on Windows, vwx-mcp has far more tools. If you need
ConnectCAD, watch showcad-mcp.

## License

MIT
