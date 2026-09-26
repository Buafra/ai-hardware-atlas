"""Learn AI page (scripts/learn.py): data rules, the page without JavaScript, links, escaping and the build entry point."""
import copy
import json
import re
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import learn

ARABIC = re.compile(r'[؀-ۿ]')
SITE = 'https://buafra.github.io/ai-hardware-atlas/'

def catalog():
    return json.loads((ROOT / 'data' / 'catalog.json').read_text(encoding='utf-8'))

def counts(concepts_doc, stacks_doc):
    """(concepts, AI stacks, foundations) from the data, so adding or removing an item never breaks these tests."""
    kinds = [s['kind'] for s in stacks_doc['stacks']]
    return len(concepts_doc['concepts']), kinds.count('stack'), kinds.count('foundation')

class Page(HTMLParser):
    """Collects the elements the tests look at: items, links, scripts, styles, images and meta tags."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items, self.links, self.metas, self.scripts, self.external = [], [], {}, [], []
        self.stack, self.text_by_lang = [], {'en': [], 'ar': []}
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'details':
            self.items.append(a)
        if tag == 'a':
            self.links.append(a)
        if tag == 'meta':
            self.metas[a.get('property') or a.get('name')] = a.get('content')
        if tag == 'script':
            self.scripts.append(a)
        for k in ('src', 'srcset', 'poster', 'data'):
            if a.get(k) and not a[k].startswith(('data:', 'brand/')):
                self.external.append((tag, k, a[k]))
        if tag == 'link' and a.get('href') and not a['href'].startswith(('data:', 'brand/')):
            self.external.append((tag, 'href', a['href']))
        if tag not in ('br', 'img', 'meta', 'link', 'input', 'hr', 'source', 'wbr'):
            self.stack.append(a.get('data-lang'))
    def handle_endtag(self, tag):
        if tag not in ('br', 'img', 'meta', 'link', 'input', 'hr', 'source', 'wbr') and self.stack:
            self.stack.pop()
    def handle_data(self, data):
        langs = [x for x in self.stack if x]
        if langs:
            self.text_by_lang[langs[-1]].append(data)

class Quiet:
    """Membership checks on the whole page that report the missing text, not the 1.3 MB page."""
    def has(self, needle, page):
        self.assertTrue(needle in page, f'missing: {needle[:120]!r}')
    def lacks(self, needle, page):
        self.assertFalse(needle in page, f'unexpected: {needle[:120]!r}')
    def lacks_re(self, pattern, page):
        m = re.search(pattern, page)
        self.assertFalse(m, f'unexpected: {m.group(0)[:120]!r}' if m else '')

class DataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.concepts, cls.stacks = learn.load()
        cls.products = catalog()['products']
    def test_repository_data_passes_validation(self):
        learn.validate(self.concepts, self.stacks, self.products)
    def test_counts(self):
        # Lower bounds and relations only: the owner can add or remove concepts and stacks without editing this test.
        n_c, n_core, n_found = counts(self.concepts, self.stacks)
        self.assertGreaterEqual(len(self.concepts['groups']), 1)
        self.assertGreaterEqual(n_c, len(self.concepts['groups']))
        self.assertTrue(n_core >= 1 and n_found >= 1)
        self.assertEqual(n_core + n_found, len(self.stacks['stacks']))
        for g in self.concepts['groups']:
            self.assertTrue(any(c['group'] == g['id'] for c in self.concepts['concepts']), f'topic {g["id"]} has no concepts')
    def test_every_concept_and_stack_is_bilingual(self):
        for x in self.concepts['concepts'] + self.stacks['stacks']:
            self.assertTrue(ARABIC.search(x['title_ar']) and ARABIC.search(x['summary_ar']), x['id'])
    def broken(self, mutate, where='concepts'):
        c, s = copy.deepcopy(self.concepts), copy.deepcopy(self.stacks)
        mutate(c if where == 'concepts' else s)
        with self.assertRaises(learn.LearnDataError) as cm:
            learn.validate(c, s, self.products)
        return str(cm.exception)
    def test_validation_catches_each_rule(self):
        cases = {
            'duplicate concept id': (lambda c: c['concepts'][1].update(id=c['concepts'][0]['id']), 'concepts'),
            'empty': (lambda c: c['concepts'][0].update(summary_ar='  '), 'concepts'),
            'no Arabic version': (lambda c: c['concepts'][0].pop('example_ar'), 'concepts'),
            'items but': (lambda c: c['concepts'][0]['practices_ar'].pop(), 'concepts'),
            'related concept': (lambda c: c['concepts'][0]['related'].append('no-such-concept'), 'concepts'),
            'https': (lambda c: c['concepts'][0]['sources'][0].update(url='http://example.com/'), 'concepts'),
            'not a page of this site': (lambda c: c['concepts'][0]['site_links'].append({'label_en': 'x', 'label_ar': 'س', 'href': 'javascript:alert(1)'}), 'concepts'),
            'unknown group': (lambda c: c['concepts'][0].update(group='g9'), 'concepts'),
            'unknown level': (lambda c: c['concepts'][0].update(level='expert'), 'concepts'),
            'as_of': (lambda c: c['concepts'][0].update(as_of='September 2026'), 'concepts'),
            'duplicate stack id': (lambda s: s['stacks'][1].update(id=s['stacks'][0]['id']), 'stacks'),
            'related stack': (lambda s: s['stacks'][0]['related_stacks'].append('no-such-stack'), 'stacks'),
            'related concept \'nope\'': (lambda s: s['stacks'][0]['related_concepts'].append('nope'), 'stacks'),
            'not in data/catalog.json': (lambda s: s['stacks'][0]['hardware_links'].append({'label_en': 'x', 'label_ar': 'س', 'href': '#hardware/p/no-such-gpu'}), 'stacks'),
            'not a hardware route': (lambda s: s['stacks'][0]['hardware_links'].append({'label_en': 'x', 'label_ar': 'س', 'href': 'https://example.com/'}), 'stacks'),
            'kind must be': (lambda s: s['stacks'][0].update(kind='recipe'), 'stacks'),
            'must be an https URL': (lambda s: s['stacks'][0]['layers'][0]['options']['local'][0].update(url='javascript:alert(1)'), 'stacks'),
            'note_ar is empty': (lambda s: s['stacks'][0]['layers'][0]['options']['local'][0].update(note_ar=''), 'stacks'),
            'options must be grouped': (lambda s: s['stacks'][0]['layers'][0]['options'].update(other=[]), 'stacks'),
            # Problems that used to pass validation (or crash it) and then break the page.
            'needs a name, an https url and notes': (lambda s: s['stacks'][0]['layers'][0]['options']['local'][0].pop('url'), 'stacks'),
            'pick needs a name and a reason': (lambda s: s['stacks'][0]['layers'][0].update(pick='just a name'), 'stacks'),
            'layer 0: must be an object': (lambda s: s['stacks'][0]['layers'].insert(0, 'not a layer'), 'stacks'),
            'is not a catalog vendor': (lambda s: s['stacks'][0]['hardware_links'].append({'label_en': 'x', 'label_ar': 'س', 'href': '#hardware/vendor/"><b>x'}), 'stacks'),
            'takes nothing after it': (lambda s: s['stacks'][0]['hardware_links'].append({'label_en': 'x', 'label_ar': 'س', 'href': '#hardware/run/anything'}), 'stacks'),
            'must open the estimator': (lambda s: s['stacks'][0]['hardware_links'].append({'label_en': 'What can it run? estimator', 'label_ar': 'س', 'href': '#hardware'}), 'stacks'),
            'is not in data/uae.json': (lambda c: c['concepts'][0]['site_links'].append({'label_en': 'x', 'label_ar': 'س', 'href': '#uae/f/no-such-fact'}), 'concepts'),
            "'#news/nowhere' is not a page of this site": (lambda c: c['concepts'][0]['site_links'].append({'label_en': 'x', 'label_ar': 'س', 'href': '#news/nowhere'}), 'concepts'),
            'summary_ar is not Arabic text': (lambda c: c['concepts'][0].update(summary_ar='An English sentence where the Arabic should be.'), 'concepts'),
            'title_ar has no Arabic letters': (lambda s: s['stacks'][0].update(title_ar='English title'), 'stacks'),
        }
        for want, (mutate, where) in cases.items():
            self.assertIn(want, self.broken(mutate, where), want)
    def test_overview_links_open_what_their_label_names(self):
        # UAE chips open the fact they name (not the top of #uae, where the headlines come first), and estimator chips
        # open the estimator (not the top of #hardware).
        facts = learn.uae_fact_ids()
        links = [l for c in self.concepts['concepts'] for l in c.get('site_links') or []]
        links += [l for s in self.stacks['stacks'] for l in s.get('hardware_links') or []]
        uae = [l['href'] for l in links if l['href'].startswith('#uae')]
        self.assertTrue(uae and all(h[len('#uae/f/'):] in facts for h in uae if h != '#uae'), uae)
        self.assertEqual([l['label_en'] for l in links if l['href'] == '#uae'], ['AI in the UAE'])
        for l in links:
            if 'What can it run?' in l['label_en']:
                self.assertIn(l['href'], ('#hardware/run', '#estimator'), l['label_en'])
    def test_validate_reads_the_uae_facts_by_default(self):
        c = copy.deepcopy(self.concepts)
        c['concepts'][0]['site_links'].append({'label_en': 'x', 'label_ar': 'س', 'href': '#uae/f/jais-arabic-llm'})
        learn.validate(c, self.stacks, self.products)
        with self.assertRaises(learn.LearnDataError):
            learn.validate(c, self.stacks, self.products, fact_ids=set())
    def test_all_problems_are_listed_together(self):
        def two(c):
            c['concepts'][0]['related'].append('missing-a')
            c['concepts'][1]['related'].append('missing-b')
        msg = self.broken(two)
        self.assertIn('missing-a', msg)
        self.assertIn('missing-b', msg)

class PageTests(Quiet, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.concepts, cls.stacks = learn.load()
        cls.catalog = catalog()
        cls.html = learn.render(cls.concepts, cls.stacks, cls.catalog)
        cls.page = Page()
        cls.page.feed(cls.html)
        cls.head = cls.html[:cls.html.index('<style>')]
    def test_head_title_icons_and_share_preview(self):
        self.has('<title>Learn AI · Cipher Lacuna</title>', self.head)
        self.has('<html lang="en" dir="ltr">', self.head)
        self.has('<link rel="icon" type="image/png" sizes="32x32" href="brand/icon-32.png"><link rel="icon" type="image/svg+xml" href="data:image/svg+xml,', self.head)
        self.has('<link rel="apple-touch-icon" href="brand/apple-touch-icon.png">', self.head)
        m = self.page.metas
        self.assertEqual(m['og:url'], SITE + 'learn.html')
        self.assertEqual(m['og:image'], SITE + 'brand/og.png')
        self.assertEqual(m['twitter:image'], SITE + 'brand/og.png')
        self.assertEqual(m['og:title'], 'Learn AI · Cipher Lacuna')
        self.assertEqual((m['og:locale'], m['og:locale:alternate']), ('en_US', 'ar_AE'))
        n_c, n_core, n_found = counts(self.concepts, self.stacks)
        # The share text counts like the status bar: AI stacks plus foundations, not their sum.
        self.assertIn(f'{n_c} key AI concepts', m['description'])
        self.assertIn(f'{n_core} recommended AI stacks', m['description'])
        self.assertIn(learn.cnt(n_found, 'foundation', 'en') + ' that apply to every stack', m['description'])
    def test_every_item_is_in_the_html_without_javascript(self):
        ids = [a.get('id') for a in self.page.items]
        concepts = [i for i in ids if i.startswith('concept/')]
        stacks = [a for a in self.page.items if a.get('id', '').startswith('stack/')]
        n_c, n_core, n_found = counts(self.concepts, self.stacks)
        self.assertEqual(sorted(concepts), sorted('concept/' + c['id'] for c in self.concepts['concepts']))
        self.assertEqual(len(stacks), n_core + n_found)
        self.assertEqual(sum(a.get('data-group') == 'core' for a in stacks), n_core)
        self.assertEqual(sum(a.get('data-group') == 'foundation' for a in stacks), n_found)
        self.assertFalse(any('hidden' in a or 'open' in a for a in self.page.items), 'items start closed and visible')
        # The full text is there, not just the titles: a body paragraph, a practice, a layer option and a pick.
        c, s = self.concepts['concepts'][5], self.stacks['stacks'][1]
        import html as h
        for text in (c['body_en'][-1], c['body_ar'][0], c['practices_ar'][-1], s['layers'][-1]['options']['local'][0]['note_ar'],
                     s['layers'][0]['pick']['why_en'], s['flow_ar'][-1], s['cost_ar']):
            self.has(h.escape(text), self.html)
    def test_arabic_is_present_and_marked(self):
        ar = ''.join(self.page.text_by_lang['ar'])
        en = ''.join(self.page.text_by_lang['en'])
        self.assertGreater(len(ARABIC.findall(ar)), 100000)
        self.assertLess(len(ARABIC.findall(en)), len(ARABIC.findall(ar)) / 50)  # English copies hold at most Arabic names
        for text in ('تعلّم الذكاء الاصطناعي', 'المفاهيم', 'التركيبات التقنية', 'اختيارنا للبداية', 'مستضاف في الإمارات', 'تابع قهوة و AI'):
            self.has(text, ar)
    def test_links(self):
        hrefs = [a.get('href', '') for a in self.page.links]
        for want in ('index.html#hardware', 'index.html#news', 'index.html#uae', 'index.html#contact', 'index.html'):
            self.assertIn(want, hrefs)
        learn_links = [a for a in self.page.links if a.get('href') == 'learn.html']
        self.assertTrue(learn_links and all(a.get('aria-current') == 'page' for a in learn_links))
        self.assertTrue(any(h.startswith('index.html#hardware/p/') for h in hrefs))
        self.assertIn('index.html#estimator', hrefs)
        pids = {p['id'] for p in self.catalog['products']}
        for h in hrefs:
            m = re.match(r'^index\.html#hardware/p/(.+)$', h)
            if m:
                self.assertIn(m.group(1), pids)
        # In-page chips point at items that exist.
        ids = {a.get('id') for a in self.page.items}
        for h in hrefs:
            if re.match(r'^#(concept|stack)/', h):
                self.assertIn(h[1:], ids)
        for a in self.page.links:
            h = a.get('href', '')
            self.assertFalse(h.lower().startswith(('javascript:', 'http:')), h)
            if h.startswith('https://') or a.get('target'):
                self.assertEqual((a.get('target'), a.get('rel')), ('_blank', 'noopener noreferrer'), h)
    def test_counts_agree(self):
        # The status bar and the AI stacks tab badge count AI stacks and foundations apart; the All chip counts both.
        n_c, n_core, n_found = counts(self.concepts, self.stacks)
        self.has(f'<span class="n" data-count="concepts">{n_c}</span>', self.html)
        self.has(f'<span class="n" data-count="stacks">{n_core}</span>', self.html)
        status = self.html[self.html.index('<p class="statusbar">'):]
        status = status[:status.index('</p>')]
        for kind, n in (('concept', n_c), ('stack', n_core), ('foundation', n_found)):
            self.has(f'<span data-lang="en">{learn.cnt(n, kind, "en")}</span><span data-lang="ar">{learn.cnt(n, kind, "ar")}</span>', status)
        stacks = self.html[self.html.index('<section id="stacks"'):]
        self.has(f'data-filter="" aria-pressed="true"><span data-lang="en">All</span><span data-lang="ar">الكل</span> <span class="n">{n_core + n_found}</span>', stacks)
    def test_uae_card_leads_with_headlines(self):
        xnav = self.html[self.html.index('<nav class="xnav"'):]
        xnav = xnav[:xnav.index('</nav>')]
        self.has('Latest UAE AI headlines, then key facts on strategy, compute and models, each with its source.', xnav)
        self.has('أحدث عناوين الذكاء الاصطناعي في الإمارات، ثم حقائق رئيسية', xnav)
    def test_series_name_stays_on_one_line_in_arabic(self):
        self.has('.l-nw{white-space:nowrap}', self.html)
        # Every Arabic «قهوة و AI» on the page is inside the no-wrap span.
        self.assertEqual(self.html.count('قهوة و AI'), self.html.count('<span class="l-nw">قهوة و AI</span>'))
        self.assertGreaterEqual(self.html.count('<span class="l-nw">قهوة و AI</span>'), 4)
        self.has('روابط دروس قهوة و AI تفتح حساب', ''.join(self.page.text_by_lang['ar']))
    def test_stack_icon_sits_in_the_title_row(self):
        for s in self.stacks['stacks']:
            if s.get('icon'):
                self.has(f'<span class="it-tl"><span class="s-ic" aria-hidden="true">{s["icon"]}</span><h4 class="it-t">', self.html)
    def test_lessons_and_as_of_notes(self):
        self.has('Qahwa &amp; AI lesson 04: What is a large language model?', self.html)
        self.has('<span class="l-nw">قهوة و AI</span>، الدرس 04: ما هو النموذج اللغوي الكبير؟', self.html)
        lessons = [a for a in self.page.links if 'lesson' in (a.get('class') or '')]
        self.assertTrue(lessons and all(a['href'] == 'https://www.instagram.com/qahwa.w.ai/' for a in lessons))
        self.has('As of September 2026', self.html)
        self.has('وفق معلومات سبتمبر 2026', self.html)
    def test_no_external_assets_and_no_contact_address(self):
        self.assertEqual(self.page.external, [])
        self.assertFalse(any(s.get('src') for s in self.page.scripts))
        self.lacks_re(r'@import|url\(\s*["\']?(https?:)?//', self.html)
        self.lacks('gmail', self.html)
        self.lacks_re(r'[\w.-]+@[\w-]+\.(com|ae|org|net)\b', self.html)
    def test_theme_and_language_share_the_overview_keys(self):
        js = (ROOT / 'web' / 'learn.js').read_text(encoding='utf-8')
        for key in ('atlas-theme', 'atlas-lang'):
            self.has(key, self.head)
            self.assertIn(key, js)
        self.has('id="lang"', self.html)
        self.has('id="theme"', self.html)
    def test_header_footer_and_follow_button(self):
        header = self.html[self.html.index('<header'):self.html.index('</header>')]
        self.has('class="brand-logo"', header)
        self.has('https://www.instagram.com/qahwa.w.ai/', header)
        footer = self.html[self.html.index('<footer'):self.html.index('</footer>')]
        self.assertEqual(footer.count('follow-btn'), 1)
        self.has('© 2026 Cipher Lacuna.', footer)
    def test_data_is_escaped(self):
        c, s = copy.deepcopy(self.concepts), copy.deepcopy(self.stacks)
        c['concepts'][0]['title_en'] = '<script>alert(1)</script>'
        c['concepts'][0]['summary_ar'] = '"><img src=x onerror=alert(2)>'
        s['stacks'][0]['layers'][0]['options']['local'][0]['name'] = '</bdi><b>x</b>'
        s['stacks'][0]['flow_en'][0] = 'A & B <i>'
        page = learn.render(c, s, self.catalog)
        self.lacks('<script>alert(1)', page)
        self.has('&lt;script&gt;alert(1)&lt;/script&gt;', page)
        self.lacks('<img src=x', page)
        self.has('&quot;&gt;&lt;img src=x onerror=alert(2)&gt;', page)
        self.has('&lt;/bdi&gt;&lt;b&gt;x&lt;/b&gt;', page)
        self.has('A &amp; B &lt;i&gt;', page)
    def test_standalone_home_name(self):
        page = learn.render(self.concepts, self.stacks, self.catalog, home='AI_Hardware_Atlas_2026.html')
        self.assertTrue('href="AI_Hardware_Atlas_2026.html#hardware/p/' in page)
        self.assertTrue('href="AI_Hardware_Atlas_2026.html#news"' in page)
        self.assertFalse(re.search(r'href="index\.html', page), 'a link still points at index.html')

class BuildTests(Quiet, unittest.TestCase):
    def test_build_writes_the_page_and_brand_files(self):
        with tempfile.TemporaryDirectory() as d:
            path = learn.build(Path(d))
            self.assertEqual(path, Path(d) / 'learn.html')
            text = path.read_text(encoding='utf-8')
            self.assertTrue(text.startswith('<!doctype html>'))
            self.has('id="concept/rag"', text)
            for f in ('og.png', 'apple-touch-icon.png', 'icon-32.png'):
                self.assertTrue((Path(d) / 'brand' / f).exists(), f)
    def test_build_refuses_bad_data(self):
        with tempfile.TemporaryDirectory() as d:
            c, s = learn.load()
            c['concepts'][0]['related'] = ['no-such-concept']
            (Path(d) / 'concepts.json').write_text(json.dumps(c, ensure_ascii=False), encoding='utf-8')
            (Path(d) / 'stacks.json').write_text(json.dumps(s, ensure_ascii=False), encoding='utf-8')
            with self.assertRaises(learn.LearnDataError):
                learn.build(Path(d) / 'out', data_dir=Path(d))
            self.assertFalse((Path(d) / 'out' / 'learn.html').exists())
    def test_landing_card_for_the_overview(self):
        card = learn.landing_card()
        n_c, n_core, _ = counts(*learn.load())
        self.assertTrue(card.startswith('<a class="xcard x-learn" href="learn.html">'))
        self.has(f'{learn.cnt(n_c, "concept", "en")} in plain language and {learn.cnt(n_core, "stack", "en")} to build with', card)
        self.has(f'{learn.cnt(n_c, "concept", "ar")} بلغة واضحة و{learn.cnt(n_core, "stack", "ar")} للبناء بها', card)
        self.has('<span data-lang="ar">تعلّم الذكاء الاصطناعي</span>', card)
    def test_helpers_load_without_the_pdf_library(self):
        # A Python without reportlab (the browser tests) still gets build.py's brand helpers and icons.
        mod = learn.site_without_pdf()
        logo, favicon = mod.brand_assets()
        self.assertTrue(logo.startswith('<img class="brand-logo"'))
        self.assertTrue(favicon.startswith('data:image/svg+xml,'))
        self.assertIn('arrow', mod.ICON)
        self.assertNotIn('canvas', vars(mod))
    def test_inline_assets_cannot_close_their_block(self):
        for name, closing in (('learn.js', '</script'), ('learn.css', '</style'), ('style.css', '</style')):
            self.lacks(closing, (ROOT / "web" / name).read_text(encoding="utf-8").lower())

if __name__ == '__main__':
    unittest.main()
