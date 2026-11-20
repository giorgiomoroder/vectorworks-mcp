# Roadmap: five items (MVR check, drawing quality, view mapping, onboarding, more objects)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement
> this plan task-by-task (inline, one commit per task). Steps use checkbox (`- [ ]`) syntax.
> Read `CLAUDE.md` (hard rules) and `docs/vs-notes.md` first. **No live Vectorworks
> calls while Michael works in his real project** (2026-11-20): everything here is built
> and unit-tested offline; the "Live check" list at the end of each task is run later on a
> throwaway document, always with `document=`.

**Goal:** Deliver the five next-step items Michael approved on 2026-11-20: an MVR export
pre-flight, drawing-quality tools (class standard, sheet layer + viewport + title block),
screenshot image-to-world mapping, onboarding (doctor tool, skill, extension bundle,
session-start document check), and more objects (hookup import, platform composite,
hoists, truss corners, band placement).

**Architecture:** Same split as today. Code that runs inside Vectorworks goes into
`src/vwmcp/vwlib.py` (Python 3.9, stdlib only, returns plain JSON) and is validated live;
everything decidable from returned data (checks, parsing, formatting, journaling) lives in
`src/vwmcp/tools/*.py` or new pure modules and is developed test-first. New write tools
take `document=`, call `app.require_document`, journal their ops for `vw_revert_last`,
and assign classes in a second job (plug-in regen resets classes, vs-notes).

**Tech Stack:** Python 3.11+ server (mcp 2.x `MCPServer`), pytest, `uv`. In-app: VW's
embedded Python (3.9 on 2026, 3.14 on 2027) with `vs.*`; signatures checked against
`src/vwmcp/data/vs_api_2027.json` (`vslint.lint` on `vwlib.py` must stay clean: there is a
test for that).

**Order** (offline-testable first): A MVR check → E1 hookup import → D onboarding →
B drawing quality → C view mapping → E2 platform composite → E3 hoists / truss corners /
band (live-dependent, built last).

---

## Conventions used by every task

- Test file per tool module; fake `vw` via the `FakeVW` pattern in `tests/test_drawing.py`
  (monkeypatch `app.vw`, `module.vw`, `app.get_journal`).
- In-app helpers are added to `vwlib.py` behind a `# ---- <section>` comment, with a
  docstring saying what is live-tested and what is not. After editing `vwlib.py` run
  `uv run pytest -q tests/test_calls.py tests/test_vslint.py` (3.9 parse + lint).
- README tool table row for every new tool; `config.TOOL_GROUPS`: spotlight for A, E1;
  a new `drawing` group for B1, B2, E2; stage for E3; none for `vw_doctor`,
  `vw_point_to_world`; `docs/vs-notes.md`
  gets a "(not run live)" note per new `vs.*` pattern, replaced by findings after the live pass.
- Commit after each task: `git add -A && git commit` with a one-line subject naming the tool.

---

## Task A: `vw_mvr_check` (MVR export pre-flight)

**Files:**
- Create: `src/vwmcp/mvr.py` (pure checks over device rows), `tests/test_mvr.py`
- Modify: `src/vwmcp/vwlib.py` (new `mvr_data()`), `src/vwmcp/tools/spotlight.py` (tool),
  `src/vwmcp/config.py` (`spotlight` group), `README.md`, `docs/vs-notes.md`

**What MVR (My Virtual Rig) export needs per Lighting Device** (Vectorworks exports what
is in the document; nothing in VectorScript triggers the export, so the tool only finds
data gaps): a GDTF fixture (`GDTF Fixture Name`, or in some builds `GDTF Type ID`) and a
`Fixture Mode`; a unique `Fixture ID`; a patch (`UniverseAddress` not empty/`0/0`,
`Absolute Address` > 0) whose footprint (`Num Channels`) does not overlap another device
in the same universe; a position name that matches a position object (unlinked positions
export as loose fixtures); a symbol with 3D geometry (2D-only symbols export as empty
geometry). Field names are read from the live document (`ld_field_names()`), so a missing
field is reported as `field_missing`, never a KeyError.

- [ ] **Step 1: write failing tests in `tests/test_mvr.py`** for `mvr.run_checks(data)` where
  `data = {"fields": [...names present...], "devices": [row...], "positions": [names],
  "symbols": {name: {"type": 0|1|2}}}`; cases: no GDTF, no mode, missing Fixture ID,
  duplicate Fixture ID (two devices listed under one issue), unpatched (`""`, `"0/0"`,
  absolute `"0"`), overlapping footprints (`1/1` × 16 ch and `1/10`), position without
  object, device without position, 2D-only symbol, fields missing from the document →
  one `field_missing` issue and the dependent check skipped; clean plot → `ok: True`.
  Output shape: `{"ok": bool, "device_count": n, "summary": {check: count},
  "issues": [{"check": str, "severity": "error"|"warning", "message": str,
  "devices": [{"uuid","position","unit","channel"}]}]}`. Severity: error = would break
  or empty the MVR (no GDTF, no mode, duplicate/missing Fixture ID, unpatched, overlap);
  warning = position, 2D symbol.
- [ ] **Step 2: run** `uv run pytest -q tests/test_mvr.py` → fails (no module).
- [ ] **Step 3: implement `src/vwmcp/mvr.py`**: `parse_address("2/101") -> (2, 101) | None`,
  `footprints(rows)` overlap detection per universe (sort by start; report pairs once),
  `run_checks(data)`. Pure, no `vs`.
- [ ] **Step 4: tests pass.**
- [ ] **Step 5: `vwlib.mvr_data()`**: fields = intersection of
  `["Unit Number","Channel","Position","Inst Type","Symbol Name","Fixture Mode",
  "GDTF Fixture Name","GDTF Type ID","Fixture ID","UniverseAddress","Absolute Address",
  "Num Channels","Device Type"]` with `ld_field_names()`; rows via `ld_row`; positions from
  `list_positions(False)` names; symbols: for each distinct `Symbol Name`,
  `vs.GetObject(name)` → `vs.GetSymbolType(h)` (0 = 2D only, 1 = 3D, 2 = hybrid; mark
  "not run live" in vs-notes). Return the dict above plus `"document"`.
- [ ] **Step 6: tool `vw_mvr_check(position=None)` in `spotlight.py`** (READ): calls
  `vw("mvr_data")`, filters by position if given, returns `mvr.run_checks(...)` plus a
  `next_steps` line pointing at `vw_set_lighting_device_fields` (Fixture ID, address) and
  `vw_list_library_resources` (3D symbols). Add to `TOOL_GROUPS["spotlight"]`, README row.
- [ ] **Step 7:** `uv run pytest -q`, commit "Add vw_mvr_check: MVR export pre-flight".

**Live check (later, read-only, Bobby Lee plot or sketch doc):** `GetSymbolType` values,
exact GDTF/Fixture ID field names on 2026 and 2027, whether `Fixture ID` is blank by
default on the Bobby Lee plot (216 devices).

---

## Task E1: `vw_import_hookup` (spreadsheet → Lighting Device fields)

**Files:**
- Create: `src/vwmcp/hookup.py`, `tests/test_hookup.py`
- Modify: `src/vwmcp/tools/spotlight.py`, `config.py`, `README.md`

- [ ] **Step 1: tests** for `hookup.read_table(path)` (CSV and TSV by extension; header row;
  BOM tolerated) and `hookup.plan_updates(rows, key, column_map, known_fields)`:
  `key` is `"channel"`, `"unit_number"` or `"position+unit_number"` (two columns);
  `column_map` maps sheet headers → Lighting Device field names (default: identity for
  headers that are known field names, case-insensitive; `Addr`/`Address` → `UniverseAddress`,
  `Dimmer/Address` split handled by `UniverseAddress` only); unknown headers listed in
  `ignored`; rows with an empty key skipped and counted; output
  `{"updates": [...vw_set_lighting_device_fields shape...], "ignored": [...],
  "skipped_rows": n}`.
- [ ] **Step 2: fail, implement, pass.**
- [ ] **Step 3: tool `vw_import_hookup(path, key="channel", column_map=None, dry_run=True,
  document=None)`**: `dry_run=True` (default) returns the plan and the fields that exist in
  the document (`vw("ld_field_names")`; `calls.call` runs any vwlib function, no registry); `dry_run=False` requires `document`, then reuses
  `vw_set_lighting_device_fields(updates, document)` so journaling and `not_applied`
  verification come free. Selector failures (`_resolve_devices`) surface as the tool error
  text listing which rows did not match; nothing changes in that case (all-or-nothing is
  already in vwlib).
- [ ] **Step 4:** README, `TOOL_GROUPS["spotlight"]`, commit.

**Live check:** one 3-row CSV against the Bobby Lee plot (OK to modify), then `vw_revert_last`.

---

## Task D: Onboarding

### D1 `vw_doctor` tool + document list in `vw_ping`
**Files:** `src/vwmcp/tools/generic.py`, `src/vwmcp/doctor.py` (reuse `run_checks`),
`tests/test_doctor.py`, `tests/test_server.py`
- [ ] Tests: `vw_doctor()` returns `{"ok", "checks": [{name, ok, detail}], "fix_hint"}` from
  `doctor.run_checks` (monkeypatched); with `fix=True` it calls `run_checks(fix=True)` and,
  when the bridge is missing or outdated, `install.install_plugin(plugin_dir(), home=root)`
  (writes into the user's own Plug-ins folder, which the user already approved as the
  bridge location) and reports the menu-drag step (`install.MENU_STEP`).
- [ ] `vw_ping` gains `"documents": documents.list_documents()` (names only; AppleScript, no
  job) wrapped in try/except → `"documents_error"`; and the server `INSTRUCTIONS` get:
  "Start a session with vw_list_documents (or vw_ping) and name the target document on
  every write (`document=`)." Tests: ping shape with a fake `_run_raw` and fake list.
- [ ] README: "Troubleshooting" row: ask Claude to "check the Vectorworks setup" (`vw_doctor`).
- [ ] Commit.

### D2 Skill with recipes
**Files:** `skills/vectorworks-spotlight/SKILL.md` (+ `README.md` pointer, `docs/claude-config.md`)
- [ ] Write the skill (frontmatter `name`, `description`); sections: session start
  (`vw_list_documents`, pick and name the document, `vw_ping` warnings), safety (writes need
  `document=`, test on a throwaway file, `vw_revert_last`, what a Script Errors dialog means
  and `vw_screenshot`), recipes: hang fixtures on a position; build a platform with steps;
  truss run and inventory; channel hookup from a spreadsheet; MVR pre-flight then
  File > Export > MVR; paperwork export; see the drawing (`vw_set_view` + `vw_screenshot`);
  raw Python rules (3.9, `vw_vs_lookup`, `vw_lint`). Install: copy the folder to
  `~/.claude/skills/` (Claude Code) or paste into a Claude Desktop project's instructions.
- [ ] `tests/test_skill.py`: frontmatter present, every `vw_*` named in the skill is a
  registered tool (`mcp._tool_manager` listing or `asyncio.run(mcp.list_tools())`).
- [ ] Commit.

### D3 Claude Desktop extension bundle (`.mcpb`)
**Files:** `scripts/build-mcpb.py`, `mcpb/manifest.json` (template), `tests/test_mcpb.py`,
`docs/claude-config.md`, `.github/workflows/tests.yml` (build step on macOS)
- [ ] Manifest (`manifest_version` "0.2"): name `vectorworks-mcp`, `server.type` `"python"`,
  `entry_point` `server/main.py`, `mcp_config.command` `python3` with `args`
  `["${__dirname}/server/main.py"]`, `env` `{"PYTHONPATH": "${__dirname}/server/lib",
  "VWMCP_VW_VERSION": "${user_config.vw_version}"}`, `user_config.vw_version` (string,
  default "2026"), `compatibility.platforms ["darwin"]`, `compatibility.runtimes.python
  ">=3.11"`. `server/main.py` checks `sys.version_info >= (3, 11)` first and prints a one-line
  fix (install Python 3.11+ from python.org/Homebrew, or use the uvx config) before
  `from vwmcp.server import main; main()`, because `python3` on macOS is often 3.9.
- [ ] `build-mcpb.py`: `uv build` wheel → `pip install --target build/mcpb/server/lib
  dist/*.whl` (pulls `mcp` and deps) → write manifest with the version from
  `pyproject.toml` → zip to `dist/vectorworks-mcp-<version>.mcpb`. Test: manifest renders
  with the version, required keys present (no network in the test; the install step is
  mocked).
- [ ] Docs: "Install as a Claude Desktop extension" (double-click the .mcpb; then say
  "check the Vectorworks setup" → `vw_doctor(fix=True)` installs the bridge; drag the
  menu command once). Note the Python ≥3.11 requirement (macOS ships 3.9; Homebrew or
  python.org) or ship it via uv in a later pass.
- [ ] Commit.

---

## Task B: Drawing quality

### B1 `vw_apply_class_standard`
**Files:** `src/vwmcp/data/class_standards.json`, `src/vwmcp/classes.py` (load/validate),
`src/vwmcp/vwlib.py` (`class_attrs`, `apply_class_attrs`, revert op `class_attrs`),
`src/vwmcp/tools/drawing.py`, `tests/test_classes.py`, `tests/test_revert.py`
- [ ] Data: standard `"spotlight"`: Spotlight-style names (`Lighting-Instruments`,
  `Lighting-Labels`, `Lighting-Positions`, `Lighting-Focus Points`, `Rigging-Truss`,
  `Rigging-Hoists`, `Stage-Decks`, `Stage-Steps`, `Soft Goods`, `Audio`, `Video`,
  `Scenery`, `People`, `Venue-Architecture`, `Venue-Seating`, `Notes`, `Dimensions`)
  each with `pen_rgb`, `fill_rgb` or null, `line_weight_mils`, `description`.
  `classes.load(name)` validates (unique names, 0-255 RGB).
- [ ] vwlib: `class_attrs(names)` → per class `{exists, pen, fill, lw, use_graphic}` via
  `GetClPenFore/GetClFillFore` (color index → `ColorIndexToRGB`), `GetClLW`,
  `GetClUseGraphic`; `apply_class_attrs(specs)` → `NameClass` for missing (then restore the
  previously active class, vs-notes), `RGBToColorIndex` → `SetClPenFore`, `SetClFillFore` +
  `SetClFPat(1)` or 0, `SetClLW`, `SetClUseGraphic(True)`; returns before-attrs per class
  and the list created. Revert op `class_attrs` restores attrs; existing `class` op deletes
  created classes. **`vwlib.revert` resolves the handle before dispatching on `kind`**
  (fallback `GetObjectByUuid(op["uuid"])` → KeyError for a name-keyed op): give
  `class_attrs` its own branch in that first if/elif, like `class`.
- [ ] Tool `vw_apply_class_standard(standard="spotlight", only=None, overwrite=False,
  document=None)`: `overwrite=False` only creates missing classes; `True` also restyles
  existing ones. Journaled. Tests: journal ops; `only` filter; unknown standard error.
- [ ] Commit.

### B2 `vw_create_sheet` (sheet layer + viewport + title block)
**Files:** `vwlib.py` (`create_sheet`), `tools/drawing.py`, `tests/test_drawing.py`
- [ ] vwlib `create_sheet(name, layers, scale, classes_hidden=None, title_block=None,
  view="top_plan")`: reuse `create_layer(name, "sheet")` (already `CreateLayer(name, 2)`), but keep the
  sheet active until the viewport and title block are made, then restore the previous
  active layer, `vp = CreateVP(sheet_handle)`,
  `SetVPLayerVisibility(vp, layer_h, 0)` for the listed design layers and -1 for others,
  `SetVPClassVisibility(vp, cls, -1)` for `classes_hidden`, scale via
  `SetObjectVariableReal(vp, 1003, scale)` (**index not verified**: candidate list 1003
  scale, 1007 projection, 1000 view; read them back live first), `UpdateVP(vp)`, then
  optional title block: `CreateCustomObjectN("Title Block Border", (0, 0), 0, False)` and
  parameters (`Sheet Title`, `Sheet Number`, `Project Name` – names read live from the
  default object with `pio_parameters`). Returns uuids of sheet layer, viewport, title block.
- [ ] Tool `vw_create_sheet(name, layers, scale=48, hide_classes=None, title=None,
  sheet_number=None, project=None, document=None)`; journal: layer op (deleting the sheet
  layer removes its viewport and title block).
- [ ] Tests on journal + argument validation; commit.

**Live check:** object-variable indices, title block parameter names, whether the
viewport shows Top/Plan by default, 2026 vs 2027.

---

## Task C: Screenshot image-to-world mapping

**Files:** `vwlib.py` (`view_mapping`), `src/vwmcp/viewmap.py`, `tools/generic.py`
(`vw_screenshot` gains `mapping`, new `vw_point_to_world`), `tests/test_viewmap.py`
- [ ] vwlib `view_mapping()`: `GetVCenter()`, `GetZoom()`, `GetLScale(ActLayer())`,
  `GetUnits()[3]`, projection (`GetProjection(ActLayer())`, 6 = Top/Plan? verify), and the
  key: `ModelPt2DToScreenPt((x, y))` for the view center and for center + 1 unit, which
  gives screen pixels per drawing unit and the center's screen position **without
  guessing dpi or Retina factor**; plus `GetScreen()` (screen bounds). Return all numbers.
- [ ] `viewmap.Mapping.from_view(view, window, image_size)`: screen point → window-relative
  → image pixel (window is in screen points; the PNG may be shrunk to `max_width` or be Retina 2x:
  read the real pixel width from the PNG IHDR header, bytes 16-24, stdlib only). `to_world(px, py)`, `to_pixel(x, y)`, `valid`
  (Top/Plan only). Tests with synthetic numbers.
- [ ] `vw_screenshot(..., mapping=False)`: when True runs one job (`view_mapping`) and adds
  `mapping` to the text part (origin, units per pixel, projection); fails soft with
  `mapping_error`. `vw_point_to_world(px, py, mapping)` is pure (no job).
- [ ] Commit. **Live check:** `ModelPt2DToScreenPt` coordinate space (window? screen? flipped
  y?), compare with an object's known position in a screenshot.

---

## Task E2: `vw_insert_platform` (decks + steps composite)

**Files:** `vwlib.py` (`insert_platform` composing `insert_stage_decks`, `insert_stage_steps`,
rails via Stage Deck `Rail*` fields read live), `tools/drawing.py`, `tests/test_drawing.py`
- [ ] Tool: `vw_insert_platform(width, depth, height, x, y, columns, rows, steps_on=
  "front"|"back"|"left"|"right"|None, step_count=None, rails=None, rotation=0, purpose,
  cls, document)`; one journal entry covering decks + steps; the tool computes `(step_x, step_y,
  step_rotation)` with `platform.step_origin(...)` (pure, unit-tested) and passes them to
  one vwlib job `insert_platform` that inserts decks then steps and returns both uuid
  lists for a single journal entry; pass through `layer`, `structure`, `kind` like the
  deck/steps tools.
- [ ] Commit. **Live check:** on the throwaway doc together with ramp and soft goods.

## Task E3: hoists, truss corners/towers, band placement (live-dependent)

- [ ] `vw_insert_hoists(positions or along truss system, capacity, cls)`: Spotlight `Hoist`
  PIO (`CreateCustomObjectN("Hoist", ...)`; parameter names read live from the default
  object first, like the ramp). Build after the live read.
- [ ] Truss corners/towers in `vw_insert_truss_run`: accept `pieces=[{"symbol", "count"}]`
  and `turn` angles; corner symbols' `BrxTrussItemRecord.ItemType`/connection geometry must
  be read live from a corner block symbol in the library (Michael's library has
  `Rigging/Truss`).
- [ ] `vw_insert_band(members=[{"symbol","x","y","rotation","name"}], layer, cls)`: symbols
  via `insert_symbol` + a text label (`CreateText`) per member, one journal entry; only
  useful after Michael downloads People/backline libraries (CLAUDE.md roadmap).

---

## Done criteria

- E3 ships nothing until the live reads (hoist and corner parameters go to vs-notes
  first); `vw_insert_band` may be built offline (insert_symbol + CreateText).
- The D2 skill names MVR checks exactly as `mvr.NEEDS` does (no_gdtf, no_mode, ...).

- `uv run pytest -q` green; `uv build` wheel still contains the bridge; CI green.
- README tool table and `docs/claude-config.md` updated; `CLAUDE.md` roadmap boxes ticked
  with "(not run live)" where applicable; `CLAUDE.local.md` session history line.
- Live checklist for the next safe window written at the top of `CLAUDE.local.md`
  "Where to pick up": ramp, soft goods, mvr_check field names, hookup import, class
  standard, sheet, view mapping, platform.
