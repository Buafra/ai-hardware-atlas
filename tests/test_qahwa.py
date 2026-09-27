"""Qahwa & AI library page (scripts/qahwa.py): data rules, published-only, links, the early state and the build.

The sample (tests/fixtures/qahwa-sample.json, covers in tests/fixtures/qahwa-images/) holds only posts already published
on Instagram. It is written by the exporter itself, so the two lanes cannot drift:
    python "C:/Projects/AI Lessons/tools/export_cipher.py" --fixture tests/fixtures
The "many posts" document is synthetic: made-up text, generated here."""
import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import qahwa

FIX = ROOT / 'tests' / 'fixtures'
SAMPLE = FIX / 'qahwa-sample.json'
IMAGES = FIX / 'qahwa-images'
PROFILE = 'https://www.instagram.com/qahwa.w.ai/'
SITE_HOST = 'cipherlacuna.ae'
START = datetime(2026, 10, 1, 8, 0, tzinfo=timezone(timedelta(hours=4)))

def sample():
    return json.loads(SAMPLE.read_text(encoding='utf-8'))

def page_data(page):
    """The JSON the page inlines for its script."""
    m = re.search(r'<script type="application/json" id="qahwa-data">(.*?)</script>', page, re.S)
    return json.loads(m.group(1))

def synthetic(n=120, lessons=100):
    """A made-up document with n posts (no real lesson text): lessons first, then other kinds."""
    kinds = ['reel', 'story', 'challenge', 'recap', 'news', 'welcome', 'other']
    posts = []
    for i in range(1, n + 1):
        is_lesson = i <= lessons
        kind = 'lesson' if is_lesson else kinds[i % len(kinds)]
        pid = f'week-{(i - 1) // 5 + 1:02d}-day-{(i - 1) % 5 + 1:02d}--sample-{i}'
        posts.append({
            'id': pid, 'kind': kind, 'lesson': i if is_lesson else None, 'code': f'L{i:02d}' if is_lesson else None,
            'week': (i - 1) // 5 + 1, 'topic': ['basics', 'tools', 'life', 'hardware', 'safety'][i % 5] if is_lesson else kind,
            'title': {'en': f'Sample title {i}', 'ar': f'عنوان تجريبي {i}'},
            'summary': {'en': f'Sample summary number {i}.', 'ar': f'ملخص تجريبي رقم {i}.'},
            'slides': [{'type': 'cover', 'en': {'title': f'Sample title {i}', 'body': 'Sample body.'}, 'ar': {'title': f'عنوان تجريبي {i}', 'body': 'نص تجريبي.'}},
                       {'type': 'text', 'en': {'title': 'Sample heading', 'body': 'Sample paragraph.'}, 'ar': {'title': 'عنوان فرعي', 'body': 'فقرة تجريبية.'}}],
            'prompt': {'en': f'Sample prompt {i}', 'ar': f'أمر تجريبي {i}', 'code': f'L{i:02d}'} if is_lesson else None,
            'permalink': PROFILE if kind == 'story' else f'https://www.instagram.com/p/SAMPLE{i}/',
            'published_at': (START + timedelta(days=i)).isoformat(),
            'cover': None, 'related_concepts': ['tokens'] if i % 10 == 0 else [],
        })
    return {'schema': 1, 'generated_at': '2027-02-01T08:00:00+04:00', 'profile': PROFILE, 'posts': posts}

def validate(doc, **kw):
    return qahwa.validate(doc, IMAGES, **kw)

class Sample(unittest.TestCase):
    def test_sample_is_valid_and_published_only(self):
        doc = sample()
        validate(doc, concept_ids=set(qahwa.load_concepts()))
        self.assertTrue(doc['posts'])
        for p in doc['posts']:
            self.assertEqual(qahwa.unpublished_flag(p), '', p['id'])
            self.assertTrue(qahwa.instagram_url(p['permalink']), p['id'])
            self.assertTrue(set(p) <= set(qahwa.POST_FIELDS), f'{p["id"]} has fields outside the contract: {set(p) - set(qahwa.POST_FIELDS)}')
            if p['cover']:
                f = IMAGES / f'{p["id"]}.webp'
                self.assertLessEqual(f.stat().st_size, 40_000, f.name)
        self.assertGreaterEqual(sum(p['kind'] == 'lesson' for p in doc['posts']), 1)

    def test_teasers_name_posts_in_the_sample(self):
        """A "Coming next" teaser may only name a post that is itself in the (published-only) sample."""
        doc = sample()
        for p in doc['posts']:
            for s in p['slides']:
                if 'next' in s:
                    self.assertIsNotNone(qahwa.teaser_target(s['next'], doc['posts']), f'{p["id"]}: {s["next"]["en"]}')

    def test_sample_follows_the_exporter_contract(self):
        """Written by tools/export_cipher.py: '<day>--<post>' ids, a story's title is its claim, its summary the format."""
        for p in sample()['posts']:
            self.assertIn('--', p['id'])
            self.assertEqual(list(p), list(qahwa.POST_FIELDS))
            if p['kind'] == 'story':
                self.assertEqual(p['summary'], {'en': 'Myth or fact?', 'ar': 'خرافة أم حقيقة؟'})
                self.assertNotEqual(p['title']['en'], 'Myth or fact?')
            for s in p['slides']:
                self.assertIsInstance(s.get('en'), dict)
                self.assertIsInstance(s.get('ar'), dict)

    def test_fixture_images_match_the_posts(self):
        """No cover in the fixture folder belongs to a post that is not in the (published-only) sample."""
        ids = {p['id'] for p in sample()['posts']}
        self.assertEqual({f.stem for f in IMAGES.glob('*.webp')}, {p['id'] for p in sample()['posts'] if p['cover']})
        self.assertTrue({f.stem for f in IMAGES.glob('*.webp')} <= ids)

    def test_small_webp_covers(self):
        from PIL import Image
        for f in IMAGES.glob('*.webp'):
            with Image.open(f) as im:
                self.assertEqual(im.format, 'WEBP')
                self.assertLessEqual(im.width, 480, f.name)

class Validation(unittest.TestCase):
    def assertProblem(self, doc, needle, **kw):
        with self.assertRaises(qahwa.QahwaDataError) as cm:
            validate(doc, **kw)
        self.assertIn(needle, str(cm.exception))

    def post(self, doc, kind):
        return next(p for p in doc['posts'] if p['kind'] == kind)

    def test_schema(self):
        doc = sample(); doc['schema'] = 2
        self.assertProblem(doc, 'schema must be 1')

    def test_duplicate_id(self):
        doc = sample(); doc['posts'].append(copy.deepcopy(doc['posts'][0]))
        self.assertProblem(doc, 'duplicate post id')

    def test_invalid_id(self):
        doc = sample(); doc['posts'][0]['id'] = 'Week 01/day|x'
        self.assertProblem(doc, 'invalid id')

    def test_permalink_must_be_https_instagram(self):
        for bad in ('http://www.instagram.com/p/x/', 'https://example.com/p/x/', 'https://instagram.com.evil.example/p/', 'javascript:alert(1)', None):
            doc = sample(); self.post(doc, 'lesson')['permalink'] = bad
            self.assertProblem(doc, 'permalink must be an https link on instagram.com')

    def test_cover_must_exist_and_follow_the_id(self):
        doc = sample(); p = self.post(doc, 'lesson'); p['cover'] = 'images/qahwa/other.webp'
        self.assertProblem(doc, 'cover must be images/qahwa/')
        doc = sample()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(qahwa.QahwaDataError) as cm:
                qahwa.validate(doc, tmp)
            self.assertIn('is missing', str(cm.exception))

    def test_unknown_kind(self):
        doc = sample(); doc['posts'][0]['kind'] = 'podcast'
        self.assertProblem(doc, 'unknown kind')

    def test_both_languages(self):
        doc = sample(); del self.post(doc, 'lesson')['title']['ar']
        self.assertProblem(doc, 'title.ar is missing')
        doc = sample(); self.post(doc, 'lesson')['title']['en'] = ' '
        self.assertProblem(doc, 'title.en is empty')
        doc = sample(); del self.post(doc, 'lesson')['slides'][1]['ar']
        self.assertProblem(doc, 'both languages')
        doc = sample(); self.post(doc, 'lesson')['prompt'] = {'en': 'x', 'code': 'L01'}
        self.assertProblem(doc, 'prompt.ar is missing')

    def test_latin_only_arabic_title_is_a_note_not_an_error(self):
        """Owner rule: product names stay in Latin, so an Arabic title like "CPU + GPU + NPU + 128 GB" is fine."""
        doc = sample(); self.post(doc, 'lesson')['title']['ar'] = 'CPU + GPU + NPU + 128 GB'
        notes = []
        validate(doc, warnings=notes)
        self.assertTrue(any('no Arabic letters' in n for n in notes), notes)

    def test_rejects_posts_flagged_unpublished(self):
        for flag in ({'status': 'waiting'}, {'status': 'approved'}, {'status': 'failed'}, {'unpublished': True},
                     {'preview': True}, {'draft': True}, {'scheduled': True}, {'published': False}):
            doc = sample(); self.post(doc, 'lesson').update(flag)
            self.assertProblem(doc, 'is not published')
        for ok in ({'status': 'posted'}, {'status': 'posted-manually'}):
            doc = sample(); self.post(doc, 'lesson').update(ok)
            validate(doc)

    def test_lessons(self):
        doc = sample(); self.post(doc, 'lesson')['lesson'] = None
        self.assertProblem(doc, 'needs its lesson number')
        doc = sample(); self.post(doc, 'lesson')['lesson'] = '01'
        self.assertProblem(doc, 'whole number')
        doc = synthetic(3, 3); doc['posts'][1]['lesson'] = 1
        self.assertProblem(doc, 'lesson 1 is also')

    def test_published_at(self):
        doc = sample(); doc['posts'][0]['published_at'] = 'yesterday'
        self.assertProblem(doc, 'published_at must be an ISO time')
        doc = sample(); doc['posts'][0]['published_at'] = '2026-09-27T15:01'
        validate(doc)  # no offset: read as Dubai time

    def test_no_image_paths_in_slides(self):
        doc = sample(); self.post(doc, 'lesson')['slides'][0]['hero'] = 'what-is-ai'
        self.assertProblem(doc, 'must not carry image paths')
        for key in ('shot', 'inset', 'logo', 'img', 'video'):  # the exporter's keys too: one list for both lanes
            doc = sample(); self.post(doc, 'lesson')['slides'][0][key] = 'x'
            self.assertProblem(doc, 'must not carry image paths')
        doc = sample(); self.post(doc, 'lesson')['slides'][0]['en']['body'] = 'out/week-01/day-01/01.png'
        self.assertProblem(doc, 'must not carry image paths')

    def test_related_concepts_must_exist(self):
        doc = sample(); self.post(doc, 'lesson')['related_concepts'] = ['no-such-concept']
        self.assertProblem(doc, 'is not in data/learn/concepts.json', concept_ids=set(qahwa.load_concepts()))

    def test_content_policy(self):
        doc = sample(); self.post(doc, 'lesson')['summary']['en'] = 'Dubai data centres were damaged in the war.'
        self.assertProblem(doc, 'content policy')

    def test_every_problem_is_listed(self):
        doc = sample(); doc['posts'][0]['kind'] = 'podcast'; doc['posts'][1]['permalink'] = 'https://example.com/'
        with self.assertRaises(qahwa.QahwaDataError) as cm:
            validate(doc)
        self.assertIn('2 problem(s)', str(cm.exception))

class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = sample()
        cls.page = qahwa.render(cls.doc, qahwa.load_concepts())
        cls.data = page_data(cls.page)

    def test_data_is_inlined_safely(self):
        m = re.search(r'<script type="application/json" id="qahwa-data">(.*?)</script>', self.page, re.S)
        self.assertNotIn('<', m.group(1))
        doc = sample()
        next(p for p in doc['posts'] if p['kind'] == 'lesson')['summary']['en'] = 'Close </script><script>alert(1)</script> & <!-- here'
        page = qahwa.render(doc)
        self.assertEqual(page.count('<script>alert(1)'), 0)
        self.assertIn('</script><script>alert(1)', json.dumps(page_data(page), ensure_ascii=False))

    def test_only_the_contract_fields_reach_the_page(self):
        doc = sample()
        doc['posts'][0]['caption'] = {'en': 'secret caption', 'ar': 'نص خاص'}
        doc['posts'][0]['answer'] = {'en': 'secret answer', 'ar': 'جواب خاص'}
        page = qahwa.render(doc)
        self.assertNotIn('secret caption', page)
        self.assertNotIn('secret answer', page)

    def test_published_posts_only(self):
        self.assertEqual({p['id'] for p in self.data['posts']}, {p['id'] for p in self.doc['posts']})
        # The page carries no preview section or wording.
        for word in ('Preview', 'preview', 'not published yet', 'Coming soon', 'معاينة', 'لم يُنشر'):
            self.assertNotIn(word, self.page, word)

    def test_teaser_for_an_unpublished_post_never_reaches_the_page(self):
        doc = sample()
        lesson = next(p for p in doc['posts'] if p['kind'] == 'lesson')
        cta = next(s for s in lesson['slides'] if s['type'] == 'cta')
        cta['next'] = {'en': 'Lesson 77: UNPUBLISHEDTEASER', 'ar': 'الدرس 77: عنوان تجريبي مخفي'}
        page = qahwa.render(doc)
        self.assertNotIn('UNPUBLISHEDTEASER', page)
        self.assertNotIn('عنوان تجريبي مخفي', page)
        cta['next'] = {'en': 'Tonight: SECRETNAME', 'ar': 'الليلة: اسم'}
        self.assertNotIn('SECRETNAME', qahwa.render(doc))
        # a teaser naming a post that is on the page stays
        n = lesson['lesson']
        cta['next'] = {'en': f'Lesson {n:02d}: again', 'ar': f'الدرس {n:02d}: مرة أخرى'}
        self.assertIn(f'Lesson {n:02d}: again', qahwa.render(doc))

    def test_stories_link_to_the_profile(self):
        stories = [p for p in self.data['posts'] if p['kind'] == 'story']
        self.assertTrue(stories)
        # Even when the data has the story's own (expiring) link, the page links the profile.
        doc = sample()
        for p in doc['posts']:
            if p['kind'] == 'story':
                p['permalink'] = 'https://www.instagram.com/stories/qahwa.w.ai/123/'
        page = qahwa.render(doc)
        self.assertIn("it.kind === 'story' || !isIG(it.permalink) ? PROFILE : it.permalink", page)
        self.assertNotIn('stories/qahwa.w.ai/123', re.search(r'<noscript>(.*?)</noscript>', page, re.S).group(1))
        # Carousels and reels keep their own permalink.
        for p in self.data['posts']:
            if p['kind'] in ('lesson', 'reel', 'welcome'):
                self.assertRegex(p['permalink'], r'^https://www\.instagram\.com/(p|reel)/')

    def test_no_freshness_line(self):
        low = self.page.lower()
        for word in ('last updated', 'updated ', 'آخر تحديث', 'تم التحديث', 'generated_at'):
            self.assertNotIn(word, low, word)

    def test_no_foreign_urls(self):
        """Only instagram.com links and the site itself; everything the page loads is same-origin."""
        for url in re.findall(r'https?://[^\s"\'<>)\\]+', self.page):
            host = urlparse(url).hostname
            self.assertIn(host, ('www.instagram.com', 'instagram.com', SITE_HOST), url)
            if host == SITE_HOST:
                self.assertTrue(url.startswith('https://'), url)
        for attr in re.findall(r'\s(?:src|href)="([^"]+)"', self.page):
            if attr.startswith(('http:', 'https:')):
                self.assertIn(urlparse(attr).hostname, ('www.instagram.com', 'instagram.com', SITE_HOST), attr)
            else:
                self.assertFalse(attr.startswith('//'), attr)
        # Nothing is loaded from another host: every src is a local path or a data: image.
        for src in re.findall(r'\ssrc="([^"]+)"', self.page):
            self.assertFalse(src.startswith(('http:', 'https:', '//')), src)
        for url in re.findall(r'url\(([^)]+)\)', self.page):
            self.assertTrue(url.strip('\'"').startswith(('fonts/qahwa/', 'data:')), url)
        self.assertNotIn('fonts.googleapis', self.page)
        self.assertNotIn('gstatic', self.page)
        self.assertNotIn('<link rel="stylesheet"', self.page)
        self.assertNotRegex(self.page, r'<script[^>]+src=')

    def test_fonts_are_self_hosted(self):
        faces = re.findall(r"@font-face \{ font-family: '([^']+)'.*?src: url\(([^)]+)\)", self.page)
        self.assertEqual({f for f, _ in faces}, {'Outfit', 'IBM Plex Sans Arabic', 'Caveat'})
        for _, url in faces:
            self.assertTrue((qahwa.FONTS.parent.parent / url).is_file(), url)
        self.assertEqual(self.page.count('font-display: swap'), len(faces))
        for fam in ('outfit', 'ibm-plex-sans-arabic', 'caveat'):
            self.assertIn('SIL OPEN FONT LICENSE', (qahwa.FONTS / fam / 'OFL.txt').read_text(encoding='utf-8').upper())

    def test_page_basics(self):
        self.assertIn('<html lang="en" dir="ltr">', self.page)
        self.assertIn('<a class="skip" href="#library"', self.page)
        self.assertIn(f'href="{PROFILE}"', self.page)
        self.assertIn('data-home href="index.html"', self.page)
        self.assertIn('Part of <b>Cipher Lacuna</b>', self.page)
        self.assertIn('<noscript><ul class="nojs">', self.page)
        self.assertNotIn('🇦🇪', self.page)
        js = (ROOT / 'web' / 'qahwa.js').read_text(encoding='utf-8')
        self.assertIn('الصقه في المساعد الذكي', js)  # the owner's term for an AI assistant
        self.assertNotIn('مساعد ذكي.', js)

    def test_related_guides_use_learn_concepts(self):
        doc = synthetic(20, 20)
        page = qahwa.render(doc, qahwa.load_concepts())
        data = page_data(page)
        self.assertEqual(set(data['concepts']), {'tokens'})
        self.assertEqual(data['learn'], 'learn.html')
        self.assertIn("`${LEARN}#concept/${encodeURIComponent(r.id)}`", page)

    def test_many_posts(self):
        doc = synthetic()
        validate(doc)
        page = qahwa.render(doc, qahwa.load_concepts())
        data = page_data(page)
        self.assertEqual(len(data['posts']), 120)
        times = [p['published_at'] for p in data['posts']]
        self.assertEqual(times, sorted(times, reverse=True))
        self.assertIn('PAGE_SIZE = 24', page)

class EmptyAndLinks(unittest.TestCase):
    def test_missing_data_builds_the_early_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = qahwa.build(Path(tmp) / 'out', data_path=Path(tmp) / 'missing.json', images_dir=Path(tmp))
            page = out.read_text(encoding='utf-8')
            self.assertEqual(page_data(page)['posts'], [])
            self.assertIn('New lessons arrive here as they are published on Instagram', page)
            self.assertIn('<section class="early" id="early" aria-labelledby="earlyH">', page)  # shown, even without JavaScript
            self.assertNotIn('<noscript><ul', page)

    def test_lesson_url(self):
        doc = sample()
        self.assertEqual(qahwa.lesson_url(1, doc), 'qahwa.html#lesson-01')
        self.assertEqual(qahwa.lesson_url('1', doc), 'qahwa.html#lesson-01')
        self.assertIsNone(qahwa.lesson_url(2, doc))
        self.assertIsNone(qahwa.lesson_url(None, doc))
        self.assertIsNone(qahwa.lesson_url(1, qahwa.empty_doc()))
        flagged = sample(); next(p for p in flagged['posts'] if p['kind'] == 'lesson')['status'] = 'waiting'
        self.assertIsNone(qahwa.lesson_url(1, flagged))
        self.assertEqual(qahwa.lesson_url(42, synthetic(50, 50)), 'qahwa.html#lesson-42')
        self.assertEqual(qahwa.slug({'kind': 'lesson', 'lesson': 7, 'id': 'x'}), 'lesson-07')
        self.assertEqual(qahwa.slug({'kind': 'reel', 'lesson': None, 'id': 'week-01-day-01--2-try-reel-cover'}), 'post-week-01-day-01--2-try-reel-cover')

class SafeBuild(unittest.TestCase):
    """build_safe(): what scripts/build.py calls. It never raises on bad Qahwa data, so the rest of the site still deploys."""

    def run_safe(self, doc_or_text):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        data = Path(tmp) / 'q.json'
        data.write_text(doc_or_text if isinstance(doc_or_text, str) else json.dumps(doc_or_text, ensure_ascii=False), encoding='utf-8')
        logged = []
        path, problems = qahwa.build_safe(Path(tmp) / 'out', data_path=data, images_dir=IMAGES, log=logged.append)
        return page_data(path.read_text(encoding='utf-8')), problems, logged

    def test_good_data_is_built_as_is(self):
        data, problems, _ = self.run_safe(sample())
        self.assertEqual(problems, [])
        self.assertEqual(len(data['posts']), len(sample()['posts']))

    def test_only_the_bad_post_is_left_out(self):
        doc = sample()
        doc['posts'][0]['permalink'] = 'https://example.com/'
        doc['posts'].append(copy.deepcopy(doc['posts'][1]))  # a repeated id
        data, problems, logged = self.run_safe(doc)
        self.assertTrue(problems)
        self.assertEqual({p['id'] for p in data['posts']}, {p['id'] for p in sample()['posts'][1:]})
        self.assertEqual(len(data['posts']), len(sample()['posts']) - 1)
        self.assertTrue(any('built qahwa.html with' in m for m in logged), logged)

    def test_broken_file_builds_the_early_state(self):
        data, problems, _ = self.run_safe('{not json')
        self.assertEqual(data['posts'], [])
        self.assertTrue(problems)
        doc = sample(); doc['schema'] = 9
        data, problems, _ = self.run_safe(doc)
        self.assertEqual(data['posts'], [])
        self.assertTrue(problems)

class CheckCommand(unittest.TestCase):
    """python scripts/qahwa.py --check: what the exporter runs before every push."""

    def run_check(self, doc):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'q.json'
            data.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
            return subprocess.run([sys.executable, str(ROOT / 'scripts' / 'qahwa.py'), '--check', '--data', str(data), '--images', str(IMAGES)],
                                  capture_output=True, text=True, encoding='utf-8', errors='replace')

    def test_check(self):
        r = self.run_check(sample())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('ok:', r.stdout)
        doc = sample(); doc['posts'][0]['kind'] = 'podcast'
        r = self.run_check(doc)
        self.assertEqual(r.returncode, 1)
        self.assertIn('unknown kind', r.stdout)
        doc = sample(); next(p for p in doc['posts'] if p['kind'] == 'lesson')['summary']['en'] = 'Dubai data centres were damaged in the war.'
        self.assertEqual(self.run_check(doc).returncode, 1)  # the content policy is part of the check

class Build(unittest.TestCase):
    def test_build_writes_page_covers_fonts_and_brand(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'images' / 'qahwa').mkdir(parents=True)
            (out / 'images' / 'qahwa' / 'stale-post.webp').write_bytes(b'old')
            path = qahwa.build(out, data_path=SAMPLE, images_dir=IMAGES)
            self.assertEqual(path, out / 'qahwa.html')
            covers = {f.name for f in (out / 'images' / 'qahwa').iterdir()}
            self.assertEqual(covers, {f'{p["id"]}.webp' for p in sample()['posts'] if p['cover']})
            self.assertTrue((out / 'fonts' / 'qahwa' / 'outfit' / 'OFL.txt').is_file())
            self.assertTrue(list((out / 'fonts' / 'qahwa').rglob('*.woff2')))
            self.assertTrue((out / 'brand' / 'qahwa' / 'bot-badge.webp').is_file())
            page = path.read_text(encoding='utf-8')
            for src in re.findall(r'(?:src|href)="((?:brand|images|fonts)/[^"]+)"', page):
                self.assertTrue((out / src).is_file(), src)

    def test_bad_data_writes_nothing(self):
        doc = sample(); doc['posts'][0]['kind'] = 'podcast'
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'q.json'
            data.write_text(json.dumps(doc), encoding='utf-8')
            with self.assertRaises(qahwa.QahwaDataError):
                qahwa.build(Path(tmp) / 'out', data_path=data, images_dir=IMAGES)
            self.assertFalse((Path(tmp) / 'out').exists())

if __name__ == '__main__':
    unittest.main()
