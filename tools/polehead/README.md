# Pole head generator

Builds pole head detail sheets in the AUD OH template from a job spec, as one
`civil3d_entity` `apply` job. Copies and the edits that fill them are tied
together with refs (`"g12:37BBC7"` = the copy of `37BBC7` made by copy `g12`),
so a whole job is one approval and one tool call.

```
python polehead.py examples/TD2536120.json -o job_TD2536120.json
python polehead.py spec.json --poles 1414703E,4904169E -o job_part.json
python station_builder.py "<TD> - STATION BUILDER.xlsx" 1414703E 4904169E > sheets.json
```

Then put the job file in the job folder on the drafting machine and run:

```
civil3d_request_approval  toolName=civil3d_entity action=apply parameters={"action":"apply","jobFile":"C:\\...\\job_TD2536120.json"}
civil3d_entity            action=apply jobFile=<same path> approvalToken=<token>
```

The old-to-new handle map lands next to the job as `job_TD2536120.result.json`
for the measure-and-fix pass.

## Spec format

```json
{
  "job": "TD2536120",
  "poles": [{
    "frame": 0,
    "pole": "1414703E",
    "profiles": [{
      "L": "L/NW", "side": "R", "gside": 1,
      "items": [{"t": "pri", "h": "41'6\"", "c": ["IN: 4/C 336ATW 16KV"], "k": "L"}],
      "anchors": [{"L": "13'", "c": "IN: 1 1/4\" 3EYE"}],
      "guys": [{"h": "37'", "an": 0, "c": "IN: 3/8\" DG @ 37'"}]
    }],
    "crew": ["-..."], "notes": ["-..."], "gps": ["34°11'32.19\"", "118°.."], "elev": "821",
    "tlm": {"ex": ["50", "31.57", "8", "63"], "pr": ["", "", "", ""], "cz": "5",
            "pc": "HAMPSHIRE 16KV", "vd": "", "flicker": "", "addr": [["1065 BURTONWOOD AVE", "322010-238159"]]}
  }]
}
```

- `frame` 0 to 11, left to right, top row first. Two profiles are drawn at Cx -/+ 300 (PDF left, then right). One profile
  goes in the slot the PDF draws it in: N slot (left) Cx - 300, E slot (right) Cx + 300, 600 apart. Set `slot: "R"` or `"L"`;
  without it an `L/E` profile goes right and anything else left.
- `side`: callout and dim side, `R` or `L`. Callout column: 5.75 past the farthest equipment on the callout side (crossarm 35 -> 40.75, dead end 30 -> 35.75, X COND 25 -> 30.75 minimum). `gside`: guys and anchors side, `1` right, `-1` left (needed when there are anchors).
- Item `h`: true height as written. No height from the planner: `h` = where the PDF draws it (for the row) and
  `label: "_'"` so the dim reads `_'`. `c`: callout lines at the row. `above`: extra lines stacked above the row's own line (FH/LA on a primary box).
- Item types (`t`) and `k`:
  - `pri` side arm box with pin and X CONDs. `k`: `R`, `L` or `C` box position, `B` a box on each side. `fhla: true` puts the SA and CUTOUT on that box.
  - `fhla` side view FH/LA box. `k: "R"` puts the box right of the pole (default left).
  - `xfmr` side transformer, `k` `L`/`C`/`R`.
  - `xr`, `xl`, `xb` X COND right, left, both. COMM and CATV lines are always X CONDs; add `dot: true` to keep the SEC-MISC dot under them.
  - `dot` SEC-MISC dot alone (a bare dot with no line).
  - `sg` span guy half, `k` `R` or `L` (never mirrored or edited). `share: 1` puts it on the row of the other item at that whole foot.
  - `arm2`, `arm4`, `armc` crossarm with 2 pins, 4 pins or 4 conductor circles. `fhlaf` front view FH/LA arm. `arm2fl` 2/C arm with FH and LA.
  - `end: "R"` / `"L"` on any crossarm: the pole sits at the arm's right / left end (offset arm), not its center.
  - `arm` crossarm with any mix: `dots` puts SEC-MISC dots on the arm at those slots (comm/CATV seen end on); `pins` and `circ` are slot indexes 0 to 3, left to right (-29.76, -12.13, +12.13, +29.76).
  - `slant: {"<slot>": "L" | "R"}` on `arm`, `arm2` or `arm4`: that slot's pin is drawn slanted (leaning left 2E3477
    or right 2E3472, already rotated in the template) with its base on the slot, 0.2 above the arm line. The upright pin
    of that slot is left out, so nothing has to be erased. Example: `"slant": {"3": "R"}`.
  - `de1` side view dead end one way (`k: "L"` points left), `de2` both ways. `nopins: true` leaves the pins off;
    `fhla: "L"` / `"R"` puts the SA and CUTOUT on the dead end boxes (`"R"` = cutout left, SA right).
  - `box: "R"` / `"L"` on any item adds a lone SIDE XARM (guard arm) beside the pole, hanging just below that row's
    line (box top on the line, insertion 2.5 below the row).
  - `omni: true` with `box`: INV OMNI CLOSED with its insertion 5 beside the SIDE XARM insertion, on the box's side (HZ INV OMNI SW).
  - `none`: no symbol of its own, used with `box` (a guard arm or comm box with its callout).
  - `riser` TOR: riser box (2A4127) from the ground to its row, `k` `C` centered on the pole (pole runs through it), `R`/`L` beside it. Callout `TOR`.
  - `qp` QUEENS POST: a line at its row from the pole out to its anchor's distance (`an`, or its own `L`). Guys with
    `via: <qp index>` run from the pole to the QP end; one more guy runs from the QP end down to the anchor.
    Callout text `QUEENS POST`.
  - `o`: tie-break order for two items at the same height.
- `anchors[].L` lead as written; `guys[].an` index into `anchors` as listed.

## Rules built in

Height scale and cluster step-up, dim tight fit (1.92 gap, 4.4 beside an
arrowhead), horizontal dim labels stepped up 8 until clear of other labels and
callout text, X CONDs starting at the pin, span guy halves 2E3466 / 2E3954,
anchor scale from the shortest lead, DG stacking and lift, pole label by guy
side, CREW/NOTE/GPS/ELEV stack, ELEV as a bare number, TLM street-only
addresses and ADDRESS LIST visibility, pole names and row 3 sheet numbers.

- Pole `calcs`: `[{"hdr": "%%UUNGUYED DE CALC (7733E)", "rows": [["left", "= right"], ...]}]`, drawn from the NOTE
  stash pieces, first box top at Cy - 100, each next 10 below. In combined
  calcs the line under each lettered load (`A. ...`, `B. ...`) is indented 9.923. `tlm.notes`: TLM NOTE box under the visible table.
- Pole `rspans`: `[[from, to, ruling span, final sag]]` as written, RULING SPAN boxes (template example 3948B8 at
  1541.4998, -817.1629) centered on Cx under the calcs (Cy - 100 when there is no calc), each 10 below the last.
- Guys attach at the row of the item with the exact same height first (DG @ 22'6" at the 22'6" COMM row).
- EX-LOAD and PR-LOAD are sent without `%` (the block prints its own).
- More than 10 TLM addresses: the block stays at ADDRESS LIST 10 and rows 11 to 20 are burst rows (row 12 pieces
  3975AC, 3975AD, 3975E9, 3975F7 copied down 11.7326 per row from the LIST 10 bottom, insertion y - 129.0591).
  The TLM NOTE box goes under the last row. Over 20: first 20 filled and reported.
  The handles differ per drawing: query `TLM_EXTRA_WINDOW` (x 1850 to 2003, y -792.5 to -779.5, layer MISC) and put
  them in the spec as `"tlm_extra": [address text, meter text, box polyline, divider line]`; `pick_tlm_extra(entities)`
  picks them out of the query result (it also returns rows 11 and 13).

## Not generated

Calc boxes are estimated: re-fit and re-center them after measuring.
Note box widths and DG leader ends use text width estimates: measure them after
the job and fix them in one edit batch.
