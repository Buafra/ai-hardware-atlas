import json, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import learn_links

class LinkTests(unittest.TestCase):
    def test_finds_every_https_link_with_where_it_is(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'reports.json'
            p.write_text(json.dumps({'reports': [{'id': 'r1', 'url': 'https://example.org/a', 'note': 'see https://x.y not a link',
                                                  'sources': [{'url': 'https://example.org/b'}, 'https://example.org/a']}]}), encoding='utf-8')
            found = learn_links.links([p])
        self.assertEqual(set(found), {'https://example.org/a', 'https://example.org/b'})
        self.assertEqual(found['https://example.org/a'], ['reports.reports[r1].url', 'reports.reports[r1].sources[1]'])

    def test_real_data_has_links_from_all_three_files(self):
        found = learn_links.links()
        kinds = {w.split('.')[0] for where in found.values() for w in where}
        self.assertEqual(kinds, {'reports', 'stacks', 'concepts'})
        self.assertTrue(all(u.startswith('https://') for u in found))

    def test_status_from_http_codes(self):
        err = lambda code: learn_links.HTTPError('u', code, 'x', {}, None)
        with mock.patch.object(learn_links, 'urlopen', side_effect=err(404)):
            self.assertEqual(learn_links.check('https://e.org/'), ('broken', 'HTTP 404'))
        with mock.patch.object(learn_links, 'urlopen', side_effect=err(403)):
            self.assertEqual(learn_links.check('https://e.org/'), ('blocked', 'HTTP 403'))
        with mock.patch.object(learn_links, 'urlopen', side_effect=TimeoutError('slow')):
            self.assertEqual(learn_links.check('https://e.org/')[0], 'broken')

if __name__ == '__main__':
    unittest.main()
