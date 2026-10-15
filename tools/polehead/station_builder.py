#!/usr/bin/env python3
"""Read sheet data (crew notes, notes, GPS, elevation) from a Station Builder xlsx.

    python station_builder.py "<TD> - STATION BUILDER.xlsx" 1414703E 4904169E ... > sheets.json

Reads ONLY columns N:P, rows 4 to 46 of each pole tab (the tabs are thousands of
rows long). Output: {pole: {crew, notes, gps, elev}} plus a "report" list of
things worth a look. Merge these into the job spec's poles.
"""
from __future__ import annotations

import json
import sys

FIX = {'DEFUALT': 'DEFAULT', 'REQUIRMENT': 'REQUIREMENT', 'EASMENT': 'EASEMENT', 'UKNOWN': 'UNKNOWN', 'VEGITATION': 'VEGETATION'}


def clean(t):
    t = ' '.join(str(t).replace('\n', ' ').split()).upper()
    for a, b in FIX.items():
        t = t.replace(a, b)
    return t


def read_rows(xlsx, pole):
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, data_only=True, read_only=True)
    ws = wb[pole]
    return [tuple(c.value for c in row) for row in ws.iter_rows(min_row=4, max_row=46, min_col=14, max_col=16)]


def sheet_from_rows(pole, rows, report):
    """rows[i] = (N, O, P) of row 4 + i."""
    crew, notes = [], []
    for i in range(13, 22):                      # N17..N25
        v = rows[i][0]
        if v:
            c = clean(v)
            crew.append(c if c.startswith('-') else '-' + c)
    for i in range(23, 43):                      # N27..N46
        v, o, q = rows[i]
        if not v:
            continue
        t = clean(v)
        fill = ' '.join(str(x) for x in (o, q) if x)
        if 'POLE SET IN' in t:
            if fill:
                a, _, b = fill.partition('INSP.')
                t = '-POLE SET IN %s, INSP. %s' % (a.strip(' ,') or 'N/A', b.strip() or 'N/A')
            else:
                t = '-POLE SET IN N/A, INSP. N/A'
        elif 'STREET NAME' in t:
            if fill:
                t = t.replace('STREET NAME', clean(fill))
        elif '___' in t and fill:
            t = t.split('___')[0].rstrip() + ' ' + clean(fill)
        if not t.startswith('-'):
            t = '-' + t
        if t in notes:
            continue                             # duplicates are dropped silently
        notes.append(t)
    gps = [str(rows[5][1] or ''), str(rows[7][1] or '')]
    elev = str(rows[9][1] or '').upper().replace("'", '').replace('FT', '').strip()
    if not gps[0] or not gps[1]:
        report.append('%s: GPS missing in Station Builder' % pole)
    return dict(crew=crew, notes=notes, gps=gps, elev=elev)


def main(argv):
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    xlsx, poles = argv[0], argv[1:]
    out, report = {}, []
    for p in poles:
        try:
            out[p] = sheet_from_rows(p, read_rows(xlsx, p), report)
        except KeyError:
            report.append('%s: no Station Builder tab' % p)
    out['report'] = report
    json.dump(out, sys.stdout, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
