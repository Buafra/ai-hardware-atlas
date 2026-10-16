"""Official MLPerf results on catalog products ("benchmarks"): links only (MLCommons' own pages or its results
repositories on GitHub), validated by scripts/build.py, shown in each product's notes and exported to the app."""
import copy
import json
import re
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import app_data
import build

CATALOG = json.loads((ROOT / 'data' / 'catalog.json').read_text(encoding='utf-8'))
WITH = [p for p in CATALOG['products'] if p.get('benchmarks')]

class DataTests(unittest.TestCase):
    def test_repository_catalog_is_valid(self):
        build.validate(copy.deepcopy(CATALOG))
        self.assertTrue(WITH, 'no product has an MLPerf link')

    def test_links_only(self):
        # Exactly label, url, round and date: no scores, no system lists, nothing copied from the results.
        for p in WITH:
            for b in p['benchmarks']:
                self.assertEqual(set(b), set(build.BENCHMARK_KEYS), p['id'])
                self.assertTrue(build.benchmark_url_ok(b['url']), b['url'])
                self.assertTrue(b['round'].startswith('MLPerf ') and b['label'] in b['round'] + ' (Preview)', b)
                self.assertLessEqual(date.fromisoformat(b['date']), date.today())
            rounds = [b['round'] for b in p['benchmarks']]
            self.assertEqual(len(rounds), len(set(rounds)), f'{p["id"]}: one link per round')

    def test_verifier_additions(self):
        # Training v6.0 (16 Jun 2026) is the current training round: GH200 appears there (only there among the rounds checked).
        by = {p['id']: p for p in WITH}
        self.assertEqual([b['round'] for b in by['gh200']['benchmarks']], ['MLPerf Training v6.0'])
        self.assertTrue(any(b['round'] == 'MLPerf Training v6.0' and b['date'] == '2026-06-16' for p in WITH for b in p['benchmarks']))
        self.assertNotIn('rtx-pro-server-8-gpu-example', by, 'related systems only, no exact MLCommons name')

    def test_url_rule(self):
        ok = ('https://mlcommons.org/benchmarks/inference-datacenter/', 'https://www.mlcommons.org/2026/06/mlperf-training-v6-0-results/',
              'https://github.com/mlcommons/inference_results_v6.1')
        bad = ('http://mlcommons.org/benchmarks/', 'https://mlcommons.org.evil.example/x', 'https://evilmlcommons.org/', 'https://github.com/someone/mlcommons',
               'https://github.com/mlcommons', 'https://user@github.com/mlcommons/x', 'https://github.com:8443/mlcommons/x', 'javascript:alert(1)', '', None,
               'https://raw.githubusercontent.com/mlcommons/x/main/a.json')
        for u in ok:
            self.assertTrue(build.benchmark_url_ok(u), u)
        for u in bad:
            self.assertFalse(build.benchmark_url_ok(u), u)

    def test_validation_refuses_bad_entries(self):
        good = {'label': 'Inference v6.1', 'url': 'https://github.com/mlcommons/inference_results_v6.1', 'round': 'MLPerf Inference v6.1', 'date': '2026-09-16'}
        cases = {'url': dict(good, url='https://example.com/mlperf'), 'score': dict(good, score=123.4), 'round': dict(good, round='Inference v6.1'),
                 'date': dict(good, date='2026-13-01'), 'label': dict(good, label=' ')}
        for name, entry in cases.items():
            data = copy.deepcopy(CATALOG)
            data['products'][0]['benchmarks'] = [entry]
            with self.assertRaises((AssertionError, ValueError), msg=name):
                build.validate(data)
        data = copy.deepcopy(CATALOG)
        data['products'][0]['benchmarks'] = []
        with self.assertRaises(AssertionError):
            build.validate(data)

class PageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data, feed, sources, uae, models = build.load_all()
        cls.data = data
        with tempfile.TemporaryDirectory() as d:
            cls.html, cls.public = build.render_page(data, feed, sources, uae, models, brand_dir=Path(d))

    def card(self, pid):
        return re.search(r'<article class="product [^"]*" id="p-%s".*?</article>' % re.escape(pid), self.html, re.S).group(0)

    def test_line_in_the_product_notes(self):
        self.assertEqual(self.html.count('<div class="bench">'), len(WITH))
        for p in self.data['products']:
            card = self.card(p['id'])
            if not p.get('benchmarks'):
                self.assertNotIn('class="bench"', card, p['id'])
                continue
            notes = card[card.index('<details>'):card.index('</details>')]
            self.assertIn('<span data-i18n>Official benchmarks (MLPerf)</span>', notes)
            links = re.findall(r'<a href="([^"]+)" target="_blank" rel="noopener noreferrer" lang="en" dir="ltr">([^<]+)</a>', notes[notes.index('class="bench"'):])
            self.assertEqual(sorted(links), sorted((b['url'], b['label']) for b in p['benchmarks']), p['id'])
            dates = [b['date'] for b in sorted(p['benchmarks'], key=lambda b: b['date'], reverse=True)]
            shown = [build.ymd(d, 'en') for d in dates]
            self.assertEqual([s for s in re.findall(r'<small><span data-lang="en">([^<]+)</span>', notes)][-len(shown):], shown, 'newest round first')

    def test_arabic_labels(self):
        js = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')
        for text in ('Official benchmarks (MLPerf)', 'Open a round to find this hardware in the results MLCommons publishes.'):
            self.assertTrue(f"'{text}':" in js, text)

    def test_public_catalog_and_app_keep_the_links(self):
        pub = {p['id']: p for p in self.public['products']}
        for p in WITH:
            self.assertEqual(pub[p['id']]['benchmarks'], p['benchmarks'])
        data, feed, sources, uae, models = build.load_all()
        out = app_data.payloads(data, feed, sources, uae, models, *build.learn.load())['catalog.json']
        app = {p['id']: p for p in out['products']}
        for p in WITH:
            self.assertEqual(app[p['id']]['benchmarks'], p['benchmarks'])
        self.assertFalse([p['id'] for p in out['products'] if 'benchmarks' in p and not p['benchmarks']], 'no empty lists')

if __name__ == '__main__':
    unittest.main()
