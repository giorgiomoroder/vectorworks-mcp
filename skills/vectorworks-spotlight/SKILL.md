---
name: vectorworks-spotlight
description: Working in a live Vectorworks Spotlight drawing through the vectorworks-mcp tools (vw_*). Use when the user asks to read, check, draw, hang, patch, export or fix anything in Vectorworks - light plots, truss, stage decks, hookups, MVR export - or when a vw_ tool fails. Covers the session-start document check, the safety rules (document=, revert, dialogs) and step-by-step recipes.
---

# Vectorworks Spotlight through vectorworks-mcp

Every `vw_*` call runs inside the Vectorworks document that is in front. The
user often has several documents open and switches between them while you
work, so the first rule is: know which document you are in, and say so.

## Session start (every time)

1. `vw_list_documents`. Tell the user which document is active. If it is not
   the one they mean, `vw_switch_document` (saved documents only) and check again.
2. `vw_ping` once: Vectorworks version, bridge version, warnings. If it fails,
   `vw_doctor` (nothing in Vectorworks is touched), then `vw_screenshot` to
   see whether a dialog or an open menu is in front.
3. For anything that changes the drawing, agree on a document first. Test
   writes belong on a throwaway file, never on the user's working document.

## Safety rules

- **Pass `document=` on every write.** The tool refuses if another document
  is active. No exceptions, even for a single object.
- **Undo is `vw_revert_last`**, one tool call at a time, repeatable.
  Vectorworks merges back-to-back scripted edits into one Cmd-Z step, so never
  promise Cmd-Z granularity. `vw_delete_objects` cannot be reverted: ask first.
- **Dialogs block everything.** A wrong `vs.*` call opens a modal **Script
  Errors** window; an open right-click menu stalls jobs too. When a call times
  out, `vw_screenshot` shows what is in front (`in_front`) without touching
  the app; the user has to close it.
- **Raw Python (`vw_exec_python`) is the last resort.** Prefer the typed
  tools. If you must: Python 3.9 syntax, `vw_vs_lookup` for signatures,
  `vw_lint` runs automatically; created objects are tracked for revert but
  changes to existing objects are not.
- Writes assign classes in a second step and re-read what Vectorworks kept:
  trust the returned `after` / `not_applied`, not your intent.

## Recipes

### See the drawing
`vw_set_view(view="top_plan", fit=True)` or an isometric, then
`vw_screenshot`. For a clean picture of specific layers independent of the
screen, `vw_render_layers`. Geometry as numbers: `vw_export_geometry`.

### Light plot inventory and paperwork
- `vw_list_positions` (positions with their devices, devices without a
  position, position names with no object), `vw_list_lighting_devices`
  (filter by position or layer, choose fields), `vw_list_truss`.
- Paperwork: `vw_lighting_device_report` (CSV or JSON, pick columns and sort,
  `output_path` writes the file).

### Edit device data
`vw_set_lighting_device_fields(updates, document=)`: select by position +
unit number (unit numbers repeat per position), channel, or uuid. Addresses go
through `UniverseAddress` ("2/101"). All-or-nothing; the result shows before,
after and anything Spotlight overrode.

### Channel hookup from a spreadsheet
1. Ask for a `.csv`/`.tsv` export of the sheet (first row = headers).
2. `vw_import_hookup(path, key="channel")` (dry run): show the user the
   planned updates, ignored columns and skipped rows. Headers are matched to
   field names; fix odd ones with `column_map={"What": "Purpose"}`.
3. `vw_import_hookup(path, key=..., dry_run=False, document=...)`. One
   revertible step. A row that matches no device or several stops everything;
   use `key="position+unit_number"` when channels are not unique yet.

### MVR export pre-flight
1. `vw_mvr_check` (optionally `position=`). Errors block or empty the MVR:
   `no_gdtf`, `no_mode`, `no_fixture_id`, `duplicate_fixture_id`,
   `unpatched`, `address_overlap`, `address_past_512`. Warnings:
   `no_position`, `position_without_object`, `symbol_without_3d`,
   `symbol_missing`. `field_missing` lists fields this document lacks.
2. Fix data with `vw_set_lighting_device_fields` (Fixture ID,
   UniverseAddress, Position, Fixture Mode); a GDTF fixture type is chosen in
   the Object Info palette; a 2D-only symbol needs a hybrid one
   (`vw_list_library_resources`, `vw_import_resource`).
3. Re-run the check, then the user exports: File > Export > Export MVR.
   There is no scripting call for the export itself.

### Hang fixtures
1. Find the symbol: `vw_list_symbols` in the document, or
   `vw_list_library_files` + `vw_list_library_resources` and
   `vw_import_resource` to bring it in.
2. `vw_insert_lighting_devices(symbol, x, y, count, spacing, position_name,
   document=)`: real Lighting Devices (symbol + Convert to Instrument), hung at
   the position's height, unit numbers / channels / purpose set and verified.
3. Check with `vw_list_lighting_devices(position=...)`.

### Truss, decks, steps, ramps, soft goods
- `vw_insert_truss_run(symbol, x, y, count, rotation, z, position_name)`:
  straight runs from a truss symbol, linked into a system; `vw_list_truss`
  to verify (broken chains are flagged).
- `vw_insert_stage_decks(width, depth, height, x, y, columns, rows, ...)`
  builds a platform; `vw_insert_stage_steps` and `vw_insert_stage_ramp` run
  down from a stage edge; `vw_insert_soft_goods` draws a curtain, truss
  border or pipe-and-drape along points. Sizes are mm strings or document
  units as each tool says; the result reports extents read back.
- Place anything else from a library with `vw_insert_symbol`; plug-in
  objects by parameter name with `vw_create_pio` / `vw_set_pio_parameters`
  (`vw_get_pio_parameters` shows the names).

### Platforms and people in one call
- `vw_insert_platform(width, depth, height, x, y, columns, rows, steps_on="front",
  rails=True, class_name="Stage-Decks", document=)`: decks plus a flight of steps
  centred on the chosen edge, one revertible step.
- `vw_insert_band(members=[{"symbol", "x", "y", "rotation", "name"}], class_name="People")`
  places people/backline symbols with a name label each. The symbols must be
  in the document first (import from the People / Audio libraries).

### Make it look like a drawing
1. `vw_apply_class_standard("spotlight", document=)`: a consistent class set
   (Lighting-*, Rigging-*, Stage-*, Soft Goods, Audio, Video, Scenery, People,
   Venue-*, Notes) with colours and line weights; `overwrite=True` restyles
   classes that already exist. Then put objects in those classes
   (`class_name=` on the insert tools).
2. `vw_create_sheet(name, layers=[...], scale=48, hide_classes=[...], title=,
   sheet_number=, document=)`: a sheet layer with a viewport of those design
   layers and a title block. Both are one revertible step each.

### Point at what you see
`vw_screenshot(mapping=True)` returns the picture plus a pixel-to-drawing
mapping (Top/Plan views); `vw_point_to_world(px, py)` turns a pixel you want
to talk about into x, y for the insert tools.

### Housekeeping
`vw_create_layer`, `vw_create_class`, `vw_move_objects`, `vw_duplicate_layer`,
`vw_set_vertices`, `vw_find_objects`, `vw_get_record` / `vw_set_record`.
All but delete are revertible.

## When something goes wrong

| Symptom | Do |
|---|---|
| Timeout, "has not answered the previous request" | `vw_screenshot`: a dialog or menu is open; ask the user to close it |
| Script Errors window | A raw `vs.*` call had wrong arguments; user clicks OK; check `vw_vs_lookup` |
| `vw_ping` fails or warns | `vw_doctor` (and `vw_doctor(fix=True)` to reinstall the bridge); then restart Vectorworks and ping again |
| Write refused: "active document is ..." | `vw_switch_document` or ask the user; never write to the wrong file |
| Object landed in the wrong place | `vw_revert_last` immediately, then re-read before trying again |
