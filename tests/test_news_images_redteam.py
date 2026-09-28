"""Red-team checks for scripts/news_images.py against a real local HTTP server (no internet): hostile image responses
(huge, wrong type, disguised SVG/HTML, redirects off the allow-list, slow or stalled servers, 404/503) and awkward
image files (decompression bombs, EXIF rotation, 16-bit, extreme aspect ratios). The allow-list check is widened to
the local test server only; every other rule is the production code."""
import io, json, sys, tempfile, threading, time, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import news_images
from PIL import Image

def img(fmt='JPEG', w=1600, h=900, mode='RGB', **save):
    im = Image.new(mode, (w, h), 120 if mode in ('L', 'I;16', '1') else (40, 90, 200))
    buf = io.BytesIO(); im.save(buf, fmt, **save); return buf.getvalue()

JPEG = img()
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900"><rect width="100%" height="100%"/></svg>'
HTML = b'<!doctype html><html><body><script>alert(1)</script></body></html>'

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, code, ctype, body, length=True, extra=()):
        self.send_response(code)
        if ctype: self.send_header('Content-Type', ctype)
        for k, v in extra: self.send_header(k, v)
        if length: self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try: self.wfile.write(body)
        except (ConnectionError, OSError): pass

    def do_GET(self):
        p, port = self.path, self.server.server_address[1]
        if p == '/ok.jpg': return self.send(200, 'image/jpeg', JPEG)
        if p == '/huge-declared.jpg':
            self.send_response(200); self.send_header('Content-Type', 'image/jpeg'); self.send_header('Content-Length', '999999999'); self.end_headers(); return
        if p == '/huge-streamed.jpg':
            self.send_response(200); self.send_header('Content-Type', 'image/jpeg'); self.end_headers()
            try:
                for _ in range(200): self.wfile.write(b'\0' * 65536)  # 13 MB, no Content-Length
            except (ConnectionError, OSError): pass
            return
        if p == '/page.html': return self.send(200, 'text/html', HTML)
        if p == '/svg-typed.svg': return self.send(200, 'image/svg+xml', SVG)
        if p == '/svg-as-png.png': return self.send(200, 'image/png', SVG)
        if p == '/html-as-jpeg.jpg': return self.send(200, 'image/jpeg', HTML)
        if p == '/no-type.jpg': return self.send(200, None, JPEG)
        if p == '/redirect-off-host.jpg': return self.send(302, None, b'', extra=[('Location', f'http://localhost:{port}/ok.jpg')])
        if p == '/redirect-on-host.jpg': return self.send(302, None, b'', extra=[('Location', '/ok.jpg')])
        if p == '/redirect-loop.jpg': return self.send(302, None, b'', extra=[('Location', '/redirect-loop.jpg')])
        if p == '/stall.jpg': time.sleep(3); return self.send(200, 'image/jpeg', JPEG)
        if p == '/drip.jpg':
            self.send_response(200); self.send_header('Content-Type', 'image/jpeg'); self.end_headers()
            try:
                for b in JPEG[:40]: self.wfile.write(bytes([b])); self.wfile.flush(); time.sleep(0.1)
            except (ConnectionError, OSError): pass
            return
        if p == '/404.jpg': return self.send(404, 'text/html', b'nope')
        if p == '/503.jpg': return self.send(503, 'text/html', b'busy')
        if p == '/bomb.png': return self.send(200, 'image/png', self.server.bomb)
        return self.send(404, 'text/plain', b'')

class Server:
    def __enter__(self):
        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.httpd.bomb = img('PNG', 12000, 12000, mode='1')  # 144 Mpx in a few KB
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown(); self.httpd.server_close()

    def url(self, path):
        return f'http://127.0.0.1:{self.port}{path}'

REAL_HOST_OK = news_images.host_ok

def local_host_ok(url, source):
    """The production check, plus plain http on 127.0.0.1 (the test server). 'localhost' stays 'another host'."""
    u = urlparse(url)
    if u.scheme == 'http' and u.hostname == '127.0.0.1':
        return True
    return REAL_HOST_OK(url, source)

SRC = {'id': 'x', 'kind': 'primary', 'region': 'global', 'image_hosts': ['example.com'], 'image_credit': 'X', 'link_hosts': ['example.com']}

class HostileServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = Server().__enter__()
        cls.patch = mock.patch.object(news_images, 'host_ok', side_effect=local_host_ok)
        cls.patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop(); cls.srv.__exit__()

    def dl(self, path):
        return news_images.download(self.srv.url(path), SRC)

    def outcome(self, path):
        try:
            raw = self.dl(path)
        except news_images.Skip as e:
            return 'skip', str(e)
        except news_images.Retry as e:
            return 'retry', str(e)
        try:
            news_images.to_webp(raw)
        except news_images.Skip as e:
            return 'skip-convert', str(e)
        return 'ok', ''

    def test_control_ok(self):
        self.assertEqual(self.outcome('/ok.jpg')[0], 'ok')

    def test_huge_declared(self):
        self.assertEqual(self.outcome('/huge-declared.jpg'), ('skip', 'image too large'))

    def test_huge_streamed_is_capped(self):
        t = time.monotonic()
        self.assertEqual(self.outcome('/huge-streamed.jpg'), ('skip', 'image too large'))
        self.assertLess(time.monotonic() - t, 20)

    def test_wrong_content_type(self):
        self.assertEqual(self.outcome('/page.html'), ('skip', 'not an image'))
        self.assertEqual(self.outcome('/no-type.jpg'), ('skip', 'not an image'))

    def test_svg_and_html_disguised(self):
        self.assertEqual(self.outcome('/svg-typed.svg'), ('skip', 'not an image'))
        self.assertEqual(self.outcome('/svg-as-png.png')[0], 'skip-convert')
        self.assertEqual(self.outcome('/html-as-jpeg.jpg')[0], 'skip-convert')

    def test_redirects(self):
        self.assertEqual(self.outcome('/redirect-off-host.jpg')[0], 'skip')
        self.assertEqual(self.outcome('/redirect-on-host.jpg')[0], 'ok')
        self.assertIn(self.outcome('/redirect-loop.jpg')[0], ('skip', 'retry'))

    def test_timeouts(self):
        with mock.patch.object(news_images, 'TIMEOUT', 1):
            self.assertEqual(self.outcome('/stall.jpg')[0], 'retry')
        with mock.patch.object(news_images, 'DEADLINE', 1):
            t = time.monotonic()
            self.assertEqual(self.outcome('/drip.jpg')[0], 'retry')
            self.assertLess(time.monotonic() - t, 6)

    def test_http_errors(self):
        self.assertEqual(self.outcome('/404.jpg')[0], 'skip')
        self.assertEqual(self.outcome('/503.jpg')[0], 'retry')

    def test_decompression_bomb(self):
        self.assertEqual(self.outcome('/bomb.png'), ('skip-convert', 'unreadable image'))

    def test_production_allow_list_rejects_plain_http_and_lookalikes(self):
        s = {'image_hosts': ['openai.com', 'images.ctfassets.net/kftzwdyauwt9/']}
        for bad in ('http://openai.com/a.png', 'https://openai.com.evil.test/a.png', 'https://evilopenai.com/a.png',
                    'https://images.ctfassets.net/other/a.png', 'https://images.ctfassets.net/kftzwdyauwt9x/a.png',
                    'https://user@openai.com/a.png', 'https://openai.com:8443/a.png'):
            self.assertFalse(REAL_HOST_OK(bad, s), bad)

class ImageFileTests(unittest.TestCase):
    def test_sixteen_bit_and_cmyk_and_palette(self):
        for raw in (img('PNG', 800, 450, mode='I;16'), img('JPEG', 800, 450, mode='CMYK'), img('GIF', 800, 450, mode='P')):
            webp, w, h = news_images.to_webp(raw)
            self.assertLessEqual(len(webp), news_images.MAX_OUT)

    def test_small_images_skipped(self):
        with self.assertRaises(news_images.Skip):
            news_images.to_webp(img('PNG', 150, 150))

    def test_extreme_panorama(self):
        webp, w, h = news_images.to_webp(img('PNG', 6000, 60))
        self.assertGreaterEqual(h, 1)  # 480x5: shown with object-fit: cover, so it is a thin smear

    def test_exif_orientation(self):
        """A phone photo stored landscape with EXIF 'rotate 90' is shown sideways unless the orientation is applied."""
        im = Image.new('RGB', (1600, 900), (40, 90, 200))
        exif = im.getexif(); exif[0x0112] = 6
        buf = io.BytesIO(); im.save(buf, 'JPEG', exif=exif.tobytes())
        _, w, h = news_images.to_webp(buf.getvalue())
        self.assertLess(w, h, 'EXIF orientation ignored: portrait photo converted as landscape')

class RunRobustnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); d = Path(self.tmp.name)
        self.out, self.cache, self.logs = d / 'dist', d / 'cache', []

    def tearDown(self):
        self.tmp.cleanup()

    def item(self, i):
        return {'id': i, 'source': 'openai-news', 'url': f'https://openai.com/index/{i}', 'title': 'GPT', 'lang': 'en', 'uae': False,
                'published': '2026-09-26T10:00:00+00:00'}

    def sources(self):
        root = Path(__file__).resolve().parents[1]
        return {s['id']: s for s in json.loads((root / 'data/news-sources.json').read_text(encoding='utf-8'))}

    def test_one_bad_index_entry_does_not_hide_every_company_image(self):
        src = self.sources()
        img_url = 'https://images.ctfassets.net/kftzwdyauwt9/a/b/og.png'
        with mock.patch.object(news_images, 'fetch_page', side_effect=lambda u, s: f'<meta property="og:image" content="{img_url}{u[-2:]}">'), \
             mock.patch.object(news_images, 'download', side_effect=lambda u, s: img('PNG')):
            got = news_images.run(self.out, [self.item('a1'), self.item('a2')], src, self.cache, log=self.logs.append)
        self.assertEqual(set(got), {'a1', 'a2'})
        idx = json.loads((self.cache / 'index.json').read_text(encoding='utf-8'))
        del idx['a2']['width']  # a hand-edited or older-format entry
        (self.cache / 'index.json').write_text(json.dumps(idx), encoding='utf-8')
        got = news_images.run(self.out, [self.item('a1'), self.item('a2')], src, self.cache, network=False, log=self.logs.append)
        self.assertIn('a1', got, 'a single malformed cache entry dropped all company images')

    def test_bad_image_skip_regex_does_not_hide_every_company_image(self):
        src = self.sources()
        src['google-research'] = {**src['google-research'], 'image_skip': '(['}
        with mock.patch.object(news_images, 'fetch_page', side_effect=lambda u, s: '<meta property="og:image" content="https://openai.com/x.png">'), \
             mock.patch.object(news_images, 'download', side_effect=lambda u, s: img('PNG')):
            got = news_images.run(self.out, [self.item('a1'), {**self.item('g1'), 'source': 'google-research', 'url': 'https://research.google/blog/g1'}],
                                  src, self.cache, log=self.logs.append)
        self.assertIn('a1', got, "one source's bad image_skip regex dropped every source's company images")

    def test_network_outage_is_retried_not_remembered_for_good(self):
        """A build with no network (or a robots.txt that times out / returns 5xx) must leave the story to be tried again;
        today the robots.txt failure becomes 'none' and the story keeps its topic image for good."""
        import news
        from urllib.error import URLError
        src = self.sources()
        news._ROBOTS.pop('openai.com', None)
        with mock.patch.object(news, '_open', side_effect=URLError('offline')):
            entry = news_images.fetch_one(self.item('a1'), src['openai-news'], self.cache)
        news._ROBOTS.pop('openai.com', None)
        self.assertEqual(entry['status'], 'retry', entry)

if __name__ == '__main__':
    unittest.main()
