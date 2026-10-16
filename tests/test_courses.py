"""Learn AI's fourth tab, "Free official AI courses in the UAE" (data/learn/courses.json): data rules, the page without
JavaScript, the deep links, and learn.json for the app. Counts come from the data."""
import copy
import html as h
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import learn
from test_learn import Page, Quiet, catalog  # the Learn AI page's own test helpers

DOC = learn.load_courses()
COURSES = DOC['courses']

class DataTests(unittest.TestCase):
    def test_repository_courses_pass(self):
        self.assertEqual(learn.course_problems(DOC), [])
        self.assertTrue(COURSES)
        c, s = learn.load()
        learn.validate(c, s, catalog()['products'])  # read by default

    def test_free_on_the_organisers_own_page(self):
        for c in COURSES:
            domains = learn.COURSE_ORGS[c['org']][1]
            for url in [c['url'], c['free_source']] + ([c['url_ar']] if c.get('url_ar') else []) + [i['url'] for i in c.get('items') or []]:
                self.assertTrue(url.startswith('https://') and learn._on_domain(url, domains), (c['id'], url))
            self.assertTrue(c['cost_en'].startswith('Free') and 'مجاني' in c['cost_ar'], c['id'])

    def test_the_verified_list(self):
        # The verifier's list: One Million Prompters (its official terms say free), the DGOV Academy items and the TDRA camp,
        # and the MBRSG and HBMSU courses (free on their own pages). Paid MBZUAI programmes are not listed.
        ids = {c['id'] for c in COURSES}
        self.assertTrue({'one-million-prompters', 'dgov-digital-literacy-ai', 'dgov-talks-ai', 'tdra-camp',
                         'mbrsg-ai-digital-transformation-government', 'hbmsu-chatgpt-smart-learning'} <= ids)
        self.assertNotIn('mbzuai', learn.COURSE_ORGS)
        camp = next(c for c in COURSES if c['id'] == 'tdra-camp')
        self.assertEqual(camp['status'], 'between-editions')
        self.assertIn('9 to 15', camp['audience_en'])

    def broken(self, mutate, today=None):
        doc = copy.deepcopy(DOC)
        mutate(doc['courses'][0], doc)
        problems = learn.course_problems(doc, today=today)
        self.assertTrue(problems)
        return '\n'.join(problems)

    def test_validation_catches_each_rule(self):
        self.assertIn('unknown field', self.broken(lambda c, d: c.update(price='AED 380')))
        self.assertIn('allow-list', self.broken(lambda c, d: c.update(org='mbzuai')))
        self.assertIn("organiser's own domain", self.broken(lambda c, d: c.update(url='https://gulfnews.com/free-ai-course')))
        self.assertIn("organiser's own domain", self.broken(lambda c, d: c.update(free_source='https://example.com/free')))
        self.assertIn('https', self.broken(lambda c, d: c.update(url='http://dub.ai/en/omp/')))
        self.assertIn('must start with "Free"', self.broken(lambda c, d: c.update(cost_en='AED 2,400 per participant')))
        self.assertIn('مجاني', self.broken(lambda c, d: c.update(cost_ar='الرسوم 2400 درهم')))
        self.assertIn('languages', self.broken(lambda c, d: c.update(languages=['xx'])))
        self.assertIn('languages', self.broken(lambda c, d: c.update(languages=[])))
        self.assertIn('format', self.broken(lambda c, d: c.update(format='webinar')))
        self.assertIn('status', self.broken(lambda c, d: c.update(status='soon')))
        self.assertIn('between editions', self.broken(lambda c, d: c.update(status='between-editions', status_en=None, status_ar=None)))
        self.assertIn('in the future', self.broken(lambda c, d: c.update(checked=(date.today() + timedelta(days=2)).isoformat())))
        self.assertIn('real date', self.broken(lambda c, d: c.update(checked='16 Oct 2026')))
        self.assertIn('Arabic version', self.broken(lambda c, d: c.pop('audience_ar')))
        self.assertIn('missing', self.broken(lambda c, d: c.pop('free_source')))
        self.assertIn('duplicate course', self.broken(lambda c, d: d['courses'].append(copy.deepcopy(c))))
        self.assertIn('breaks the content policy', self.broken(lambda c, d: c.update(audience_en='People in Dubai affected by the crisis')))
        with_items = lambda f: lambda c, d: (c.update(items=[{'title_en': 'A', 'title_ar': 'أ', 'minutes': 5, 'url': c['url']}]), f(c['items'][0]))
        self.assertIn('minutes', self.broken(with_items(lambda i: i.update(minutes=0))))
        self.assertIn('needs exactly', self.broken(with_items(lambda i: i.update(views=10))))
        self.assertIn("organiser's own domain", self.broken(with_items(lambda i: i.update(url='https://www.youtube.com/watch?v=x'))))
        self.assertEqual(learn.course_problems({'items': []}), ['courses.json must be {"courses": [...]}'])

    def test_build_refuses_bad_courses(self):
        with tempfile.TemporaryDirectory() as d:
            c, s = learn.load()
            doc = copy.deepcopy(DOC)
            doc['courses'][0]['url'] = 'https://mirror.example.org/course'
            for name, obj in (('concepts.json', c), ('stacks.json', s), ('reports.json', learn.load_reports()), ('courses.json', doc)):
                (Path(d) / name).write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')
            with self.assertRaises(learn.LearnDataError) as cm:
                learn.build(Path(d) / 'out', data_dir=Path(d))
            self.assertIn("is not on the organiser's own domain", str(cm.exception))
            self.assertFalse((Path(d) / 'out' / 'learn.html').exists())

class PageTests(Quiet, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.concepts, cls.stacks = learn.load()
        cls.html = learn.render(cls.concepts, cls.stacks, catalog())
        cls.panel = cls.html[cls.html.index('<section id="courses"'):]
        cls.panel = cls.panel[:cls.panel.index('</section>\n')]
        cls.page = Page()
        cls.page.feed(cls.html)

    def test_fourth_tab_status_and_order(self):
        n = len(COURSES)
        self.has(f'<a class="l-tab" href="#courses" data-tab="courses"><span data-lang="en">Courses</span><span data-lang="ar">الدورات</span> '
                 f'<span class="n" data-count="courses">{n}</span></a></nav>', self.html)
        status = self.html[self.html.index('<p class="statusbar">'):]
        self.has(f'<span data-lang="en">{learn.cnt(n, "course", "en")}</span><span data-lang="ar">{learn.cnt(n, "course", "ar")}</span>',
                 status[:status.index('</p>')])
        i = [self.html.index(f'<section id="{p}" class="l-panel" data-panel="{p}"') for p in ('concepts', 'stacks', 'reports', 'courses')]
        self.assertEqual(i, sorted(i))
        self.assertLess(i[3], self.html.index('<p class="muted l-note">'))
        self.has("/^#course/.test(location.hash)?'courses'", self.html)
        self.has('<h2 id="courses-h"><span data-lang="en">Free official AI courses in the UAE</span>'
                 '<span data-lang="ar">دورات رسمية مجانية في الذكاء الاصطناعي في الإمارات</span></h2>', self.panel)
        self.has('html[data-ltab="courses"] [data-panel]:not([data-panel="courses"]){display:none}', self.html)

    def test_every_course_with_its_facts(self):
        ids = [a['id'][len('course/'):] for a in self.page.items if a.get('id', '').startswith('course/')]
        self.assertEqual(ids, [c['id'] for c in COURSES])
        for c in COURSES:
            item = self.panel[self.panel.index(f'id="course/{c["id"]}"'):]
            item = item[:item.index('</details>')]
            for text in (c['title_en'], c['title_ar'], c['organiser_en'], c['organiser_ar'], c['audience_en'], c['audience_ar'],
                         c['format_en'], c['format_ar'], c['cost_en'], c['cost_ar'], c['how_en'], c['how_ar']):
                self.has(h.escape(text), item)
            for code in c['languages']:
                self.has(learn.COURSE_LANGS[code][0], item)
                self.has(learn.COURSE_LANGS[code][1], item)
            self.has(learn.L(*learn.COURSE_FORMATS[c['format']]), item)
            self.has(learn.L(*learn.COURSE_STATUS[c['status']]), item)
            self.has(f'<a class="c-link r-link" href="{h.escape(c["url"])}" target="_blank" rel="noopener noreferrer">', item)
            if c.get('url_ar'):
                self.has(f'href="{h.escape(c["url_ar"])}" hreflang="ar" target="_blank" rel="noopener noreferrer"', item)
            self.has(f'<time datetime="{c["checked"]}">{learn.L(learn.report_date(c["checked"], "en"), learn.report_date(c["checked"], "ar"))}</time>', item)
            for ep in c.get('items') or []:
                self.has(f'href="{h.escape(ep["url"])}"', item)
            if c.get('title_ar_translated'):
                self.has(f'العنوان الرسمي: <bdi lang="en" dir="ltr">{h.escape(c["title_en"])}</bdi>', item)
        self.has('Paid courses are not listed.', self.panel)
        self.has('لا ندرج الدورات المدفوعة.', self.panel)

    def test_no_images_and_no_other_hosts(self):
        self.lacks('<img', self.panel)
        self.lacks('<iframe', self.panel)
        self.assertEqual(self.page.external, [])
        allowed = [d for _, ds in learn.COURSE_ORGS.values() for d in ds]
        hosts = {learn.urlparse(a['href']).hostname for a in self.page.links if a.get('class', '').startswith('c-link')}
        self.assertTrue(hosts and all(any(x == d or x.endswith('.' + d) for d in allowed) for x in hosts), hosts)

    def test_render_takes_the_courses_it_is_given(self):
        one = {'courses': [copy.deepcopy(COURSES[0])]}
        page = learn.render(self.concepts, self.stacks, catalog(), courses_doc=one)
        self.has('<span class="n" data-count="courses">1</span>', page)
        self.assertEqual(page.count('class="l-item l-course"'), 1)
        empty = learn.render(self.concepts, self.stacks, catalog(), courses_doc={'courses': []})
        self.has('No courses yet.', empty)
        self.lacks('class="l-item l-course"', empty)

    def test_course_text_is_escaped(self):
        doc = copy.deepcopy(DOC)
        doc['courses'][0]['title_en'] = '<script>alert(1)</script>'
        doc['courses'][0]['audience_ar'] = '"><img src=x onerror=alert(2)>'
        page = learn.render(self.concepts, self.stacks, catalog(), courses_doc=doc)
        self.lacks('<script>alert(1)', page)
        self.lacks('<img src=x', page)

    def test_script_knows_the_tab(self):
        js = (ROOT / 'web' / 'learn.js').read_text(encoding='utf-8')
        self.has("const TABS = ['concepts', 'stacks', 'reports', 'courses'];", js)
        self.has('(concept|stack|report|course)\\/', js)
        self.has('courses|concept\\/|stack\\/|report\\/|course\\/', js)

class AppTests(unittest.TestCase):
    def test_learn_json_carries_the_courses(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import app_data
        import build
        data, feed, sources, uae, models = build.load_all()
        docs = learn.load()
        out = app_data.payloads(data, feed, sources, uae, models, *docs)
        self.assertEqual(out['learn.json']['courses'], COURSES)
        self.assertTrue({'groups', 'concepts', 'stacks', 'reports', 'courses'} <= set(out['learn.json']))
        none = app_data.payloads(data, feed, sources, uae, models, *docs, courses_doc={'courses': []})
        self.assertEqual(none['learn.json']['courses'], [])

if __name__ == '__main__':
    unittest.main()
