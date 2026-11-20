# Other Vectorworks MCP projects: what to learn (2026-11-20)

Two read-only reviews of the repos Glama lists for "vectorworks" (plus GitHub
search). Nothing from them was executed. This file is the long version of the
README's "How this compares" and the CLAUDE.md Landscape paragraph.

## Keystone (seraphinernst4/vectorworks-2d-mcp)

A fork of this repo made 2026-10-29, German, architecture-only 2D drawing;
v0.8.0 on 2026-11-13; 37 tools + 3 doc tools, our Spotlight tools hidden
behind `VWMCP_SPOTLIGHT=1`. All commits authored as Claude; human name
Seraphin Ernst in LICENSE/NOTICE. Tested on VW 2026 U7 German (student
licence); 2027 prepared, not live-tested.

Worth borrowing (file paths are inside that repo):

1. **Type-checked `vs` proxy in the bridge.** `vw-plugin/vwmcp/vwmcp_bridge.py`
   (`CheckedVS`, `check_args`, `load_check_table`) checks every `vs.*` call's
   argument count and types against `src/vwmcp/data/vs_index.json` (3192
   functions, built by `tools/build_vs_index.py` from the developer-scripting
   `vs.py` stub + Function Reference) and raises a Python error with the
   signature instead of letting Vectorworks show the modal Script Errors
   dialog. Replaces our count-only `vslint.py`. Medium.
2. **Atomic job protocol.** Bridge claims a job by renaming `.json` to
   `.working`; the server cancels by renaming to `.cancelled` after a
   15 s claim timeout; `target_alive()` notices a quit Vectorworks in 2 s;
   helper libraries are sent once by sha and cached in `~/.vwmcp/lib/`
   (10 ms to 0.7 ms per call). `src/vwmcp/client.py`, bridge
   `_claim_oldest`, `_compiled_lib`. Credits MattA-Official/vwmcp. Medium.
3. **Document pin guard.** `src/vwmcp/documents.py` (`DocumentPin`,
   `GUARD_TEMPLATE`): a guard snippet runs first in every job and raises
   `WrongDocument` if `GetFName`/`GetFPathName` differ from the pinned
   document. Pure `vs`, no UI scripting. Would have caught the Visit
   Bushwick ramp. Small.
4. **Start-screen preflight.** Any job while Vectorworks shows only the
   start screen (no document) segfaults 2026 and 2027. Refuse before
   triggering; our CGWindowList code in `screenshot.py` can tell. Small.
5. **Menu-command-free trigger** (`src/vwmcp/trigger.py`, `DIRECT_VSS`):
   `run VectorScript` with `PythonBeginContext; PythonExecute('...
   run_pending()'); PythonEndContext`. Claimed live on 2026 U7 (0.2 s per
   call). Same Apple Event class as our hop, but it is Python started from
   AppleScript, which is where our crashes came from. Test on a throwaway
   doc only; if it holds, it removes the Plug-in Manager install step.
6. **Exact revert snapshots** with stacking order and `_check_restorable`
   (`src/vwmcp/vwlib2d.py`: `snapshot`, `restore`, `_restack`). Large.
7. **Rule-based organize with dry run** (`src/vwmcp/organize.py`): sort an
   imported venue DWG onto classes by name pattern/type/pen in one
   revertable step. Medium.
8. **Check image from geometry** (`src/vwmcp/geom/render.py`): numbered
   issue markers drawn on a rendering, not a screenshot. Could mark
   unpatched fixtures or broken truss chains on our `render.py` output.
9. **Profile block in the server instructions** (`src/vwmcp/profile.py`):
   user settings (units, class standard, "ask before touching more than N
   objects") rendered into `instructions`. Small.

VS findings recorded there that we did not have (`docs/vs-notes.md`,
`docs/api-pitfalls.md` in that repo): `vs.Mirror` on a symbol instance
corrupts its matrix, use `MirrorN(h, dup, p1, p2, True)`;
`ImportDXFDWGFile(path, True)` imports DWG without a dialog; `AddSurface`
keeps the first object's attributes, `ClipSurfaceN(a, b)` deletes a;
`OffsetPolyN` results land on the active layer/class; set `*ByClass` flags
last because colour setters clear them; line weights in mils;
`GetObjectByUuid` costs 4.6 ms at 20k objects so build one uuid map with
`ForEachObject`; `Layer(name)` costs 13 ms so switch once per run; Python
inside Vectorworks opens files as ASCII, always pass `encoding="utf-8"`;
the `.mcpb` `uv` server type did not work for them, they use a Node
launcher that answers `initialize` instantly from a static file (Claude
Desktop drops servers that take over 3 s).

Do not copy: the update nag appended to every tool result ("KEYSTONE UPDATE
REQUIRED ... insist on it"), the System Events/Accessibility document
switching (two permissions, hard-coded "Fenster"/"Window"), the Raumpilot
knowledge base (copyrighted books), heavy dependencies (shapely, matplotlib,
numpy, Python 3.11+).

## Gribiche64/vectorworks-bridge (Lightwright Data Exchange)

No plug-in. Spotlight Preferences > Lightwright > "Use automatic Lightwright
Data Exchange" makes Vectorworks write an XML next to the `.vwx` whenever it
loses focus and watch it for patches stamped `<AppStamp>Lightwright</AppStamp>`.
`PROTOCOL.md` (210 lines) decodes the format: `<SLData>` > `<ExportFieldList>`
> `<InstrumentData>` with one block per fixture keyed by the Vectorworks UID
(Device_Type, Symbol_Name, Inst_Type, Layer, Class, Channel, Dimmer,
Absolute_Address, Position, Purpose, Color, Template/Template2, Circuit_*,
Wattage, Unit_Number, User_Field_1..6, Focus, Lightwright_ID, X/Y/Z_Location_mm,
Rotation, Accessories). Write-back works for Channel and Inst_Type/Symbol_Name
(applied 1 to 2 s after Vectorworks regains focus). Hazards they hit: a
Symbol_Name not in the document breaks fixture selection drawing-wide
(restore a backup); Wattage is not updated on a type swap; writes over VM
mounts do not fire; a stale `.lw6` emits phantom Deletes. Two commits,
2026-09-05, dormant.

For us: a free, always-current hookup export and a Lightwright-compatible
paperwork round trip without touching the plug-in; read-only
`vw_lightwright_snapshot` first, write-back later with the Symbol_Name guard.
Medium.

## stevenmorgan94/vw-mcp

C++ `.vwlibrary` plug-in for 2027, loopback HTTP, Node relay, `.mcpb`, 4
tools, split out of a Solotech plug-in. The value is `docs/sweep/README.md`:
~2,800 `vs.*` functions called against throwaway documents and sorted into
2,247 safe, 425 interactive (open a dialog) and 11 crashers (among them
`LDevice_SetAccPos2D/3D` on wrong types, `UprString`, `TBB_AttachRecords`).
Their finding: running inside a menu command made no difference to the
crashers. Feed the interactive and crasher lists into `vslint.py`. Small.

## MattA-Official/vwmcp

Rust, Windows, single `.exe`, 12 tools, file IPC; trigger posts Ctrl+Shift+B
into the Vectorworks message queue to run a one-line menu command installed
via Help > Install Partner Products. 4 stars, the most of any of these. Good
explanations of dialog and minimised-window states in
`docs/explanation/architecture.md`. Relevant if we build the Windows trigger.

## BhaveshY/vectorworks-mcp (update)

Active through 2026-11-17; surface reduced to 10 compact tools. Windows path
is now a compiled SDK plug-in (`native_bridge/`): TCP on localhost with
token auth, calls handed to the main thread through a message-only Win32
window pumped by WM_TIMER, a UI-state gate that auto-dismisses the Home
screen, update notice and autosave prompt, error codes `vectorworks_busy`,
`document_changed` (document fingerprint), `script_crashed`. Screenshot
mapping uses `gSDK->ViewPt2WorldPt` on the export region corners (SDK side).
Their `vs_lint.py` checks argument types (colour tuples, handle vs string,
modal-dialog functions). No Spotlight.

## mrmoj0risin fork (feature/mac-safety-0.2)

Based on our 2026-10-16 commit. `vw_bind_document(path)` required before
writes, `VWMCP_ALLOWED_PROJECT_ROOT`, a `fcntl` lock across MCP processes,
`.running` markers block until inspected, journal by full path, bridge
refuses jobs without `protocol_version: 2` (breaks every 0.1 client). Take
the bridge-side document check and the full-path journal; not the protocol
break or the mandatory binding.

## Glama (glama.ai)

Directory that crawls GitHub. Ours: licence A, quality A, maintenance B,
tool quality 3.6/5 scored 2026-10-17 over 17 tools; README mirror from
2026-10-16; claimed by Michael 2026-11-20 (the only claimed Vectorworks
server there). `glama.json` at the repo root names the maintainer. The Admin
tab has "Request a re-sync" for after a push, plus name/description/category
edits and analytics. Keystone: A/A/B, 3.6 over 28 tools. vicquick/vwx-mcp
and BhaveshY are not indexed.
