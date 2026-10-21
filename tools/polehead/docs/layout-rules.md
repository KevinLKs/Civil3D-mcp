# Layout rules (rows, callouts, dims, pole label, frames)

The generator implements all of this. Read only when hand-placing or hand-fixing pole detail pieces, or when a qc.py failure needs the rule behind it.

## Sheet frames

- Frame: closed LWPOLYLINE on NO-PLOT, 2088.93 x 1404 (a 10 vertex outline shares it). C = (left + 1044.4648, bottom + 702).
- Fresh template: 8 frames, 4 per row, columns 2790 apart, rows 2070 apart. Row center y -3575.8251, -5645.8251 (next -7715.8251, ...); column x -543.912, 2246.088, 5036.088, 7826.088. Fill left to right, top row first.
- Frame 8 and up are added by copying the row 2 frame set 2070 lower per row (handles in template-pieces.md); pole name edited, sheet number = frame + 2.
- Pole name TEXT (Defpoints, color 4, Match, height 125) reads `POLE#` when empty.
- G = Cy. N (left) slot P = Cx - 300, E (right) slot P = Cx + 300.

## Heights (rows)

- Equipment y = G + the height scale position of its whole foot (see template-pieces.md).
- Clusters: sort by true height. The lowest takes its own position; each next takes the next dim up (8 higher) when its own position is used or closer than 8 to the one below. Never below its own position. Example: 16'2" G + 54, 16'5" G + 62, 17'5" G + 70, 17'8" G + 78, 28'6" back on its own 28'.
- True height goes in the dim text override.

## Callouts

- Column col = 5.75 past the farthest equipment on the callout side: crossarm 35 -> 40.75, dead end arrow 30 -> 35.75, X COND 25 -> 30.75 (minimum). Right: left justified at P + col. Left: right justified at P - col.
- Baseline = row y + 1.6; a second line at the same row 8 lower.
- FH/LA on the primary side box: SA and CUTOUT on the box, FH and LA lines stacked ABOVE the conductor callout (3 lines, 1 dim).
- Two items at one height: one row, one line each, one dim.

## Height dimensions

- Copy 2E34A7; edit xLine1, xLine2 = (P, G), dimLine = (x, G), text, textPosition, `layer: "DIMENSION"`, `colorIndex: 256`, always in one edit.
- xLine1 at the equipment end on the dim side: crossarm P +/- 35, dead end arrow tip P +/- 30, X COND tip P +/- 25, box or XFMR edge, FH/LA cutout edge P + 5.43, PH group end (6.99 or 3.89), guard arm line end P +/- 17.5, span guy end P +/- 33.76 when it points to the dim side, dot at P. Pointing away, or box on the far side: attach at P.
- Dims on the callout side, lowest closest, 12 apart.
- Stack x0 = max over i of (farthest text extent at or below dim i + gap - 12i). Gap 1.92; 4.4 when the binding text sits beside that dim's arrowhead.
- Labels are horizontal, about 5.2 tall and 3.5 x chars - 2.7 wide. Lowest label at its midpoint (G + top)/2; each next starts at its midpoint and steps UP 8 until it clears all placed labels (0.5 sideways, 1 vertical) and all callouts. Never above its dim's top. Always set textPosition explicitly.

## Pole label

- PROPOSED / L/xx / pole number at G - 11.08, - 19.08, - 27.08, center justified.
- No guys: centered on P. Guys left: centered at P + 25.45. Guys right: centered at P - 25.41.

## Side boxes and pins (placement detail)

- Side box: edge facing the pole ON the pole line (left P - 5 to P, right P to P + 5); centered only when the PDF pole line runs through it (shift box and pin by -2.5). Pin centered on the box; both X CONDs start at the pin top. Pole line top at the box row.
- Lone SIDE XARM centered on its row so the wall middle on the dim side is the dim point.
- XFMR: pole through the box = centered (insertion x = P); beside it = edge on the pole line (P -/+ 5.21).
- Guard arm line centered on the pole (P - 17.5 to P + 17.5); comm dots hang under it at the PDF offsets (e.g. 4.5, 10, 15.5), none on the pole.
