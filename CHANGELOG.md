# Changelog

Releases are tagged after a live-tested batch, not after every commit.
Dates are the day the batch was verified inside Vectorworks.

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
