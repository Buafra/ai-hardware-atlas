"""UAE and Gulf models from official model cards (data/models-extra.json): data rules, the merge with OpenRouter's list
(scripts/models.py keeps refreshing data/models.json on its own), the estimator's model data, the Arabic chip and
My hardware markup, and dist/app/models.json. Counts always come from the data, never fixed numbers."""
import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import app_data
import build
import models as models_py

EXTRA = json.loads((ROOT / 'data' / 'models-extra.json').read_text(encoding='utf-8'))
OPENROUTER = json.loads((ROOT / 'data' / 'models.json').read_text(encoding='utf-8'))
JS = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')

def ar_key(text):
    """True when app.js has an Arabic translation for this English string."""
    return f"'{text}':" in JS or f'"{text}":' in JS

class DataTests(unittest.TestCase):
    def test_repository_file_passes(self):
        self.assertEqual(build.models_extra_problems(EXTRA), [])
        self.assertTrue(EXTRA['models'], 'no official-card models')
        self.assertEqual(build.load_models_extra(), EXTRA)

    def test_contract_fields(self):
        # Fields compatible with data/models.json, plus maker, country, arabic, runnable, card_url and license.
        for m in EXTRA['models']:
            self.assertTrue(set(build.MODEL_FIELDS) | set(build.EXTRA_KEYS) <= set(m), m['id'])
            self.assertIn(m['country'], build.EXTRA_COUNTRIES)
            self.assertTrue(m['sources'] and all(s.startswith('https://') for s in m['sources']), m['id'])

    def test_runnable_and_chat_only(self):
        for m in EXTRA['models']:
            if m['runnable']:
                self.assertTrue(m['open'] and m['hf'] and m['params_b'] > 0 and m['params_source'] in build.PARAMS_SOURCES, m['id'])
            else:  # chat only: listed, never fitted
                self.assertEqual((m['open'], m['hf'], m['params_b'], m['params_source']), (False, None, None, None), m['id'])

    def test_verifier_corrections(self):
        by = {m['id']: m for m in EXTRA['models']}
        # Falcon3: created is TII's official release day (17 Dec 2024), not the repository day.
        falcon3 = [m for m in EXTRA['models'] if m['id'].startswith('tiiuae/falcon3')]
        self.assertTrue(falcon3)
        for m in falcon3:
            self.assertEqual(m['created'], 1734393600, m['id'])
        # Falcon-H1-Arabic: context 128K / 256K / 256K from TII's own post, chat only (no downloadable weights).
        for size, ctx in (('3b', 131072), ('7b', 262144), ('34b', 262144)):
            m = by[f'tiiuae/falcon-h1-arabic-{size}']
            self.assertEqual((m['context'], m['runnable'], m['open'], m['arabic']), (ctx, False, False, True), size)
        # Left out: Fanar-2-Diwan (stored weights do not match the card), and the models the research did not recommend.
        for gone in ('qcri/fanar-2-diwan', 'silma-ai/silma-9b-instruct-v1.0', 'silma-ai/silma-kashif-2b-instruct-v1.0',
                     'navid-ai/yehia-7b-preview', 'inception42/llama-3.1-sherkala-8b-chat'):
            self.assertNotIn(gone, by)
        # Falcon-Edge (1.58-bit BitNet) would need a special case in the estimator, so it is left out.
        self.assertFalse([i for i in by if i.startswith('tiiuae/falcon-e-')])

    def test_names_never_pass_for_inception_labs(self):
        # "Inception: Mercury" on OpenRouter is Inception Labs, a different company: the Jais models carry Inception42.
        for m in EXTRA['models']:
            if 'Jais' in m['name']:
                self.assertTrue(m['name'].startswith('Inception42'), m['name'])

    def broken(self, mutate):
        doc = copy.deepcopy(EXTRA)
        mutate(doc)
        problems = build.models_extra_problems(doc)
        self.assertTrue(problems)
        return '\n'.join(problems)

    def test_validation_catches_each_rule(self):
        first = lambda d: next(m for m in d['models'] if m['runnable'])
        chat = lambda d: next(m for m in d['models'] if not m['runnable'])
        self.assertIn('needs open true', self.broken(lambda d: first(d).update(params_b=None)))
        self.assertIn('needs open true', self.broken(lambda d: first(d).update(params_source='guess')))
        self.assertIn('chat-only', self.broken(lambda d: chat(d).update(params_b=7.0)))
        self.assertIn('chat-only', self.broken(lambda d: chat(d).update(open=True)))
        self.assertIn('country', self.broken(lambda d: first(d).update(country='Elsewhere')))
        self.assertIn('card_url', self.broken(lambda d: first(d).update(card_url='http://huggingface.co/x')))
        self.assertIn('unknown field', self.broken(lambda d: first(d).update(benchmark_score=90)))
        self.assertIn('duplicate id', self.broken(lambda d: d['models'].append(dict(first(d), name='Other name'))))
        self.assertIn('arabic', self.broken(lambda d: first(d).update(arabic='yes')))
        self.assertIn('hf must be', self.broken(lambda d: first(d).update(hf='not a repo')))
        self.assertIn('sources', self.broken(lambda d: first(d).update(sources=[])))
        self.assertIn('breaks the content policy', self.broken(lambda d: first(d).update(maker='TII, after sanctions on the UAE')))
        self.assertEqual(build.models_extra_problems({'items': []}), ['models-extra.json must be {"models": [...]}'])

    def test_bad_file_stops_the_build(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / 'models-extra.json'
            doc = copy.deepcopy(EXTRA)
            doc['models'][0]['country'] = 'Elsewhere'
            bad.write_text(json.dumps(doc), encoding='utf-8')
            with self.assertRaises(build.ModelsExtraError):
                build.load_models_extra(bad)
            self.assertEqual(build.load_models_extra(Path(d) / 'missing.json'), {'models': []})

class MergeTests(unittest.TestCase):
    def test_merged_list(self):
        merged = build.merge_models(OPENROUTER, EXTRA)
        ids = [m['id'] for m in merged['models']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue({m['id'] for m in OPENROUTER['models']} <= set(ids))
        self.assertTrue({m['id'] for m in EXTRA['models']} <= set(ids))
        # A card model that OpenRouter lists too (same id, Hugging Face repo or name) is listed once.
        listed = lambda x: any(m['id'] == x['id'] or (x['hf'] and (m.get('hf') or '').lower() == x['hf'].lower())
                               or m['name'].casefold() == x['name'].casefold() for m in OPENROUTER['models'])
        self.assertEqual(len(ids), len(OPENROUTER['models']) + sum(not listed(x) for x in EXTRA['models']))
        keys = [(not m['open'], m['name'].casefold()) for m in merged['models']]
        self.assertEqual(keys, sorted(keys), 'open weights first, then by name (as scripts/models.py sorts)')
        self.assertEqual((merged['updated_at'], merged['source']), (OPENROUTER['updated_at'], OPENROUTER['source']))
        card = next(m for m in merged['models'] if m['id'] == EXTRA['models'][0]['id'])
        self.assertEqual(set(card), set(build.MODEL_FIELDS) | set(build.EXTRA_KEYS))  # sources stay in the data file

    def test_merge_is_pure_and_enriches_an_openrouter_entry(self):
        x = next(m for m in EXTRA['models'] if m['runnable'])
        listed = {'updated_at': 'u', 'source': 's', 'models': [{'id': 'or/x', 'name': 'OR: X', 'hf': x['hf'].upper(), 'context': 9,
                                                                'created': 1, 'open': True, 'params_b': 1.0, 'params_source': 'huggingface', 'moe': False}]}
        before = copy.deepcopy(listed), copy.deepcopy(EXTRA)
        merged = build.merge_models(listed, EXTRA)
        self.assertEqual((listed, EXTRA), before, 'inputs unchanged')
        same = [m for m in merged['models'] if m.get('hf', '') and m['hf'].lower() == x['hf'].lower()]
        self.assertEqual(len(same), 1, 'listed once')
        self.assertEqual((same[0]['id'], same[0]['params_b'], same[0]['country'], same[0]['maker']), ('or/x', 1.0, x['country'], x['maker']))

    def test_openrouter_refresh_never_drops_them(self):
        # scripts/models.py rewrites data/models.json from OpenRouter; the official-card models live in their own file and
        # are merged at build time, so a refresh (here: a tiny OpenRouter answer) keeps every one of them.
        answer = [{'id': 'meta/llama-4-scout', 'name': 'Meta: Llama 4 Scout', 'hugging_face_id': 'meta-llama/Llama-4-Scout-17B-16E-Instruct',
                   'context_length': 1310720, 'created': 1}]
        with mock.patch.object(models_py, 'hf_total', return_value=108641793536):
            refreshed = {'models': models_py.build(answer, OPENROUTER)}
        merged = build.merge_models(refreshed, EXTRA)
        self.assertTrue({m['id'] for m in EXTRA['models']} <= {m['id'] for m in merged['models']})
        self.assertNotIn('models-extra', (ROOT / 'scripts' / 'models.py').read_text(encoding='utf-8'))

    def test_load_all_merges(self):
        *_, merged = build.load_all()
        self.assertEqual(len(merged['models']), len(build.merge_models(OPENROUTER, EXTRA)['models']))

class PageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data, feed, sources, uae, models = build.load_all()
        cls.models = models
        with tempfile.TemporaryDirectory() as d:
            cls.html, _ = build.render_page(data, feed, sources, uae, models, brand_dir=Path(d))
        raw = re.search(r'<script type="application/json" id="models-data">(.*?)</script>', cls.html, re.S).group(1)
        cls.slim = json.loads(raw)['models']

    def test_estimator_carries_maker_country_and_flags(self):
        self.assertEqual(len(self.slim), len(self.models['models']))
        cards = [s for s in self.slim if 'co' in s]
        self.assertEqual(len(cards), len(EXTRA['models']))
        by = {m['name']: m for m in EXTRA['models']}
        for s in cards:
            m = by.get(s['n'])
            if m is None:
                continue  # an OpenRouter entry enriched with its card's fields keeps OpenRouter's name and size
            self.assertEqual((s['mk'], s['co'], s['r'], s['u'], s['l'], s['b'], s['o']),
                             (m['maker'], m['country'], m['runnable'], m['card_url'], m['license'], m['params_b'], m['open']))
            self.assertEqual(s.get('ar'), m['arabic'])  # left out when the card does not say
        for s in self.slim:
            if 'co' not in s:
                self.assertFalse({'mk', 'r', 'u', 'l', 'ar'} & set(s), s['n'])
        self.assertEqual(sum(1 for s in self.slim if s.get('ar') is True), sum(1 for m in EXTRA['models'] if m['arabic'] is True))

    def test_picker_chip_and_my_hardware_markup(self):
        hw = self.html[self.html.index('id="estimator"'):]
        hw = hw[:hw.index('</section>')]
        self.assertIn('<span class="fl" data-i18n>Pick a model</span>', hw)
        self.assertIn('<button type="button" class="chip mp-ar js-only" id="model-ar" aria-pressed="false"><span data-i18n>Arabic models</span>', hw)
        self.assertIn('<div class="myhw js-only" id="myhw">', hw)
        self.assertIn('<select id="myhw-sel" class="inp"></select>', hw)
        # Every product card can be marked as My hardware; the tag starts hidden (app.js shows it).
        n = self.html.count('class="product ')
        self.assertEqual(self.html.count('class="myhw-btn js-only" data-myhw="'), n)
        self.assertEqual(self.html.count('<span class="myhw-tag" hidden><span data-i18n>My hardware</span></span>'), n)
        self.assertIn('(q|vendor|level|scope|sort|dir|view|cmp|p|bits|extra|fit|m|arabic)(=|&|$)', self.html)

    def test_every_new_label_has_arabic(self):
        for text in ('Pick a model', 'Arabic models', 'Chat only — no download', 'My hardware', 'None selected', 'Qatar', 'Saudi Arabia', 'UAE',
                     '{name} is chat only: its maker offers it in an online chat and has not published weights to download, so no hardware on this page can run it.',
                     'size from the official model card', 'Made by {maker} · {country}', 'Supports Arabic', 'License: {l}', 'Model card', 'Official page',
                     'Choose from {n} models listed on OpenRouter (list updated {d}) and {x} UAE and Gulf models from their official model cards, or enter a size below.',
                     'Arabic models only: {n} whose official model card lists Arabic. Choose one, or enter a size below.',
                     'Choose the GPU or system you have to see which AI models fit it. It is saved in this browser only.',
                     'With {hw}: {fit}', '{n} of {m} models fit {hw} at this precision, largest first:',
                     'No model with a published size fits {hw} at this precision. Try a lower precision.',
                     'This memory is a total across several GPUs: the model has to be split across them.',
                     'Saved as My hardware', 'My hardware cleared', 'Show all {n} models', 'Show fewer', 'Clear'):
            self.assertTrue(ar_key(text), text)
        for country in build.EXTRA_COUNTRIES:
            self.assertTrue(ar_key(country), country)

    def test_my_hardware_is_kept_in_this_browser_only(self):
        # localStorage only through the try/catch wrapper (the page works without it), under one key; never in the URL.
        uses = [line for line in JS.splitlines() if 'localStorage.' in line]
        self.assertEqual(len(uses), 1, 'localStorage is used only inside the store wrapper')
        self.assertTrue(uses[0].strip().startswith('const store = {') and uses[0].count('try{') == 3, uses[0])
        self.assertIn("const MYHW_KEY = 'atlas-myhw'", JS)
        self.assertNotIn('myhw', re.search(r'const PARAMS = \{[^}]*\}', JS).group(0))

class AppTests(unittest.TestCase):
    def test_models_json_for_the_app(self):
        data, feed, sources, uae, models = build.load_all()
        docs = build.learn.load()
        out = app_data.payloads(data, feed, sources, uae, models, *docs)['models.json']['models']
        cards = [m for m in out if 'country' in m]
        self.assertEqual(len(cards), len(EXTRA['models']))
        by = {m['id']: m for m in EXTRA['models']}
        # As build.merge_models: a card model OpenRouter also lists keeps OpenRouter's name, size and context and gains
        # the card's maker, country and flags. data/models.json is rewritten from OpenRouter on every scheduled run, so
        # OpenRouter starting to list a card model under the card's id is no failure.
        listed = {m['id']: m for m in OPENROUTER.get('models', [])}
        for m in cards:
            self.assertEqual(set(m), set(app_data.MODEL_KEYS) | set(app_data.EXTRA_MODEL_KEYS))
            want = by.get(m['id'])
            if not want:
                continue
            for k in app_data.EXTRA_MODEL_KEYS:
                self.assertEqual(m[k], want[k], (m['id'], k))
            base = listed.get(m['id'], want)
            for k in app_data.MODEL_KEYS:
                self.assertEqual(m[k], base.get(k), (m['id'], k))
        self.assertTrue(any(m['runnable'] is False and m['params_b'] is None for m in cards), 'chat-only models are exported, unsized')

if __name__ == '__main__':
    unittest.main()
