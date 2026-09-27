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
SITE = 'https://cipherlacuna.ae/'

def catalog():
    return json.loads((ROOT / 'data' / 'catalog.json').read_text(encoding='utf-8'))

def published(*numbers, **flags):
    """A Qahwa & AI document (the shape of data/qahwa.json, only what lesson_url reads) with these lessons published.
    flags (e.g. status='waiting') mark every post as not published."""
    return {'schema': 1, 'posts': [dict({'id': f'week-01-day-{n:02d}--1-learn-lesson-{n:02d}', 'kind': 'lesson', 'lesson': n}, **flags)
                                   for n in numbers]}

def concept(doc, cid):
    return next(c for c in doc['concepts'] if c['id'] == cid)

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
            # Lesson chips link to qahwa.html#lesson-NN: a real lesson number and both titles.
            'related_lessons[0] needs a lesson number (1 to 999)': (lambda c: concept(c, 'llm')['related_lessons'][0].update(lesson=0), 'concepts'),
            "related_lessons[1] needs a lesson number (1 to 999)": (lambda c: concept(c, 'llm')['related_lessons'][1].update(lesson=1000), 'concepts'),
            'related_lessons[2] needs a lesson number': (lambda c: concept(c, 'llm')['related_lessons'][2].update(lesson='6'), 'concepts'),
            'titles in both languages': (lambda c: concept(c, 'llm')['related_lessons'][0].pop('title_ar'), 'concepts'),
            'repeats lesson 4': (lambda c: concept(c, 'llm')['related_lessons'].append(dict(concept(c, 'llm')['related_lessons'][0])), 'concepts'),
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
    def test_content_policy_guard(self):
        # Learn text never pairs a UAE/GCC name with conflict, war, damage, sanctions, spyware or human-rights wording,
        # in English or Arabic (the owner's content policy): the removed rag-memory pitfall must fail validation.
        bad = {
            'en': "AWS's UAE region (me-central-1) has been disrupted since March 2026 after conflict damage.",
            'ar': 'فمنطقة AWS في الإمارات (me-central-1) تعاني اضطراباً منذ مارس 2026 بعد أضرار ناجمة عن النزاع.',
        }
        for lang, text in bad.items():
            msg = self.broken(lambda s: s['stacks'][0][f'pitfalls_{lang}'].__setitem__(0, text), 'stacks')
            self.assertIn('breaks the content policy', msg, lang)
            self.assertIn(f'pitfalls_{lang}[0]', msg, lang)
        for text in ('Saudi firms face US sanctions over chips', 'A war in the Gulf', 'Spyware claims about a Qatari ministry',
                     "AWS's UAE region has been down since March after drone attacks.", 'Export-control concerns about G42',
                     'The blockade of Qatar', 'Critics accused Abu Dhabi of a crackdown', 'Dubai data centre hit by strikes',
                     'تعطلت منطقة AWS في الإمارات بعد هجمات', 'بسبب الحَرب في الإمارات', 'بسبب الحـرب في الإمارات', 'مخاوف أمنية بشأن G42',
                     'The Dubаi region was bombed',  # a Cyrillic а
                     'Human rights groups criticised Abu Dhabi', 'حرب في الخليج', 'تقارير عن برامج التجسس في دبي',
                     'انتقادات لحقوق الإنسان في البحرين', 'فرضت واشنطن عقوبات على شركات في الإمارات', "Kuwait's grid was damaged"):
            self.assertTrue(learn.policy_problems(text, 'x'), text)
        # Neutral text, other countries' matters and words that only look like place names pass.
        for text in ('Test on Gulf dialect, not only MSA.', 'Report deepfake fraud to Dubai Police eCrime.',
                     'The EU AI Act bans social scoring; fines can reach EUR 35 million.', 'Over-broad permissions cause real damage.',
                     'وفي دولة الإمارات، يحدّد المرسوم بقانون عقوبات على نشر المعلومات الكاذبة.', 'النزاعات في الرياضيات والأدب',
                     'قطرة ماء في نزاع قانوني', 'تُدرج منطقة UAE North فحوص المحتوى الضار',
                     'Choosing edge hardware by peak TOPS alone, or ignoring Gulf heat that makes enclosed devices throttle or fail.',
                     'تجاهل حرارة الخليج التي تجعل الأجهزة تتعطّل', 'تعمل الخدمة دون انقطاع في دبي', 'معارض دبي التجارية للتقنية'):
            self.assertEqual(learn.policy_problems(text, 'x'), [], text)
        # The same guard covers the other fixed pages (data/uae.json, data/about.json) through validate().
        with tempfile.TemporaryDirectory() as d:
            uae = json.loads((ROOT / 'data' / 'uae.json').read_text(encoding='utf-8'))
            uae['facts'][0]['text_en'] = 'The UAE was hit by conflict damage.'
            (Path(d) / 'uae.json').write_text(json.dumps(uae, ensure_ascii=False), encoding='utf-8')
            with self.assertRaises(learn.LearnDataError) as cm:
                learn.validate(self.concepts, self.stacks, self.products, fixed_paths=(Path(d) / 'uae.json',))
            self.assertIn('uae.json.facts[0].text_en breaks the content policy', str(cm.exception))
        self.assertEqual(learn.fixed_content_problems(), [])
        # The hardware notes (data/catalog.json) are fixed content too.
        self.assertIn(learn.CATALOG, learn.FIXED_CONTENT)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'catalog.json').write_text(json.dumps({'products': [{'id': 'x', 'notes': 'Shipments to the UAE were halted by export controls.'}]}), encoding='utf-8')
            self.assertIn('catalog.json.products[0].notes breaks the content policy', learn.fixed_content_problems((Path(d) / 'catalog.json',))[0])
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
        # Qahwa & AI lesson 4 is published; the other lessons the concepts name are not (yet).
        cls.html = learn.render(cls.concepts, cls.stacks, cls.catalog, lessons_doc=published(4))
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
        self.has('روابط دروس قهوة و AI تفتح الدرس في صفحة دروس قهوة و AI.', ''.join(self.page.text_by_lang['ar']))
    def test_stack_icon_sits_in_the_title_row(self):
        for s in self.stacks['stacks']:
            if s.get('icon'):
                self.has(f'<span class="it-tl"><span class="s-ic" aria-hidden="true">{s["icon"]}</span><h4 class="it-t">', self.html)
    def test_lessons_and_as_of_notes(self):
        self.has('Qahwa &amp; AI lesson 04: What is a large language model?', self.html)
        self.has('<span class="l-nw">قهوة و AI</span>، الدرس 04: ما هو النموذج اللغوي الكبير؟', self.html)
        # Published lessons only, each opening its lesson on qahwa.html (same tab: a page of this site).
        lessons = [a for a in self.page.links if 'lesson' in (a.get('class') or '')]
        with_4 = [c['id'] for c in self.concepts['concepts'] if any(x['lesson'] == 4 for x in c.get('related_lessons') or [])]
        self.assertEqual(len(lessons), len(with_4))
        self.assertTrue(all(a['href'] == 'qahwa.html#lesson-04' and not a.get('target') for a in lessons))
        self.has('Qahwa &amp; AI lesson links open the lesson on the Qahwa &amp; AI lessons page.', self.html)
        self.has('As of September 2026', self.html)
        self.has('وفق معلومات سبتمبر 2026', self.html)
    def test_unpublished_lessons_are_never_named(self):
        # Titles of lessons that are not published yet stay off the page (no spoilers), in both languages.
        for c in self.concepts['concepts']:
            for les in c.get('related_lessons') or []:
                if les['lesson'] != 4:
                    self.lacks(f'lesson {les["lesson"]:02d}:', self.html)
                    self.lacks(f'الدرس {les["lesson"]:02d}:', self.html)
                    self.lacks(learn.esc(learn.lesson_title(les['title_en'])), self.html)
        # A concept with no published lesson has no lessons block at all; one with lesson 4 has it.
        for c in self.concepts['concepts']:
            item = self.html[self.html.index(f'id="concept/{c["id"]}"'):]
            item = item[:item.index('</details>')]
            has_4 = any(x['lesson'] == 4 for x in c.get('related_lessons') or [])
            self.assertEqual('<h5><span data-lang="en">Qahwa &amp; AI lessons</span>' in item, has_4, c['id'])
    def test_no_published_lesson_hides_every_block(self):
        for doc in (None, published(), published(4, status='waiting'), published(4, draft=True), published(999)):
            page = learn.render(self.concepts, self.stacks, self.catalog, lessons_doc=doc)
            self.lacks('class="lchip lesson"', page)
            self.lacks('<h5><span data-lang="en">Qahwa &amp; AI lessons</span>', page)
            self.lacks('lesson links open', page)
            self.lacks('What is a large language model?', page)
            # The card and the footer link to the lessons page stay.
            self.has('<a class="xcard x-qahwa l-qahwa" href="qahwa.html">', page)
    def test_qahwa_card_near_the_top(self):
        card = self.html[self.html.index('<a class="xcard x-qahwa l-qahwa" href="qahwa.html">'):]
        card = card[:card.index('</a>')]
        self.has('<span data-lang="en">Daily lessons from Qahwa &amp; AI</span><span data-lang="ar">دروس يومية من <span class="l-nw">قهوة و AI</span></span>', card)
        # Right under the page header, before the tabs.
        i = self.html.index('class="xcard x-qahwa')
        self.assertLess(self.html.index('<div class="ihead ih-learn">'), i)
        self.assertLess(i, self.html.index('<div class="l-tools">'))
        self.lacks('target=', card)
        self.lacks('Updated', card)
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
        # The footer links, in the overview's order, with the Qahwa & AI lessons page after Learn AI.
        nav = footer[footer.index('<nav class="foot-links"'):]
        self.assertEqual(re.findall(r'<a href="([^"]+)"', nav), ['index.html', 'index.html#hardware', 'index.html#news', 'index.html#uae',
                                                                 'learn.html', 'qahwa.html', 'index.html#contact', 'index.html#contact/about'])
        self.has('<a href="qahwa.html"><span data-lang="en">Qahwa &amp; AI lessons</span><span data-lang="ar">دروس <span class="l-nw">قهوة و AI</span></span></a>', nav)
        # The header keeps its six items (the lessons page is not a seventh).
        header_nav = header[header.index('<nav class="nav"'):]
        self.assertEqual(len(re.findall(r'<a href=', header_nav[:header_nav.index('</nav>')])), 6)
        self.lacks('qahwa.html', header)
    def test_qahwa_links_carry_the_language(self):
        # learn.js adds ?lang= to every qahwa.html link (card, footer, lesson chips) like app.js does for learn.html.
        js = (ROOT / 'web' / 'learn.js').read_text(encoding='utf-8')
        self.assertIn('a[href^="qahwa.html"]', js)
        self.assertIn("const wantQ = lang === 'ar' ? 'ar' : saved === 'ar' ? 'en' : '';", js)
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
    def test_build_uses_the_published_lessons_and_survives_bad_qahwa_data(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(learn.qahwa, 'page_doc', return_value=(published(4), [])):
                text = learn.build(Path(d)).read_text(encoding='utf-8')
            self.has('href="qahwa.html#lesson-04"', text)
            with mock.patch.object(learn.qahwa, 'page_doc', side_effect=ValueError('broken')):
                text = learn.build(Path(d)).read_text(encoding='utf-8')
            self.lacks('class="lchip lesson"', text)
            self.has('href="qahwa.html"', text)
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

class ReportDataTests(Quiet, unittest.TestCase):
    """data/learn/reports.json: free AI reports summarised in our own words, each linking to the publisher's own page."""
    @classmethod
    def setUpClass(cls):
        cls.doc = learn.load_reports()
        cls.reports = cls.doc['reports']
    def test_repository_reports_pass(self):
        self.assertEqual(learn.report_problems(self.doc), [])
        self.assertGreaterEqual(len(self.reports), 3)
        # Kept newest first in the file too, so a diff reads in page order.
        self.assertEqual([r['id'] for r in self.reports], [r['id'] for r in learn.sorted_reports(self.doc)])
    def test_links_stay_on_the_publishers_own_domains(self):
        for r in self.reports:
            name, group, domains = learn.report_org(r)
            for k in ('url', 'arabic_version_url'):
                if k in r:
                    host = learn.urlparse(r[k]).hostname
                    self.assertTrue(r[k].startswith('https://') and any(host == d or host.endswith('.' + d) for d in domains), (r['id'], r[k]))
        # Every allow-listed publisher points at a known organisation, and every organisation has a group.
        self.assertTrue(set(learn.REPORT_PUBLISHERS.values()) <= set(learn.REPORT_ORGS))
        self.assertTrue({g for _, g, _ in learn.REPORT_ORGS.values()} <= {g for g, _, _ in learn.REPORT_GROUPS})
    def test_text_and_links_only(self):
        # No images, logos, charts, page references or private evidence notes in the published data.
        for r in self.reports:
            self.assertTrue(set(r) <= set(learn.REPORT_KEYS), r['id'])
            self.assertTrue(3 <= len(r['findings_en']) == len(r['findings_ar']) <= 5, r['id'])
        raw = json.dumps(self.doc, ensure_ascii=False).lower()
        for word in ('evidence', '.png', '.jpg', '.svg', 'logo', 'pdftotext'):
            self.assertNotIn(word, raw)
    def broken(self, mutate, i=0):
        doc = copy.deepcopy(self.doc)
        mutate(doc['reports'][i])
        return '\n'.join(learn.report_problems(doc))
    def test_validation_catches_each_rule(self):
        gcc = next(i for i, r in enumerate(self.reports) if 'arabic_version_url' in r)
        cases = {
            'is not on the allow-list': lambda r: r.update(publisher='Gartner'),
            "is not on the publisher's own domain (mckinsey.com)": lambda r: r.update(publisher='McKinsey & Company', url='https://example.com/state-of-ai.pdf'),
            "'https://mckinsey.com.example.net/x' is not on the publisher's own domain": lambda r: r.update(publisher='McKinsey & Company', url='https://mckinsey.com.example.net/x'),
            'must be an https URL': lambda r: r.update(url='http://www.mckinsey.com/x'),
            'findings_en has 2 findings; give 3 to 5': lambda r: (r['findings_en'].__delitem__(slice(2, None)), r['findings_ar'].__delitem__(slice(2, None))),
            'findings_ar has 6 findings': lambda r: (r['findings_en'].extend(['One more.'] * (6 - len(r['findings_en']))),
                                                     r['findings_ar'].extend(['نتيجة أخرى.'] * (6 - len(r['findings_ar'])))),
            'items but findings_ar has': lambda r: r['findings_ar'].pop(),
            'access must be one of': lambda r: r.update(access='paid'),
            'region must be one of': lambda r: r.update(region='europe'),
            'topics must be a non-empty list of distinct topics': lambda r: r.update(topics=['agents', 'agents']),
            "topics must be a non-empty list": lambda r: r.update(topics=[]),
            "published must be a real date as YYYY-MM-DD or YYYY-MM, not '2026-02-30'": lambda r: r.update(published='2026-02-30'),
            "not 'September 2026'": lambda r: r.update(published='September 2026'),
            'is in the future': lambda r: r.update(published='2999-01'),
            "unknown field(s) ['image']": lambda r: r.update(image='https://www.mckinsey.com/chart.png'),
            "unknown field(s) ['evidence']": lambda r: r.update(evidence='page 3'),
            'why_ar is empty': lambda r: r.update(why_ar=' '),
            'why_ar is not Arabic text': lambda r: r.update(why_ar='An English sentence where the Arabic should be.'),
            'title_ar has no Arabic letters': lambda r: r.update(title_ar='English title'),
            'characters; keep it under 320': lambda r: r['findings_en'].__setitem__(0, 'x' * 321),
            'quotes 9 words': lambda r: r['findings_en'].__setitem__(0, 'The report says "AI will change every part of how we work" today.'),
            'title_en missing': lambda r: r.pop('title_en'),
            'publisher is empty': lambda r: r.update(publisher=''),
        }
        for want, mutate in cases.items():
            self.assertIn(want, self.broken(mutate), want)
        self.assertIn('arabic_version_url', self.broken(lambda r: r.update(arabic_version_url='https://example.com/ar'), gcc))
        doc = copy.deepcopy(self.doc)
        doc['reports'][1]['id'] = doc['reports'][0]['id']
        doc['reports'][2]['url'] = doc['reports'][0]['url']
        msg = '\n'.join(learn.report_problems(doc))
        self.assertIn('duplicate report id', msg)
        self.assertIn('url is the same as report', msg)
        self.assertEqual(learn.report_problems({'items': []}), ['reports.json must be {"reports": [...]}'])
        # A short quoted term is fine; a date a report gives as a month only is fine.
        self.assertEqual(self.broken(lambda r: r.update(published='2026-01')), '')
        self.assertEqual(self.broken(lambda r: r['findings_en'].__setitem__(0, "Only 5% ('future-built') firms get value.")), '')
    def test_content_policy_guard_covers_reports(self):
        for lang, text in (('en', 'Saudi firms face sanctions over chips.'), ('ar', 'فرضت واشنطن عقوبات على شركات في الإمارات.')):
            msg = self.broken(lambda r: r[f'findings_{lang}'].__setitem__(0, text))
            self.assertIn(f'reports.reports[0].findings_{lang}[0] breaks the content policy', msg, lang)
        self.assertIn('why_en breaks the content policy', self.broken(lambda r: r.update(why_en='Critics accused the UAE of a crackdown.')))
    def test_validate_includes_the_reports(self):
        concepts, stacks = learn.load()
        products = catalog()['products']
        learn.validate(concepts, stacks, products)  # the repository reports, read by default
        bad = copy.deepcopy(self.doc)
        bad['reports'][0]['url'] = 'https://example.com/copy.pdf'
        with self.assertRaises(learn.LearnDataError) as cm:
            learn.validate(concepts, stacks, products, reports_doc=bad)
        self.assertIn("is not on the publisher's own domain", str(cm.exception))
        learn.validate(concepts, stacks, products, reports_doc={'reports': []})
    def test_group_follows_the_region(self):
        by_id = {r['id']: r for r in self.reports}
        for r in self.reports:
            want = 'gcc' if r['region'] in ('uae', 'gcc') else learn.report_org(r)[1]
            self.assertEqual(learn.report_group(r), want, r['id'])
        self.assertTrue(all(learn.report_group(r) in {g for g, _, _ in learn.REPORT_GROUPS} for r in by_id.values()))
    def test_dates(self):
        self.assertEqual(learn.report_date('2026-08-25', 'en'), '25 August 2026')
        self.assertEqual(learn.report_date('2026-08-25', 'ar'), '25 أغسطس 2026')
        self.assertEqual(learn.report_date('2026-01', 'en'), 'January 2026')
        self.assertEqual(learn.report_date('2026-01', 'ar'), 'يناير 2026')
        self.assertEqual(learn.cnt(29, 'report', 'ar'), '29 تقريراً')
        self.assertEqual(learn.cnt(1, 'report', 'en'), '1 report')

class ReportPageTests(Quiet, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.concepts, cls.stacks = learn.load()
        cls.doc = learn.load_reports()
        cls.reports = learn.sorted_reports(cls.doc)
        cls.html = learn.render(cls.concepts, cls.stacks, catalog())
        cls.panel = cls.html[cls.html.index('<section id="reports"'):]
        cls.panel = cls.panel[:cls.panel.index('</section>\n')]
        cls.page = Page()
        cls.page.feed(cls.html)
    def test_third_tab_and_status(self):
        n = len(self.reports)
        self.has(f'<a class="l-tab" href="#reports" data-tab="reports"><span data-lang="en">Reports</span><span data-lang="ar">التقارير</span> '
                 f'<span class="n" data-count="reports">{n}</span></a></nav>', self.html)
        status = self.html[self.html.index('<p class="statusbar">'):]
        self.has(f'<span data-lang="en">{learn.cnt(n, "report", "en")}</span><span data-lang="ar">{learn.cnt(n, "report", "ar")}</span>',
                 status[:status.index('</p>')])
        # Tabs, then the three panels in order, then the editorial note: the existing tabs keep their place.
        i = [self.html.index(f'<section id="{p}" class="l-panel" data-panel="{p}"') for p in ('concepts', 'stacks', 'reports')]
        self.assertEqual(i, sorted(i))
        self.assertLess(i[2], self.html.index('<p class="muted l-note">'))
        self.has("/^#report/.test(location.hash)?'reports'", self.html)
        self.has('placeholder="Search concepts, stacks and reports…"', self.html)
    def test_every_report_is_in_the_html_newest_first(self):
        ids = [a['id'][len('report/'):] for a in self.page.items if a.get('id', '').startswith('report/')]
        self.assertEqual(ids, [r['id'] for r in self.reports])
        import html as h
        for r in self.reports:
            item = self.panel[self.panel.index(f'id="report/{r["id"]}"'):]
            item = item[:item.index('</details>')]
            for text in (r['title_en'], r['title_ar'], r['why_en'], r['why_ar'], r['findings_en'][-1], r['findings_ar'][0], r['publisher']):
                self.has(h.escape(text), item)
            self.has(f'data-group="{learn.report_group(r)}" data-topics="{" ".join(r["topics"])}" data-year="{r["published"][:4]}"', item)
            self.has(f'<time datetime="{r["published"]}">', item)
            self.has(f'<a class="r-link" href="{h.escape(r["url"])}" target="_blank" rel="noopener noreferrer">', item)
            self.has(f'Read the report on <bdi lang="en" dir="ltr">{h.escape(learn.report_org(r)[0])}</bdi>', item)
            self.has(learn.L(*learn.REPORT_REGIONS[r['region']]), item)
            self.has(learn.L(*learn.REPORT_ACCESS[r['access']]), item)
            if r.get('arabic_version_url'):
                self.has(f'href="{h.escape(r["arabic_version_url"])}" hreflang="ar" target="_blank" rel="noopener noreferrer"', item)
            self.assertEqual('r-reg' in item, r['access'] == 'free-registration', r['id'])
    def test_filters_and_note(self):
        groups = {g: sum(learn.report_group(r) == g for r in self.reports) for g, _, _ in learn.REPORT_GROUPS}
        self.has(f'data-filter="" data-dim="group" aria-pressed="true"><span data-lang="en">All sources</span><span data-lang="ar">كل المصادر</span> <span class="n">{len(self.reports)}</span>', self.panel)
        for g, n in groups.items():
            self.has(f'data-filter="{g}" data-dim="group" aria-pressed="false">', self.panel)
        self.assertEqual(sum(groups.values()), len(self.reports))
        for y in {r['published'][:4] for r in self.reports}:
            self.has(f'<option value="{y}" data-en="{y}" data-ar="{y}">{y} ({sum(r["published"][:4] == y for r in self.reports)})</option>', self.panel)
        for t in {t for r in self.reports for t in r['topics']}:
            self.has(f'<option value="{t}"', self.panel)
        self.has('class="r-selects js-only"', self.panel)
        self.has('These summaries are ours and may simplify.', self.panel)
        self.has('هذه الملخصات من إعدادنا وقد تبسّط بعض التفاصيل.', self.panel)
        # Owner-approved notes: AI-written label, no affiliation, and a way for publishers to ask for a fix (the Contact page).
        self.has('Summaries were written with AI and checked against each report.', self.panel)
        self.has('is not affiliated with or endorsed by', self.panel)
        self.has('كُتبت الملخصات بالذكاء الاصطناعي وروجعت على نص كل تقرير.', self.panel)
        self.has('#contact">contact page</a>', self.panel)
        self.has('#contact">صفحة التواصل</a>', self.panel)
        self.assertGreater(self.panel.index('class="muted r-note"'), self.panel.rindex('</details>'))
    def test_no_images_and_no_other_hosts(self):
        self.lacks('<img', self.panel)
        self.lacks('<iframe', self.panel)
        self.assertEqual(self.page.external, [])
        hosts = {learn.urlparse(a['href']).hostname for a in self.page.links if a.get('class', '').startswith('r-link')}
        allowed = [d for _, _, ds in learn.REPORT_ORGS.values() for d in ds]
        self.assertTrue(hosts and all(any(h == d or h.endswith('.' + d) for d in allowed) for h in hosts), hosts)
    def test_render_takes_the_reports_it_is_given(self):
        one = {'reports': [copy.deepcopy(self.doc['reports'][0])]}
        page = learn.render(self.concepts, self.stacks, catalog(), reports_doc=one)
        self.has('<span class="n" data-count="reports">1</span>', page)
        self.assertEqual(page.count('class="l-item l-report"'), 1)
        empty = learn.render(self.concepts, self.stacks, catalog(), reports_doc={'reports': []})
        self.has('No reports yet.', empty)
        self.lacks('class="l-item l-report"', empty)
    def test_report_text_is_escaped(self):
        doc = copy.deepcopy(self.doc)
        doc['reports'][0]['title_en'] = '<script>alert(1)</script>'
        doc['reports'][0]['findings_ar'][0] = '"><img src=x onerror=alert(2)>'
        page = learn.render(self.concepts, self.stacks, catalog(), reports_doc=doc)
        self.lacks('<script>alert(1)', page)
        self.lacks('<img src=x', page)

class ReportBuildTests(Quiet, unittest.TestCase):
    def test_build_refuses_bad_reports(self):
        with tempfile.TemporaryDirectory() as d:
            c, s = learn.load()
            doc = learn.load_reports()
            doc['reports'][0]['url'] = 'https://mirror.example.org/report.pdf'
            for name, obj in (('concepts.json', c), ('stacks.json', s), ('reports.json', doc)):
                (Path(d) / name).write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')
            with self.assertRaises(learn.LearnDataError) as cm:
                learn.build(Path(d) / 'out', data_dir=Path(d))
            self.assertIn("is not on the publisher's own domain", str(cm.exception))
            self.assertFalse((Path(d) / 'out' / 'learn.html').exists())
    def test_build_writes_the_reports_tab(self):
        with tempfile.TemporaryDirectory() as d:
            text = learn.build(Path(d)).read_text(encoding='utf-8')
            self.has('id="report/' + learn.load_reports()['reports'][0]['id'] + '"', text)

if __name__ == '__main__':
    unittest.main()
