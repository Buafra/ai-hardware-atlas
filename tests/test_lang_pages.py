"""The English and Arabic copies of the overview, Learn AI and the lessons page (scripts/lang_pages.py): the address
rule in the head (run in node), hreflang and canonical tags, the Arabic first paint from the scripts' own strings, and
the Arabic copies' links to the site's shared files."""
import html
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import lang_pages  # noqa: E402

NODE = shutil.which('node')
SITE = 'https://cipherlacuna.ae/'

def node_eval(js):
    out = subprocess.run([NODE, '-e', js], capture_output=True, text=True, encoding='utf-8', timeout=60)
    if out.returncode:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)

class JsStringsTests(unittest.TestCase):
    def test_escapes_comments_and_non_strings(self):
        js = r"""const X = {
          // a comment, with 'quotes', and a comma
          'a b':'one\u00a0two', "it's":"don\'t", plain: 'x, y', /* block, comment */ fn: (n) => `${n}, more`,
          nested: {k: 'v'}, num: 3, 'tab':'a\tb', 'uni':'\u{1F600}'
        };"""
        got = lang_pages.js_strings(js, 'const X = {')
        self.assertEqual(got, {'a b': 'one\u00a0two', "it's": "don't", 'plain': 'x, y', 'tab': 'a\tb', 'uni': '\U0001F600'})

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_app_js_arabic_table_matches_node(self):
        """Every string of app.js's AR table, read the way node reads it (the overview's Arabic first paint uses them)."""
        js = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')
        mine = lang_pages.js_strings(js, 'const AR = {')
        start = js.index('const AR = {') + len('const AR = ')
        end = js.index('\n  };', start) + 4
        theirs = node_eval('process.stdout.write(JSON.stringify(' + js[start:end] + '))')
        self.assertEqual(mine, {k: v for k, v in theirs.items() if isinstance(v, str)})
        self.assertGreater(len(mine), 200)

    @unittest.skipUnless(NODE, 'node is not installed')
    def test_qahwa_js_strings_match_node(self):
        js = (ROOT / 'web' / 'qahwa.js').read_text(encoding='utf-8')
        start = js.index('const T = {') + len('const T = ')
        end = js.index('\n  };', start) + 4
        theirs = node_eval('const T = ' + js[start:end] + ';process.stdout.write(JSON.stringify(T))')
        for lang in ('en', 'ar'):
            mine = lang_pages.js_strings(js, f'{lang}: {{', after='const T = {')
            self.assertEqual(mine, {k: v for k, v in theirs[lang].items() if isinstance(v, str)}, lang)
        self.assertEqual(lang_pages.js_strings(js, 'ar: {', after='const T = {')['title'], 'دروس قهوة و AI · Cipher Lacuna')

class AddressTests(unittest.TestCase):
    def test_urls_and_twins(self):
        self.assertEqual(lang_pages.url('index.html'), SITE)
        self.assertEqual(lang_pages.url('ar/index.html'), SITE + 'ar/')
        self.assertEqual(lang_pages.url('learn.html'), SITE + 'learn.html')
        self.assertEqual(lang_pages.url('apk/index.html'), SITE + 'apk/')
        self.assertEqual(lang_pages.twin('qahwa.html', 'ar'), 'ar/qahwa.html')
        self.assertEqual(lang_pages.twin('qahwa.html', 'en'), 'qahwa.html')

    def test_head_links(self):
        for page, en, ar in (('index.html', SITE, SITE + 'ar/'), ('learn.html', SITE + 'learn.html', SITE + 'ar/learn.html')):
            for lang in ('en', 'ar'):
                links = lang_pages.head_links(page, lang)
                self.assertEqual(re.findall(r'<link rel="canonical" href="([^"]+)">', links), [en if lang == 'en' else ar])
                self.assertEqual(re.findall(r'hreflang="([^"]+)" href="([^"]+)"', links), [('en', en), ('ar', ar), ('x-default', en)])

class RelocateTests(unittest.TestCase):
    def test_moved(self):
        cases = {'brand/icon-32.png': '../brand/icon-32.png', 'images/x.webp': '../images/x.webp', 'news-ar.xml': '../news-ar.xml',
                 'download/Cipher-Lacuna.apk': '../download/Cipher-Lacuna.apk', 'site.webmanifest': '../site.webmanifest',
                 # The paired pages stay: they have Arabic copies beside the page.
                 'index.html': 'index.html', 'learn.html#concept/rag': 'learn.html#concept/rag', 'qahwa.html?lang=en': 'qahwa.html?lang=en',
                 # Not site files.
                 '#news': '#news', 'https://www.nvidia.com/x': 'https://www.nvidia.com/x', 'data:image/svg+xml,x': 'data:image/svg+xml,x',
                 # Pages in the Arabic folder itself (the Arabic weekly pages): relative to it.
                 'ar/weekly/2026-w42.html': 'weekly/2026-w42.html', 'ar/weekly/index.html#x': 'weekly/index.html#x', 'weekly/index.html': '../weekly/index.html',
                 '../index.html': '../index.html', '/brand/x.png': '/brand/x.png', 'mailto:x': 'mailto:x', '': ''}
        for link, want in cases.items():
            self.assertEqual(lang_pages.moved(link), want, link)

    def test_scripts_are_untouched_and_css_urls_move(self):
        page = ('<link rel="icon" href="brand/a.png"><style>@font-face{src:url(fonts/q/a.woff2)}.x{mask:url("data:image/svg+xml,y")}'
                '</style><script>const s = `<img src="${f}">`; const h = \'<a href="brand/b.png">\';</script>'
                '<script type="application/json" id="d">{"file":"images/x.webp"}</script><img src="images/y.webp" alt="">')
        out = lang_pages.relocate(page)
        self.assertIn('<link rel="icon" href="../brand/a.png">', out)
        self.assertIn('src:url(../fonts/q/a.woff2)', out)
        self.assertIn('url("data:image/svg+xml,y")', out)
        self.assertIn('<script>const s = `<img src="${f}">`; const h = \'<a href="brand/b.png">\';</script>', out)
        self.assertIn('{"file":"images/x.webp"}', out)
        self.assertIn('<img src="../images/y.webp" alt="">', out)
        self.assertEqual(sorted(lang_pages.relative_links(out)), ['../brand/a.png', '../fonts/q/a.woff2', '../images/y.webp'])

class TranslateTests(unittest.TestCase):
    AR = {'Overview': 'الرئيسية', 'Follow Qahwa & AI': 'تابع قهوة و AI', 'Search news…': 'ابحث في الأخبار…', 'Main sections': 'الأقسام الرئيسية'}

    def test_overview_strings(self):
        page = ('<a href="#home" data-i18n>Overview</a><span data-i18n>Follow Qahwa &amp; AI</span><span data-i18n>No entry</span>'
                '<input placeholder="Search news…" data-i18n-ph="Search news…"><nav aria-label="Main sections" data-i18n-aria="Main sections">'
                '<p class="use" data-ar="للاستدلال">For inference</p><p data-ar="">Only English</p><span data-i18n-aria="Unknown" aria-label="Unknown">x</span>'
                '<script>el.innerHTML = \'<b data-i18n>Overview</b>\'</script>')
        out = lang_pages.translate_overview(page, self.AR)
        self.assertIn('<a href="#home" data-i18n data-en="Overview">الرئيسية</a>', out)
        self.assertIn('<span data-i18n data-en="Follow Qahwa &amp; AI">تابع قهوة و AI</span>', out)
        self.assertIn('<span data-i18n>No entry</span>', out)  # no Arabic string: stays English, as app.js leaves it
        self.assertIn('<input placeholder="ابحث في الأخبار…" data-i18n-ph="Search news…">', out)
        self.assertIn('<nav aria-label="الأقسام الرئيسية" data-i18n-aria="Main sections">', out)
        self.assertIn('<p class="use" data-ar="للاستدلال" data-en="For inference">للاستدلال</p>', out)
        self.assertIn('<p data-ar="">Only English</p>', out)
        self.assertIn('aria-label="Unknown"', out)
        self.assertIn("<script>el.innerHTML = '<b data-i18n>Overview</b>'</script>", out)  # scripts are never touched

    def test_keyed_strings(self):
        strings = {'skip': 'انتقل إلى الدروس', 'partOf': 'جزء من موقع <b>Cipher Lacuna</b>', 'searchPh': 'ابحث', 'linksLabel': 'روابط'}
        page = ('<a class="skip" href="#library" data-i18n="skip">Skip to the lessons</a><span data-i18n-html="partOf">Part of <b>Cipher Lacuna</b></span>'
                '<input id="q" data-i18n-ph="searchPh" placeholder="Search"><nav class="links" aria-label="Links" data-i18n-aria="linksLabel">'
                '<span data-i18n="none">Kept</span>')
        out = lang_pages.translate_keys(page, strings)
        self.assertIn('<a class="skip" href="#library" data-i18n="skip">انتقل إلى الدروس</a>', out)
        self.assertIn('<span data-i18n-html="partOf">جزء من موقع <b>Cipher Lacuna</b></span>', out)
        self.assertIn('<input id="q" data-i18n-ph="searchPh" placeholder="ابحث">', out)
        self.assertIn('aria-label="روابط"', out)
        self.assertIn('<span data-i18n="none">Kept</span>', out)

@unittest.skipUnless(NODE, 'node is not installed')
class HeadScriptTests(unittest.TestCase):
    """lang_script() run in node with a stand-in location, storage and navigator: where each visit goes."""
    def visit(self, page_lang, other, url, saved=None, nav='en-US', navigator=False):
        script = lang_pages.lang_script(page_lang, other, navigator)
        harness = (
            "const u = new URL(" + json.dumps(url) + "); let went = null;"
            "globalThis.location = {search: u.search, hash: u.hash, protocol: u.protocol, replace: x => { went = x; }};"
            "globalThis.localStorage = {getItem: k => k === 'atlas-lang' ? " + json.dumps(saved) + " : null};"
            "Object.defineProperty(globalThis, 'navigator', {value: {language: " + json.dumps(nav) + "}, configurable: true});"
            "globalThis.document = {documentElement: {style: {}}};"
            + script +
            "process.stdout.write(JSON.stringify([went, document.documentElement.style.visibility || '']));")
        return node_eval(harness)

    def test_english_page(self):
        en = ('en', 'ar/index.html')
        self.assertEqual(self.visit(*en, 'https://cipherlacuna.ae/'), [None, ''])
        self.assertEqual(self.visit(*en, 'https://cipherlacuna.ae/', saved='en'), [None, ''])
        # Old links and the saved choice go to the Arabic page, the query (without lang) and the view along.
        self.assertEqual(self.visit(*en, 'https://cipherlacuna.ae/?lang=ar#news'), ['ar/#news', 'hidden'])
        self.assertEqual(self.visit(*en, 'https://cipherlacuna.ae/?q=4090&lang=ar&view=table#hardware'), ['ar/?q=4090&view=table#hardware', 'hidden'])
        self.assertEqual(self.visit(*en, 'https://cipherlacuna.ae/index.html#uae', saved='ar'), ['ar/#uae', 'hidden'])
        # ?lang=en wins over a saved Arabic (and saves nothing); an unknown value is ignored.
        self.assertEqual(self.visit(*en, 'https://cipherlacuna.ae/?lang=en', saved='ar'), [None, ''])
        self.assertEqual(self.visit(*en, 'https://cipherlacuna.ae/?lang=xx'), [None, ''])
        # A copy opened from a file keeps the file name.
        self.assertEqual(self.visit(*en, 'file:///C:/site/index.html?lang=ar'), ['ar/index.html', 'hidden'])

    def test_arabic_page(self):
        ar = ('ar', '../index.html')
        self.assertEqual(self.visit(*ar, 'https://cipherlacuna.ae/ar/'), [None, ''])
        self.assertEqual(self.visit(*ar, 'https://cipherlacuna.ae/ar/', saved='en'), [None, ''])  # the address wins
        self.assertEqual(self.visit(*ar, 'https://cipherlacuna.ae/ar/?lang=ar'), [None, ''])
        self.assertEqual(self.visit(*ar, 'https://cipherlacuna.ae/ar/?lang=en&nq=g42#news'), ['../?nq=g42#news', 'hidden'])
        self.assertEqual(self.visit('ar', '../learn.html', 'https://cipherlacuna.ae/ar/learn.html?lang=en#concept/rag'), ['../learn.html#concept/rag', 'hidden'])

    def test_lessons_page_reads_the_browser_language(self):
        en = ('en', 'ar/qahwa.html')
        self.assertEqual(self.visit(*en, 'https://cipherlacuna.ae/qahwa.html', nav='ar-AE', navigator=True), ['ar/qahwa.html', 'hidden'])
        self.assertEqual(self.visit(*en, 'https://cipherlacuna.ae/qahwa.html', saved='en', nav='ar-AE', navigator=True), [None, ''])
        self.assertEqual(self.visit(*en, 'https://cipherlacuna.ae/qahwa.html', nav='ar-AE'), [None, ''])  # only where asked
        self.assertEqual(self.visit('ar', '../qahwa.html', 'https://cipherlacuna.ae/ar/qahwa.html', nav='en-US', navigator=True), [None, ''])

class PageTests(unittest.TestCase):
    """The three pages in Arabic, as the build writes them."""
    @classmethod
    def setUpClass(cls):
        import build
        cls.build = build
        data, feed, sources, uae, models = build.load_all()
        cls.en, _ = build.render_page(data, feed, sources, uae, models)
        cls.ar, _ = build.render_page(data, feed, sources, uae, models, lang='ar')
        concepts, stacks = build.learn.load()
        cls.learn_en = build.learn.render(concepts, stacks, data)
        cls.learn_ar = build.learn.render(concepts, stacks, data, lang='ar')
        doc, _ = build.qahwa.page_doc()
        cls.qahwa_en = build.qahwa.render(doc, build.qahwa.load_concepts())
        cls.qahwa_ar = build.qahwa.render(doc, build.qahwa.load_concepts(), lang='ar')

    def head(self, page):
        return page[:page.index('</head>')]

    def meta(self, page, key):
        m = re.search(r'<meta (?:name|property)="%s" content="([^"]*)">' % re.escape(key), page)
        return html.unescape(m.group(1)) if m else None

    def test_html_lang_title_and_share_tags(self):
        ar_title = 'Cipher Lacuna | ' + self.build.app_ar()['AI hardware, AI news and UAE AI']
        for page, lang, title, url in ((self.en, 'en', 'Cipher Lacuna | AI hardware, AI news and UAE AI', SITE), (self.ar, 'ar', ar_title, SITE + 'ar/'),
                                       (self.learn_en, 'en', 'Learn AI · Cipher Lacuna', SITE + 'learn.html'),
                                       (self.learn_ar, 'ar', 'تعلّم الذكاء الاصطناعي · Cipher Lacuna', SITE + 'ar/learn.html'),
                                       (self.qahwa_en, 'en', 'Qahwa & AI Lessons · Cipher Lacuna', SITE + 'qahwa.html'),
                                       (self.qahwa_ar, 'ar', 'دروس قهوة و AI · Cipher Lacuna', SITE + 'ar/qahwa.html')):
            head = self.head(page)
            self.assertIn(f'<html lang="{lang}" dir="{"rtl" if lang == "ar" else "ltr"}"', head, url)
            self.assertIn(f'<title>{html.escape(title)}</title>', head, url)
            self.assertEqual(self.meta(head, 'og:title'), title, url)
            self.assertEqual(self.meta(head, 'og:url'), url)
            self.assertEqual(re.findall(r'<link rel="canonical" href="([^"]+)">', head), [url])
            self.assertEqual(len(re.findall(r'<link rel="alternate" hreflang="(?:en|ar|x-default)"', head)), 3, url)
            self.assertEqual((self.meta(head, 'og:locale'), self.meta(head, 'og:locale:alternate')), (('ar_AE', 'en_US') if lang == 'ar' else ('en_US', 'ar_AE')), url)
            desc = self.meta(head, 'description')
            ar_letters = len(re.findall(r'[\u0600-\u06ff]', desc))
            self.assertTrue(ar_letters > 40 if lang == 'ar' else ar_letters == 0, (url, desc))
            self.assertIn("localStorage.getItem('atlas-lang')", head)  # the address rule runs before anything is drawn

    def test_overview_arabic_description_is_the_approved_promise(self):
        about = json.loads((ROOT / 'data' / 'about.json').read_text(encoding='utf-8'))
        self.assertEqual(self.meta(self.ar, 'description'), 'Cipher Lacuna: ' + about['promise']['ar'])

    def test_language_links_lead_to_the_twin(self):
        link = lambda page: re.search(r'<a class="btn-ghost" id="lang" href="([^"]+)" hreflang="(\w+)" lang="(\w+)">(.*?)</a>', page)
        self.assertEqual(link(self.en).groups()[:3], ('ar/index.html', 'ar', 'ar'))
        self.assertEqual(link(self.ar).groups()[:3], ('../index.html', 'en', 'en'))
        self.assertIn('English', link(self.ar).group(4))
        self.assertEqual(link(self.learn_en).groups()[:3], ('ar/learn.html', 'ar', 'ar'))
        self.assertEqual(link(self.learn_ar).groups()[:3], ('../learn.html', 'en', 'en'))
        self.assertIn('id="langBtn" href="ar/qahwa.html" hreflang="ar" lang="ar"', self.qahwa_en)
        self.assertIn('id="langBtn" href="../qahwa.html" hreflang="en" lang="en"', self.qahwa_ar)

    def test_arabic_overview_first_paint(self):
        ar = self.build.app_ar()
        markup = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', self.ar, flags=re.S)
        # Every [data-i18n] text that app.js translates is already Arabic, with the English key in data-en.
        leaves = re.findall(r'<[a-z0-9]+(?:\s[^<>]*?)?\sdata-i18n(?=[\s>])([^<>]*)>([^<]*)<', markup)
        self.assertGreater(len(leaves), 500)
        for attrs, text in leaves:
            en = re.search(r'data-en="([^"]*)"', attrs)
            self.assertTrue(en, text)
            self.assertEqual(html.unescape(text), ar[html.unescape(en.group(1))])
        for key in re.findall(r'data-i18n-ph="([^"]*)"', markup):
            self.assertIn(f'placeholder="{html.escape(ar[html.unescape(key)])}"', markup)
        self.assertIn('data-root="../"', self.head(self.ar))
        self.assertNotIn('i18n-wait', ''.join(re.findall(r'<script>(.*?)</script>', self.head(self.ar), re.S)))  # no waiting for app.js
        # The English page keeps its English texts (app.js reads them as keys).
        self.assertNotIn('data-en=', re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', self.en, flags=re.S))
        self.assertIn(f'<strong id="count" aria-live="polite">{self.build.cnt(len(self.build.load_all()[0]["products"]), "product", "ar")}</strong>', self.ar)

    def test_arabic_copies_share_the_site_files(self):
        for page, name in ((self.ar, 'ar/index.html'), (self.learn_ar, 'ar/learn.html'), (self.qahwa_ar, 'ar/qahwa.html')):
            for link in lang_pages.relative_links(page):
                path = link.split('#')[0].split('?')[0]
                # The site's files one folder up, the paired pages beside it, and the Arabic weekly pages (ar/weekly/).
                self.assertTrue(path.startswith('../') or path in lang_pages.PAGES or path.startswith('weekly/'), (name, link))
        self.assertIn('url(../fonts/qahwa/', self.qahwa_ar)
        self.assertIn('"root":"../"', self.qahwa_ar)
        self.assertIn('"root":""', self.qahwa_en)
        js = (ROOT / 'web' / 'qahwa.js').read_text(encoding='utf-8')
        self.assertIn("const BRAND = `${ROOT}brand/qahwa/`;", js)
        self.assertIn('esc(ROOT + it.cover)', js)
        app = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')
        self.assertIn('esc(ROOT + p.image.file)', app)

    def test_arabic_lessons_page_first_paint(self):
        strings = self.build.qahwa.strings('ar')
        for key in ('skip', 'follow', 'website', 'earlyH', 'searchLabel'):
            self.assertIn(f'data-i18n="{key}">{html.escape(strings[key], quote=False)}<', self.qahwa_ar, key)
        self.assertIn(f'placeholder="{html.escape(strings["searchPh"])}"', self.qahwa_ar)
        self.assertIn(strings['partOf'], self.qahwa_ar)

    def test_arabic_learn_labels(self):
        self.assertIn('<nav class="nav" aria-label="الأقسام الرئيسية" data-aria-ar="الأقسام الرئيسية" data-aria-en="Main sections">', self.learn_ar)
        self.assertIn('placeholder="ابحث في المفاهيم والتركيبات والتقارير والدورات…"', self.learn_ar)
        self.assertIn('aria-label="المظهر: تلقائي"', self.learn_ar)

    def test_learn_description_length(self):
        for page in (self.learn_en, self.learn_ar):
            self.assertLessEqual(len(self.meta(page, 'description')), self.build.learn.DESC_MAX)
        self.assertLessEqual(len(self.build.learn.description(999, 999, 999, 'en')), self.build.learn.DESC_MAX)
        self.assertLessEqual(len(self.build.learn.description(999, 999, 999, 'ar')), self.build.learn.DESC_MAX)

    def test_page_scripts_follow_the_address(self):
        app = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')
        self.assertIn("const PAGE_LANG = document.documentElement.getAttribute('lang') === 'ar' ? 'ar' : 'en';", app)
        self.assertIn('function urlQuery() { return encodeState({...state, lang: DEFAULTS.lang}); }', app)
        self.assertIn("langLink.setAttribute('href', pageUrl(langBase, urlQuery(), hashNow()));", app)
        self.assertIn("langLink.addEventListener('click', () => store.set('atlas-lang', PAGE_LANG === 'ar' ? 'en' : 'ar'));", app)
        self.assertNotIn("$('lang').addEventListener('click', () => { state.lang", app)  # no switching in place
        learn_js = (ROOT / 'web' / 'learn.js').read_text(encoding='utf-8')
        self.assertIn("store.set('atlas-lang', lang === 'ar' ? 'en' : 'ar');", learn_js)
        self.assertIn("const lang = d.lang === 'ar' ? 'ar' : 'en';", learn_js)
        qahwa_js = (ROOT / 'web' / 'qahwa.js').read_text(encoding='utf-8')
        self.assertIn("localStorage.setItem('atlas-lang', other(S.lang))", qahwa_js)
        self.assertNotIn('renderAll();\n  });', qahwa_js[qahwa_js.index("langBtn.addEventListener"):])

if __name__ == '__main__':
    unittest.main()
