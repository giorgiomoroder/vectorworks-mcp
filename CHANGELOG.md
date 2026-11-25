# Changelog

Releases are tagged after a live-tested batch, not after every commit.
Dates are the day the batch was verified inside Vectorworks.

## Unreleased

## 0.2.1 (2026-11-25), beta

Live-tested on Vectorworks 2027 (32.1.1) for the first time across the
board, and on 2026 (31.7). 61 tools. **Bridge 0.2.1: run `vwmcp
install-plugin` (or `vw_doctor(fix=True)`) and restart Vectorworks once**,
or reload it from a job as described in docs/vs-notes.md.

- Vectorworks 2027: a plug-in object made by a job was not painted until a
  later reset; every creating write now ends with a refresh job and the
  bridge repaints after each write (`BRIDGE_VERSION` 0.2.1). Title block
  fields are written in a follow-up job when the records arrive late.
- Two versions side by side: `vw_screenshot` matched windows by the word
  "Vectorworks" and could capture the other version's window. Fixed.
- `vw_list_documents` lists document tabs behind the front one (they are
  invisible windows); `vw_open_document` opens a .vwx from disk and waits
  for its window, reporting the converted `_v2027` copy of an older file.
- Lifecycle tools from the TDQS review: `vw_rename_layer`, `vw_delete_layer`,
  `vw_rename_class`, `vw_delete_class`, `vw_rotate_objects`,
  `vw_duplicate_objects`, `vw_save_document` (in place; Vectorworks has no
  silent Save As).
- Library imports journal the nested symbols that come along (a hoist's
  hook parts) so `vw_revert_last` removes them too.
- `vw_apply_class_standard` is all-or-nothing and checks the created names;
  the standard's "Soft Goods" class is now "Scenery-Soft Goods" (a record
  format of the old name made Vectorworks create "Soft Goods-2").
- The argument check accepts a colour index for COLOR parameters
  (`SetClPenFore(name, index)` was refused).
- `vw_screenshot`: the Script Errors alert is recognised at the modal level
  too and carries the text of Vectorworks' "Error Output" file; tool-tip
  sized floating windows are no longer listed as in front.
- The job trigger refuses at once while the Script Errors alert is up,
  quoting the Error Output text, instead of waiting out a 15 s claim.
- `vw_set_view(fit=True)` fits every object, as described; it used to fit
  the selection when there was one.
- `vw_mvr_check`: `gdtf_unlinked` for a GDTF name typed into the field
  without a linked fixture type (writing the field links nothing; only the
  Object Info palette's GDTF chooser does).

## 0.2.0 (2026-11-21), beta

Live-tested on Vectorworks 2026 (31.7). 53 tools.

- `vw_insert_hoists` / `vw_list_hoists`: Spotlight hoists (`BrxHoist`) at
  points with ID, location, function, direction and hook height, data
  copied from the hoist symbol's record; inventory with capacities.
- Towers: `vw_insert_truss_run(vertical=True, base_symbol=, top_symbol=)`
  stacks a base plate, pieces stood on end and a spindle into one system.
  `vw_insert_truss_path` takes `fit` (start, center, end) for the gap.
- `vw_insert_truss_path`: L, U and rectangle truss shapes from straights
  and a matching corner piece, one linked system. Truss pieces are now
  placed by their record's start point: the F34 library straights are
  start-based, so `vw_insert_truss_run` used to sit half a piece late with
  them (tool-made DJ truss pieces were centred).

- 50 tools instead of 54: `vw_get_record` / `vw_set_record` read and write a
  plug-in object's parameters when no record is named (replaces
  `vw_get_pio_parameters` / `vw_set_pio_parameters`); `vw_exec_python` takes
  `path` for a script file (replaces `vw_exec_file`); `vw_list_library`
  searches library files or lists one file's resources (replaces
  `vw_list_library_files` / `vw_list_library_resources`). `vw_set_record`'s
  parameter order changed to (uuid, values, record, document) and both record
  tools return {record, fields} / {uuid, record, after}.
- A description on every tool parameter; docstrings say when to use each
  tool, side effects and the result keys.
- Start screen detected by its untitled window; Vectorworks' own dialogs no
  longer count as documents; Lightwright patches back up the export and
  journal the undo from live values.

## 0.1.0 (2026-11-21), beta

First tagged release. Tested on Vectorworks 2026 (Update 3 and 31.7) and
2027 (32.1.1), English Spotlight, macOS. 54 tools.

**Talking to Vectorworks**
- Job folder plus one AppleScript hop into a user-made "MCP Run Job" menu
  command; no SDK, no socket, no in-app polling. The bridge (0.2.0) runs
  inside Vectorworks' own Python.
- Every `vs.*` call is checked inside Vectorworks against a signature table
  (argument count and types) and a safety table (functions known to crash,
  hang, or open a dialog). A bad call returns an error instead of the modal
  "Script Errors" window. Dialog openers need `allow_dialogs=True`.
- Jobs name their document; the bridge refuses to run in another one.
  Jobs are cancelled (and never run late) if Vectorworks does not take them
  within 15 s. Nothing is sent while only the start screen is open, which
  would crash Vectorworks.
- Per-call undo: `vw_revert_last` replays a journal, since Vectorworks
  merges consecutive scripted runs into one Cmd-Z step.
- `vw_lint` checks Python before it is sent (syntax, `vs.*` argument
  counts, deprecated and unsafe calls).

**Spotlight**
- Lighting devices: list, bulk field edits with read-back, reports (CSV or
  JSON), positions, truss inventory, hookup import from a spreadsheet
  export, MVR export pre-flight, Lightwright Data Exchange snapshot and
  patch (with backup and live-value undo).
- Inserts: lighting devices (symbol + Convert to Instrument), truss runs,
  stage decks, steps, ramps, platforms, soft goods, band members, library
  symbols and plug-in objects; class standard and sheet layers with
  viewport and title block.

**Seeing and navigating**
- `vw_screenshot` without touching the app (also shows blocking dialogs and
  menus), pixel-to-drawing mapping, rendered layer images, geometry export.
- Several open documents: list and switch; one server per Vectorworks
  version side by side.

**Setup**
- One-line macOS installer, `vwmcp doctor [--fix]`, `vw_doctor` from
  Claude, Claude Desktop extension bundle (`.mcpb`), a skill with recipes.

Thanks to bgst84 (PO4 fork: lint, revert of raw Python, document tools,
German libraries), seraphinernst4/Keystone (type table, checked `vs`
design), stevenmorgan94 (safety sweep) and Gribiche64 (Lightwright
exchange format). See NOTICE.
