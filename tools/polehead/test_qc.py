"""python -m unittest discover -s tools/polehead"""
import json
import os
import tempfile
import unittest

import polehead as ph
import qc

HERE = os.path.dirname(os.path.abspath(__file__))


def example():
    with open(os.path.join(HERE, 'examples', 'TD2536120.json'), encoding='utf-8') as f:
        return json.load(f)


def text(handle, s, x0, y0, x1, y1):
    return dict(handle=handle, type='TEXT', layer='MISC', text=s, position=dict(x=x0, y=y0),
                extents=dict(min=dict(x=x0, y=y0), max=dict(x=x1, y=y1)))


def poly(handle, pts, kind='LWPOLYLINE'):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return dict(handle=handle, type=kind, layer='MISC', vertices=[dict(x=x, y=y) for x, y in pts],
                extents=dict(min=dict(x=min(xs), y=min(ys)), max=dict(x=max(xs), y=max(ys))))


class QCTests(unittest.TestCase):
    def setUp(self):
        self.spec = example()
        self.J = ph.build_job(self.spec)
        self.job = self.J.to_apply_job()
        self.maps = {c['id']: {h: '%X' % (0x100000 + i * 50 + j) for j, h in enumerate(c['handles'])}
                     for i, c in enumerate(self.job['copies'])}
        self.H = qc.handle_map(self.J, dict(handles=self.maps))
        self.pole = self.spec['poles'][0]['pole']

    def new(self, part, src, pole=None, nth=0, **kw):
        hits = [self.H[k][src] for k, op in self.J.ops if src in op['handles'] and
                self.J.meta[k].get('part') == part and self.J.meta[k].get('pole') == (pole or self.pole) and
                all(self.J.meta[k].get(a) == b for a, b in kw.items())]
        return hits[nth]

    def run_qc(self, ents):
        return qc.QC(self.spec, self.J, {e['handle']: e for e in ents}, self.H).run()

    def msgs(self, q):
        return [m for p, m in q.issues]

    def test_wrong_text_is_reported(self):
        h = self.new('callout', ph.CALLOUT[0])
        q = self.run_qc([text(h, 'PH ARM', 0, 0, 20, 4.8)])
        self.assertTrue(any("reads 'PH ARM'" in m for m in self.msgs(q)))

    def test_note_box_refit(self):
        lines = [h for k, op in self.J.ops for h in [self.H[k].get(s) for s in op['handles']]
                 if self.J.meta[k].get('part') == 'note' and self.J.meta[k].get('pole') == self.pole
                 and op['handles'][0] in qc.NOTE_TEXT]
        box = self.new('note', ph.NOTE['box'])
        ents = [text(h, 'X', 10, -10 * i, 100 - i, -10 * i + 4.8) for i, h in enumerate(lines)]
        ents.append(poly(box, [(7, 5), (120, 5), (120, -60), (7, -60)]))
        q = self.run_qc(ents)
        fix = [e for e in q.fix_edits if e['handle'] == box]
        self.assertEqual(len(fix), 1)
        self.assertAlmostEqual(fix[0]['vertices'][1]['x'], 103, 3)
        self.assertAlmostEqual(fix[0]['vertices'][0]['x'], 7, 3)
        self.assertFalse(q.fix_moves)                      # notes stay put; only calcs re-center

    def test_note_box_that_fits_is_clean(self):
        line = self.new('note', ph.NOTE['line'][0])
        box = self.new('note', ph.NOTE['box'])
        q = self.run_qc([text(line, 'X', 10, 0, 100, 4.8), poly(box, [(7, 5), (103.1, 5), (103.1, -10), (7, -10)])])
        self.assertFalse([e for e in q.fix_edits if e['handle'] == box])

    def test_dg_leader_repointed_to_measured_edge(self):
        poles = [m['pole'] for m in self.J.meta.values() if m.get('part') == 'dg']
        pole = poles[0]
        t = self.new('dg', ph.DGTXT[0], pole=pole, dg=0)
        ld = self.new('dg', ph.LEADER[0], pole=pole, dg=0)
        guy = self.new('guy', ph.GUY[0], pole=pole)
        ents = [text(t, 'IN: 3/8" DG @ 36\'', 200, 50, 240, 54.8),
                poly(ld, [(140, 60), (190, 53), (195, 53)], kind='LEADER'),
                poly(guy, [(100, 100), (200, 0)])]
        q = qc.QC(self.spec, self.J, {e['handle']: e for e in ents}, self.H).run()
        fix = [e for e in q.fix_edits if e['handle'] == ld][0]
        self.assertAlmostEqual(fix['vertices'][2]['x'], 197.2, 3)
        self.assertAlmostEqual(fix['vertices'][1]['x'], 194.2, 3)
        self.assertAlmostEqual(fix['vertices'][2]['y'], 53, 3)
        self.assertFalse(any('not on a guy' in m for m in self.msgs(q)))

    def test_overlapping_callouts(self):
        a = self.new('callout', ph.CALLOUT[0], nth=0)
        b = self.new('callout', ph.CALLOUT[0], nth=1)
        q = self.run_qc([text(a, self.J.edits[0][2].get('text', 'A'), 0, 0, 30, 4.8), text(b, 'B', 10, 2, 40, 6.8)])
        self.assertTrue(any('overlaps' in m for m in self.msgs(q)))

    def test_text_on_guy(self):
        pole = next(m['pole'] for m in self.J.meta.values() if m.get('part') == 'guy')
        guy = self.new('guy', ph.GUY[0], pole=pole)
        c = self.new('callout', ph.CALLOUT[0], pole=pole)
        q = self.run_qc([poly(guy, [(0, 0), (50, 50)]), text(c, 'X', 20, 18, 30, 22.8)])
        self.assertTrue(any('runs through text' in m for m in self.msgs(q)))

    def test_lint(self):
        spec = dict(poles=[dict(pole='1', notes=['-ok', 'no dash', '-ok'], tlm=dict(notes=['-x']))])
        out = [m for p, m in qc.lint(spec)]
        self.assertTrue(any('leading dash' in m for m in out))
        self.assertTrue(any('duplicate' in m for m in out))
        self.assertTrue(any('TLM note should not' in m for m in out))

    def test_stops_on_a_different_job(self):
        d = tempfile.mkdtemp()
        sp, jp, rp, qp = (os.path.join(d, n) for n in ('s.json', 'j.json', 'r.json', 'q.json'))
        json.dump(self.spec, open(sp, 'w'))
        bad = dict(self.job, edits=self.job['edits'][1:])
        json.dump(bad, open(jp, 'w'))
        json.dump(dict(status='completed', handles=self.maps), open(rp, 'w'))
        json.dump([], open(qp, 'w'))
        self.assertEqual(qc.main([sp, jp, rp, qp]), 2)

    def test_loads_saved_tool_output(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, 'q.json')
        json.dump([{'type': 'resource_link'}, {'type': 'text', 'text': json.dumps(
            {'entities': [dict(handle='abc', type='TEXT')]})}], open(p, 'w'))
        self.assertIn('ABC', qc.load_entities([p]))


if __name__ == '__main__':
    unittest.main()
