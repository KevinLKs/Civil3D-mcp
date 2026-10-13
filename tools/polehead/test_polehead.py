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


if __name__ == '__main__':
    unittest.main()
