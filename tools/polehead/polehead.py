#!/usr/bin/env python3
"""Pole head detail generator for the AUD OH template.

Turns a per-job spec (JSON) into one civil3d_entity "apply" job: every copy,
plus edits that reference the new copies as "<copyId>:<sourceHandle>", so a
whole job is drawn with one approval and one tool call.

    python polehead.py job_spec.json -o apply_job.json

Spec format: see README.md and examples/. All template handles below are the
same in every fresh copy of the AUD OH template.
"""
from __future__ import annotations

import argparse
import copy as _copy
import json
import re
import sys

# ------------------------------------------------------------------ frames
COLS = [-543.912, 2246.088, 5036.088, 7826.088]
ROW0, ROW_STEP = -3575.8251, 2070
NAME_HANDLES = ['386B22', '386B24', '386B25', '386B26', '386B27', '386B28', '386B29', '386B2A']
# The template only has frames 0 to 7 (two rows, sheets 2 to 9). Frame 8 and up: copy the row 2 frame set of that
# column (both NO-PLOT outlines, the Defpoints pole name and sheet number) 2070 lower per row, then edit the name
# and set the sheet number to frame + 2.
ROW2_FRAME_SET = [('2A3C5C', '2A3D50', '386B27', '2A2A1A'), ('2A3C5D', '2A3D4D', '386B28', '2A2A1B'),
                  ('2A3C5E', '2A3D4E', '386B29', '2A2A1C'), ('2A3C5F', '2A3D4F', '386B2A', '2A2A1E')]


def frame(i):
    if i < 0:
        raise ValueError('frame %d: frames start at 0' % i)
    return COLS[i % 4], ROW0 - ROW_STEP * (i // 4)


# ------------------------------------------------------------------ scales
def pos(h):
    """Height scale position above ground for a whole-foot height."""
    h = int(h)
    if h <= 9:
        return 38
    if h <= 13:
        return 46
    if h <= 17:
        return 54
    return 8 * h - 82


def anchor_base(n):
    if n <= 7:
        return 34
    if n <= 11:
        return 38
    if n <= 15:
        return 42
    if n <= 19:
        return 46
    return 50 + 4 * (n - 20)


def ft(s):
    """24'6" -> 24.5"""
    s = s.replace('"', '').replace(' ', '')
    f, _, i = s.partition("'")
    return int(f) + (int(i) / 12 if i.strip() else 0)


def callout_w(t):      # STA-TEXT 4.8, conservative width for the dim tight fit
    return len(t) * 3.7


def label_w(t):        # horizontal dim label width
    return 3.5 * len(t) - 2.7


LABEL_H = 5.2
LABEL_STEP = 8.27     # vertical offset between neighbouring labels that would collide (about 14.5 corner to corner)
LABEL_GAP = 2.0       # clear space between neighbouring dim labels (0.5 let 23' and 23'6" touch)
TEXT_H = 4.8


def note_w(t):         # SIMPLEX 4.8
    return len(t) * 3.97


# ------------------------------------------------------------------ template pieces
SRC = {
    'pri':    dict(h=['2E3492', '2E348D', '2E3423', '2E3422'], px=4697.5843, py=-1396.6283),
    'fhla':   dict(h=['2E3870', '2E3806', '2E3872'], px=5264.5156, py=-1329.3281),
    'fhla_on_box': dict(h=['2E3870', '2E3872'], px=5264.5156, py=-1329.3281),  # SA + CUTOUT, no box
    'xfmr':   dict(h=['2E3425'], px=4697.5843, py=-1973.8214),
    'xr':     dict(h=['2E3BD7'], px=4402.66, py=-1420.6994),
    'xl':     dict(h=['2E3BD8'], px=4402.66, py=-1420.6994),
    'dot':    dict(h=['2A4FAD'], px=3823.6518, py=-1005.5445),
    'arm':    dict(h=['2E3400'], px=4610.268, py=-1446.6283),
    'pins2':  dict(h=['2E3401', '2E3403'], px=4610.268, py=-1446.6283),
    'pins4':  dict(h=['2E3401', '2E3402', '2E3404', '2E3403'], px=4610.268, py=-1446.6283),
    'circ4':  dict(h=['2E3405', '2E3408', '2E3407', '2E3406'], px=4610.268, py=-1446.6283),
    'fhlaf':  dict(h=['2E380B', '2E382B', '2E382C', '2E3830', '2E3832'], px=5177.1994, py=-1341.8281),
    'fhlaf_sa': dict(h=['2E380B', '2E382D', '2E382E', '2E382F', '2E3831'], px=5177.1994, py=-1341.8281),  # SA at the ends, CUTOUTs inner
    'arm2fl': dict(h=['2E380C', '2E383D', '2E383E', '2E383F', '2E3840', '2E3842', '2E3841'], px=5177.1994, py=-1471.8281),
    'de1':    dict(h=['2E3415', '2E3912', '2E3419', '2E3916', '2E3913', '2E3914', '2E3915', '2E3918'], px=4697.5843, py=-1446.6283),
    'de2x':   dict(h=['2E3490', '2E3418', '2E3417', '2E3416'], px=4697.5843, py=-1446.6283),
    'sg_l':   dict(h=['2E3466'], px=4371.2932, py=-1992.9099),   # span guy half running LEFT
    'sg_r':   dict(h=['2E3954'], px=4371.2932, py=-1992.9099),   # span guy half running RIGHT
    'riser':  dict(h=['2A4127'], px=3137.8555, py=-643.5052),   # riser box, 3.4169 wide, ground to TOR
    'sbox':   dict(h=['2E3912'], px=4697.5843, py=-1446.6283),   # lone SIDE XARM, box pole to pole + 5
}
ARM_PINS = ['2E3401', '2E3402', '2E3404', '2E3403']      # -29.76, -12.13, +12.13, +29.76
ARM_CIRC = ['2E3405', '2E3408', '2E3407', '2E3406']
ARM_SLOT_X = [-29.7551, -12.128, 12.128, 29.7551]   # pin / circle slot offsets from the arm center
DE1_PINS = ('2E3419', '2E3916')
# slanted VERT P&I, already rotated in the template (never rotate): insertion = pin base, 0.2 above its arm line
SLANT_PIN = {'L': ('2E3477', 4529.5100, -1471.6283),    # leaning left, 25 deg (mirrored)
             'R': ('2E3472', 4525.7361, -1496.6283)}    # leaning right, 335 deg
SG_LEN = 33.76
RCS = ('2E3432', 4784.9005, -2011.4173)            # RCS control box rectangle: left edge, center y
RCS_W = 6.5467
GALINE = ('2E3922', 4767.4005, -2151.7964)        # 35 long guard arm line: start (left end)
GALDOT = ('2A500C', 3805.6404, -386.763)          # SEC-MISC hanging under a guard arm line (insertion x, LINE y)
# PH & LA side view (template examples): SIDE XARM + SURGE ARRESTER + POTHEAD, (handles, side pole x, row y,
# extent right of the pole, extent left of the pole). 'L' = left leaning PH, 'R' = right leaning PH.
PH = {'L': (['2E3866', '2E386B', '2E386D'], 5333.5588, -1291.8281, 6.9924, 3.8930),
      'R': (['2E3811', '2E386C', '2E386E'], 5264.5156, -1291.6289, 3.8930, 6.9924)}
ANC_LEADER_MIN = 15.1                               # shorter and the leader arrowhead does not draw
RISER_W = 3.4169
COL_GAP = 5.75                                    # callout column clearance past the farthest equipment
COL_MIN = 30.75                                   # never closer than an X COND tip (25) + gap
CALLOUT = ('37BBC7', 4558.3319, -1320.0283)      # right justified: right edge, baseline
HDIM = ('2E34A7', 3329.4667, -1946.2563)         # pole x, ground
LDIM = ('38F31B', 3415.3369, -1946.2563)
LINE = ('2A42F4', 2772.8085, -774.2588)
GUY = ('2E3B8F', 4303.0156, -1707.4371)
ARC = ('38F2F8', 3449.3367, -1944.2563)          # center
LEADER = ('2E3390', 4040.0, -1970.0)
DGTXT = ('2A4B31', 5377.2848, -1033.4725)        # right edge, baseline
ANCTXT = ('2A4B30', 5307.1477, -1087.0188)       # left edge, baseline
LBL = [('2A4BC2', 4292.2155, -377.0894), ('2A4BC3', 4292.2155, -385.0894), ('2A4BC4', 4292.2155, -393.0894)]

STASH_X = 2379.0399
STASH_TEXT_X = 2381.9156
CREW = dict(box='391E85', hdr=('391E97', -129.6132), line=('391E98', -137.6402), title='CREW NOTE:')
NOTE = dict(box='391E86', hdr=('391EA3', -162.9075), line=('391E99', -170.9346), title='NOTE:')
GPS = ('391E87', -263.517, 43.23)
ELEV = ('391EA0', -283.4196, 14.90)
TLM = ('392289', 2350.1087, -540.1907)
CALC_INDENT = 9.923
TLM_W = 144.5734
TLM_L10_BOTTOM = 129.0591          # insertion y minus the bottom of the LIST 10 table
TLM_ROW = 11.7326
# Burst rows 11 to 20 (loose text and lines under a LIST 10 block). Row 12 is the copy source for every row.
TLM_EXTRA = dict(h=['3975AC', '3975AD', '3975E9', '3975F7'], left=1854.666, top=-779.9231)
TLM_MAX = 20
# Query this window (layers MISC) to find the row 12 pieces: TEXT starting ADDRESS (address), TEXT starting METER
# (meter, center justified on x 1971.588), LWPOLYLINE (open box), LINE (divider). Pass them as spec 'tlm_extra'.
TLM_EXTRA_WINDOW = dict(minX=1850, minY=-792.5, maxX=2003, maxY=-779.5)
# RULING SPAN box (template example at 1541.4998, -817.1629, same handles in every template copy):
# box, underlined header, '-FROM a TO b', ' RULING SPAN = x', ' FINAL SAG = y' (layer DECAL, SIMPLEX 4.8)
RSPAN = dict(box='3948B8', left=1538.624, top=-807.5353, x=1541.4998,
             lines=[('3948B9', -815.5629), ('3948BA', -825.19), ('3948BB', -833.217), ('3948BC', -841.2441)],
             bottom=-844.8897)
TLMNOTE = dict(box='392285', hdr=('392287', -677.2306), line=('392288', -689.5668), x=2354.3102)


def r4(v):
    return round(v, 4)


def pt(x, y):
    return dict(x=r4(x), y=r4(y))


def color_for(text):
    return 90 if text.startswith(('IN', 'RM')) else 256


class Job:
    """Collects copies and edits; edits refer to copies by (op key, source handle)."""

    def __init__(self):
        self.ops = []          # (key, op)
        self.edits = []        # (key or None, handle, edit)
        self.report = []
        self.ctx = {}          # what is being drawn now (pole, part, ...); stored per copy for qc.py
        self.meta = {}         # op key -> ctx at copy time
        self.keymap = {}       # op key -> group index, set by to_apply_job

    def tag(self, **kw):
        self.ctx = dict(self.ctx, **kw)

    def cp(self, handles, dx, dy, mirror=None, edit=None):
        key = len(self.ops)
        op = dict(handles=list(handles), dx=r4(dx), dy=r4(dy))
        if mirror is not None:
            op['mirrorX'] = r4(mirror)
        self.ops.append((key, op))
        self.meta[key] = dict(self.ctx)
        for i, e in enumerate(edit or []):
            if e:
                self.edits.append((key, handles[i], e))
        return key

    def edit_existing(self, handle, edit):
        self.edits.append((None, handle, edit))

    def to_apply_job(self):
        """Group copies sharing dx/dy/mirror (no handle overlap) and emit refs."""
        groups, keymap = [], {}
        for key, op in self.ops:
            sig = (op['dx'], op['dy'], op.get('mirrorX'))
            for gi, g in enumerate(groups):
                if g['sig'] == sig and not (g['set'] & set(op['handles'])):
                    g['op']['handles'] += op['handles']
                    g['set'] |= set(op['handles'])
                    keymap[key] = gi
                    break
            else:
                groups.append(dict(sig=sig, op=dict(op, handles=list(op['handles'])), set=set(op['handles'])))
                keymap[key] = len(groups) - 1
        self.keymap = keymap
        copies = [dict(id='g%d' % gi, **g['op']) for gi, g in enumerate(groups)]
        edits = []
        for key, handle, e in self.edits:
            x = dict(handle=handle) if key is None else dict(ref='g%d:%s' % (keymap[key], handle))
            x.update(e)
            edits.append(x)
        return dict(version=1, copies=copies, edits=edits, erase=[])


# ------------------------------------------------------------------ pole detail
def assign_rows(items):
    """Cluster rule: lowest keeps its scale position, each next steps up 8 when crowded."""
    items.sort(key=lambda it: (ft(it['h']), it.get('o', 0)))
    used = []
    for it in items:
        if it.get('share'):
            continue
        y = pos(ft(it['h']))
        while any(abs(y - u) < 8 for u in used):
            y += 8
        it['row'] = y
        used.append(y)
    for it in items:
        if it.get('share'):
            it['row'] = next(o['row'] for o in items
                             if o is not it and not o.get('share') and int(ft(o['h'])) == int(ft(it['h'])))


CUTOUT_SIDE = ('2E3872', 5267.7315)                # side view CUTOUT (S), insertion = center, P + 3.2159 in the Builder


def cp_fhla(J, P, r, handles, cutout_left, left_edge=None):
    """Side view SA (+ box) and CUTOUT. The S is NEVER mirrored: with the cutout on the left of the pole the
    other pieces are mirrored and the S is copied unmirrored. On the left it sits 1.1 clear of the leftmost box
    (left_edge, the pole when no box is on that side): center = left_edge - 3.3132."""
    src = SRC['fhla']
    rest = [h for h in handles if h != CUTOUT_SIDE[0]]
    J.cp(rest, P - src['px'], r - src['py'], mirror=P if cutout_left else None)
    cx = (P if left_edge is None else left_edge) - 3.3132 if cutout_left else P + 3.2159
    J.cp([CUTOUT_SIDE[0]], cx - CUTOUT_SIDE[1], r - src['py'])


def place_item(J, P, r, it, sc):
    """Copies one equipment item at row y r; returns attach offset on the dim side."""
    t, k = it['t'], it.get('k', 'C')
    a = 0.0
    if t == 'pri':
        src = SRC['pri']
        dy = r - src['py']
        if k == 'B':                                       # a box on each side, X CONDs at the pole
            J.cp(src['h'][2:], P - src['px'], dy)
            J.cp(src['h'][2:], P - src['px'], dy, mirror=P)
        else:
            J.cp(src['h'][2:], P - src['px'] + (-2.5 if k == 'C' else 0), dy, mirror=P if k == 'L' else None)
        pinx = P + {'R': 2.5, 'L': -2.5, 'C': 0, 'B': 0}[k]
        J.cp(src['h'][:2], pinx - src['px'], dy)          # X CONDs start at the pin
        box = {'R': (0, 5), 'L': (-5, 0), 'C': (-2.5, 2.5), 'B': (-5, 5)}[k]
        a = max(sc * box[0], sc * box[1], 0)
        if it.get('fhla'):
            # FH/LA drawn on the primary box: SA + CUTOUT on that box, no box of their own.
            box_right = k == 'R'
            cp_fhla(J, P, r, SRC['fhla_on_box']['h'], box_right)
            right, left = (7.0, 5.43) if box_right else (5.43, 7.0)
            a = max(a, right if sc > 0 else left)
    elif t == 'fhla':
        box_right = k == 'R'                               # box left of the pole unless 'R'
        cp_fhla(J, P, r, SRC['fhla']['h'], box_right)
        right, left = (7.0, 5.43) if box_right else (5.43, 7.0)
        a = right if sc > 0 else left
    elif t == 'xfmr':
        src = SRC['xfmr']
        off = {'C': 0, 'L': -5.21, 'R': 5.21}[k]
        J.cp(src['h'], P + off - src['px'], r - src['py'])
        a = max(sc * (off - 5.21), sc * (off + 5.21), 0)
    elif t in ('xr', 'xl', 'xb'):
        for d in {'xr': ['xr'], 'xl': ['xl'], 'xb': ['xr', 'xl']}[t]:
            src = SRC[d]
            J.cp(src['h'], P - src['px'], r - src['py'])
        dirs = {'xr': [1], 'xl': [-1], 'xb': [1, -1]}[t]
        a = 25 if sc in dirs else 0
    elif t == 'rcs':
        # RCS CONTROL BOX: the oddly shaped template rectangle 2E3432 (6.5467 x 8.746), centered on its row, edge on
        # the pole line on the side the PDF draws it (k 'L' or 'R'). Plain polyline, so mirroring would also be fine.
        x0 = P - RCS_W if k == 'L' else P
        J.cp([RCS[0]], x0 - RCS[1], r - RCS[2])
        a = RCS_W if (1 if k == 'R' else -1) == sc else 0
    elif t == 'gal':
        # guard arm drawn as a line through the pole in the PDF: 35 long LINE 2E3922, centered on the pole
        J.cp([GALINE[0]], (P - 17.5) - GALINE[1], r - GALINE[2])
        a = 17.5
        for ox in it.get('dots', []):                  # SEC-MISC dots hanging under the line (offsets from the pole)
            J.cp([GALDOT[0]], (P + ox) - GALDOT[1], r - GALDOT[2])
    elif t == 'ph':
        # PH & LA: copy the template example group as is, k 'L' (left leaning PH) or 'R' (right leaning PH)
        hs, px, py, ext_r, ext_l = PH[k]
        J.cp(hs, P - px, r - py)
        a = ext_r if sc > 0 else ext_l
    elif t in ('dot', 'none'):
        pass                                               # dot: handled below; none: only a 'box' (guard arm, comm box)
    elif t == 'riser':
        # TOR: riser box from the ground up to its row. k 'C' centered on the pole (pole runs through it in the PDF),
        # 'R' / 'L' beside the pole touching it.
        x0 = {'C': -RISER_W / 2, 'R': 0, 'L': -RISER_W}[k]
        src = SRC['riser']
        G = it['G']
        J.cp(src['h'], P - src['px'], G - src['py'], edit=[dict(vertices=[
            pt(P + x0, r), pt(P + x0 + RISER_W, r), pt(P + x0 + RISER_W, G), pt(P + x0, G)])])
        a = max(sc * x0, sc * (x0 + RISER_W), 0)
    elif t == 'qp':
        # QUEENS POST: a line from the pole out to the anchor distance at its row; guys bend at its end
        qx = it['qx']
        J.cp([LINE[0]], P - LINE[1], r - LINE[2], edit=[dict(start=pt(P, r), end=pt(qx, r))])
        a = abs(qx - P) if (qx - P) * sc > 0 else 0
    elif t == 'sg':
        d = 1 if k == 'R' else -1
        src = SRC['sg_r' if d > 0 else 'sg_l']
        J.cp(src['h'], P - src['px'], r - src['py'])       # never mirrored, never edited
        a = SG_LEN if d == sc else 0
    elif t == 'armc' and it.get('slant'):
        raise ValueError('armc has conductor circles, no pins to slant; use arm with pins and slant')
    elif t in ('arm2', 'arm4') and it.get('slant'):
        # a slanted pin replaces its upright one: draw it as the generic arm with those pin slots
        it = dict(it, t='arm', pins={'arm2': [0, 3], 'arm4': [0, 1, 2, 3]}[t])
        return place_item(J, P, r, it, sc)
    elif t in ('arm2', 'arm4', 'armc'):
        # end: 'R' = pole at the arm's right end (arm runs left of the pole), 'L' = pole at its left end
        sh = {'R': -35, 'L': 35}.get(it.get('end'), 0)
        src = SRC['arm']
        J.cp(src['h'], P + sh - src['px'], r - src['py'])
        src = SRC[{'arm2': 'pins2', 'arm4': 'pins4', 'armc': 'circ4'}[t]]
        J.cp(src['h'], P + sh - src['px'], r - src['py'])
        a = max(sc * (sh - 35), sc * (sh + 35), 0)
    elif t == 'arm':
        # crossarm with any mix of pins and conductor circles: pins/circ = slot indexes 0..3 (left to right)
        sh = {'R': -35, 'L': 35}.get(it.get('end'), 0)
        src = SRC['arm']
        slant = {int(i): d for i, d in (it.get('slant') or {}).items()}
        hs = src['h'] + [ARM_PINS[i] for i in it.get('pins', []) if i not in slant] + \
            [ARM_CIRC[i] for i in it.get('circ', [])]
        J.cp(hs, P + sh - src['px'], r - src['py'])
        for i, d in sorted(slant.items()):             # slanted VERT P&I: base on the slot, arm line + 0.2
            h, ix, iy = SLANT_PIN[d]
            J.cp([h], P + sh + ARM_SLOT_X[i] - ix, (r + 0.2) - iy)
        for i in it.get('dots', []):                   # SEC-MISC dots on the arm (comm / CATV seen end on)
            d = SRC['dot']
            J.cp(d['h'], P + sh + ARM_SLOT_X[i] - d['px'], r - d['py'])
        a = max(sc * (sh - 35), sc * (sh + 35), 0)
    elif t in ('fhlaf', 'arm2fl'):
        if it.get('slant'):
            raise ValueError('%s: slant is only supported on arm, arm2 and arm4' % t)
        src = SRC['fhlaf_sa' if t == 'fhlaf' and it.get('ends') == 'sa' else t]
        J.cp(src['h'], P - src['px'], r - src['py'])
        a = 35
    elif t in ('de1', 'de2'):
        src = SRC['de1']
        hs = src['h'] + (SRC['de2x']['h'] if t == 'de2' else [])
        if it.get('nopins'):
            hs = [h for h in hs if h not in DE1_PINS]
        J.cp(hs, P - src['px'], r - src['py'], mirror=P if k == 'L' else None)
        dirs = [1, -1] if t == 'de2' else ([-1] if k == 'L' else [1])
        a = 30 if sc in dirs else 5
        if it.get('top'):
            # X COND both ways from the pin tops as well (a run over the dead end): right from the right pin
            # (P + 2.5), left from the left pin (P - 2.5), at pin insertion + 4.4648 like the primary box group
            yt = r + 2.5 + 4.4648
            J.cp(['2E348D'], (P + 2.5) - 4697.5843, yt - (-1389.6635))
            J.cp(['2E3492'], (P - 2.5) - 4697.5843, yt - (-1389.6635))
        if it.get('fhla'):
            # SA + CUTOUT on the dead end boxes; fhla 'R' = cutout left, SA right (mirrored)
            cp_fhla(J, P, r, SRC['fhla_on_box']['h'], it['fhla'] == 'R', left_edge=P - 5)   # dead end boxes P - 5 to P + 5
    else:
        raise ValueError('unknown item type %r' % t)
    if it.get('box'):
        # lone SIDE XARM (guard arm): CENTERED on its row, so the middle of the wall on the dim side sits on the dim
        # point. With an omni switch the box hangs just below the row line (box top on the line) and the omni sits
        # at the box center height (template example: omni 4690.0843 and box 4695.0843, both at -1596.6283).
        src = SRC['sbox']
        by = r - 2.5 if it.get('omni') else r
        J.cp(src['h'], P - src['px'], by - src['py'], mirror=P if it['box'] == 'L' else None)
        if (1 if it['box'] == 'R' else -1) == sc:
            a = max(a, 5)
        if it.get('omni'):
            # INV OMNI CLOSED (2E344E, template orientation): insertion exactly 5 beside the SIDE XARM insertion
            # (box center P +/- 2.5, row y), on the side the box is on
            d = 1 if it['box'] == 'R' else -1
            J.cp(['2E344E'], (P + d * 7.5) - 4580.5129, by - (-1596.6283))
    if t == 'dot' or it.get('dot'):
        src = SRC['dot']
        J.cp(src['h'], P - src['px'], r - src['py'])
    return a


def build_pole(J, P, G, spec):
    sc = 1 if spec['side'] == 'R' else -1
    items = spec['items']
    assign_rows(items)
    anchors = spec.get('anchors', [])
    gs = spec.get('gside', 0)
    if anchors:
        if gs == 0:
            raise ValueError('pole %s: anchors need gside +1 or -1' % spec.get('num'))
        short = min(int(ft(a['L'])) for a in anchors)
        for a in anchors:
            a['x'] = P + gs * (anchor_base(short) + 4 * (int(ft(a['L'])) - short))
    for it in items:
        if it['t'] == 'qp':     # QP length = its anchor's distance unless the planner gives its own 'L'
            it['qx'] = (P + gs * (anchor_base(short) + 4 * (int(ft(it['L'])) - short))) if it.get('L') \
                else anchors[it.get('an', 0)]['x']
    J.tag(part='equip', P=P, G=G, side=spec['side'], gside=spec.get('gside', 0))
    top = 0
    texts = []           # callout text boxes (x0, x1, baseline)
    for it in items:
        it['G'] = G
        it['a'] = place_item(J, P, G + it['row'], it, sc)
        top = max(top, it['row'])
    # callout column: 5.75 past the farthest equipment on the callout side (arm 35 -> 40.75, dead end 30 -> 35.75)
    col = max([COL_MIN] + [it['a'] + COL_GAP for it in items])
    J.tag(part='callout')
    for it in items:
        r = G + it['row']
        lines = list(it.get('above', [])) + list(it['c'])
        n_above = len(it.get('above', []))
        it['lines'] = []
        for j, line in enumerate(lines):
            yb = r + 1.6 + 8 * (n_above - j)              # 'above' lines stack over the row's own line
            J.cp([CALLOUT[0]], (P - col) - CALLOUT[1], yb - CALLOUT[2], mirror=P if sc > 0 else None,
                 edit=[dict(text=line, colorIndex=90) if color_for(line) == 90 else dict(text=line)])
            it['lines'].append((yb, line))
            x0, x1 = col, col + callout_w(line)
            texts.append((P + sc * x0, P + sc * x1, yb))

    # pole line
    J.tag(part='line')
    J.cp([LINE[0]], P - LINE[1], G - LINE[2], edit=[dict(start=pt(P, G), end=pt(P, G + top))])

    # anchors decide the base line
    if anchors:
        fx = max(abs(a['x'] - P) for a in anchors) + 2
        b0, b1 = (P - 17.5, P + fx) if gs > 0 else (P - fx, P + 17.5)
    else:
        b0, b1 = P - 17.5, P + 17.5
    J.cp([LINE[0]], P - LINE[1], G - LINE[2], edit=[dict(start=pt(b0, G), end=pt(b1, G))])

    # height dims: tight fit, ordered outward by height
    J.tag(part='dim')
    dims = sorted([it for it in items if not it.get('share')], key=lambda it: it['row'])
    x0 = 0
    for i, it in enumerate(dims):
        ext, beside = 0, False
        for jt in dims:
            if jt['row'] <= it['row']:
                for (yb, line) in jt['lines']:
                    e = col + callout_w(line)
                    if e > ext:
                        ext, beside = e, (jt is it and yb < G + it['row'])
        x0 = max(x0, ext + (4.4 if beside else 1.92) - 12 * i)
    tys, bad = place_labels(dims, G, P, sc, x0, texts)
    for i in bad:
        J.report.append('%s: dim label %s could not clear its neighbours; check it' % (spec.get('num'), dims[i].get('label', dims[i]['h'])))
    for i, it in enumerate(dims):
        dxp = P + sc * (x0 + 12 * i)
        top_y = G + it['row']
        txt = it.get('label', it['h'])                   # no planner height: h = drawn spot, label "_'"
        ty = tys[i]
        J.cp([HDIM[0]], P - HDIM[1], G - HDIM[2], edit=[dict(
            xLine1=pt(P + sc * it['a'], top_y), xLine2=pt(P, G), dimLine=pt(dxp, G),
            text=txt, textPosition=pt(dxp, ty), layer='DIMENSION', colorIndex=256)])

    # guys and anchors
    if anchors:
        J.tag(part='anchor')
        # guys[].an and qp 'an' index the anchors AS LISTED in the spec; never sort the list itself
        by_dist = sorted(anchors, key=lambda a: abs(a['x'] - P))
        for i, a in enumerate(by_dist):
            J.cp([ARC[0]], a['x'] - ARC[1], G + 2 - ARC[2])
            J.cp([LDIM[0]], P - LDIM[1], G - LDIM[2], edit=[dict(
                xLine1=pt(a['x'], G), xLine2=pt(P, G), dimLine=pt(P, G - 12 * (i + 1)),
                text=a['L'].replace(' ', ''), layer='DIMENSION', colorIndex=256)])
        rowof, exact = {}, {}
        for it in items:
            rowof.setdefault(int(ft(it['h'])), it['row'])
            exact.setdefault(ft(it['h']), it['row'])
        qps = [it for it in items if it['t'] == 'qp']
        guys = spec.get('guys', [])
        J.tag(part='guy')
        for g in guys:
            hf = int(ft(g['h']))
            # exact height first (DG @ 22'6" at the 22'6" row), then the whole foot, then its own position
            g['ya'] = G + exact.get(ft(g['h']), rowof.get(hf, pos(hf)))
            g['ax'] = anchors[g['an']]['x']
            if g.get('via') is not None:            # guy to the QUEENS POST end, then on to the anchor
                q = qps[g['via']]
                g['q'] = (q['qx'], G + q['row'])
                J.cp([GUY[0]], P - GUY[1], g['ya'] - GUY[2], edit=[dict(vertices=[pt(P, g['ya']), pt(*g['q'])])])
            else:
                J.cp([GUY[0]], P - GUY[1], g['ya'] - GUY[2], edit=[dict(vertices=[pt(P, g['ya']), pt(g['ax'], G)])])
        for q in qps:                                # one guy from the QP end down to its anchor
            ax = anchors[q.get('an', 0)]['x']
            J.cp([GUY[0]], P - GUY[1], G + q['row'] - GUY[2], edit=[dict(vertices=[pt(q['qx'], G + q['row']), pt(ax, G)])])

        def gx(g, y):
            if 'q' in g:
                qx, qy = g['q']
                if y >= qy:
                    return P + (qx - P) * (g['ya'] - y) / (g['ya'] - qy)
                return qx + (g['ax'] - qx) * (qy - y) / (qy - G)
            return P + (g['ax'] - P) * (g['ya'] - y) / (g['ya'] - G)

        gl = sorted(guys, key=lambda g: -g['ya'])
        last = None
        for g in gl:
            g['yt'] = g['ya'] - 28 if last is None else min(g['ya'] - 28, last - 30)
            last = g['yt']
        lift = max(0, (G + 20) - last) if gl else 0
        for gi, g in enumerate(gl):
            J.tag(part='dg', dg=gi)
            yt = g['yt'] + lift
            near = max([gs * (gx(o, yt + 3) - P) for o in guys if o['ya'] > yt] or [0]) + 20
            nx = P + gs * near
            txt = g['c']
            right = nx + len(txt) * 3.9 if gs > 0 else nx
            J.cp([DGTXT[0]], right - DGTXT[1], yt - DGTXT[2], edit=[dict(text=txt, colorIndex=color_for(txt))])
            endx = nx - gs * 2.8
            elb = endx - gs * 3
            ay = min(yt + 3 + 8, g['ya'] - 4)
            if 'q' in g:
                ay = max(ay, g['q'][1] + 4)          # arrow on the upper run, above the QP
            J.cp([LEADER[0]], P - LEADER[1], yt - LEADER[2], edit=[dict(
                vertices=[pt(gx(g, ay), ay), pt(elb, yt + 3), pt(endx, yt + 3)])])
        J.tag(part='anclabel')
        far_a = by_dist[-1]
        # far anchor's label at ground, then the others from the farthest up to the nearest, so leaders never cross
        lab = sorted([a for a in by_dist if a.get('c')], key=lambda a: (0, 0) if a is far_a else (1, -abs(a['x'] - P)))
        lx = far_a['x'] + gs * 6
        ybs, prev = [], None
        for a in lab:
            yb = G + 1.6 if prev is None else prev + 8
            if a is not far_a:
                # leader arrow segment (anchor to elbow) at least ANC_LEADER_MIN long, or the arrowhead does not draw
                ddx = (lx - gs * 5.8) - (a['x'] + gs * 1.2)
                while (ddx ** 2 + (yb + 3 - (G + 1.5)) ** 2) ** 0.5 < ANC_LEADER_MIN:
                    yb += 4
            ybs.append(yb)
            prev = yb
        for i, a in enumerate(lab):
            yb = ybs[i]
            J.cp([ANCTXT[0]], lx - ANCTXT[1], yb - ANCTXT[2], mirror=lx if gs < 0 else None,
                 edit=[dict(text=a['c'], colorIndex=color_for(a['c']))])
            if a is not far_a:
                ex = lx - gs * 2.8
                J.cp([LEADER[0]], P - LEADER[1], G - LEADER[2], edit=[dict(
                    vertices=[pt(a['x'] + gs * 1.2, G + 1.5), pt(ex - gs * 3, yb + 3), pt(ex, yb + 3)])])

    # pole label
    J.tag(part='label')
    cx = P if gs == 0 else (P + 9.9 + 15.55 if gs < 0 else P - 9.86 - 15.55)
    for k, ((h, sx, sy), t) in enumerate(zip(LBL, ['PROPOSED', spec['L'], spec['num']])):
        J.cp([h], cx - sx, (G - 11.08 - 8 * k) - sy, edit=[dict(text=t)] if k else None)
    return top


def place_labels(dims, G, P, sc, x0, texts):
    """Horizontal dim labels, inner dim first. Each label sits at its dim's midpoint, but always at least LABEL_STEP
    above the label inside it (14.5 corner to corner; neighbours are never level). Labels also
    step clear of callout text. When a staircase would run past a dim's top, the first label of that run is lowered
    below its midpoint (down to just above ground) so the whole run fits. Returns (y list, indexes still clashing)."""
    n = len(dims)
    xs = [P + sc * (x0 + 12 * i) for i in range(n)]
    ws = [label_w(d.get('label', d['h'])) for d in dims]
    mids = [(2 * G + d['row']) / 2 for d in dims]
    tops = [G + d['row'] - LABEL_H / 2 - 1 for d in dims]
    floor = G + LABEL_H / 2 + 1.5
    drop = [0.0] * n

    def on_text(i, ty):
        for (tx0, tx1, yb) in texts:
            lo, hi = min(tx0, tx1), max(tx0, tx1)
            if xs[i] + ws[i] / 2 > lo - 0.5 and xs[i] - ws[i] / 2 < hi + 0.5 and \
                    ty - LABEL_H / 2 < yb + TEXT_H + 1 and ty + LABEL_H / 2 > yb - 1:
                return True
        return False

    def hits(i, j, ti, tj):
        return abs(xs[i] - xs[j]) < (ws[i] + ws[j]) / 2 + LABEL_GAP and abs(ti - tj) < LABEL_STEP - 0.01

    for _ in range(60):
        ty, start = [], []
        for i in range(n):
            y, s0 = mids[i] - drop[i], i
            if i:                                       # always at least LABEL_STEP above the label inside it
                if ty[i - 1] + LABEL_STEP > y:
                    y, s0 = ty[i - 1] + LABEL_STEP, start[i - 1]
            y = max(y, ty[i - 1] if i else y)          # never below the label inside it
            k = 0
            while (on_text(i, y) or any(hits(i, j, y, ty[j]) for j in range(i))) and k < 40:
                y += 1
                k += 1
            ty.append(y)
            start.append(s0)
        over = [(ty[i] - tops[i], i) for i in range(n) if ty[i] > tops[i] + 0.01]
        if not over:
            break
        o, i = max(over)
        j = start[i]
        room = mids[j] - drop[j] - floor
        if room <= 0.01:
            break
        drop[j] += min(o, room)
    bad = [i for i in range(n) if ty[i] > tops[i] + 0.01 or on_text(i, ty[i]) or
           any(hits(i, j, ty[i], ty[j]) for j in range(n) if j != i)]
    return ty, bad


# ------------------------------------------------------------------ sheet data
def build_sheet(J, Cx, Cy, sheet):
    L = Cx - 919.971
    top = Cy + 618.326

    def box(spec, lines, top):
        J.tag(part=spec['title'].rstrip(':').lower().replace(' ', ''))
        J.cp([spec['hdr'][0]], L + 2.876 - STASH_TEXT_X, (top - 8.03) - spec['hdr'][1])
        yb = top - 8.03
        for t in lines:
            yb -= 8.027
            J.cp([spec['line'][0]], L + 2.876 - STASH_TEXT_X, yb - spec['line'][1], edit=[dict(text=t)])
        bot = yb - 4.21
        right = L + 2.876 + max(note_w(t) for t in lines + [spec['title']]) + 3   # re-fit after measuring
        J.cp([spec['box']], 0, 0, edit=[dict(vertices=[pt(L, top), pt(right, top), pt(right, bot), pt(L, bot)])])
        return bot

    crew = sheet.get('crew') or []
    notes = sheet.get('notes') or []
    if crew:
        top = box(CREW, crew, top) - 5
    bot = box(NOTE, notes, top) if notes else top + 5
    J.tag(part='blocks')
    gy = bot - 5 - GPS[2]
    gps = sheet.get('gps') or ['', '']
    J.cp([GPS[0]], L - STASH_X, gy - GPS[1], edit=[dict(attributes={'LAT': gps[0], 'LONG': gps[1]})])
    ey = gy - 5 - ELEV[2]
    elev = str(sheet.get('elev', '')).upper().replace("'", '').replace('FT', '').strip()
    J.cp([ELEV[0]], L - STASH_X, ey - ELEV[1], edit=[dict(attributes={'FOOTAGE': elev})])
    tlm = sheet.get('tlm')
    if tlm:
        addr = [[street_only(a), m] for a, m in tlm.get('addr', [])]
        if len(addr) > TLM_MAX:
            J.report.append('%s: %d TLM addresses, only the first %d fit; needs guidance' % (sheet['pole'], len(addr), TLM_MAX))
            addr = addr[:TLM_MAX]
        attr = {'STRUCTURE': sheet['pole'], 'CLIMATE-ZONE': tlm.get('cz', ''), 'VD-DROP': tlm.get('vd', ''),
                'FLICKER': tlm.get('flicker', ''), 'PRI-CIRC': tlm.get('pc', '')}
        for pre in ('EX', 'PR'):
            for key, v in zip(['SIZE', 'KVA', 'CUST', 'LOAD'], tlm.get(pre.lower(), ['', '', '', ''])):
                # the block prints its own % after LOAD: never send one
                attr[pre + '-' + key] = v.replace('%', '').strip() if key == 'LOAD' else v
        for i in range(10):
            a, m = addr[i] if i < len(addr) else ('', '')
            attr['ADDRESS%d' % (i + 1)] = a
            attr['METER%d' % (i + 1)] = m
        ix, iy = Cx + 777.554, Cy + 114.314
        J.cp([TLM[0]], ix - TLM[1], iy - TLM[2], edit=[dict(
            dynamicProperties={'ADDRESS LIST': 'ADDRESS LIST %d' % max(1, min(10, len(addr)))}, attributes=attr)])
        if len(addr) > 10 and not sheet.get('tlm_extra'):
            J.report.append('%s: no tlm_extra handles in the spec; using the TD2536012 handles' % sheet['pole'])
        tlm_extra_rows(J, ix, iy, addr[10:], sheet.get('tlm_extra'))
        notes = tlm.get('notes') or []
        J.tag(part='tlmnote')
        if notes:
            # box directly under the visible table; same x span as the block
            top = tlm_bottom(iy, len(addr))
            tx = ix + 4.20
            J.cp([TLMNOTE['hdr'][0]], tx - TLMNOTE['x'], (top - 7.98) - TLMNOTE['hdr'][1])
            yb = top - 20.32
            for t in notes:
                J.cp([TLMNOTE['line'][0]], tx - TLMNOTE['x'], yb - TLMNOTE['line'][1], edit=[dict(text=t)])
                yb -= 8.03
            bot = yb + 8.03 - 7.40
            J.cp([TLMNOTE['box']], 0, 0, edit=[dict(vertices=[pt(ix, top), pt(ix + TLM_W, top), pt(ix + TLM_W, bot), pt(ix, bot)])])
    top = Cy - 100
    for n, calc in enumerate(sheet.get('calcs') or []):
        J.tag(part='calc', box=n)
        top = build_calc(J, Cx, top, calc) - 10
    for n, rs in enumerate(sheet.get('rspans') or []):            # RULING SPAN boxes under the calcs
        J.tag(part='rspan', box=n)
        top = build_rspan(J, Cx, top, rs) - 10


def build_rspan(J, Cx, top, rs):
    """rs = [from pole, to pole, ruling span, final sag] as written. Centered on Cx; returns the bottom."""
    lines = ['%%URULING SPAN:', '-FROM %s TO %s' % (rs[0], rs[1]), ' RULING SPAN = %s' % rs[2], ' FINAL SAG = %s' % rs[3]]
    w = 2.876 + max(note_w(t.replace('%%U', '')) for t in lines) + 3        # re-fit after measuring
    L = Cx - w / 2
    dy = top - RSPAN['top']
    for (h, yb), t in zip(RSPAN['lines'], lines):
        J.cp([h], L + 2.876 - RSPAN['x'], (yb + dy) - yb, edit=[dict(text=t)] if not t.startswith('%%U') else None)
    bot = RSPAN['bottom'] + dy
    J.cp([RSPAN['box']], 0, 0, edit=[dict(vertices=[pt(L, top), pt(L + w, top), pt(L + w, bot), pt(L, bot)])])
    return bot


def build_calc(J, Cx, top, calc):
    """DE CALC box from the NOTE stash pieces (DECAL, SIMPLEX 4.8), centered on Cx. Returns the bottom."""
    rows = calc['rows']
    w = max([2.876 + note_w(calc['hdr'].replace('%%U', '')) + 3] +
            [208.34 + note_w(r[1]) + 5.63 if r[1] else 2.876 + note_w(r[0]) + 3 for r in rows])   # re-fit after measuring
    L = Cx - w / 2
    J.cp([NOTE['hdr'][0]], L + 2.876 - STASH_TEXT_X, (top - 8.02) - NOTE['hdr'][1], edit=[dict(text=calc['hdr'])])
    yb = top - 17.65
    prev = ''
    for left, right in rows:
        # combined calcs: the LBS x height line under a lettered load (A., B., ...) is indented
        ind = CALC_INDENT if re.match(r'^[A-Z]\. ', prev) else 0
        prev = left
        J.cp([NOTE['line'][0]], L + 2.876 + ind - STASH_TEXT_X, yb - NOTE['line'][1], edit=[dict(text=left)])
        if right:
            J.cp([NOTE['line'][0]], L + 208.34 - STASH_TEXT_X, yb - NOTE['line'][1], edit=[dict(text=right)])
        yb -= 8.027
    bot = yb + 8.027 - 4.22
    J.cp([NOTE['box']], 0, 0, edit=[dict(vertices=[pt(L, top), pt(L + w, top), pt(L + w, bot), pt(L, bot)])])
    return bot


def tlm_bottom(iy, n):
    """Bottom of the visible TLM table, including burst rows 11 and up."""
    n = max(1, n)
    if n <= 10:
        return iy - 70.40 - (n - 5) * 11.73
    return iy - TLM_L10_BOTTOM - (n - 10) * TLM_ROW


def pick_tlm_extra(entities):
    """Row 12 handles [address, meter, box, line] from a civil3d_entity query of TLM_EXTRA_WINDOW.

    The query returns anything touching the window (rows 11 and 13 too), so pick by text and by the row 12 span."""
    def span(e):
        return abs(e['extents']['max']['y'] - TLM_EXTRA['top']) < 0.1 and \
            abs(e['extents']['min']['y'] - (TLM_EXTRA['top'] - TLM_ROW)) < 0.1
    pick = lambda f: next(e['handle'] for e in entities if f(e))
    return [pick(lambda e: e['type'] == 'TEXT' and e.get('text', '').upper().startswith('ADDRESS')),
            pick(lambda e: e['type'] == 'TEXT' and e.get('text', '').upper().startswith('METER')),
            pick(lambda e: e['type'] == 'LWPOLYLINE' and span(e)),
            pick(lambda e: e['type'] == 'LINE' and span(e))]


def tlm_extra_rows(J, ix, iy, extra, handles=None):
    """Rows 11 and up: copy the row 12 pieces (address, meter, open box, divider) under a LIST 10 block.

    handles: [address, meter, box, line] of the row 12 pieces in THIS drawing (spec 'tlm_extra'), found with a
    query of the TLM_EXTRA_WINDOW; the coordinates are fixed in the template but the handles are not."""
    src = dict(TLM_EXTRA, h=list(handles or TLM_EXTRA['h']))
    for j, (a, m) in enumerate(extra):
        top = iy - TLM_L10_BOTTOM - j * TLM_ROW
        J.cp(src['h'], ix - src['left'], top - src['top'], edit=[dict(text=a), dict(text=m)])


def street_only(address):
    """Drop city and state: '1065 BURTONWOOD AVE THOUSAND OAKS CA' -> '1065 BURTONWOOD AVE'."""
    a = ' '.join(str(address).upper().replace(',', ' ').split())
    suffixes = ('AVE', 'DR', 'ST', 'RD', 'WAY', 'LN', 'CT', 'BLVD', 'PL', 'CIR', 'TER', 'PKWY', 'HWY', 'TRL')
    words = a.split()
    for i in range(len(words) - 1, -1, -1):
        if words[i] in suffixes:
            return ' '.join(words[:i + 1])
    return a


# ------------------------------------------------------------------ job
def build_job(spec):
    J = Job()
    for pole in spec['poles']:
        idx = pole['frame']
        Cx, Cy = frame(idx)
        profiles = pole['profiles']
        if len(profiles) == 1:
            # one profile goes in the slot the PDF draws it in: N slot (left) Cx - 300, E slot (right) Cx + 300
            slot = profiles[0].get('slot') or ('R' if profiles[0].get('L', '').replace(' ', '').upper() == 'L/E' else 'L')
            xs = [Cx + 300 if slot == 'R' else Cx - 300]
        else:
            xs = [Cx - 300, Cx + 300]
        J.ctx = dict(pole=pole['pole'], frame=idx, Cx=Cx, Cy=Cy)
        for pi, (P, prof) in enumerate(zip(xs, profiles)):
            J.tag(profile=pi)
            prof = _copy.deepcopy(prof)
            prof['num'] = pole['pole']
            build_pole(J, P, Cy, prof)
        if spec.get('tlm_extra'):
            pole = dict(pole, tlm_extra=spec['tlm_extra'])
        J.ctx = dict(pole=pole['pole'], frame=idx, Cx=Cx, Cy=Cy, part='sheet')
        build_sheet(J, Cx, Cy, pole)
        if idx < len(NAME_HANDLES):
            J.edit_existing(NAME_HANDLES[idx], dict(text=pole['pole']))
        else:
            J.tag(part='frame')
            fs = ROW2_FRAME_SET[idx % 4]
            J.cp(list(fs), 0, -ROW_STEP * (idx // 4 - 1),
                 edit=[None, None, dict(text=pole['pole']), dict(text=str(idx + 2))])
    return J


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('spec', help='job spec JSON')
    ap.add_argument('-o', '--out', help='apply job JSON to write (default: stdout)')
    ap.add_argument('--poles', help='comma separated pole numbers to build (default: all)')
    args = ap.parse_args(argv)
    spec = json.load(open(args.spec, encoding='utf-8'))
    if args.poles:
        keep = set(args.poles.split(','))
        spec['poles'] = [p for p in spec['poles'] if p['pole'] in keep]
    J = build_job(spec)
    job = J.to_apply_job()
    text = json.dumps(job, separators=(',', ':'))
    if args.out:
        open(args.out, 'w', encoding='utf-8').write(text)
    else:
        sys.stdout.write(text + '\n')
    print('%d copy ops, %d edits' % (len(job['copies']), len(job['edits'])), file=sys.stderr)
    for line in J.report:
        print('NOTE: ' + line, file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
