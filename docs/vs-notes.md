# `vs.*` notes (Vectorworks 2026, macOS, live-tested)

Findings from building and using this server against Vectorworks 2026
Update 3 (build 846827) and, from 2026-11-17, 31.7. Embedded Python is **3.9.2**. Each run of the
menu command gets a fresh Python state (module globals don't persist).

## General

- **Pre-flight lint.** `vw_exec_python` / `vw_exec_file` check the code
  before sending it (`vslint.py`, from the PO4 fork): syntax, vs.* argument
  counts against the live docstrings (`src/vwmcp/data/vs_api_<year>.json`;
  `vwmcp dump-api` rebuilds it from a running Vectorworks, 2026-11-19: the
  2027 table from Michael's English 32.1.1 matched the fork's from the
  German build) and deprecated calls marked "will generate error" (e.g.
  `vs.GetLS`, use `GetLSN`). Wrong argument *types* still reach Vectorworks
  and open the Script Errors dialog. `vwmcp lint FILE...` checks
  menu-command scripts; `vwlib.py` lints clean.

- `vs.GetName(h)` returns `"none"` for unnamed objects. A real object named
  "none" is the one `vs.GetObject("none")` returns, though that call can
  also match the class **None**, so compare handles.
- Layer names: `vs.GetLName(layer)`. `GetName` returns `""` for layers.
- Handles print as integers and are only valid during one script run. Use
  `vs.GetObjectUuid(h)` / `vs.GetObjectByUuid(uuid)` across calls.
- A nil handle compares as `str(h) == "0"`.
- `vs.ForEachObject(fn, "(ALL)")`, `"(T=RECT)"`, `"(PON='Lighting Device')"`,
  `"(T=86)"` (plug-in objects) all work.
- `vs.GetUnits()` → `(fraction, display, format, upi, name, sqName)`, e.g.
  `(25, 3, 2, 1.0, '"', ' sq ft')` for feet-and-inches documents.
- Most `vs` functions carry a docstring with a `Definition:` signature;
  `LDevice_*` don't.
- A call with the wrong number or type of arguments doesn't raise. It
  queues a modal **Script Errors** dialog shown when the script ends.
- `vs.NameUndoEvent(...)` neither names the Undo menu item nor stops
  Vectorworks merging consecutive scripted menu-command runs into one undo.

## Spotlight

- Lighting Device = plug-in object; parameters via
  `vs.GetRField(h, "Lighting Device", field)` / `SetRField`, then
  `vs.ResetObject(h)`. The reset takes effect when the script ends, so read
  back in a separate run.
- `UniverseAddress` (`"2/101"`) or `Absolute Address` are authoritative;
  `Universe` / `DMX Address` written on their own are overwritten on reset.
  Absolute = (universe-1)*512 + address.
- Useful fields: Unit Number, Channel, Dimmer, Purpose, Position, Inst Type,
  Wattage, Color, Template / Template2 (gobos), Focus, Circuit Number/Name,
  Symbol Name, Device Type, Num Channels, Fixture Mode, GDTF Fixture Name,
  User Field 1-6. Unit numbers repeat per position and may be blank.
- Positions: `Light Position Obj` (name in `Position Name`), `Lighting Pipe`,
  `Lighting Pipe Ladder` (`Name`). Devices reference positions by name.
- `LDevice_GetParamStr(h, 0, name)` is the wrong signature (Script Errors,
  returns `""`). Real signature unknown.

## Live findings 2026-11-20 (VW 2026 31.7, blank doc, while 2027 ran alongside)

- Two versions open at once work: the 2026 server's jobs ran in 2026 only.
- `vs.ModelPt2DToScreenPt((x, y))` returns the point **unchanged** in Top/Plan
  from the menu command: it is a model/screen-plane conversion, not pixels.
  `GetProjection(ActLayer())` = 6 in Top/Plan; `GetZoom()` 115.38 (percent),
  `GetScreen()` = (0, 0, 1728, 1117). Pixel mapping needs another route
  (calibrate with an object at known coordinates).
- Class attributes: `SetClPenFore(name, RGBToColorIndex(r, g, b))` with
  0-65535 components works (`RGBToColorIndex(65535, 0, 0)` = index 1256 on
  this doc; it adds palette entries). In Python `GetClPenFore(name)` and
  `GetClFillFore(name)` return an **(r, g, b) tuple**, not an index.
  `SetClFPat(name, 1)` + fill colour, `SetClLW(name, mils)` read back as set.
  `vw_apply_class_standard` created 18 classes with the right line weights
  and colours (first read-back looked white because the reader converted
  the tuple as an index).
- Feeding that tuple to `ColorIndexToRGB` opened the **"A Script error has
  occurred" alert**: a 324x130 window titled "Vectorworks" at window level 0
  (not a modal level), which blocked the next job for good. `vw_screenshot`
  now reports it as `in_front` (`screenshot.is_script_error_alert`).

## MVR pre-flight (live 2026-11-20 on the Bobby Lee plot, VW 2026, 216 devices)

- Lighting Device fields present: `FixtureID` (**the fixture type name**,
  e.g. "Astera AX5", shared by all units of a type: not an MVR identity),
  `Fixture Mode`, `GDTF Fixture Mode`, `GDTF Fixture Name`, `GDTF Fixture
  Type ID`, `GDTF Fixture Custom ID`, `Vision Fixture Name`,
  `UniverseAddress`, `Universe`, `DMX Address`, `Absolute Address`, `Num
  Channels`, `UseGDTFGeometry`. No `Fixture ID` (with a space). Symbol
  definitions carry `EntEquipUniversal.MVR-ID`.
- `vs.GetSymbolType` returned 2 for a hybrid library symbol and 0 for three
  2D-only fixture symbols on the plot (`ElektraLite 30º`, `RGB WW/CW Tape`,
  `Spotting Lamp`).
- Result on the plot: 214/216 without GDTF fixture, 106 unpatched, 20
  address pairs (mostly identical addresses on paired units: now
  `address_shared`, a warning; 3 real partial overlaps at 2/311-2/330-2/349
  and 3/311-3/330 with 21-channel footprints), 44 devices without position,
  8 position names without an object (known from `vw_list_positions`).
- `vw_import_hookup` (same plot): 3 rows keyed by position + unit, dry run,
  apply (Purpose + User Field 6 on FOH TRUSS 8/20, User Field 6 on Balcony
  Rail 3), `vw_revert_last` restored all three (re-read).

### Earlier assumptions (before the live run)

- `vwlib.mvr_data` reads the MVR-relevant Lighting Device fields that exist in
  the document (`ld_field_names`), so `Fixture ID`, `GDTF Fixture Name`,
  `Fixture Mode`, `GDTF Type ID` are assumed names until checked on 2026 and
  2027; absent ones come back as `field_missing`.
- `vs.GetSymbolType(symdef)` is assumed to return 0 (2D only), 1 (3D), 2
  (hybrid) as the VectorScript reference says; `vw_mvr_check` flags 0.
  Verify on a fixture symbol and on a plain 2D symbol.

## More live findings 2026-11-20 (VW 2026, test_mcp.vwx)

- **Screenshot mapping** (`viewmap.py`): Vectorworks' zoom is true size on
  the physical display: pixels per drawing unit = display points/inch
  (`CGDisplayScreenSize`, 127.5 on this MacBook) x capture px per point (2 on
  Retina) x zoom/100 / (layer scale x units per inch). The view centre
  (`GetVCenter`) is the centre of the white drawing area (found in the
  capture by sampling near-white rows/columns). Verified: a 2x1 platform at
  (0..96, 0..96) at zoom 201 % on 1:48 measured 10.72 px/inch (predicted
  10.69) and its corner landed within 3 px; a second capture matched the
  rulers. A capture taken right after a job can show a stale window (the
  deck was not painted yet): fit/redraw, then capture.
- **Soft Goods**: `CreateCustomObjectPath("Soft Goods", path, None)` creates
  the object and consumes the path (length 216 for a 120+96 L), height
  applied, but opens the plug-in's **Object Preferences** dialog (250x1002,
  window level 0) and the job waits until the user clicks OK (367 s here).
  `CreateCustomObjectN("Soft Goods", p, 0, False)` + `SetCustomObjectPath(h,
  polyline)` gives the identical object (extents 123 x 99 x 120) silently.
- **Stage Ramp** (`vw_insert_stage_ramp`, first live run): 24" stage, 144"
  ramp with rails: centre (0, -71, 30), size 38.5 x 142 x 60; reverted.
- **Platform** (`vw_insert_platform`): decks at (24, 48) and (72, 48), the
  "Simple" 3-step flight centred on the front edge at (48, -18), descending
  -y; one revert removed all three. Inserting selects the new objects
  (Object Info showed "3 Objects"): the composite tools do not restore the
  user's selection yet (`vw_insert_lighting_devices` does).
- **Band** (`vw_insert_band`): `TextJust(2)`, `TextOrigin`, `CreateText`,
  `LNewObj` make a centred text under each symbol; 2 symbols + 2 texts,
  reverted as one step; `vw_import_resource` revert removed the symbol.
- **Save As under a tool's feet**: the journal keys entries by document
  name, so after "Untitled 1" was saved as `test_mcp.vwx` the platform entry
  could not be reverted by `vw_revert_last` (guard refused, correctly); the
  entry was popped and its ops replayed by hand. Idea: remember the window
  id or offer `journal_document=`.
- `vw_switch_document` / `document=` guard worked throughout with 2027
  open beside 2026; nothing reached 2027.

## Hoists and truss corners (reads 2026-11-20, VW 2026)

- `CreateCustomObjectN("Hoist", ...)` → "plug-in 'Hoist' is not available in
  this document". The only hoist `.vso` in the app Plug-ins folder is
  `HoistVW.vso` = **"Hoist (Legacy)"**, flagged "Don't Put In Workspace"
  (parameters: MotorNumber, MotorLabel, Location, Type, MaximumLoadStr,
  BrakeType, Function, Manufacturer, HoistPos, HiHook, LoHook, LoadTrim,
  Speed, Phasing, Voltage, ChainLength, HoistWt, ChainWt, LoadWt, ControlID
  …). The current Hoist tool is native; read its plug-in name with
  `pio_name` from a hoist Michael inserted (e.g. on a real plot) before
  building `vw_insert_hoists`. The Lighting Device is native too: no
  `.vso`, so its parameter names come from a plot (`ld_field_names`).
- Truss corner symbol (`Global Truss F34Box Corner`, F34 library):
  `GetSymbolType` = 2 (hybrid), `BrxTrussItemRecord`: `ItemType` "Corner",
  `Length` 0, `Height`/`Width` 290, `Weight` 7.71, `CenterBased` True,
  `Center X` 145, connection points `Right` (290, 0, 0), `Top` (145, 145, 0),
  `Bottom` (145, -145, 0), `High` (0, 0, 290), `Low` (0, 0, 0) with
  `* Valid` flags, `CornerType` "CornerNone", `HingeGeometry` "Book Corner".
  The F34 library also has C19…C61 corners, T35/T40 tees and R10…R750
  curved pieces (`ItemType` to read). This is what a corner-aware
  `vw_insert_truss_run` needs: place the corner so its Low/start point meets
  the run's end, continue from the chosen connection point at ±90°.

## Sheets (live 2026-11-20, VW 2026)

- `CreateVP(sheet_layer_handle)` with the sheet active makes a viewport (type
  122); `SetObjectVariableReal(vp, 1003, 48)` reads back 48.0 (scale);
  `GetObjectVariableInt(vp, 1000)` = 6 (Top/Plan). `SetVPLayerVisibility`,
  `SetVPClassVisibility`, `UpdateVP` raised nothing. Deleting the sheet layer
  (`vw_revert_last`) removes viewport and title block with it.
- `CreateCustomObjectN("Title Block Border", (0, 0), 0, False)` creates a
  title block; its ~100 parameters are layout only. Sheet title/number live
  in the attached record **"Title Block Sheet Data"** (`Sheet Title`, `Sheet
  Number`, `Page Number`, `Date`, `Status`, `Scale`...), project data in
  **"Title Block Project Data"** (`Project Name`, `Project ID`, `Project
  Address`, `File Name`...), revisions in "Title Block Revision Data".
  `SetRField(h, "Title Block Sheet Data", "Sheet Title", ...)` + `ResetObject`
  sticks. `NumRecords(h)` / `GetRecord(h, i)` list the attached records.

## Class standards (live 2026-11-20, see "Live findings" above)

- `vwlib.create_sheet`: `CreateVP(sheet_layer)` while the sheet is active,
  `SetVPLayerVisibility(vp, layer_h, 0 | -1)`, `SetVPClassVisibility(vp,
  name, -1)`, scale via `SetObjectVariableReal(vp, 1003, scale)` (**index
  assumed**: read 1003 back on a hand-made viewport first), `UpdateVP`. A new
  viewport is assumed to show Top/Plan. Title block: `CreateCustomObjectN(
  "Title Block Border", (0, 0), 0, False)`; the tool only writes parameters
  that exist in the object's parametric record and reports the available
  names, so the first live run tells us what "Sheet Title" etc. are called.
- `vwlib.apply_class_attrs`: `RGBToColorIndex(r, g, b)` with 0-65535
  components, `SetClPenFore/SetClFillFore(name, index)`, `SetClFPat(name, 1)`
  solid / `0` none, `SetClLW(name, mils)`, `SetClUseGraphic(name, True)`;
  `NameClass` creates and activates (restored afterwards). Readers
  `GetClPenFore` … `ColorIndexToRGB` feed the `class_attrs` revert op.

## View mapping for screenshots (not run live, 2026-11-20)

- `vwlib.view_mapping`: `GetVCenter()`, `ModelPt2DToScreenPt((x, y))` for the
  centre and centre + 1 unit along x and y, `GetZoom()`, `GetLScale(ActLayer())`,
  `GetProjection(ActLayer())`, `GetScreen()`. Assumptions to check live:
  the screen point space (global screen points like the CGWindow bounds that
  `vw_screenshot` reports? window-relative? Retina pixels?), the y direction,
  and that `GetProjection` returns 6 for Top/Plan (`TOP_PLAN_PROJECTIONS`).
  Calibrate by clicking a known object in a mapped screenshot and comparing
  `vw_point_to_world` with its `GetSymLoc`.

## Drawing and 3D

- Walls from `vs.Wall(...)` have one component; `SetWallThickness` and
  `SetWallHeights` silently do nothing (even after `ConvertToUnstyledWall`).
  Use `vs.SetComponentWidth(w, 1, t)` for thickness and
  `vs.SetWallCornerHeights(w, h, 0, h, 0)` for height.
- Doors: `vs.CreateCustomObjectN('Door', pt, rot, False)` (no dialog). Set
  both `Width` and `DoorWidth` (Width alone reverts). Local frame:
  `SwingDirection` Out → local +y, In → local -y; `SwingHingeSide` Right →
  hinge at local -x, Left → +x. `vs.GetBBox` on doors is unreliable; verify
  via the arc inside `FInGroup` (`HCenter` / `GetArc`).
- Extruded circles (`ArcByCenter` inside `BeginXtrd`) render as octagons at
  low 3D conversion resolution; build round things from 48-gon polygons.
- Top/Plan view: `vs.DoMenuTextByName('Standard Views', 1)`. Zoom to objects:
  select them, then `vs.DoMenuTextByName('Fit To Objects', 0)`.

## Geometry read-back (Vectorworks 2027, live-tested)

- Vectorworks 2027 (32.1) embeds **Python 3.14** (3.14.5 in 32.1.1); 2026 embeds 3.9.
  vwlib stays 3.9-compatible so one prelude serves both.
- `vs.GetBBox(h)` is the bounding box of the projection **on the screen
  plane**: with a rotated plan view the same object returns different,
  rotated coordinates. Don't use it for exact geometry.
- Exact geometry: lines `GetSegPt1/2`; polygons `GetVertNum` + `GetPolyPt(h, i)`
  (1-based); polylines `GetPolylineVertex(h, i)` → `(p, vertexType, arcRadius)`;
  texts `GetTextOrientation(h)` → `(origin, angle, mirrored)`, `GetText`,
  `GetTextSize(h, 0)`, `GetTextJust`; dimensions `GetDimText`.
- Arcs: `HCenter` is the arc's center, `GetSegPt1/2` its start and end
  points, `GetArc` → `(startAngle, sweep)` in degrees. Radius = distance
  center → start point.
- `vs.GetObjectUuid` + `vs.GetParent` over `ForEachObject(fn, "(ALL)")` gives
  a cheap before/after snapshot to find the objects a script created.

## Layers, vertices, attributes (Vectorworks 2027, found live on plan work)

- Duplicate a design layer: `vs.CreateLayer(name, 1)` (becomes the active
  layer, restore with `vs.Layer(previous)`), `vs.SetLScale(new, vs.GetLScale(src))`,
  then `vs.CreateDuplicateObject(h, newLayerHandle)` for every top-level
  object (collect the handles first). Order and groups are kept.
- A new layer is visible and sits at the end of the layer list. Visibility is
  `Get/SetObjectVariableInt(layer, 153)` (0 visible, -1 hidden, 2 gray).
  `vs.HMoveBackward(layer, False)` / `vs.HMoveForward(layer, False)` move a
  layer in the stack; one call can jump several places (seen: 13, past the
  sheet layers), so re-read the order after every step.
- Viewports: `vs.GetVPLayerVisibility(vp, layer)` -> `(ok, vis)`,
  `vs.SetVPLayerVisibility(vp, layer, vis)`, then `vs.UpdateVP(vp)`.
  Viewports are type 122 on sheet layers.
- `vs.SetPolyPt(h, i, x, y)` works on polygons (type 5) but **silently does
  nothing on polylines (type 21)**; use
  `vs.SetPolylineVertex(h, i, (x, y), vertexType, radius, True)` there.
  `vs.InsertVertex(h, x, y, beforeVertexNum, 0, 0)` and `vs.DelVertex(h, n)`
  work on both; `vs.ResetBBox(h)` afterwards. `vs.HArea(h)` returned None.
- New objects take the document defaults, not the look of their neighbors.
  Read fill and pen first (`GetFPat`, `GetFillBack`, `GetFillFore`,
  `GetPenFore`, `GetLW`, `GetLS`, `IsFPatByClass`, `IsFillColorByClass`,
  `IsLWByClass`, `IsLSByClass`, `IsPenColorByClass`; colors are 16-bit
  tuples) and copy them, or set them by class with the `Set...ByClass` calls.
- `vs.SetParent(h, groupHandle)` moves a new object into an existing group.
- Text: `vs.SetText(h, s)` replaces the string ("\r" is a line break),
  `vs.GetTextOrientation(h)[0]` is the origin, `vs.SetTextJust(h, 1|2|3)`
  left/center/right, `vs.SetTextVerticalAlign(h, 1..5)` top .. bottom.
- Not validated live yet: `vs.DelObject(layerHandle)` to delete a layer
  (used by the revert of `vw_duplicate_layer`; it reports "missing" if the
  layer is still there afterwards), and `vw_duplicate_layer`,
  `vw_set_vertices`, the `attrs` of `vw_export_geometry` and
  `vw_render_layers` as typed tools (their vs calls all ran live through
  `vw_exec_python`).

## Screenshots (outside Vectorworks)

VectorScript can't save the viewport to a file (`ExportImageFile` only
exports existing image objects). From macOS: get the document window's id
from `CGWindowListCopyWindowInfo` (owner name "Vectorworks 2026", layer 0,
title = document name; palettes are layer 103), then
`screencapture -x -o -l <id> out.png`. That works even when the window is
covered. It needs Screen Recording permission for the calling app.
`src/vwmcp/screenshot.py` does this through ctypes; calling the same API
through JXA's ObjC bridge segfaulted `osascript` (2026-11-17).

## Drawing tools (live-tested 2026-11-17, VW 2026 build 31.7)

Call patterns first read from vicquick/vwx-mcp's `commands.py` (MIT), then
run here through the menu command on the user's sketch document
(solarplexia_dec2026.vwx), every step reverted afterwards.

- **Layer activation.** VW 2026 Python has **no `SetActiveLayerN`**; the only
  call is `vs.Layer(name)`. vwx-mcp found it hazardous from a palette callback
  or Windows timer (nested event loop), but from our menu-command context
  `CreateLayer` + `vs.Layer(previous)` ran cleanly and restored the active
  layer. Keep using it only from the menu command.
- Resources: `vs.BuildResourceListN(16, path)` → `(list_id, count)` lists the
  symbols of a library `.vwx` without opening it (49 names from Global Truss
  F34.vwx in ~0 s). `vs.GetNameFromResourceList(list_id, i)` is 1-based.
  **`vs.ImportResourceToCurrentFile(list_id, i)`** (two args, documented)
  imports one symbol; `ImportResToCurFileN` also exists but has no docstring
  and was not used. Importing a truss symbol brought only the 2D/hybrid
  definition, not a `_3d` companion like the ones Spotlight's Insert Truss
  tool had left in the file. `vs.GetObject(name)` finds a symbol definition;
  `vs.DelObject` on it removes it. `ForEachObject` with `T=SYMDEF` never sees
  resources; walk `FSymDef` / `NextSymDef` (as `list_symbols` does).
- **Truss objects are `TrussItem`**, not `Truss`. `vs.CreateCustomObjectN(
  'Truss', ...)` returns nil. `CreateCustomObjectN('TrussItem', (x, y), rot,
  False)` works; fields: `Symbol` (a truss symbol definition in the document),
  `Name`, `Type`, `PositionName`, `Length`, `Height`, `Width`, `Weight`,
  `TrussSystem`, `ItemType` ... Setting `Symbol` + `ResetObject` draws the
  truss, but `Length`/`Height`/`Width` stay 0 (Insert Truss reads them from
  the symbol's truss record); set them explicitly if Braceworks needs them.
  Existing plot: 13 TrussItem, 33 Lighting Device, 4 Light Position Obj.
- Right after `CreateCustomObjectN` the object reports an empty bbox and
  "not visible"; it regenerates by the next job. A regen can shift the
  insertion point slightly (observed 0.45 units), so a move + reverse move
  around a `ResetObject` doesn't land exactly on the start point.
- `vs.GetBBox` on the TrussItem returned coordinates ~2000 units from its
  `GetSymLoc` (0, 0): user origin vs internal origin. Use `GetSymLoc` for
  plug-in object positions.
- **A new plug-in object's class is reset by its first regeneration**, which
  happens at the end of the creating job even after an explicit
  `ResetObject`. `SetClass` in the same job as `CreateCustomObjectN` is lost
  (TrussItem came back "None"); `SetClass` in a later job sticks through
  further resets and moves. Tools therefore assign the class in a second
  job (`set_objects_class`).

## Lighting devices (live 2026-11-17)

How to make a Lighting Device by script, found by experiment on the user's
plot (33 Martin MAC One devices on 4 Light Position Objs and a truss run):

- **`CreateCustomObjectN("Lighting Device", ...)` is a dead end.** It makes a
  plug-in object with no symbol geometry (`GetSymName` ""), `Inst Type`
  empty, `Device Type` "Light", `Num Channels` 1, nothing from the symbol.
- **What works:** `vs.Symbol(fixture, pt, rot)`, select only the new symbol
  instance(s) (`DSelectAll`, `SetSelect`), then
  `vs.DoMenuTextByName("Convert to Instrument", 0)`. The selection is
  replaced by Lighting Device objects (new uuids) with `Inst Type`,
  `Device Type` "Moving Light", `Wattage`, `Num Channels` 108, `GDTF Fixture
  Name`, `GDTF Type ID` filled from the symbol's **`Light Info Record`**.
  `Weight` shows "0" until the next reset, then "9.92 lb". Works for several
  selected symbols at once. The command needs a selection, so
  `vwlib.insert_lighting_devices` records and restores the user's selection.
- **Position does not hang the device.** Writing `Position` + `ResetObject`
  sets the name but leaves z at 0; Spotlight's insertion tool sets z itself.
  So read the position's z (`GetSymLoc3D` of the Light Position Obj /
  TrussItem / pipe with that name, `POSITION_PLUGINS`) and `Move3DObj` the
  device to it. Existing devices on "palm NE" sit at the position's z (118)
  on 17" centres; the Light Position Obj itself has `StartNum`, `Increment`,
  `Direction`, `Numbering Style`, `TotalHungWeight` fields.
- The `LDevice_*` functions (`LDevice_Reset`, `LDevice_GetActSym`,
  `LDevice_SetParamStr`, ...) and `HP_ConvertToHangPos`, `SL_Import`/`SL_Export`
  have **no docstrings** in 2026; still unused. Unit Number, Channel, Purpose,
  Position are set with plain `SetRField` + `ResetObject` and stick.
- Local fixture libraries on this Mac: only 3 files under
  `Entertainment/Lighting/Instruments` (incl. "Martin Lighting Moving
  Light.vwx"); the rest is download-on-demand.

## Truss runs (live 2026-11-17)

What Spotlight's Insert Truss tool leaves behind, read from a 5-piece
DJ truss on the user's plot, and reproduced by `vwlib.insert_truss_run`:

- One `TrussItem` per piece, `CenterBased`, `GetSymLoc3D` = piece centre
  with z = trim height in document units (120 = 10' on a feet-inches doc;
  `TrimHeight` field stays 0). Consecutive centres are one symbol length
  apart along the piece's rotation (`GetSymRot`).
- Dimensions come from the symbol definition's **`BrxTrussItemRecord`**
  (Length/Height/Width in mm, Weight in kg, Type, Section, Connection,
  ItemType). Writing `Length` as `"3000mm"` through `SetRField` parses
  correctly (reads back `9.84251968503937e00'`). Document units per mm =
  `GetUnits()[3] / 25.4`. The symbol also carries `Truss Record` (model,
  manufacturer, "3000mm" strings) and `EntEquipUniversal`.
- `Weight` on the TrussItem is grams (`19050` for 19.05 kg); `Distributed
  weight` is kg/m (`6.35`).
- `vw_list_truss` (live 2026-11-17): TrussItem `Length` reads back as
  "9.842519685039372e00'" on the feet-inches doc (parsed by `_dim_to_doc`);
  the sketch doc had systems T0, T2, T3, T4 with T2 mixing F34-200/300 pieces
  and a broken chain (`linked: false`), which the tool reports.
- Linking: each piece's `C_START_UUID` holds the uuid of the previous piece
  in the run (first piece empty). `TrussSystem` "T<n>", `TrussLine` "1",
  `TrussSystemLineIdent` "T<n>-1"; Insert Truss numbers systems T0, T2…
  with gaps, so pick the lowest unused. `ConStart`/`ConEnd` stayed 0.
  Michael has no Braceworks licence (2026-11-17), so whether a calculation
  accepts the run is unverified and not a goal; the fields match what Insert
  Truss writes.
- Layers: `vs.CreateLayer(name, 1)` design / `2` sheet (makes it active),
  `vs.SetLScale(h, 48)` (read back 48.0), `vs.DelObject(layer_handle)` deletes.
- Classes: `vs.NameClass(name)` creates **and activates**; calling it again
  with the previous name restores; `vs.DelClass(name)` removes.
- Views: `vs.SetViewVector((1, -1, 1), (0, 0, 0), (0, 0, 1))` gives Right
  Isometric; `vs.DoMenuTextByName('Fit To Objects', 0)` fits all (no
  selection needed) and VW 2026 has no `ZoomToSel`. `ReDrawAll` after.
- Moving: `vs.HMove(h, dx, dy)` on a plug-in object works and reverses.
- `vs.CombineIntoSurface` took 215 s on vwx-mcp's test; avoid in bulk.

Library files on this Mac: `/Applications/Vectorworks 2026/Libraries/`
(Entertainment/{Lighting, Stage, Audio, Rigging/Truss, Rigging/Truss Pickups},
Visualization/People, Defaults/Stage Deck; 60 `.vwx` under Entertainment) and
`~/Library/Application Support/Vectorworks/2026/Libraries/` (user, Favorites).
Some app libraries are download-on-demand (`*.db.proxy`); only present `.vwx`
files are listed. `Libraries/defaultContent.db` is a plain SQLite index
(tables `Files` 622 rows: FileName, FilePath, FileOnLineFlag; `Resources`
20k rows: ResourceName, ResourceType 16 = symbol, Tags, FileID, PNG previews)
of the default content only; the full online catalogue (`vwlibraries.db`) is
a proxy here, so people/backline libraries are invisible until downloaded.
On 2026-11-17 the only people-related file was `Human Figure Textures.vwx`.

## Stage decks (live 2026-11-17, build 31.7)

`vs.CreateCustomObjectN("Stage Deck", (x, y), rot, False)` works; the deck
regenerates at the end of the creating job (bbox 0 until then: read
geometry in a follow-up job, `vwlib.object_extents`). Findings:

- **Insertion point is the deck's corner**, not its centre: a 96x48 deck
  inserted at (0, 0) spans x 0..96, y 0..48, z 0..height (centre (48, 24, 18)).
  Rotation 90 turns it so it extends +y by Width and -x by Depth, so
  corner-offset tiling (`vw_insert_stage_decks`) forms a gapless platform.
- `Width`/`Depth`/`Height` written as "2438.4mm" strings read back as
  **feet in exponent notation** on a feet-inches doc ("8.000000000000002e00'");
  `DeckSize` is derived ("4' x 8'"), `TopSurfaceArea` "32 sq ft", `LegTotal` 6
  for 8x4 at the default 3 ft leg spacing. `MasterClass` "Staging",
  `ClassParts` False by default; the object itself lands in the active class.
- `vs.GetBBox` is **projected in 3D views** (the sketch doc was in a custom
  view: a flat deck came back as a 100x69 box). `vs.Get3DCntr(h)` →
  `((x, y), z)` and `vs.Get3DInfo(h)` → `(y extent, x extent, z extent)` are
  view-independent; `vwlib._extent3d` uses them (`vw_list_truss`, decks).

## Stage steps (live 2026-11-17)

`vs.CreateCustomObjectN("Stage Steps", (x, y), rot, False)`: the insertion
point is the **top centre of the flight at the stage edge**; at rotation 0
the flight is `Treadwidth` wide centred on x and descends toward -y (default
4 ft stage height, 6 steps, 36 in wide, plan depth ~62 in). Writing
`Stageheight` "609.6mm" + `StepTotal` "3" (with `BuildMethod` "Stage height
and number of steps") gave a 2 ft flight with a 6 in rise; `RailRight`
"True" adds the rail (`RailHeight` 3 ft). Type "Self-Adjusting" keeps a fixed
`StringerLength` (6 ft default), so a 2 ft flight lies at 19.47° and spans
81 in in plan with the rail; set `StringerLength` or use Type "Simple" for a
compact flight. `Get3DInfo` on the flight returned (y extent, x extent, z
extent) like the deck.

### Parameter names (from the plug-in's string table)

Spotlight's stage plug-ins are all installed on this Mac (`Plug-ins/*.vso`):
`Stage Deck` (marked "Don't Put In Workspace": inserted by the Stage Deck tool,
but `CreateCustomObjectN("Stage Deck", ...)` is the plan), `Stage Steps`,
`Stage Ramp`, `Stage Plug`, `Stage Lift`, `Soft Goods` (path object),
`Seating Layout`, `Simple/Custom/Circular Stair`, `Ramp`, `Guardrail`.
`strings "Stage Deck.vso"` lists the parameter names and popup choices
(no Vectorworks call needed), in record order:

- Shape/size: `DeckShape` (Rectangular | Round), `Height` 1200mm, `Depth`
  1200mm, `Width` 2400mm, `RoundRad`, `RoundDia`, `RoundSweep`, `DeckSize`
  (popup, "4'x8'"...; relation to Width/Depth to be checked live),
  `TopSurfaceArea` (computed), `HideDeck`, `TopThick` 25mm, `TrimHeight` 150mm.
- Structure: `StgStyle` (Legs-Basic | Legs-Braced | Folding | Deck Only |
  Border | Simple), `LegDia` 75mm, `LegProfile` (Square | Octagonal | Round),
  `LegSpace` 900mm, `LegTotal` (computed), `Additions` (None | Casters |
  Blocks), colours `TreadColor`/`EdgeColor`/`BorderColor`/`LgFrmColor`.
- Rails: `RailFront`/`RailBack`/`RailLeft`/`RailRight` (None | Straight |
  Box Open | Box Filled | Toe | Box Filled+Toe), `RailHeight` 900mm,
  `RailProfile`, `RailColor`, `CRailR1`/`CRailR2`/`CRailArc` for round decks.
- Spotlight data: `Location`, `Position`, `Unit`, `Purpose`, `SetCartID`,
  `Brand`, `Model`, `Vendor`, `Cost`, `Note`, `ClassParts`, `MasterClass`
  ("Staging").
- `Stage Steps` shares the data block and adds `Type` (Self-Adjusting | Frame
  Free-Standing | Solid Free-Standing | Open Free-Standing | Simple),
  `BuildMethod`, `Stageheight`, `Treadwidth`, `StepTotal`, `TreadRiseVar`,
  `TreadDepth`, `RailLeft`/`RailRight` (booleans), `RailHeight`.
- `Soft Goods` is a path plug-in: `GdsFunct` (Curtain | Truss Border |
  Pipe-and-Drape), `CurtHeight`, `TopTrim`/`BottomTrim`, `OpenFrom`,
  `OpenWidth`, `DraperyWidth`, `Traveler`, `AddPipe`, `AddTrack`, `TrackWidth`,
  `ShowMarkers` (None | Start | Both), pipe-and-drape: `SliderMod` (6'-10',
  2'-3', ..., Custom), `HardwareToInclude`, `BaseSize`, `Show3DUprights`,
  `StckDrpWdth`, `DrpOverlap`, `TiedFullness`; fabric: `SoftOpts` (Opaque |
  Scrim | Image), `Material`, `Color`, `TopFin` (Rope Ties | S Hooks | ... |
  Unfinished), `BtmFin` (Sewn-In Chain | Pipe Pocket ... | Sewn-In Lead
  Tape), `Fullness`, weight fields, Spotlight data block, `MasterClass`
  "SoftGoods". `vw_insert_soft_goods` (2026-11-20) builds an open polyline
  (`OpenPoly`/`BeginPoly`/`AddPoint`/`EndPoly`, `ClosePoly` after) and calls
  `CreateCustomObjectPath("Soft Goods", path, None)`; **not run live yet**.
  To verify first: the path is consumed by the plug-in (else delete it),
  `None` is accepted as the nil profile group, `OpenFrom` popup values.

## Stage ramp (default object read live on 2027, 2026-11-19)

`CreateCustomObjectN("Stage Ramp", (x, y), rot, False)` works like Stage
Steps: insertion is the **top centre** at the stage edge, the ramp runs
toward -y at rotation 0, centred on x. Default object: `Type` Legs (popup
Legs | Solid | Simple), `BuildMethod` "Ramp Length" (| Pitch Angle | Pitch
Ratio | Pitch Percent), `Stageheight` 4', `RampLength` 8' (along the
slope), `Treadwidth` 3', computed `FloorLength` 6.93' (= plan length),
`PitchAngVar` 30 (`PitchAngCalc` "30°"), `PitchRatioVar` 1.73,
`PitchPercVar` 57.7, `Extend` 0, `BottomVertical`, `DrawArrow` None | Down,
`RailLeft`/`RailRight` "True"/"False", `RailHeight` 3', legs `LegDia`
`LegProfile` `LegSpace` `LegTotal`, the usual Spotlight data block,
`MasterClass` "Staging". `Get3DCntr` → ((x, y - plan/2), height/2),
`Get3DInfo` → (plan length 83.1", width 36", height 48") for the default.
Values read back in feet exponent form like the other stage objects.
`vw_insert_stage_ramp` (ramp_length or pitch_angle) is built on this and
has **not** run live yet as a tool.

**Lesson (2026-11-19):** that default ramp was created while Michael had
switched Vectorworks 2027 to another document (his Visit Bushwick model):
the object went there, the revert found and deleted it, and a census
confirmed nothing was left. Every test write now passes `document=` so it
refuses when another file is in front. Live tests should also start with
`vw_list_documents`.

## Open menus block the bridge (live 2026-11-17)

A contextual (right-click) menu left open in Vectorworks stops it from
servicing Apple Events, exactly like a modal dialog: the job file is never
claimed, `osascript` sits until its own ~2 min timeout, and the server
reports "did not pick up the job". No crash, nothing to clean up: when the
menu closes, the pending menu hops run `MCP Run Job` with no job waiting.
CoreGraphics shows it as a Vectorworks window at level 101 (popup menu);
modal dialogs are level 8. `vw_screenshot` now returns these under
`in_front`, so Claude can say what is blocking without touching the app.

## AppleScript

See `architecture.md`: only `run VectorScript` calling
`DoMenuTextByName('MCP Run Job', 0)` is safe; `run Python script` writes,
and any script sent during launch or a modal dialog, crash Vectorworks.
The dictionary has no usable document list (`every document` → `missing value`),
but `name of every window` works; see "Switching documents".

## Switching documents (outside Vectorworks, live-tested on VW 2027 32.1, German UI)

There is no vs.* call to list open documents or activate one, and switching
inside a running script is not safe. Plain AppleScript to the app works
(Automation permission only):

- `name of every window`: open documents front to back, plus helper windows
  ("" and "Window"); window 1 is the active document.
- `documents` / `every VectorworksDocument` return nothing usable, and
  windows have `document: missing value`, so the file path is not
  available: remember it from `vs.GetFPathName()` when a document is active.
- `set index of window "X" to 1` (even after `activate`) reorders windows
  but does **not** select the document tab; `vs.GetFName()` stays the same.
- `open POSIX file "<path>"` of an already open document brings it to the
  front without opening it twice. Unsaved documents can't be reached this way.
- The app's dictionary: Contents/Resources/Vectorworks.sdef (Cocoa standard
  suite + open, run VectorScript, run Python script, translate).
- Probing from inside a job: start osascript detached (`sleep 1; osascript`
  in a new session) so the Apple Event arrives after the script has ended,
  and read its output file in the next call.

## Vectorworks 2027 (live 2026-11-19, 32.1.1 build 888839, English, macOS)

Same bridge, same trigger (`run VectorScript` → `DoMenuTextByName`), served
from a second server (`VWMCP_VW_VERSION=2027`, `VWMCP_HOME=~/.vwmcp-2027`,
bridge with `vwmcp_home.txt`). What was checked on a migrated copy of the
sketch doc: `vw_ping`, `vw_document_info`, `vw_list_layers`, `vw_list_truss`,
`vw_exec_python` (read and create + revert), `vw_export_geometry` (651
objects, a 3D layer), `vw_render_layers`, `vw_duplicate_layer` + revert
(`vs.DelObject` on the layer handle deletes it), `vw_set_vertices` + revert,
`vw_list_documents`, `vw_switch_document` (same-document no-op). Not yet on
2027: the Spotlight, truss, lighting-device and stage write tools.

- The migrated workspace (Spotlight.vww) carries the **MCP Run Job** item,
  but a `.vsm` copied into `2027/Plug-ins` after the first launch is not
  loaded until the workspace is reloaded (Tools > Workspaces > pick it
  again) or Vectorworks restarts; until then `DoMenuTextByName` silently
  does nothing and jobs time out. Michael reloading the workspace was enough.
- `name of every window` in 2027 lists a window named **"Vectorworks"**
  first (visible, index 1), the document window second, then hidden helper
  windows ("Migration Progress", "Exporting MVR", ""). `documents.py` asks
  for visible windows only and skips the app-named one.
- `vw_render_layers` on a 3D layer (extrudes, meshes, plug-ins) in a 3D
  view shows only projected gray boxes (`bbox_view` from `GetBBox`); it is a
  2D plan check, not a 3D view.
- Type codes seen on the 3D layer without a `TYPE_NAMES` entry: 24 and 113.

## Safety tables and the checked `vs` (2026-11-20, built offline)

Bridge 0.2.0 wraps `vs` in a proxy (`CheckedVS` in `vwmcp_bridge.py`, after
Keystone's design, MIT). What it catches before Vectorworks sees the call:

- argument **count** and **types** against `vs_types.json` (3,142 functions
  with type codes H/R/I/B/S/P/Q/V/C/F, from the Vectorworks developer-
  scripting stub via Keystone). Only functions whose live docstring
  ("Definition: ... vs.Name(a, b)") has the same parameter count are checked;
  a point may be one tuple or two numbers, a colour must be one tuple (three
  loose numbers are silently ignored by Vectorworks), a string where a handle
  is expected gets the hint to use `GetObjectByUuid`;
- functions the stevenmorgan94 sweep (Vectorworks 2027, ~2,800 functions
  against throwaway documents) classified as **crash** (11: `UprString`,
  `TBB_AttachRecords`, `AddVectorFillLayer`, `CC_GetCircuitSource/Dest`,
  `DisplayLayerScaleDialog`, `DisplayOrganizationDialog`,
  `DisplayContextHelpOfCurrentPlugin`, `Plant_ReplacePlantParam`,
  `SetConstraintValue`, `SetTexSpaceEndCap`), **hang** (`RetrieveOpenGLPrefs`,
  `RefreshResManager`) or **interactive** (31 dialog openers such as
  `EditProperties`, `RunColorPaletteMgr`, `OLDHoistSectionDlg`): refused, the
  interactive ones unless the job has `allow_dialogs`. 99 functions have a
  recorded bad case; `wrong-object-type:crash` (the `LDevice_*`, gradient,
  light, roof and wall families) is a lint warning: a handle of the wrong
  object type crashes them, a null-handle check is not enough.

Not checked: argument values, handle object types, `Begin*`/`End*` pairing
(unpaired `BeginPoly`/`EndSym` crash). Keystone also found: a job sent while
only the start screen is open segfaults 2026 and 2027 (first `vs` call).

Live check done 2026-11-20/21 on VW 2026 31.7 (build 879357), Bobby Lee
plot, 2027 untouched: see "Live findings 2026-11-21" below.

## Lightwright Data Exchange (format from Gribiche64/vectorworks-bridge; live 2026-11-20 on VW 2026)

Spotlight > Preferences > Lightwright > "Use automatic Lightwright Data
Exchange" makes Vectorworks write `<document>.xml` beside the `.vwx` on
losing focus and watch it for patches stamped `Lightwright`. `<SLData>` >
`<ExportFieldList>` (the exported fields, configurable) > `<InstrumentData>`
with one `<UID_1246_1_1_0_0>` block per fixture (Device_Type, Symbol_Name,
Inst_Type, Layer, Class, Channel, Dimmer, Absolute_Address, Position,
Purpose, Color, Template, Wattage "700 W", Unit_Number, User_Field_1..6,
Lightwright_ID, X/Y/Z_Location_mm, nested Accessories). A patch = envelope
with the ExportFieldList copied verbatim + per-fixture blocks with only the
changed fields, `Lightwright_ID`, `UID`, `AppStamp Lightwright`, 14-digit UTC
`TimeStamp`, `Action Update`; written in place (FSEvents), applied 1 to 2 s
after Vectorworks regains focus. Hazards from that project: an unknown
`Symbol_Name` breaks fixture selection drawing-wide and permanently (restore
a backup); `Wattage` is not updated on a type swap; `Delete` actions from a
stale `.lw6` removed fixtures. Our tools refuse all three. Verified live
2026-11-20 (details in "Live findings 2026-11-21"): the file is
`<document stem>.xml` beside the `.vwx` (`~/Downloads/BobbyLee-BalboaTheater-
LightPlot_v2026.xml`), a Channel patch landed about a second after the click
into Vectorworks, the inverse patch on revert landed the same way.

## Live findings 2026-11-21 (safety batch on VW 2026 31.7 build 879357; Bobby Lee plot; 2027 untouched)

- **Bridge upgrade without a restart.** 2026 had bridge 0.1.0 cached (uptime
  about 6 h). One job did `importlib.reload(vwmcp.vwmcp_bridge)` from inside
  the old bridge; the next job reported 0.2.0. Useful when a restart is
  unwelcome, but `install-plugin` docs still say restart.
- **Checked `vs` works.** `vs.ColorIndexToRGB((1000,2000,3000))` (the call
  that popped the Script Errors alert on 2026-11-20) came back as
  `VSArgumentError` in 9 ms, no window in the CoreGraphics list. 2,218
  functions were type-checked against their live docstrings: 0 parameter-count
  disagreements, 842 have no "Definition:" docstring (unchecked), 82 of the
  table's functions do not exist in this Vectorworks.
- **vwlib by reference:** second call `vw_s` 10 ms instead of 18 ms.
- **Document guard:** a job with `document={"name": "nope"}` was refused with
  `WrongDocument` and `never_ran`; `vw_create_layer(..., document=...)` plus
  `vw_revert_last` round-tripped cleanly (8 ms in-app).
- **Vectorworks' own dialogs do not block jobs.** Help > About Vectorworks
  and Tools > Options > Vectorworks Preferences were both open while
  `vw_ping` ran normally underneath (also the Script Errors alert and the
  Object Preferences dialog had blocked on 2026-11-20, and a right-click menu
  on 2026-11-17). So the blockers are system alerts and menu tracking, not
  Vectorworks' layout-manager dialogs. The 15 s claim/cancel path could
  therefore not be provoked live (Michael's right-click menu did not stay
  open either); it is covered by the unit tests only. Side effect found:
  `name of every window` lists those dialogs, so `vw_list_documents`
  reported "About Vectorworks" as a document; both titles are now in
  `documents.HELPER_WINDOWS`.
- **Start screen = one untitled window.** With all documents closed the
  CoreGraphics list shows a single layer-0 window, 1728 x 1002, title `""`;
  no "Vectorworks"/"Home Screen" title at all. `has_document_window` now
  returns False for "normal windows but none titled" when the Screen
  Recording permission is granted (`CGPreflightScreenCaptureAccess`, no
  prompt), None without it (every title is empty then, cannot tell). Live:
  `vw_ping` refused in 60 ms with "No document is open ... (only the start
  screen)", job renamed `.cancelled`, Vectorworks kept running. The AppleScript
  `name of every window` returned an empty name in that state ("No document
  is open" from `vw_list_documents`), consistent.
- **Lightwright round trip.** Exchange was already on for the Bobby Lee plot;
  `~/Downloads/BobbyLee-BalboaTheater-LightPlot_v2026.xml` (697 KB, header
  TimeStamp 2025-12-08, VWVersion 3120, build 841021) held 398 fixture blocks
  (Device_Type Light 307 / Moving Light 89 / Practical 2; 36 symbol names;
  116 with a Lightwright_ID) where `vw_list_lighting_devices` lists 216
  devices: the export spans more layers (`[VENUE] - LX Rep`, `NNA#18_*`) and
  probably Lighting Devices our census filter skips; not resolved. Dry run,
  then a patch for FOH TRUSS unit 27 (UID 4690.1.1.0.0) Channel -> 998:
  about one second after Michael clicked into the window the drawing read
  998. Vectorworks then **wrote back only an acknowledgement**: the field
  list, `<InstrumentData>` with AppStamp Vectorworks, AutoRot2D true and
  **no fixtures**, the old TimeStamp kept (1,249 bytes). So after a patch
  the snapshot is empty until the next full export (`vw_lightwright_snapshot`
  now says so, `hint`). The inverse patch from `vw_revert_last` landed the
  same way. **The export was stale:** it said channel 999 for unit 27 while
  the drawing said 901, so the journaled inverse restored 999; set back to
  901 with `vw_set_lighting_device_fields`. Since then the patch tool reads
  the drawing's current values for the touched fixtures (one
  `list_lighting_devices` job per position, matched by Unit Number) and
  journals those (`inverse_from: live`), falling back to the export's values
  with a warning; and it copies the full export to `~/.vwmcp/lightwright/`
  before overwriting (`backup` in the result).
