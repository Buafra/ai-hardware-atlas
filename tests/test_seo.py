"""Search basics (scripts/seo.py): robots.txt, the sitemap built from the pages in dist/, favicon.ico, the web app
manifest that never offers to install the website, the bilingual 404 page and JSON-LD from facts the site already has.
The last class builds the whole site into a temporary folder (no network) and checks what a visitor or a crawler gets."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build  # noqa: E402
import lang_pages  # noqa: E402
import seo  # noqa: E402

SITE = 'https://cipherlacuna.ae/'
BRAND = ROOT / 'web' / 'brand'

def ld_blocks(page):
    return [json.loads(x) for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)]

class FileTests(unittest.TestCase):
    def test_robots(self):
        text = seo.robots()
        self.assertTrue(text.startswith('User-agent: *\n'))
        self.assertIn('Disallow: /app/\nDisallow: /download/\n', text)
        self.assertIn(f'Sitemap: {SITE}sitemap.xml', text)
        self.assertNotIn('Disallow: /\n', text)

    def test_manifest_is_not_installable(self):
        m = seo.manifest(BRAND, 'A description.')
        # "browser" is not an app display mode, so Chrome on Android never offers to install the website (the app is the APK).
        self.assertEqual(m['display'], 'browser')
        self.assertNotIn('display_override', m)
        self.assertEqual((m['name'], m['start_url'], m['scope'], m['theme_color']), ('Cipher Lacuna', './', './', '#6537d7'))
        self.assertEqual([(i['src'], i['sizes']) for i in m['icons']], [('brand/icon-32.png', '32x32'), ('brand/apple-touch-icon.png', '180x180'),
                                                                       ('brand/icon-512.png', '512x512')])
        for i in m['icons']:
            self.assertTrue((BRAND / i['src'].split('/', 1)[1]).exists())

    def test_favicon(self):
        with tempfile.TemporaryDirectory() as d:
            path = seo.favicon(BRAND, Path(d) / 'favicon.ico')
            data = path.read_bytes()
            self.assertEqual(data[:4], b'\x00\x00\x01\x00')  # ICO header
            self.assertEqual(int.from_bytes(data[4:6], 'little'), 3)  # 16, 32 and 48 px
            self.assertIsNone(seo.favicon(Path(d), Path(d) / 'none.ico'))  # no brand icon: no file

    def test_404(self):
        page = seo.page_404('data:image/svg+xml,logo', 'data:image/svg+xml,icon')
        self.assertIn('<meta name="robots" content="noindex">', page)
        self.assertIn('<a class="btn" href="/">Go to the home page</a>', page)
        self.assertIn('<section class="card" lang="ar" dir="rtl"><h2>الصفحة غير موجودة</h2>', page)
        self.assertIn('<a class="btn" href="/ar/">اذهب إلى الصفحة الرئيسية</a>', page)
        # Served at any depth: every link starts at the site root; nothing comes from another host.
        for link in re.findall(r'\s(?:src|href)="([^"]+)"', page):
            self.assertTrue(link.startswith(('/', 'data:')), link)
        self.assertNotRegex(page, r'https?://(?!www\.w3\.org)')
        self.assertNotIn('<script', page)

    def test_sitemap_is_built_from_the_pages(self):
        head = lambda links: f'<!doctype html><html><head>{links}</head><body></body></html>'
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            pages = {'index.html': head(lang_pages.head_links('index.html', 'en')), 'ar/index.html': head(lang_pages.head_links('index.html', 'ar')),
                     'apk/index.html': head(f'<link rel="canonical" href="{SITE}apk/">'), 'weekly/2026-w42.html': head(''),
                     '404.html': head('<meta name="robots" content="noindex">'), 'draft.html': head('<meta name="robots" content="noindex">'),
                     'copy.html': head(f'<link rel="canonical" href="{SITE}">'), 'other.html': head('<link rel="canonical" href="https://example.com/">')}
            for name, text in pages.items():
                (out / name).parent.mkdir(parents=True, exist_ok=True)
                (out / name).write_text(text, encoding='utf-8')
            got = seo.sitemap_pages(out)
            self.assertEqual([loc for loc, _ in got], [SITE, SITE + 'apk/', SITE + 'ar/', SITE + 'weekly/2026-w42.html'])
            self.assertEqual(got[0][1], [('en', SITE), ('ar', SITE + 'ar/'), ('x-default', SITE)])
            xml = seo.sitemap(out)
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml.encode('utf-8'))
            ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9', 'x': 'http://www.w3.org/1999/xhtml'}
            self.assertEqual(len(root.findall('s:url', ns)), 4)
            self.assertEqual(len(root.findall('s:url/x:link', ns)), 6)

    def test_organization_has_no_contact_address(self):
        text = json.dumps(seo.website('en', 'Desc.'))
        self.assertNotIn('@', text.replace('"@', ''))
        self.assertNotIn('email', text)
        graph = seo.website('ar', 'وصف.')['@graph']
        self.assertEqual([g['@type'] for g in graph], ['WebSite', 'Organization'])
        self.assertEqual(graph[1]['slogan'], 'كشف المجهول في عالم الذكاء الاصطناعي')
        self.assertEqual(graph[1]['logo'], SITE + 'brand/icon-512.png')

class JsonLdPageTests(unittest.TestCase):
    """JSON-LD on the overview (WebSite + Organization), learn (ItemList of LearningResource), the lessons page and /apk/."""
    @classmethod
    def setUpClass(cls):
        cls.data, feed, sources, uae, models = build.load_all()
        cls.en, _ = build.render_page(cls.data, feed, sources, uae, models)
        cls.ar, _ = build.render_page(cls.data, feed, sources, uae, models, lang='ar')

    def test_overview(self):
        for page, lang in ((self.en, 'en'), (self.ar, 'ar')):
            blocks = ld_blocks(page)
            self.assertEqual(len(blocks), 1)
            site, org = blocks[0]['@graph']
            self.assertEqual((site['@type'], site['url'], site['name'], site['inLanguage']), ('WebSite', SITE, 'Cipher Lacuna', ['en', 'ar']))
            self.assertEqual(site['description'], build.meta_description(build.load_about(), lang))
            self.assertEqual(org['@id'], site['publisher']['@id'])
            self.assertNotIn('<', page[page.index('application/ld+json'):page.index('</script>', page.index('application/ld+json'))].split('>', 1)[1])

    def test_learn(self):
        concepts, stacks = build.learn.load()
        for lang in ('en', 'ar'):
            page = build.learn.render(concepts, stacks, self.data, lang=lang)
            (ld,) = ld_blocks(page)
            items = [x['item'] for x in ld['itemListElement']]
            self.assertEqual(ld['@type'], 'ItemList')
            self.assertEqual(ld['numberOfItems'], len(concepts['concepts']) + len(stacks['stacks']))
            self.assertEqual({x['@type'] for x in items}, {'LearningResource'})
            first = concepts['concepts'][0]
            self.assertEqual(items[0]['name'], first[f'title_{lang}'])
            self.assertEqual(items[0]['url'], lang_pages.url(lang_pages.twin('learn.html', lang)) + '#concept/' + first['id'])
            for x in items:
                self.assertIn(x['url'].split('#')[1], [f'concept/{c["id"]}' for c in concepts['concepts']] + [f'stack/{s["id"]}' for s in stacks['stacks']])

    def test_lessons_page(self):
        doc, _ = build.qahwa.page_doc()
        lessons = [p for p in doc['posts'] if p['kind'] == 'lesson']
        for lang in ('en', 'ar'):
            (ld,) = ld_blocks(build.qahwa.render(doc, build.qahwa.load_concepts(), lang=lang))
            self.assertEqual(ld['numberOfItems'], len(lessons))
            for row in ld['itemListElement']:
                x = row['item']
                self.assertTrue(x['url'].startswith(lang_pages.url(lang_pages.twin('qahwa.html', lang)) + '#lesson-'))
                self.assertTrue(x['sameAs'].startswith('https://www.instagram.com/'))
                self.assertNotIn('==', x['name'] + x['description'])

    def test_apk_page(self):
        info = {'tag': 'android-v1.2.0', 'version': '1.2.0', 'published': '2026-10-15T10:00:00Z', 'size': 2878160, 'sha256': 'ab' * 32}
        page = build.apk_page.render(info)
        (ld,) = ld_blocks(page)
        latest = build.android_app.latest(info)
        self.assertEqual(ld['@type'], 'SoftwareApplication')
        self.assertEqual((ld['softwareVersion'], ld['datePublished'], ld['downloadUrl']), (latest['version'], latest['published'], latest['url']))
        self.assertEqual(ld['operatingSystem'], f'Android {latest["min_android"]} or newer')
        self.assertEqual(ld['fileSize'], '2.7 MB')
        self.assertEqual(ld['url'], SITE + 'apk/')
        self.assertEqual(ld_blocks(build.apk_page.render(None)), [])  # no checked APK: no app facts

class BuiltSiteTests(unittest.TestCase):
    """The whole build in a temporary folder (no network: every news-image fetch fails), with a standalone copy."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        cls.out, cls.target = d / 'dist', d / 'site' / 'Atlas.html'
        cls.target.parent.mkdir()
        fake_pdf = lambda data: (cls.out / 'AI_Hardware_Atlas_2026_One_Page.pdf').write_bytes(b'%PDF-1.4\n')
        offline = mock.Mock(side_effect=build.news_images.Retry('offline'))
        with mock.patch.object(build, 'OUT', cls.out), mock.patch.object(build, 'pdf', fake_pdf), \
             mock.patch.object(sys, 'argv', ['build.py', '--standalone', str(cls.target)]), mock.patch('builtins.print'), \
             mock.patch.object(build.news_images, 'CACHE', d / 'cache'), mock.patch.object(build.news_images, 'fetch_page', offline), \
             mock.patch.object(build.news_images, 'download', offline), mock.patch.object(build.android_app, 'load', return_value=None):
            build.main()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_files(self):
        for name in ('index.html', 'ar/index.html', 'learn.html', 'ar/learn.html', 'qahwa.html', 'ar/qahwa.html', 'apk/index.html', '404.html',
                     'robots.txt', 'sitemap.xml', 'site.webmanifest', 'favicon.ico', 'news-en.xml', 'news-ar.xml', 'uae-en.xml', 'uae-ar.xml'):
            self.assertTrue((self.out / name).is_file(), name)
        # Nothing is copied into ar/: the Arabic pages use the site's files one folder up. ar/weekly/ holds the Arabic
        # weekly pages only (their stylesheet is weekly/weekly.css).
        self.assertEqual(sorted(f.name for f in (self.out / 'ar').iterdir()), ['index.html', 'learn.html', 'qahwa.html', 'weekly'])
        self.assertTrue((self.out / 'ar' / 'weekly' / 'index.html').is_file())
        self.assertEqual({f.suffix for f in (self.out / 'ar' / 'weekly').iterdir()}, {'.html'})

    def test_every_link_of_every_page_resolves(self):
        for page in sorted(self.out.rglob('*.html')):
            if page.name == '404.html':
                continue
            for link in lang_pages.relative_links(page.read_text(encoding='utf-8')):
                path = link.split('#')[0].split('?')[0]
                if not path:
                    continue
                target = (page.parent / path).resolve()
                self.assertTrue(target.exists(), f'{page.relative_to(self.out)}: {link}')

    def test_sitemap_lists_every_page_once(self):
        xml = (self.out / 'sitemap.xml').read_text(encoding='utf-8')
        locs = re.findall(r'<loc>([^<]+)</loc>', xml)
        # The weekly pages (weekly/ and ar/weekly/, scripts/weekly.py) are listed too, as the build wrote them.
        weeks = [lang_pages.url(f.relative_to(self.out).as_posix()) for f in self.out.rglob('*.html') if 'weekly' in f.relative_to(self.out).parts]
        self.assertIn(SITE + 'weekly/', weeks);self.assertIn(SITE + 'ar/weekly/', weeks)
        fixed = [SITE + 'apk/', SITE + 'ar/', SITE + 'ar/learn.html', SITE + 'ar/qahwa.html', SITE + 'learn.html', SITE + 'qahwa.html']
        self.assertEqual(locs, [SITE] + sorted(fixed + weeks))
        self.assertIn(f'<url><loc>{SITE}ar/weekly/</loc><xhtml:link rel="alternate" hreflang="en" href="{SITE}weekly/"/>'
                      f'<xhtml:link rel="alternate" hreflang="ar" href="{SITE}ar/weekly/"/>', xml)
        self.assertNotIn('404', ' '.join(locs))

    def test_canonical_on_home_and_learn(self):
        home = (self.out / 'index.html').read_text(encoding='utf-8')
        self.assertIn(f'<link rel="canonical" href="{SITE}">', home)
        self.assertIn(f'<link rel="canonical" href="{SITE}learn.html">', (self.out / 'learn.html').read_text(encoding='utf-8'))
        self.assertIn('<link rel="manifest" href="site.webmanifest">', home)
        self.assertIn('<link rel="manifest" href="../site.webmanifest">', (self.out / 'ar' / 'index.html').read_text(encoding='utf-8'))
        # The iPhone Home Screen tags stay.
        for tag in ('<link rel="apple-touch-icon" href="brand/apple-touch-icon.png">', '<meta name="apple-mobile-web-app-capable" content="yes">',
                    '<meta name="apple-mobile-web-app-title" content="Cipher Lacuna">'):
            self.assertIn(tag, home)

    def test_standalone_copy_has_its_arabic_twin(self):
        ar = (self.target.parent / 'ar' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<a class="btn-ghost" id="lang" href="../Atlas.html" hreflang="en" lang="en">', ar)
        self.assertIn("('ar','../Atlas.html',0)", ar)
        self.assertIn('<a class="btn-ghost" id="lang" href="ar/index.html" hreflang="ar" lang="ar">', self.target.read_text(encoding='utf-8'))
        for name in ('ar/learn.html', 'ar/qahwa.html', 'news-ar.xml', 'site.webmanifest'):
            self.assertTrue((self.target.parent / name).is_file(), name)
        self.assertIn('<a href="index.html" class="n-home">', (self.target.parent / 'ar' / 'learn.html').read_text(encoding='utf-8'))
        for page in (self.target, self.target.parent / 'ar' / 'index.html', self.target.parent / 'ar' / 'learn.html'):
            for link in lang_pages.relative_links(page.read_text(encoding='utf-8')):
                path = link.split('#')[0].split('?')[0]
                self.assertTrue(not path or (page.parent / path).exists(), f'{page.name}: {link}')

if __name__ == '__main__':
    unittest.main()
