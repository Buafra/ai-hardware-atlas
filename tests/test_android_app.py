"""The Android app download: release choice, APK checks (size, SHA-256, signing certificate), the cache, the files in
dist/download/ and the card on the page."""
import hashlib
import io
import json
import re
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import android_app as A

ROOT = Path(__file__).resolve().parents[1]
CERT = b'test certificate DER'
CERT_SHA = hashlib.sha256(CERT).hexdigest()

def lp(b):
    return struct.pack('<I', len(b)) + b

def seq(items):
    return lp(b''.join(lp(i) for i in items))

def fake_apk(certs=(CERT,), scheme=A.V2_ID, manifest=True, signed=True, extra=b''):
    """A small ZIP laid out like an APK, with a v2 (or v3) signature block holding `certs` before the central directory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        if manifest:
            z.writestr('AndroidManifest.xml', b'\x03\x00\x08\x00')
        z.writestr('classes.dex', b'dex\n035' + extra)
    data = buf.getvalue()
    if not signed:
        return data
    eocd = data.rfind(b'PK\x05\x06')
    cd = struct.unpack_from('<I', data, eocd + 16)[0]
    signed_data = seq([b'digest']) + seq(list(certs)) + seq([])
    signer = lp(signed_data) + seq([b'signature']) + lp(b'public key')
    value = seq([signer])
    # The first pair has an id the reader does not know (like the padding pair apksigner adds): it must skip it.
    pairs = struct.pack('<QI', 8, 0x42726577) + b'\0\0\0\0' + struct.pack('<QI', len(value) + 4, scheme) + value
    size = len(pairs) + 8 + 16
    block = struct.pack('<Q', size) + pairs + struct.pack('<Q', size) + b'APK Sig Block 42'
    return data[:cd] + block + data[cd:eocd + 16] + struct.pack('<I', cd + len(block)) + data[eocd + 20:]

def release(tag, apk=b'', draft=False, prerelease=False, name=A.ASSET, url=None, state='uploaded', published='2026-09-28T08:19:58Z', digest=True, size=None):
    asset = {'name': name, 'state': state, 'size': len(apk) if size is None else size,
             'browser_download_url': url or f'https://github.com/Buafra/ai-hardware-atlas/releases/download/{tag}/{name}'}
    if digest:
        asset['digest'] = 'sha256:' + hashlib.sha256(apk).hexdigest()
    return {'tag_name': tag, 'draft': draft, 'prerelease': prerelease, 'published_at': published, 'assets': [asset]}

class Opener:
    """urlopen stand-in: the releases API answers with `releases`, each download URL with its bytes."""
    def __init__(self, releases=(), files=None, fail_api=False):
        self.releases, self.files, self.fail_api, self.calls = list(releases), files or {}, fail_api, []
    def __call__(self, req, timeout=None):
        url = req.full_url
        self.calls.append((url, req.get_header('Authorization')))
        if url.startswith('https://api.github.com/'):
            if self.fail_api:
                raise OSError('network down')
            return io.BytesIO(json.dumps(self.releases).encode())
        if url in self.files:
            return io.BytesIO(self.files[url])
        raise OSError('404 ' + url)

class VersionTests(unittest.TestCase):
    def test_tags(self):
        self.assertEqual(A.version_of('android-v1.0.12'), (1, 0, 12))
        for bad in ('v1.0.1', 'android-v1.0', 'android-v1.0.1-beta', 'android-1.0.1', 'Android-v1.0.1', '', None):
            self.assertIsNone(A.version_of(bad), bad)

class PickTests(unittest.TestCase):
    def test_highest_version_wins_not_the_latest_date(self):
        rels = [release('android-v1.0.9', b'a', published='2026-12-01T00:00:00Z'), release('android-v1.0.10', b'b', published='2026-10-01T00:00:00Z')]
        self.assertEqual(A.pick(rels)['tag'], 'android-v1.0.10')

    def test_drafts_prereleases_and_bad_releases_are_skipped(self):
        good = release('android-v1.0.1', b'ok')
        rels = [good,
                release('android-v2.0.0', b'x', draft=True),
                release('android-v1.9.0', b'x', prerelease=True),
                release('v9.0.0', b'x'),
                release('android-v1.8.0', b'x', name='app-release.apk'),
                release('android-v1.7.0', b'x', state='starter'),
                release('android-v1.6.0', b'x', url='https://evil.example/Cipher-Lacuna.apk'),
                release('android-v1.5.0', b'', size=0),
                release('android-v1.4.0', b'x', size=A.MAX_BYTES + 1),
                'junk', None]
        got = A.pick(rels)
        self.assertEqual(got['tag'], 'android-v1.0.1')
        self.assertEqual(got['version'], '1.0.1')
        self.assertEqual(got['sha256'], hashlib.sha256(b'ok').hexdigest())
        self.assertIsNone(A.pick([]))
        self.assertIsNone(A.pick({'message': 'Not Found'}))

    def test_missing_digest_and_bad_dates(self):
        got = A.pick([release('android-v1.0.1', b'ok', digest=False, published='yesterday')])
        self.assertIsNone(got['sha256'])
        self.assertEqual(got['published'], '')

class SignatureTests(unittest.TestCase):
    def write(self, d, data, name='x.apk'):
        p = Path(d) / name
        p.write_bytes(data)
        return p

    def test_reads_v2_and_v3_certificates(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(A.signing_certs(self.write(d, fake_apk())), {CERT_SHA})
            self.assertEqual(A.signing_certs(self.write(d, fake_apk(scheme=A.V3_ID))), {CERT_SHA})
            two = A.signing_certs(self.write(d, fake_apk(certs=(CERT, b'other'))))
            self.assertEqual(two, {CERT_SHA, hashlib.sha256(b'other').hexdigest()})

    def test_unsigned_damaged_and_non_zip_files_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            for name, data in (('unsigned', fake_apk(signed=False)), ('text', b'hello world' * 50), ('empty', b''),
                               ('v1-only scheme id', fake_apk(scheme=0x12345678))):
                with self.assertRaises(ValueError, msg=name):
                    A.signing_certs(self.write(d, data))
            good = fake_apk()
            i = good.index(b'APK Sig Block 42')
            broken = good[:i - 8] + struct.pack('<Q', 10 ** 9) + good[i:]  # a size that points outside the file
            with self.assertRaises(ValueError):
                A.signing_certs(self.write(d, broken))

    @unittest.skipUnless((A.CACHE / A.ASSET).exists(), 'no release APK in .cache/android (run scripts/android_app.py)')
    def test_the_real_release_carries_the_cipher_lacuna_certificate(self):
        self.assertIn(A.SIGNER_SHA256, A.signing_certs(A.CACHE / A.ASSET))

class CheckApkTests(unittest.TestCase):
    def test_checks(self):
        data = fake_apk()
        sha = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'a.apk'
            p.write_bytes(data)
            self.assertEqual(A.check_apk(p, len(data), sha, signer=CERT_SHA), sha)
            self.assertEqual(A.check_apk(p, signer=CERT_SHA.upper()), sha)
            for kwargs, why in ((dict(size=len(data) + 1, signer=CERT_SHA), 'size'),
                                (dict(sha256='0' * 64, signer=CERT_SHA), 'SHA-256'),
                                (dict(signer=A.SIGNER_SHA256), 'certificate')):
                with self.assertRaisesRegex(ValueError, why):
                    A.check_apk(p, **kwargs)
            p.write_bytes(fake_apk(manifest=False))
            with self.assertRaisesRegex(ValueError, 'AndroidManifest'):
                A.check_apk(p, signer=CERT_SHA)

class FetchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / 'android'
        self.logs = []
        self.v1, self.v2 = fake_apk(extra=b'1'), fake_apk(extra=b'22')

    def tearDown(self):
        self.tmp.cleanup()

    def run_fetch(self, opener):
        return A.fetch('Buafra/ai-hardware-atlas', self.cache, token='TOKEN', opener=opener, signer=CERT_SHA, log=self.logs.append)

    def files(self, *pairs):
        return {f'https://github.com/Buafra/ai-hardware-atlas/releases/download/{t}/{A.ASSET}': b for t, b in pairs}

    def test_first_fetch_then_current_then_a_new_release_replaces_it(self):
        o = Opener([release('android-v1.0.1', self.v1)], self.files(('android-v1.0.1', self.v1)))
        self.assertEqual(self.run_fetch(o), 'updated')
        info = A.load(self.cache, CERT_SHA)
        self.assertEqual((info['tag'], info['sha256']), ('android-v1.0.1', hashlib.sha256(self.v1).hexdigest()))
        # The token goes to the API only, never with the download (it is redirected to another host).
        self.assertEqual([auth for url, auth in o.calls], ['Bearer TOKEN', None])
        o.calls.clear()
        self.assertEqual(self.run_fetch(o), 'current')
        self.assertEqual(len(o.calls), 1, 'no second download')
        o = Opener([release('android-v1.0.1', self.v1), release('android-v1.0.2', self.v2)], self.files(('android-v1.0.1', self.v1), ('android-v1.0.2', self.v2)))
        self.assertEqual(self.run_fetch(o), 'updated')
        self.assertEqual(A.load(self.cache, CERT_SHA)['version'], '1.0.2')
        self.assertEqual((self.cache / A.ASSET).read_bytes(), self.v2)
        self.assertFalse((self.cache / (A.ASSET + '.part')).exists())

    def test_a_bad_new_file_keeps_the_old_one(self):
        self.run_fetch(Opener([release('android-v1.0.1', self.v1)], self.files(('android-v1.0.1', self.v1))))
        wrong_key = fake_apk(certs=(b'someone else',))
        for rel, body in ((release('android-v1.0.2', wrong_key), wrong_key),          # signed with another key
                          (release('android-v1.0.2', self.v2), self.v2[:-10]),       # truncated download
                          (release('android-v1.0.2', self.v2), None)):               # download fails
            files = self.files(('android-v1.0.2', body)) if body is not None else {}
            self.assertEqual(self.run_fetch(Opener([rel], files)), 'kept')
            info = A.load(self.cache, CERT_SHA)
            self.assertEqual(info['tag'], 'android-v1.0.1')
            self.assertFalse((self.cache / (A.ASSET + '.part')).exists())

    def test_github_unreachable(self):
        self.assertEqual(self.run_fetch(Opener(fail_api=True)), 'none')
        self.run_fetch(Opener([release('android-v1.0.1', self.v1)], self.files(('android-v1.0.1', self.v1))))
        self.assertEqual(self.run_fetch(Opener(fail_api=True)), 'kept')
        self.assertIsNotNone(A.load(self.cache, CERT_SHA))

    def test_no_release_left_removes_the_download(self):
        self.run_fetch(Opener([release('android-v1.0.1', self.v1)], self.files(('android-v1.0.1', self.v1))))
        self.assertEqual(self.run_fetch(Opener([])), 'none')
        self.assertIsNone(A.load(self.cache, CERT_SHA))
        self.assertFalse((self.cache / A.ASSET).exists())

class LoadPublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / 'android'
        self.cache.mkdir()
        self.apk = fake_apk()
        (self.cache / A.ASSET).write_bytes(self.apk)
        self.info = {'tag': 'android-v1.2.3', 'version': '1.2.3', 'published': '2026-09-28T08:19:58Z', 'size': len(self.apk),
                     'sha256': hashlib.sha256(self.apk).hexdigest()}
        (self.cache / 'latest.json').write_text(json.dumps(self.info), encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_rechecks_the_cached_file(self):
        self.assertEqual(A.load(self.cache, CERT_SHA)['version'], '1.2.3')
        self.assertIsNone(A.load(self.cache), 'the real certificate is required by default')
        (self.cache / A.ASSET).write_bytes(fake_apk(extra=b'swapped'))
        self.assertIsNone(A.load(self.cache, CERT_SHA))

    def test_load_refuses_a_bad_record(self):
        for bad in ({**self.info, 'version': '9.9.9'}, {**self.info, 'tag': 'v1.2.3'}, {**self.info, 'sha256': None}, {}, []):
            (self.cache / 'latest.json').write_text(json.dumps(bad), encoding='utf-8')
            self.assertIsNone(A.load(self.cache, CERT_SHA), bad)
        (self.cache / 'latest.json').write_text('{not json', encoding='utf-8')
        self.assertIsNone(A.load(self.cache, CERT_SHA))
        self.assertIsNone(A.load(Path(self.tmp.name) / 'missing', CERT_SHA))

    def test_publish_copies_the_apk_and_latest_json_and_clears_old_files(self):
        out = Path(self.tmp.name) / 'dist'
        info = A.load(self.cache, CERT_SHA)
        A.publish(out, info)
        self.assertEqual((out / A.PUBLIC_APK).read_bytes(), self.apk)
        latest = json.loads((out / A.PUBLIC_DIR / 'latest.json').read_text(encoding='utf-8'))
        self.assertEqual(latest['url'], 'https://cipherlacuna.ae/download/Cipher-Lacuna.apk')
        self.assertEqual((latest['version'], latest['sha256'], latest['size']), ('1.2.3', info['sha256'], len(self.apk)))
        self.assertNotIn('path', latest)
        (out / A.PUBLIC_DIR / 'old.apk').write_bytes(b'x')
        A.publish(out, info)
        self.assertFalse((out / A.PUBLIC_DIR / 'old.apk').exists())
        A.publish(out, None)
        self.assertFalse((out / A.PUBLIC_DIR).exists(), 'no APK: no download folder')

    def test_size_in_mb(self):
        self.assertEqual(A.size_mb(2878160), '2.7')

class PageTests(unittest.TestCase):
    INFO = {'tag': 'android-v1.0.1', 'version': '1.0.1', 'published': '2026-09-27T21:30:00Z', 'size': 2878160,
            'sha256': '0a0273fa03a3af1636dc7e1448bd5d86d162d776717b85e84c830ce9e64e01f2', 'path': Path('unused')}

    @classmethod
    def setUpClass(cls):
        import build
        cls.build = build
        data, feed, sources, uae, models = build.load_all()
        cls.with_app, _ = build.render_page(data, feed, sources, uae, models, android=cls.INFO)
        cls.without, _ = build.render_page(data, feed, sources, uae, models)

    def card(self, page):
        m = re.search(r'<div class="ab-box ab-app" id="android">.*?</a></div>', page, re.S)
        return m.group(0) if m else ''

    def test_card_in_the_about_section(self):
        card = self.card(self.with_app)
        self.assertTrue(card)
        about = self.with_app[self.with_app.index('id="about"'):]
        self.assertIn(card, about[:about.index('</section>')])
        for text in ('Version <bdi>1.0.1</bdi>', '<bdi>2.7</bdi> MB', 'الإصدار <bdi>1.0.1</bdi>', 'ميجابايت', self.INFO['sha256'],
                     'Download for Android', 'نزّل التطبيق', 'Android 8.0'):
            self.assertIn(text, card)
        # The release time in UAE time: 21:30 UTC on 27 Sep is 28 Sep in Dubai.
        self.assertIn('28 Sep 2026', card)
        self.assertIn('href="download/Cipher-Lacuna.apk" download="Cipher-Lacuna.apk"', card)
        self.assertNotIn('github.com', card, 'the site serves the file itself')

    def test_footer_link_only_with_an_app(self):
        self.assertIn('<a href="#android" data-route="contact/android" data-i18n>Android app</a></nav>', self.with_app)
        for page in (self.without,):
            self.assertNotIn('id="android"', page)
            self.assertNotIn('download/Cipher-Lacuna.apk', page)
            self.assertNotIn('>Android app</a>', page)
        self.assertNotIn('__ANDROID_LINK__', self.with_app + self.without)

    def test_learn_footer_link(self):
        import learn
        c, s = learn.load()
        self.assertIn('<a href="index.html#contact/android">', learn.render(c, s, android=True))
        self.assertNotIn('<a href="index.html#contact/android">', learn.render(c, s))

    def test_router_and_first_paint_know_android(self):
        js = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')
        self.assertIn("contact: ['about', 'android']", js)
        self.assertIn("h === 'about' || h === 'android'", js)
        self.assertIn("'Android app':'تطبيق Android'", js)
        self.assertIn("h==='about'||h==='android'?'contact'", (ROOT / 'web' / 'template.html').read_text(encoding='utf-8'))

class WorkflowTests(unittest.TestCase):
    def test_publish_workflow_fetches_the_app_before_the_build(self):
        wf = (ROOT / '.github' / 'workflows' / 'publish.yml').read_text(encoding='utf-8')
        # A release run runs on its tag, which the github-pages environment does not let deploy: publish.yml has no
        # release trigger; android-release.yml starts it on main instead.
        self.assertNotRegex(wf, r'(?m)^  release:')
        self.assertIn('workflow_dispatch:', wf)
        # Claude is paid for only on the 3 scheduled runs a day (or a manual run with "ai" ticked), in Message Batches.
        ai_if = "if: github.event_name == 'schedule' || inputs.ai"
        for name in ('run: python scripts/news.py', 'run: python scripts/draft.py'):
            at = wf.index(name)
            self.assertIn(ai_if, wf[wf.rfind('- name:', 0, at):at])
        self.assertEqual(wf.count('ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}'), 2)
        self.assertIn("NEWS_BATCH: '1'", wf[wf.rfind('- name:', 0, wf.index('run: python scripts/news.py')):wf.index('run: python scripts/news.py')])
        self.assertRegex(wf, r"cron: '15 3,11,19 \* \* \*'")
        rel = (ROOT / '.github' / 'workflows' / 'android-release.yml').read_text(encoding='utf-8')
        self.assertRegex(rel, r'release:\s*\n\s*types: \[published\]')
        self.assertIn("startsWith(github.event.release.tag_name, 'android-v')", rel)
        self.assertIn('gh workflow run publish.yml --ref main', rel)
        self.assertIn('actions: write', rel)
        fetch, build = wf.index('run: python scripts/android_app.py'), wf.index('run: python scripts/build.py')
        restore = wf.index('path: .cache/android')
        self.assertLess(restore, fetch)
        self.assertLess(fetch, build)
        step = wf[wf.rfind('- name:', 0, fetch):fetch]
        self.assertIn('continue-on-error: true', step)
        self.assertIn('GH_TOKEN: ${{ github.token }}', step)
        self.assertIn("key: android-apk-${{ hashFiles('.cache/android/latest.json') }}", wf[build:])

if __name__ == '__main__':
    unittest.main()
