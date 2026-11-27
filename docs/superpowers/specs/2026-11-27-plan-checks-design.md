# Plan checks on a real Windows/2027 plot: GDTF false positive, positions by name

Date: 2026-11-27. Source: a read-only survey of a production Spotlight plot
(273 Lighting Devices, Vectorworks 2027 32.1.0 German, Windows 11) through
`vw_list_lighting_devices`, `vw_list_positions`, `vw_mvr_check`,
`vw_lighting_device_report`, `vw_lightwright_snapshot`. Everything answered in
under 0.5 s and the field names are the English internal ones on the German
build, so no localisation work is needed. Two results were wrong or useless on
this plot; this spec fixes both.

## 1. `gdtf_unlinked` fires on every linked device

Observed: all 247 devices with a GDTF name have `GDTF Fixture Type ID` = `"0"`
(and `GDTF Fixture Custom ID` = `"0"`), yet each carries a real GDTF mode
("Mode 1 - Standard 16 bit.Robin Forte") and the channel count that mode
implies (Forte: 54). They are linked; the id field is simply not populated on
this Vectorworks build. The rule from the 2026 macOS live test (name set, id 0
→ unlinked) reports 247 errors and makes `ok: false` meaningless.

Design (data-driven, keeps the macOS behaviour):

- In `mvr.run_checks`, before the `gdtf_unlinked` check: if the field
  `GDTF Fixture Type ID` is present but **no device row** has a value other
  than `""`/`"0"`, the check is skipped. One warning issue
  `{"check": "field_unused", "severity": "warning", "message": "GDTF Fixture
  Type ID is 0 on every device (seen on Vectorworks 2027): the unlinked check
  is skipped; a GDTF fixture mode and channel count show the link instead.",
  "devices": []}` is appended, like `field_missing`.
- If at least one row has a non-zero id, the existing rule runs unchanged
  (the macOS plot where typed-in names kept id 0 while linked devices had an
  id).
- The existing `no_mode` check still catches a GDTF name without a mode.

Tests (`tests/test_mvr.py`): a document where every row has id `"0"` and a
mode → no `gdtf_unlinked`, one `field_unused` warning, summary unchanged
otherwise; the existing `test_gdtf_name_typed_but_not_linked_is_an_error`
(mixed ids) must still pass.

## 2. `vw_list_positions` is empty when positions are only names

Observed: the plot has no position objects at all (the truss layers are empty;
positions live only in the devices' `Position` text: "LX 1".."LX 5", "K C",
"K SL", "K SR", "L 1".."L 6", "Floor US"). The tool returns `positions: []` and
`device_positions_without_object: {name: count}`; nothing tells the user what
hangs where.

Design: `vwlib.list_positions` gains a key `by_name`, one entry per distinct
non-empty position name, whether or not an object carries it:

```
{"name": "K C", "has_object": false, "device_count": 38,
 "inst_types": {"Roxx Cluster B2 FC": 36, "MAC Ultra Perf": 2},
 "universes": [14, 15], "channels": [401, 438], "unpatched": 0}
```

- `inst_types`: counts by `Inst Type`, most common first (dict insertion
  order).
- `universes`: sorted distinct integers parsed from `UniverseAddress`
  ("14/1" → 14); unparseable or "0/0" rows count as `unpatched`.
- `channels`: `[min, max]` over rows whose `Channel` parses as an integer,
  else `null`.
- Sorted by `_natural(name)`. Existing keys (`positions`,
  `unassigned_device_count`, `device_positions_without_object`) and the
  per-device rows are unchanged.
- The summary is a pure function `summarize_positions(rows, named)` in
  `vwlib.py` (Python 3.9, stdlib) so it is unit-testable with the
  exec-with-fake-vs pattern of `tests/test_drawing.py`.
- `vw_list_positions` docstring is corrected to the real keys
  (`positions`, `by_name`, `unassigned_device_count`,
  `device_positions_without_object`).

Tests: `summarize_positions` on rows with mixed types, two universes, an
unpatched row, a non-numeric channel, and a name without an object; natural
sort ("LX 2" before "LX 10").

## Out of scope

Channel renumbering, Lightwright, position objects' geometry, grouping the
`position_without_object` MVR warning per name.

## Verification

Unit: `uv run pytest tests/test_mvr.py tests/test_drawing.py -q`, lint on
`vwlib.py`. Live on the surveyed plot with MCP Listen open:
`vw_mvr_check` summary has no `gdtf_unlinked`, one `field_unused` warning,
`address_overlap: 2` still present; `vw_list_positions(include_devices=False)`
has 15 `by_name` entries, "K C" with 38 devices and universe 14 among its
universes.
