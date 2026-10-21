# Riser details

Read when the RISER/OBSTRUCTION DETAIL box on a PDF page shows risers (small circles beside the pole circle). The generator places them from the pole's `riser` spec. Fences and other obstructions are obstruction.md.

## What the detail is

- The pole circle (r 12.604) with four tick lines 2.75 long (top, right, bottom, left), the pole name split in two lines inside it (same split as obstruction details: 8 characters 4 / 4, 7 = 4 / 3, 6 = 3 / 3, 9 = 5 / 4), `PROPOSED` and `L/xx` under it. No large green easement circle: that belongs to obstruction details only.
- Each riser is a small circle touching the outside of the pole circle, with a leader and a callout.
- Template example "A": pole circle 39253F, center (2157.6227, -872.5787); ticks 39253D, 39253E, 392540, 392541; name 39256C / 39256D (UTIL 4.8, left justified); PROPOSED 392548; L/N 392547.

## Riser sizes (circle radius)

| Size | Radius | Template circle |
| --- | --- | --- |
| 1" | 1.95 | 392544 |
| 2" | 2.925 | 392543 |
| 3" | 3.315 | 3925C4 |
| 4" | 3.6075 (between 3" and 5") | none: the plugin cannot set a radius, so it draws the 5" circle and reports it |
| 5" | 3.9 | 392550 |

- Riser called only by its conduit type: `SEC RISER` = 3", `PRIMARY RISER` = 5".

## Callouts

- Callout = size (when the planner gives one) and type: `3" PRI`, `1" COMM`, `2" CATV`, `5" COMM`, `EMPTY 3"`. Use `PRI`, never `PRIMARY`. Drop the word RISER when the planner only names the type: `SEC RISER @42'` becomes `SEC`, `PRIMARY RISER @25'` becomes `PRI`.
- NEVER heights in riser callouts (the planner's `@42'` is wrong). No width given: no width in the callout.
- Text: copy 39269A (layer TEXT, Standard 4.8, RIGHT justified, right edge 2117.5897, baseline -854.1364). Left side: right edge 2.8 short of the leader end. Right side: same copy plus `mirrorX` = leader end x (left justified 2.8 past the end). Baseline = leader end y - 3.0.
- Leader: copy 392542 and edit its vertices: arrow on the riser circle edge facing the elbow, elbow 18 out from the riser center (diagonal visible), end 4.29 further, horizontal, away from the pole.

## Position around the pole

- Riser center = pole center + (12.604 + r) at the angle the PDF draws it (spec `deg`, counterclockwise from 3 o'clock: 3:00 = 0, 12:00 = 90, 9:00 = 180, 6:00 = 270 or -90). Read it from a -r 300 crop; the PDF pole is drawn squashed, so normalize by its two radii.
- Edge touching the pole circle always. A riser drawn partly inside the pole is a planner error: keep its clock position, edge touching (TD2587599 1879680E: drawn overlapping at about 8:30, drafted touching at 195 deg).
- Callout on the side the riser is on. Leader direction (spec `lead`, degrees) defaults to up and out (20 deg) for a riser at or above about 4 o'clock, down and out (-25 deg) below it, mirrored on the left; set `lead` when that would cross PROPOSED or another callout.

## Guards on a riser

- U-GUARD: ARC 3926EA (r 1.95, centered on the pole circle edge, opening toward the pole) at about 50 deg on template pole B (2342.6413, -872.5787). The plugin cannot rotate an arc: it is drawn at 50 deg, or mirrored to 130 deg, and any other angle is reported for a hand fix.
- UNISTRUT: open LWPOLYLINE 39257A with a SOLID hatch 392579 (template pole 2153.0721, -989.5914, drawn at about 70 deg). The generator rotates the vertices to `deg`, closes the polyline and hatches it like 392579.
- KICKBLOCK: four LINEs 392566 to 392569 (template pole 2343.3995, -975.1775, below the pole at -90 deg), rotated to `deg`. Never seen on a job yet.
- Guard callouts are not taught yet: draft the symbol and note it.

## Placement

- Same spot as an obstruction detail: pole center (notes left + 50.9461, ELEV bottom - 150.3311). The ELEV insertion y is its bottom.
- A sheet with both a riser detail and a separate obstruction detail: riser detail first, the obstruction detail further south (set its easement circle top 100 below the lowest riser detail text), and keep stacking south so nothing overlaps. `drop` in the riser spec pushes the riser detail down when it has to go below something else.

## Spec

```json
"riser": {"L": "L/N", "items": [{"c": "SEC", "deg": -10}, {"c": "2\\" CATV", "size": 2, "deg": 200, "lead": 160}],
          "guards": [{"t": "unistrut", "deg": 70}]}
```

- `c` callout as drafted, `size` 1 to 5 (inches; default from the type: SEC 3, PRI 5, else 3), `deg` position, `lead` optional leader angle. `L` defaults to the first profile's L/xx.
