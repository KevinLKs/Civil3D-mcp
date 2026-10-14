"""python -m unittest discover -s tools/polehead"""
import json
import os
import unittest

import polehead as ph
import station_builder as sbm

HERE = os.path.dirname(os.path.abspath(__file__))


def example():
    with open(os.path.join(HERE, 'examples', 'TD2536120.json'), encoding='utf-8') as f:
        return json.load(f)


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.J = ph.build_job(example())
        self.job = self.J.to_apply_job()

    def test_every_ref_points_at_a_copied_handle(self):
        copies = {c['id']: set(c['handles']) for c in self.job['copies']}
        for e in self.job['edits']:
            if 'ref' in e:
                cid, h = e['ref'].split(':')
                self.assertIn(h, copies[cid], e['ref'])

    def test_grouped_copies_never_repeat_a_handle(self):
        for c in self.job['copies']:
            self.assertEqual(len(c['handles']), len(set(c['handles'])))

    def test_span_guys_use_the_halves(self):
        sg = [c for c in self.job['copies'] if '2E3466' in c['handles'] or '2E3954' in c['handles']]
        self.assertTrue(sg)
        self.assertFalse(any('mirrorX' in c for c in sg))
        guy_edits = [e for e in self.job['edits'] if e.get('ref', '').endswith(':2E3B8F')]
        for e in guy_edits:                               # every GUY copy is a down guy to ground
            self.assertEqual(len(e['vertices']), 2)

    def test_dim_labels_do_not_overlap(self):
        dims = [e for e in self.job['edits'] if 'xLine2' in e and 'textPosition' in e and 'dimLine' in e]
        by_pole = {}
        for e in dims:
            by_pole.setdefault((e['xLine2']['x'], e['xLine2']['y']), []).append(e)
        for group in by_pole.values():
            for i, a in enumerate(group):
                for b in group[i + 1:]:
                    wa, wb = ph.label_w(a['text']), ph.label_w(b['text'])
                    overlap_x = abs(a['textPosition']['x'] - b['textPosition']['x']) < (wa + wb) / 2
                    overlap_y = abs(a['textPosition']['y'] - b['textPosition']['y']) < ph.LABEL_H
                    self.assertFalse(overlap_x and overlap_y, (a['text'], b['text']))

    def test_rows_follow_the_cluster_rule(self):
        items = [dict(t='dot', h="16'2\"", c=[]), dict(t='dot', h="16'5\"", c=[]),
                 dict(t='dot', h="17'5\"", c=[]), dict(t='dot', h="17'8\"", c=[]), dict(t='dot', h="28'6\"", c=[])]
        ph.assign_rows(items)
        self.assertEqual([it['row'] for it in items], [54, 62, 70, 78, 142])

    def test_elev_is_a_bare_number(self):
        J = ph.Job()
        ph.build_sheet(J, 0, 0, dict(pole='X', notes=['-A'], gps=['1', '2'], elev="821'"))
        footage = [e for _, h, e in J.edits if h == ph.ELEV[0]]
        self.assertEqual(footage[0]['attributes']['FOOTAGE'], '821')

    def test_street_only(self):
        self.assertEqual(ph.street_only('1065 Burtonwood Ave, Thousand Oaks CA'), '1065 BURTONWOOD AVE')


class StationBuilderTests(unittest.TestCase):
    def test_fills_and_dedupes(self):
        rows = [(None, None, None)] * 43
        rows = [list(r) for r in rows]
        rows[5] = [None, "34°11'32.19\"", None]
        rows[7] = [None, "118°53'1.0\"", None]
        rows[9] = [None, "821'", None]
        rows[23] = ['POLE SET IN ______, INSP. ______', '2018,  INSP. N/A', None]
        rows[24] = ['TRUCK ACCESS VIA STREET NAME', 'Windsor Dr', None]
        rows[25] = ['TRUCK ACCESS VIA STREET NAME', 'Windsor Dr', None]
        out = sbm.sheet_from_rows('P', [tuple(r) for r in rows], [])
        self.assertEqual(out['notes'], ['-POLE SET IN 2018, INSP. N/A', '-TRUCK ACCESS VIA WINDSOR DR'])
        self.assertEqual(out['elev'], '821')


class NewRulesTest(unittest.TestCase):
    def _sheet(self, **kw):
        J = ph.Job()
        sheet = dict(pole='1312225E', notes=['-X'], gps=['', ''], elev='')
        sheet.update(kw)
        ph.build_sheet(J, 0, 0, sheet)
        return J

    def test_tlm_load_has_no_percent(self):
        J = self._sheet(tlm=dict(ex=['37.5', '46.3', '12', '123.47%'], pr=['50', '1', '1', '113.72 %'], addr=[]))
        attrs = [e['attributes'] for k, h, e in J.edits if h == ph.TLM[0]][0]
        self.assertEqual((attrs['EX-LOAD'], attrs['PR-LOAD']), ('123.47', '113.72'))

    def test_tlm_burst_rows(self):
        addr = [['%d MAIN ST' % i, 'M%d' % i] for i in range(12)]
        J = self._sheet(tlm=dict(addr=addr, notes=['A']))
        e = [e for k, h, e in J.edits if h == ph.TLM[0]][0]
        self.assertEqual(e['dynamicProperties']['ADDRESS LIST'], 'ADDRESS LIST 10')
        rows = [op for k, op in J.ops if op['handles'] == ph.TLM_EXTRA['h']]
        self.assertEqual(len(rows), 2)
        iy = 114.314
        self.assertAlmostEqual(rows[0]['dy'], iy - ph.TLM_L10_BOTTOM - ph.TLM_EXTRA['top'], 3)
        self.assertAlmostEqual(rows[0]['dy'] - rows[1]['dy'], ph.TLM_ROW, 3)
        box = [e for k, h, e in J.edits if h == ph.TLMNOTE['box']][0]
        self.assertAlmostEqual(box['vertices'][0]['y'], iy - ph.TLM_L10_BOTTOM - 2 * ph.TLM_ROW, 3)

    def test_single_profile_slot(self):
        def P(prof):
            J = ph.build_job(dict(poles=[dict(frame=0, pole='1', profiles=[prof], notes=['-X'])]))
            line = [e for k, h, e in J.edits if h == ph.LINE[0]][0]   # pole line starts at (P, G)
            return line['start']['x'] - ph.COLS[0]
        base = dict(side='R', items=[dict(t='xb', h="20'", c=['COMM'])])
        self.assertAlmostEqual(P(dict(base, L='L/N')), -300)
        self.assertAlmostEqual(P(dict(base, L='L/E')), 300)
        self.assertAlmostEqual(P(dict(base, L='L/NW', slot='R')), 300)

    def test_pick_tlm_extra(self):
        top, bot = -779.9231, -791.6558
        ext = lambda y0, y1: dict(min=dict(x=1854.666, y=y0), max=dict(x=1999.2395, y=y1))
        ents = [dict(handle='A', type='TEXT', text='ADDRESS12', extents=ext(-787.9, -783.1)),
                dict(handle='M', type='TEXT', text='METER12', extents=ext(-788.2, -783.4)),
                dict(handle='B13', type='LWPOLYLINE', extents=ext(-803.3884, bot)),
                dict(handle='B12', type='LWPOLYLINE', extents=ext(bot, top)),
                dict(handle='L11', type='LINE', extents=ext(top, -768.1905)),
                dict(handle='L12', type='LINE', extents=ext(bot, top))]
        self.assertEqual(ph.pick_tlm_extra(ents), ['A', 'M', 'B12', 'L12'])

    def test_tlm_over_20_reported(self):
        J = self._sheet(tlm=dict(addr=[['%d A ST' % i, ''] for i in range(22)]))
        self.assertEqual(len([op for k, op in J.ops if op['handles'] == ph.TLM_EXTRA['h']]), 10)
        self.assertTrue(any('22 TLM addresses' in r for r in J.report))

    def test_calc_indent_under_lettered_loads(self):
        J = ph.Job()
        ph.build_calc(J, 0, 0, dict(hdr='H', rows=[['A. X', '= 1'], ['1 x 2', '= 2'], ['TOTAL', '= 3']]))
        lefts = [op['dx'] for k, op in J.ops if op['handles'] == [ph.NOTE['line'][0]]][0::2]
        self.assertAlmostEqual(lefts[1] - lefts[0], ph.CALC_INDENT, 3)
        self.assertAlmostEqual(lefts[2], lefts[0], 3)

    def test_callout_column_follows_equipment(self):
        def col(side, items):
            J = ph.Job()
            spec = dict(L='L/N', side=side, num='1', items=items)
            ph.build_pole(J, 0, 0, spec)
            return max([ph.COL_MIN] + [it['a'] + ph.COL_GAP for it in spec['items']])
        self.assertAlmostEqual(col('R', [dict(t='arm2', h="37'", c=['A'])]), 40.75)
        self.assertAlmostEqual(col('L', [dict(t='de2', h="37'", c=['A'])]), 35.75)
        self.assertAlmostEqual(col('R', [dict(t='xb', h="20'", c=['COMM'])]), 30.75)


if __name__ == '__main__':
    unittest.main()
