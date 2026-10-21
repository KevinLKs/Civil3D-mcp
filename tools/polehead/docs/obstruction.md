# Riser and obstruction details

Read when the RISER/OBSTRUCTION DETAIL box at the top left of a PDF page shows a fence or other obstruction. Risers are risers.md. Only fence obstructions are taught; walls, trees and structures: skip and note. When the sheet also has a riser detail, this detail goes south of it (easement circle top 100 below the riser detail's lowest text). The generator does not place these yet: build a small apply job after the main apply (query that frame's ELEV insert for its position).

## Template sample OBSTRUCTION DETAIL "A" (easement circle center 2248.5841, -1320.2260)

- Pole CIRCLE 392587 (MISC, r 12.604, center 2248.4846, -1319.5115).
- Pole name TEXT 392588 (top), 392589 (bottom), UTIL 4.8, centered on the circle.
- Fence outlines LWPOLYLINE 39258B (horizontal), 39258C (vertical), layer 0. Template hatch 39258A: never copy it (it keeps the sample's shape).
- Gap dims (aligned, MISC): 39258D (vertical gap), 392593 (horizontal gap).
- Fence labels (TEXT, Standard 4.8): 392599 `WOOD FENCE` (horizontal, baseline 1.64 above its fence), 39259A `FENCE` (rotated 90, reads upward, baseline 1.84 clear of its fence).
- Easement CIRCLE 3926A9 (layer 0, color 90, linetype EASEMENT, r 51.0456).
- Label under the circle (TEXT, color 90): 3926B3 `OBSTRUCTION`, 3926B4 `DETAIL "A"`, 3926B5 `L/N`.

## Placement

- Easement circle top 100 below the ELEV bottom (ELEV insertion y is its bottom), left edge on the notes left (Cx - 919.971). Easement center = (Cx - 919.971 + 51.0456, ELEV bottom - 151.0456); pole circle center = easement center + (-0.0995, +0.7145).
- Copy the whole sample set with one dx/dy so the pole circle lands there, then edit. The label stays under the circle; L/xx = the profile direction.
- Pole name split: 8 characters 4 / 4 (`1473` / `035E`), 7 = 4 / 3, 6 = 3 / 3, 9 = 5 / 4.

## Fences

- One per fence the PDF draws (a line beside the pole circle with `FENCE: 19"`).
- Each fence is its own CLOSED rectangle, 5 wide: one 50 long, the other 55 long, joined in a T like the sample (the 50 fence runs from the inside face of the 55 fence; the 55 fence runs 5 past the joint). Edit each copied outline to 4 vertices with `closed: true` in the same edit.
- Gap from the pole circle edge to the fence face = inches x 2.5 / 6.
- There is no vertical mirror or rotate: turn the sample by editing vertices. Example TD2533028 1473035E (south 14", east 19", pole center (Px, Py)): south fence top at Py - 12.604 - 5.833, x from Px - 24.479 to Px + 30.521; east fence inner face at Px + 12.604 + 7.917, rising 50 from the south fence top.

## Dims and labels

- One dim per fence, pole circle edge to fence face, text exactly as the PDF (`14"`, `19"`). Copy 39258D / 392593; edit xLine1, xLine2, dimLine, text, textPosition (text near its dim, clear of the fences).
- `FENCE` (or the PDF wording, such as WOOD FENCE) outside each fence: horizontal from 392599, vertical from 39259A. Copy each straight to its final spot (edit cannot move text).

## Hatch

- After the outlines are closed: one hatch over both fences (`hatches` job stage or `hatch` action): `boundaries` = both outlines, `pattern: "ANSI31"`, `scale: 30`, `angleDeg: 0`, `layer: "0"`. Every template obstruction detail uses exactly these settings, so pass them directly rather than `like`.

## Job shape

```json
{"version": 1,
 "copies": [{"id": "d", "handles": ["392587","3926A9","392588","392589","39258B","39258C","39258D","392593","3926B3","3926B4","3926B5"], "dx": 0, "dy": 0},
            {"id": "h", "handles": ["392599"], "dx": 0, "dy": 0},
            {"id": "v", "handles": ["39259A"], "dx": 0, "dy": 0}],
 "edits": [{"ref": "d:392588", "text": "1473"}, {"ref": "d:39258B", "vertices": [], "closed": true}],
 "hatches": [{"boundaries": [{"ref": "d:39258B"}, {"ref": "d:39258C"}], "pattern": "ANSI31", "scale": 30, "angleDeg": 0, "layer": "0"}]}
```
