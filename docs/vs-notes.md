# `vs.*` notes (Vectorworks 2026, macOS, live-tested)

Findings from building and using this server against Vectorworks 2026
Update 3 (build 846827) and, from 2026-11-17, 31.7. Embedded Python is **3.9.2**. Each run of the
menu command gets a fresh Python state (module globals don't persist).

## General

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

- Vectorworks 2027 (32.1) embeds **Python 3.14**; 2026 embeds 3.9.
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
  `OpenWidth`, `DraperyWidth`, `Traveler`... Needs a path, so a different
  creation call (`CreateCustomObjectPath`); not started.

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
