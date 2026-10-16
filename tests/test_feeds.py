"""RSS feeds of the headlines (scripts/feeds.py): the page's own lists in each language, newest 50, the summary with who
wrote it and "via cipherlacuna.ae", RFC 822 dates, guids, topics, and well-formed XML."""
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build  # noqa: E402
import feeds  # noqa: E402

SOURCES = [{'id': 'g', 'name': 'Global Lab', 'name_ar': 'مختبر عالمي', 'homepage': 'https://lab.example/', 'region': 'global', 'lang': 'en', 'kind': 'primary'},
           {'id': 'u', 'name': 'Gulf Daily', 'name_ar': 'الخليج اليومي', 'homepage': 'https://gulf.example/', 'region': 'uae', 'lang': 'ar', 'kind': 'news'}]

def item(n, **kw):
    base = {'id': f'i{n:03d}', 'title': f'Lab releases model {n}', 'url': f'https://lab.example/{n}', 'source': 'g', 'lang': 'en', 'uae': False,
            'published': f'2026-10-{1 + n % 28:02d}T{n % 24:02d}:00:00+00:00'}
    base.update(kw)
    return base

def verified(i):
    """A UAE story with a passing content-policy verdict for its current texts (only such a story is shown)."""
    return dict(i, policy_ok=True, policy_version=build.policy.POLICY_VERSION, policy_hash=build.policy.fingerprint(i))

def channel(text):
    return ET.fromstring(text.encode('utf-8')).find('channel')

class FeedTests(unittest.TestCase):
    def setUp(self):
        self.items = [item(n) for n in range(70)] + [
            item(100, title='OpenAI opens an office', title_ar='OpenAI تفتح مكتباً', summary_source='ai', summary_en='An English summary <b>bold</b> & more.',
                 summary_ar='ملخص عربي.', published='2026-10-30T10:00:00+00:00'),
            verified(item(101, title='عنوان إماراتي عن الذكاء الاصطناعي', url='https://gulf.example/1', source='u', lang='ar', uae=True,
                          excerpt='نص من الناشر.', published='2026-10-30T09:00:00+00:00', topic='uae')),
            item(102, title='Hidden: not mainly about AI', ai_focus=False, published='2026-10-31T09:00:00+00:00'),
            item(103, title='Not https', url='http://lab.example/x', published='2026-10-31T08:00:00+00:00'),
        ]
        self.feed = {'updated_at': '2026-10-31T12:00:00+00:00', 'items': self.items}
        self.shown = build.news_items(self.feed, SOURCES)
        self.src = {s['id']: s for s in SOURCES}

    def rss(self, kind, lang):
        return feeds.rss(kind, lang, self.shown, self.src, self.feed['updated_at'])

    def test_channels(self):
        for (kind, lang), name in feeds.FILES.items():
            ch = channel(self.rss(kind, lang))
            self.assertEqual(ch.findtext('title'), feeds.TITLE[kind, lang])
            self.assertEqual(ch.findtext('language'), lang)
            self.assertEqual(ch.findtext('link'), ('https://cipherlacuna.ae/ar/#' if lang == 'ar' else 'https://cipherlacuna.ae/#') + kind)
            self.assertEqual(ch.findtext('lastBuildDate'), 'Sat, 31 Oct 2026 12:00:00 GMT')
            self_link = ch.find('{http://www.w3.org/2005/Atom}link')
            self.assertEqual((self_link.get('href'), self_link.get('rel')), (f'https://cipherlacuna.ae/{name}', 'self'))
        self.assertEqual(set(feeds.FILES.values()), {'news-en.xml', 'news-ar.xml', 'uae-en.xml', 'uae-ar.xml'})

    def test_the_pages_lists_newest_fifty(self):
        en = channel(self.rss('news', 'en')).findall('item')
        self.assertEqual(len(en), feeds.LIMIT)
        want = [i['url'] for i in self.shown if build.in_lang(i, 'en')][:50]
        self.assertEqual([x.findtext('link') for x in en], want)
        self.assertEqual(en[0].findtext('link'), 'https://lab.example/100')  # newest first
        links = {x.findtext('link') for x in en}
        self.assertNotIn('https://lab.example/102', links)  # not mainly about AI: hidden on the page, so here
        self.assertNotIn('http://lab.example/x', links)
        # Arabic: native Arabic headlines plus English ones that carry an AI translation, as on the page.
        ar = channel(self.rss('news', 'ar')).findall('item')
        self.assertEqual([x.findtext('link') for x in ar], ['https://lab.example/100', 'https://gulf.example/1'])
        self.assertEqual(ar[0].findtext('title'), 'OpenAI تفتح مكتباً')
        # UAE feeds: only the UAE list.
        self.assertEqual([x.findtext('link') for x in channel(self.rss('uae', 'ar')).findall('item')], ['https://gulf.example/1'])
        self.assertEqual(channel(self.rss('uae', 'en')).findall('item'), [])

    def test_item_fields(self):
        x = channel(self.rss('news', 'en')).findall('item')[0]
        self.assertEqual(x.findtext('title'), 'OpenAI opens an office')
        self.assertEqual(x.findtext('pubDate'), 'Fri, 30 Oct 2026 10:00:00 GMT')
        guid = x.find('guid')
        self.assertEqual((guid.text, guid.get('isPermaLink')), ('https://lab.example/100', 'true'))
        self.assertEqual(x.findtext('description'), '<p>An English summary &lt;b&gt;bold&lt;/b&gt; &amp; more.</p>'
                         '<p>Source: Global Lab · AI summary · via <a href="https://cipherlacuna.ae/">cipherlacuna.ae</a></p>')
        self.assertTrue(x.findtext('category'))
        # Arabic: the summary in Arabic, the publisher's Arabic name, the translated headline marked, and the Arabic site.
        a = channel(self.rss('news', 'ar')).findall('item')
        self.assertEqual(a[0].findtext('description'), '<p dir="rtl">ملخص عربي.</p><p dir="rtl">المصدر: مختبر عالمي · ملخص بالذكاء الاصطناعي · '
                         'العنوان: ترجمة بالذكاء الاصطناعي · عبر <a href="https://cipherlacuna.ae/ar/">cipherlacuna.ae</a></p>')
        # The publisher's own excerpt says so; its topic from news.py names the category.
        self.assertIn('<p dir="rtl">نص من الناشر.</p><p dir="rtl">المصدر: الخليج اليومي · من الناشر · عبر', a[1].findtext('description'))
        self.assertEqual(a[1].findtext('category'), 'الذكاء الاصطناعي في الإمارات')

    def test_no_summary_means_the_via_line_only(self):
        x = channel(self.rss('news', 'en')).findall('item')[1]
        self.assertEqual(x.findtext('description'), '<p>Source: Global Lab · via <a href="https://cipherlacuna.ae/">cipherlacuna.ae</a></p>')

    def test_topic_falls_back_to_the_topic_rule(self):
        i = item(5, title='New GPU chips for AI training')
        self.assertEqual(feeds.topic(i, SOURCES[0]), build.topics.topic_of(i, SOURCES[0]))
        self.assertEqual(feeds.topic(dict(i, topic='robotics'), SOURCES[0]), 'robotics')
        self.assertEqual(feeds.topic(dict(i, topic='made-up'), SOURCES[0]), build.topics.topic_of(i, SOURCES[0]))

    def test_control_characters_never_break_the_xml(self):
        shown = [dict(self.shown[0], title='Bad \x0b title \x1f')]
        ET.fromstring(feeds.rss('news', 'en', shown, self.src).encode('utf-8'))

    def test_write(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(feeds.write(Path(d), self.feed, SOURCES), list(feeds.FILES.values()))
            for name in feeds.FILES.values():
                channel((Path(d) / name).read_text(encoding='utf-8'))
            self.assertEqual(feeds.write(Path(d) / 'none', self.feed, []), [])  # no news sources: no feeds

    def test_head_links_and_side_panel_links(self):
        self.assertEqual(feeds.head_links('ar'), '<link rel="alternate" type="application/rss+xml" title="Cipher Lacuna · أخبار الذكاء الاصطناعي" href="news-ar.xml">'
                         '<link rel="alternate" type="application/rss+xml" title="Cipher Lacuna · أخبار الذكاء الاصطناعي في الإمارات" href="uae-ar.xml">')
        for kind in ('news', 'uae'):
            link = build.rss_link(kind)
            self.assertIn(f'<a href="{kind}-en.xml" type="application/rss+xml" data-lang="en" lang="en">', link)
            self.assertIn(f'<a href="{kind}-ar.xml" type="application/rss+xml" data-lang="ar" lang="ar">', link)
            self.assertIn('<span>RSS feed</span>', link)
            self.assertIn('خلاصة <bdi lang="en" dir="ltr">RSS</bdi>', link)

class PageLinkTests(unittest.TestCase):
    """The overview links the feeds of its language in its head and in the AI news and UAE AI side panels."""
    @classmethod
    def setUpClass(cls):
        data, feed, sources, uae, models = build.load_all()
        cls.en, _ = build.render_page(data, feed, sources, uae, models)
        cls.ar, _ = build.render_page(data, feed, sources, uae, models, lang='ar')
        cls.none, _ = build.render_page(data, feed, [], uae, models)

    def test_head(self):
        head = lambda page: page[:page.index('</head>')]
        self.assertIn(feeds.head_links('en'), head(self.en))
        self.assertIn(feeds.head_links('ar', '../'), head(self.ar))
        self.assertNotIn('application/rss+xml', head(self.none))

    def test_side_panels(self):
        for view in ('news', 'uae'):
            side = self.en[self.en.index(f'<section id="{view}"'):]
            side = side[:side.index('</aside>')]
            self.assertIn(build.rss_link(view), side)
        self.assertIn('href="../news-ar.xml"', self.ar)
        css = (ROOT / 'web' / 'style.css').read_text(encoding='utf-8')
        self.assertIn('.rss a{display:inline-flex;align-items:center;gap:6px;min-height:24px;color:var(--muted);', css)

if __name__ == '__main__':
    unittest.main()
