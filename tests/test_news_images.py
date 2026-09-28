"""Company images for news cards (scripts/news_images.py): the allow-list, the UAE official rule, size and type limits,
the cache and the fallback to topic images. No network: every fetch is a fake."""
import io, json, random, sys, tempfile, unittest
from email.message import Message
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import news, news_images, topics
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {s['id']: s for s in json.loads((ROOT / 'data/news-sources.json').read_text(encoding='utf-8'))}
OPENAI = SOURCES['openai-news']

def png(w=1600, h=900, noise=False, mode='RGB'):
    im = Image.new(mode, (w, h), (40, 90, 200) if mode == 'RGB' else (40, 90, 200, 0))
    if noise:
        rnd = random.Random(7)
        im.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(w * h)])
    buf = io.BytesIO(); im.save(buf, 'PNG'); return buf.getvalue()

def gif():
    frames = [Image.new('RGB', (300, 200), c) for c in ((255, 0, 0), (0, 255, 0))]
    buf = io.BytesIO(); frames[0].save(buf, 'GIF', save_all=True, append_images=frames[1:]); return buf.getvalue()

def page(img, key='og:image'):
    return f'<html><head><meta property="{key}" content="{img}"><title>x</title></head><body></body></html>'

def item(i='a1', source='openai-news', **kw):
    return {'id': i, 'source': source, 'url': f'https://openai.com/index/{i}', 'title': 'Introducing GPT-6 Sol and Luna',
            'lang': 'en', 'uae': False, 'published': '2026-09-26T10:00:00+00:00', **kw}

IMG = 'https://images.ctfassets.net/kftzwdyauwt9/abc/def/og.png?w=1600&h=900'

class RuleTests(unittest.TestCase):
    def test_allow_list(self):
        ok = ['https://openai.com/images/a.png', IMG, 'https://images.ctfassets.net/kftzwdyauwt9/x.jpg']
        bad = ['http://openai.com/a.png',                          # not https
               'https://images.ctfassets.net/otherspace/x.jpg',    # another Contentful customer
               'https://cdn.openai.com.evil.example/a.png', 'https://evil-openai.com/a.png', 'https://sub.openai.com/a.png',
               'https://user@openai.com/a.png', 'https://openai.com:8443/a.png',
               'https://media.gettyimages.com/photos/x.jpg', 'https://www.reuters.com/resizer/x.jpg', 'not a url', '']
        for u in ok: self.assertTrue(news_images.host_ok(u, OPENAI), u)
        for u in bad: self.assertFalse(news_images.host_ok(u, OPENAI), u)
        self.assertFalse(news_images.host_ok(IMG, SOURCES['techcrunch-ai']))  # no allow-list: nothing is allowed
        # Every allow-list entry is the source's own (sub)domain or a path on a shared CDN, never a bare shared host.
        for s in SOURCES.values():
            for e in s.get('image_hosts', []):
                host = e.split('/')[0]
                if host in ('storage.googleapis.com', 'images.ctfassets.net', 'iprsoftwaremedia.com'):
                    self.assertRegex(e, r'^[\w.-]+/[\w.-]+/$', (s['id'], e))
                for agency in ('getty', 'reuters', 'apnews', 'afp', 'wam.ae', 'mediaoffice', 'sharjah24'):
                    self.assertNotIn(agency, e, s['id'])

    def test_only_official_company_sources_and_never_uae_official(self):
        self.assertTrue(news_images.eligible(item(), OPENAI))
        self.assertFalse(news_images.eligible(item(uae=True), OPENAI))
        self.assertFalse(news_images.eligible(item(source='techcrunch-ai'), SOURCES['techcrunch-ai']))  # news outlet
        for sid in ('wam-en', 'wam-ar', 'mediaoffice-en2', 'mediaoffice-ar2', 'sharjah24-en', 'sharjah24-ar'):
            s = {**SOURCES[sid], 'image_hosts': ['www.wam.ae', 'mediaoffice.ae', 'sharjah24.ae']}  # even with an allow-list
            self.assertFalse(news_images.eligible(item(source=sid), s), sid)
            self.assertNotIn('image_hosts', SOURCES[sid], sid)
        self.assertFalse(news_images.eligible(item(), {**OPENAI, 'official_region': True}))
        # The real allow-lists are on official company sources only.
        for s in SOURCES.values():
            if s.get('image_hosts'):
                self.assertEqual((s['kind'], s['region']), ('primary', 'global'), s['id'])
                self.assertTrue(s.get('image_credit'), s['id'])

    def test_page_images(self):
        html = ('<meta name="twitter:image" content="https://openai.com/t.png">'
                '<meta content="https://images.ctfassets.net/kftzwdyauwt9/a.png?w=1&amp;h=2" property="og:image">'
                '<meta property="og:title" content="x"><meta property="og:image" content="/rel.png">')
        self.assertEqual(news_images.page_images(html, 'https://openai.com/index/a'),
                         ['https://images.ctfassets.net/kftzwdyauwt9/a.png?w=1&h=2', 'https://openai.com/t.png'])
        self.assertEqual(news_images.page_images(page('/img/a.png'), 'https://openai.com/index/a'), ['https://openai.com/img/a.png'])
        self.assertEqual(news_images.page_images('<html></html>', 'https://openai.com/'), [])

    def test_country_government_and_gcc_stories_get_the_topic_image(self):
        """No flags, no heads of state: a company story naming a country, a government or a national event (EN or AR,
        headline, translation or excerpt) gets the topic image. Real-style headlines."""
        place = ['From Enablement to Execution, Egypt\u2019s AI Ecosystem Reaches Production Scale',
                 'At AI Day Singapore, NVIDIA and Partners Showcase AI Advancements Across Southeast Asia',
                 'Sam Altman\u2019s remarks at the United Nations Security Council',
                 'ChatGPT Ads expands to Southeast Asia and Taiwan',
                 'How UK AISI and EvalEval Are Making Benchmark Results Reproducible',
                 'NVIDIA and HUMAIN build AI factories of the future in Saudi Arabia',
                 'OpenAI and Qatar Investment Authority announce partnership', 'AWS opens a new Region in the Kingdom of Bahrain',
                 'Microsoft signs AI agreement with the Government of Oman', 'OpenAI for Countries: Stargate Kuwait',
                 'Crown Prince visits NVIDIA headquarters', 'Supporting sovereign AI across the GCC',
                 'President announces national AI strategy with Google', 'Extending public sector intelligence with Agentforce and AWS',
                 'OpenAI opens an office in Riyadh', 'Google Beam expands to five new countries']
        place_ar = ['إنفيديا توقع شراكة مع السعودية', 'OpenAI تفتتح مكتباً في الدوحة', 'وزير الذكاء الاصطناعي يزور مقر الشركة',
                    'شراكة مع حكومة البحرين', 'ولي العهد يطلق مبادرة للذكاء الاصطناعي', 'احتفالاً باليوم الوطني', 'مصر تستضيف قمة']
        for t in place:
            self.assertTrue(news_images.place_story({'title': t}), t)
            self.assertFalse(news_images.eligible(item(title=t), OPENAI), t)
        for t in place_ar:
            self.assertTrue(news_images.place_story({'title': 'x', 'title_ar': t}), t)
        self.assertTrue(news_images.place_story({'title': 'Grand opening', 'excerpt': 'Today, Egypt\u2019s AI builders gathered'}))
        # Everyday company stories keep their image: "international", "American Express", a CEO («الرئيس التنفيذي»),
        # «مصرف» (a bank, not «مصر») and «قطرة» (a drop, not «قطر») are not places.
        plain = ['Introducing GPT-6 Sol and Luna', 'Claude Opus 5.5 is now available on AWS',
                 'How Reactiv automates mobile commerce 80% faster with Amazon Bedrock AgentCore',
                 'An international benchmark for agents', 'American Express builds with GPT-6',
                 'NVIDIA Launches DSX Ready to Qualify Power and Cooling Products for AI Factories',
                 'Transformers now runs llama.cpp quants', 'Scaling MoE reinforcement learning on Amazon EKS with EFA',
                 'Ship agents safely with feature flags', 'Let us know what you build', 'Un-hackable by design']
        plain_ar = ['الرئيس التنفيذي يعلن نموذجاً جديداً', 'مصرف يعتمد الذكاء الاصطناعي', 'كل قطرة ماء', 'نموذج جديد للبرمجة', 'أدوات علم البيانات']
        for t in plain:
            self.assertEqual(news_images.place_story({'title': t}), '', t)
            self.assertTrue(news_images.eligible(item(title=t), OPENAI), t)
        for t in plain_ar:
            self.assertEqual(news_images.place_story({'title': 'x', 'title_ar': t}), '', t)
        # The NVIDIA Egypt photo is also skipped by name, whatever the gate says.
        self.assertFalse(news_images.usable('https://blogs.nvidia.com/wp-content/uploads/2026/09/5723250-ent-dig-egypt-ecosystem-reception-blog-1920x1080-1.jpg', SOURCES['nvidia-news']))

    def test_partner_posts_on_hugging_face_get_the_topic_image(self):
        hf = SOURCES['huggingface']
        def hf_item(url): return item('h1', 'huggingface', url=url, title='Transformers now runs llama.cpp quants')
        self.assertTrue(news_images.eligible(hf_item('https://huggingface.co/blog/transformers-llama-cpp-quants'), hf))
        self.assertTrue(news_images.eligible(hf_item('https://huggingface.co/blog/omlx/'), hf))
        for url in ('https://huggingface.co/blog/nvidia/how-to-use-nvidia-warp-and-mjwarp',
                    'https://huggingface.co/blog/LiquidAI/lfm2-5-vl-dspark'):
            self.assertFalse(news_images.eligible(hf_item(url), hf), url)
        self.assertFalse(news_images.own_post(hf_item('x'), {**hf, 'image_page_paths': '(['}))  # a bad regex: no image

    def test_mit_news_has_no_company_images(self):
        # MIT News pictures are often stock or third-party ("Photo: iStock", "courtesy of ...") and licensed CC BY-NC-ND.
        mit = SOURCES['mit-news-ai']
        self.assertNotIn('image_hosts', mit); self.assertNotIn('image_credit', mit)
        self.assertFalse(news_images.eligible(item('m1', 'mit-news-ai', url='https://news.mit.edu/2026/x'), mit))

    def test_allow_list_path_cannot_be_escaped(self):
        g = SOURCES['google-ai']
        self.assertTrue(news_images.host_ok('https://storage.googleapis.com/gweb-uniblog-publish-prod/images/a.png', g))
        for bad in ('https://storage.googleapis.com/gweb-uniblog-publish-prod/../other-bucket/x.png',
                    'https://storage.googleapis.com/gweb-uniblog-publish-prod/%2e%2e/other-bucket/x.png',
                    'https://storage.googleapis.com/gweb-uniblog-publish-prod/..%2Fother-bucket/x.png',
                    'https://storage.googleapis.com/gweb-uniblog-publish-prod%2F..%2Fother/x.png',
                    'https://storage.googleapis.com/gweb-uniblog-publish-prod/%252e%252e/x.png',
                    'https://storage.googleapis.com/gweb-uniblog-publish-prod/.%5C../x.png',
                    'https://storage.googleapis.com/gweb-uniblog-publish-prod/./x.png'):
            self.assertFalse(news_images.host_ok(bad, g), bad)
        # An ordinary encoded space in a file name is fine.
        self.assertTrue(news_images.host_ok('https://openai.com/images/David%20Siegel.jpg', OPENAI))

    def test_image_skip_and_credit(self):
        g = SOURCES['google-research']
        self.assertFalse(news_images.usable('https://storage.googleapis.com/gweb-research2023-media/images/HO_previewImage1.width-800.format-jpeg.jpg', g))
        self.assertTrue(news_images.usable('https://storage.googleapis.com/gweb-research2023-media/images/Figure1.width-1250.png', g))
        self.assertEqual(news_images.credit(OPENAI), 'OpenAI')

    def test_page_may_redirect_to_the_companys_other_domain(self):
        # DeepMind posts move to blog.google: allowed for the image lookup only (image_page_hosts), never elsewhere.
        dm = SOURCES['deepmind']
        self.assertEqual(dm.get('image_page_hosts'), ['blog.google'])
        resp = FakeResp(page(IMG).encode(), 'text/html', url='https://blog.google/x/')
        with mock.patch.object(news, 'robots_allowed', return_value=True), mock.patch.object(news, '_open', return_value=resp) as op:
            news_images.fetch_page('https://deepmind.google/blog/a/', dm)
        used = op.call_args[0][1]
        self.assertIn('blog.google', used['link_hosts']); self.assertNotIn('blog.google', dm['link_hosts'])
        with mock.patch.object(news, 'robots_allowed', return_value=True), mock.patch.object(news, '_open', return_value=resp), \
             self.assertRaises(news_images.Skip):
            news_images.fetch_page('https://deepmind.google/blog/a/', {**dm, 'image_page_hosts': []})

    def test_workflow_keeps_the_cache(self):
        wf = (ROOT / '.github/workflows/publish.yml').read_text(encoding='utf-8')
        cache, build_step = wf.index('uses: actions/cache/restore@'), wf.index('run: python scripts/build.py')
        self.assertLess(cache, build_step)
        step = wf[cache:build_step]
        self.assertIn('path: .cache/news-img', step); self.assertIn('restore-keys:', step)
        self.assertIn('steps.news-img-week.outputs.week', step)
        # Saved right after the build, even when a later step (the data push) fails.
        save = wf.index('uses: actions/cache/save@')
        self.assertLess(build_step, save); self.assertLess(save, wf.index('name: Save refreshed data'))
        self.assertIn('if: always()', wf[wf.rindex('- name:', 0, save):save])
        self.assertIn('path: .cache/news-img', wf[save:save + 300])
        self.assertIn('.cache/', (ROOT / '.gitignore').read_text(encoding='utf-8').split())
        self.assertEqual(news_images.CACHE, ROOT / '.cache' / 'news-img')

class ConvertTests(unittest.TestCase):
    def test_webp_size_and_width(self):
        for raw in (png(), png(noise=True), png(300, 200), png(900, 900, mode='RGBA')):
            out, w, h = news_images.to_webp(raw)
            self.assertEqual(out[:4] + out[8:12], b'RIFFWEBP')
            self.assertLessEqual(w, news_images.MAX_WIDTH); self.assertLessEqual(len(out), news_images.MAX_OUT)
            self.assertEqual((w, h), Image.open(io.BytesIO(out)).size)
        self.assertEqual(news_images.to_webp(png(1600, 900))[1:], (480, 270))
        self.assertEqual(news_images.to_webp(gif())[1:], (300, 200))  # first frame of an animation

    def test_rejects(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        for raw in (b'', b'<html>not an image</html>', svg, png(20, 20)):
            with self.assertRaises(news_images.Skip): news_images.to_webp(raw)
        with mock.patch.object(news_images, 'MAX_PIXELS', 10_000):  # a decompression bomb
            with self.assertRaises(news_images.Skip): news_images.to_webp(png(1000, 1000))
        buf = io.BytesIO(); Image.new('RGB', (100, 100)).save(buf, 'BMP')
        with self.assertRaises(news_images.Skip): news_images.to_webp(buf.getvalue())

class FakeResp:
    def __init__(self, body, ctype='image/png', url=IMG, length=True):
        self.body, self.url = io.BytesIO(body), url
        self.headers = Message(); self.headers['Content-Type'] = ctype
        if length: self.headers['Content-Length'] = str(len(body))
    def read(self, n=-1): return self.body.read(n)
    def geturl(self): return self.url
    def __enter__(self): return self
    def __exit__(self, *a): return False

class DownloadTests(unittest.TestCase):
    def opener(self, resp=None, exc=None):
        o = mock.Mock()
        o.open.side_effect = exc if exc else (lambda req, timeout: resp)
        return mock.patch.object(news_images, 'build_opener', return_value=o)

    def test_type_and_size_limits(self):
        with self.opener(FakeResp(png())):
            self.assertEqual(news_images.download(IMG, OPENAI)[:4], b'\x89PNG')
        for resp in (FakeResp(b'<html>', 'text/html'), FakeResp(b'<svg/>', 'image/svg+xml'),
                     FakeResp(png(), url='https://evil.example/x.png')):
            with self.opener(resp), self.assertRaises(news_images.Skip): news_images.download(IMG, OPENAI)
        with mock.patch.object(news_images, 'MAX_DOWNLOAD', 1000):
            with self.opener(FakeResp(b'x' * 2000)), self.assertRaises(news_images.Skip): news_images.download(IMG, OPENAI)
            with self.opener(FakeResp(b'x' * 2000, length=False)), self.assertRaises(news_images.Skip): news_images.download(IMG, OPENAI)
        # Never even asked: a host off the allow-list.
        with self.opener(exc=AssertionError('no request')), self.assertRaises(news_images.Skip):
            news_images.download('https://media.gettyimages.com/x.jpg', OPENAI)

    def test_network_errors_are_retried_later(self):
        for exc in (URLError('down'), TimeoutError(), HTTPError(IMG, 503, 'busy', None, None)):
            with self.opener(exc=exc), self.assertRaises(news_images.Retry): news_images.download(IMG, OPENAI)
        with self.opener(exc=HTTPError(IMG, 404, 'gone', None, None)), self.assertRaises(news_images.Skip):
            news_images.download(IMG, OPENAI)
        # A bot wall seen from one runner (401/403/429) is not a lasting answer.
        for code in (401, 403, 429):
            with self.opener(exc=HTTPError(IMG, code, 'no', None, None)), self.assertRaises(news_images.Retry):
                news_images.download(IMG, OPENAI)

    def test_redirects_stay_on_the_allow_list(self):
        h = news_images._StayOnImageHosts(OPENAI)
        with self.assertRaises(HTTPError):
            h.redirect_request(mock.Mock(), None, 302, 'Found', Message(), 'https://evil.example/x.png')

    def test_unreadable_robots_is_retried_but_a_robots_no_is_final(self):
        from urllib.robotparser import RobotFileParser
        url = 'https://openai.com/index/a'
        unreadable = RobotFileParser(); unreadable.disallow_all = True   # what news._robots does on a fetch error
        says_no = RobotFileParser(); says_no.parse(['User-agent: *', 'Disallow: /'])
        try:
            for rp, exc in ((unreadable, news_images.Retry), (says_no, news_images.Skip)):
                news._ROBOTS['openai.com'] = rp
                with mock.patch.object(news, '_open', side_effect=AssertionError('robots said no: no page request')), \
                     self.assertRaises(exc):
                    news_images.fetch_page(url, OPENAI)
            # A real outage: neither robots.txt nor the page can be read: retried, never remembered as "no image".
            news._ROBOTS.pop('openai.com', None)
            with mock.patch.object(news, '_open', side_effect=URLError('offline')), self.assertRaises(news_images.Retry):
                news_images.fetch_page(url, OPENAI)
            news._ROBOTS.pop('openai.com', None)
            with mock.patch.object(news, '_open', side_effect=HTTPError(url, 403, 'bot wall', None, None)), \
                 self.assertRaises(news_images.Retry):
                news_images.fetch_page(url, OPENAI)
        finally:
            news._ROBOTS.pop('openai.com', None)

    def test_page_fetch_rules(self):
        with mock.patch.object(news, 'robots_allowed', return_value=False), self.assertRaises(news_images.Skip):
            news_images.fetch_page('https://openai.com/index/a', OPENAI)
        with self.assertRaises(news_images.Skip):  # off the source's own domains
            news_images.fetch_page('https://evil.example/a', OPENAI)
        with mock.patch.object(news, 'robots_allowed', return_value=True), \
             mock.patch.object(news, '_open', side_effect=URLError('down')), self.assertRaises(news_images.Retry):
            news_images.fetch_page('https://openai.com/index/a', OPENAI)
        resp = FakeResp(page(IMG).encode(), 'text/html; charset=utf-8', url='https://openai.com/index/a')
        with mock.patch.object(news, 'robots_allowed', return_value=True), mock.patch.object(news, '_open', return_value=resp):
            self.assertIn('og:image', news_images.fetch_page('https://openai.com/index/a', OPENAI))
        resp = FakeResp(b'{}', 'application/json', url='https://openai.com/index/a')
        with mock.patch.object(news, 'robots_allowed', return_value=True), mock.patch.object(news, '_open', return_value=resp), \
             self.assertRaises(news_images.Skip):
            news_images.fetch_page('https://openai.com/index/a', OPENAI)

class RunTests(unittest.TestCase):
    """run(): cache, fallback, counts, never raising."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.out, self.cache = self.dir / 'dist', self.dir / 'cache'
        self.logs = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_(self, items, page_fn=None, dl_fn=None, **kw):
        page_fn = page_fn or (lambda url, s: page(IMG))
        dl_fn = dl_fn or (lambda url, s: png())
        with mock.patch.object(news_images, 'fetch_page', side_effect=page_fn) as p, \
             mock.patch.object(news_images, 'download', side_effect=dl_fn) as d:
            got = news_images.run(self.out, items, SOURCES, self.cache, log=self.logs.append, **kw)
        return got, p.call_count, d.call_count

    def test_company_image_then_cache_hit(self):
        items = [item('a1'), item('t1', 'techcrunch-ai')]
        got, pages, dls = self.run_(items)
        self.assertEqual((pages, dls), (1, 1))  # the news outlet's story is never fetched
        self.assertEqual(got, {'a1': {'file': 'images/news/a1.webp', 'width': 480, 'height': 270, 'credit': 'OpenAI'}})
        self.assertTrue((self.out / 'images/news/a1.webp').is_file())
        index = json.loads((self.cache / 'index.json').read_text(encoding='utf-8'))
        self.assertEqual({k: index['a1'][k] for k in ('status', 'file', 'image_url', 'page_url', 'source')},
                         {'status': 'ok', 'file': 'a1.webp', 'image_url': IMG, 'page_url': 'https://openai.com/index/a1', 'source': 'openai-news'})
        self.assertIn('fetched_at', index['a1'])
        # Second build, fresh dist: no request at all, the same result from the cache.
        (self.out / 'images/news/a1.webp').unlink()
        again, pages, dls = self.run_(items, page_fn=AssertionError, dl_fn=AssertionError)
        self.assertEqual((again, pages, dls), (got, 0, 0))
        self.assertTrue((self.out / 'images/news/a1.webp').is_file())
        # A story no longer shown (or no longer allowed a company image): its file leaves the output too.
        (self.out / 'images/news/old.webp').write_bytes(b'x')
        self.run_([item('t1', 'techcrunch-ai')], page_fn=AssertionError, dl_fn=AssertionError)
        self.assertEqual(list((self.out / 'images/news').glob('*.webp')), [])
        # Logs are counts only: no titles, URLs or ids.
        for line in self.logs:
            self.assertNotIn('http', line); self.assertNotIn('a1', line); self.assertNotIn('GPT', line)

    def test_feed_image_skips_the_page(self):
        got, pages, dls = self.run_([item('a1', image='https://openai.com/feed-image.png')])
        self.assertEqual((pages, dls), (0, 1)); self.assertIn('a1', got)

    def test_uae_official_never_fetched(self):
        items = [item('w1', 'wam-en', uae=True), item('m1', 'mediaoffice-ar2', uae=True, lang='ar'), item('u1', uae=True)]
        got, pages, dls = self.run_(items)
        self.assertEqual((got, pages, dls), ({}, 0, 0))
        pics = news_images.pictures(items, SOURCES, {'w1': {'file': 'images/news/w1.webp', 'width': 1, 'height': 1, 'credit': 'WAM'}})
        self.assertEqual(pics['w1'], {'file': 'news-img/uae.svg', 'width': 640, 'height': 360, 'topic': 'uae'})
        self.assertEqual(pics['m1']['file'], 'news-img/uae.svg')

    def test_failures_fall_back_and_are_remembered(self):
        # No image on the page: remembered, not asked again.
        got, pages, _ = self.run_([item('a1')], page_fn=lambda u, s: '<html></html>')
        self.assertEqual((got, pages), ({}, 1))
        got, pages, _ = self.run_([item('a1')])
        self.assertEqual((got, pages), ({}, 0))
        # An image off the allow-list (a news agency's): the topic image.
        got, _, dls = self.run_([item('a2')], page_fn=lambda u, s: page('https://media.gettyimages.com/id/1/photo.jpg'))
        self.assertEqual((got, dls), ({}, 0))
        # A broken image file.
        got, _, _ = self.run_([item('a3')], dl_fn=lambda u, s: b'not an image')
        self.assertEqual(got, {})

    def test_network_errors_retried_up_to_tries(self):
        def down(u, s): raise news_images.Retry('URLError')
        calls = 0
        for _ in range(news_images.TRIES + 2):
            got, pages, _ = self.run_([item('a1')], page_fn=down)
            calls += pages
            self.assertEqual(got, {})
        self.assertEqual(calls, news_images.TRIES)
        self.assertEqual(json.loads((self.cache / 'index.json').read_text(encoding='utf-8'))['a1']['tries'], news_images.TRIES)

    def test_exhausted_retries_are_tried_again_a_day_later(self):
        def down(u, s): raise news_images.Retry('URLError')
        for _ in range(news_images.TRIES):
            self.run_([item('a1')], page_fn=down)
        got, pages, _ = self.run_([item('a1')])
        self.assertEqual((got, pages), ({}, 0))  # waits
        idx = json.loads((self.cache / 'index.json').read_text(encoding='utf-8'))
        idx['a1']['fetched_at'] = (news_images._now() - news_images.RETRY_AFTER - news_images.timedelta(minutes=1)).isoformat()
        (self.cache / 'index.json').write_text(json.dumps(idx), encoding='utf-8')
        got, pages, _ = self.run_([item('a1')])  # the network is back
        self.assertEqual((set(got), pages), ({'a1'}, 1))

    def test_generic_image_shared_by_stories_is_not_used(self):
        got, _, _ = self.run_([item('a1'), item('a2')])  # both pages give the same picture: a logo card
        self.assertEqual(got, {})
        got, _, _ = self.run_([item('a1'), item('a3')], page_fn=lambda u, s: page(f'https://openai.com/{u[-2:]}.png'))
        self.assertEqual(set(got), {'a3'})  # a1 still shares its picture with a2 in the cache

    def test_allow_list_change_looks_again(self):
        src = {**SOURCES, 'openai-news': {**OPENAI, 'image_hosts': ['openai.com']}}
        with mock.patch.object(news_images, 'fetch_page', side_effect=lambda u, s: page(IMG)), \
             mock.patch.object(news_images, 'download', side_effect=lambda u, s: png()):
            self.assertEqual(news_images.run(self.out, [item('a1')], src, self.cache, log=self.logs.append), {})
        got, pages, _ = self.run_([item('a1')])  # the real list allows the CDN
        self.assertEqual((set(got), pages), ({'a1'}, 1))
        # And an image cached under a list that no longer allows it is not shown.
        with mock.patch.object(news_images, 'fetch_page', side_effect=AssertionError), mock.patch.object(news_images, 'download', side_effect=lambda u, s: png()):
            idx = json.loads((self.cache / 'index.json').read_text(encoding='utf-8'))
            self.assertFalse(news_images.usable(idx['a1']['image_url'], src['openai-news']))

    def test_offline_and_never_raises(self):
        got, pages, dls = self.run_([item('a1')], network=False)
        self.assertEqual((got, pages, dls), ({}, 0, 0))
        # A crash anywhere: {} and a log line, never an exception.
        with mock.patch.object(news_images, '_run', side_effect=RuntimeError('boom')):
            self.assertEqual(news_images.run(self.out, [item('a1')], SOURCES, self.cache, log=self.logs.append), {})
        self.assertIn('topic images used', self.logs[-1])
        # Unexpected errors inside one fetch: that story keeps its topic image.
        got, _, _ = self.run_([item('a1')], page_fn=lambda u, s: 1 / 0)
        self.assertEqual(got, {})
        # A corrupt index is ignored.
        (self.cache / 'index.json').write_text('{not json', encoding='utf-8')
        got, _, _ = self.run_([item('a4')])
        self.assertIn('a4', got)

    def test_old_entries_are_pruned(self):
        self.run_([item('a1')])
        idx = json.loads((self.cache / 'index.json').read_text(encoding='utf-8'))
        idx['a1']['fetched_at'] = '2020-01-01T00:00:00+00:00'
        (self.cache / 'index.json').write_text(json.dumps(idx), encoding='utf-8')
        self.run_([item('a1')])  # still shown: kept
        self.assertTrue((self.cache / 'a1.webp').exists())
        self.run_([])            # no longer shown and old: dropped
        self.assertFalse((self.cache / 'a1.webp').exists())
        self.assertNotIn('a1', json.loads((self.cache / 'index.json').read_text(encoding='utf-8')))

    def test_pictures_topic_fallback(self):
        items = [item('a1'), item('t1', 'techcrunch-ai', title='Tesla workers balk at training Optimus humanoid robots')]
        pics = news_images.pictures(items, SOURCES, {'a1': {'file': 'images/news/a1.webp', 'width': 480, 'height': 270, 'credit': 'OpenAI'}})
        self.assertEqual(pics['a1'], {'file': 'images/news/a1.webp', 'width': 480, 'height': 270, 'credit': 'OpenAI', 'topic': 'models'})
        self.assertEqual(pics['t1'], {'file': 'news-img/robotics.svg', 'width': 640, 'height': 360, 'topic': 'robotics'})
        # A company image offered for a story that may not have one is ignored.
        pics = news_images.pictures([item('t1', 'techcrunch-ai')], SOURCES, {'t1': {'file': 'images/news/t1.webp', 'width': 1, 'height': 1, 'credit': 'X'}})
        self.assertTrue(pics['t1']['file'].startswith('news-img/'))

    def test_topic_images_copied(self):
        news_images.copy_topic_images(self.out)
        self.assertEqual(sorted(f.stem for f in (self.out / 'news-img').glob('*.svg')), sorted(topics.TOPICS))

if __name__ == '__main__':
    unittest.main()
