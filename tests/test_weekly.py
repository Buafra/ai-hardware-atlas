"""Weekly pages (scripts/weekly.py): "AI this week" and "UAE AI this week" per ISO week in UAE time, in English and
Arabic, from the current list and the archive, grouped by day and topic, rule-based, shareable and self-contained."""
import html,re,sys,tempfile,unittest
from datetime import date,datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build,topics,weekly

SOURCES=[{'id':'g','name':'Global Pub','name_ar':'ناشر عالمي','homepage':'https://g.example/','region':'global','lang':'en'},
         {'id':'u','name':'Gulf Daily','name_ar':'صحيفة الخليج','homepage':'https://u.example/','region':'uae','lang':'en'},
         {'id':'a','name':'Arabic Pub','name_ar':'ناشر عربي','homepage':'https://a.example/','region':'uae','lang':'ar'}]
def story(n,published,source='g',lang='en',uae=False,**kw):
    return {'id':f's{n}','source':source,'lang':lang,'uae':uae,'published':published,'title':f'Story {n} about AI chips','url':f'https://{source}.example/{n}',**kw}
# Week 42 of 2026 is 12-18 Oct. 20:30 UTC on Sunday 11 Oct is already Monday 12 Oct 00:30 in the UAE.
CURRENT=[story(1,'2026-10-16T09:00:00+00:00',title='NVIDIA ships a new GPU',summary_en='The GPU has 288 GB.',summary_ar='المعالج بذاكرة 288 جيجابايت.',summary_source='ai',title_ar='إنفيديا تشحن معالجاً'),
         story(2,'2026-10-16T07:00:00+00:00',title='OpenAI releases a new model',excerpt='The model reasons over images.'),
         story(3,'2026-10-11T20:30:00+00:00',source='u',uae=True,title='Abu Dhabi opens an AI campus',excerpt='For 2,000 students.'),
         story(4,'2026-10-14T10:00:00+00:00',source='a',lang='ar',uae=True,title='دبي تطلق برنامجاً للذكاء الاصطناعي',summary_en='Dubai launches an AI programme.',summary_ar='أطلقت دبي برنامجاً.',summary_source='ai')]
ARCHIVED=[{'id':'s5','source':'g','lang':'en','uae':False,'topic':'research','published':'2026-10-06T10:00:00+00:00','title':'A study of AI benchmarks','title_ar':None,
           'url':'https://g.example/5','summary_en':'Researchers compared benchmarks.','summary_ar':'قارن الباحثون المعايير.','excerpt':None},
          {'id':'s1','source':'g','lang':'en','uae':False,'topic':'hardware','published':'2026-10-16T09:00:00+00:00','title':'Duplicate of the current story','title_ar':None,
           'url':'https://g.example/1','summary_en':None,'summary_ar':None,'excerpt':None}]
NOW=datetime(2026,10,17,8,tzinfo=timezone.utc)

class WeeklyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages,cls.links=weekly.pages(CURRENT,ARCHIVED,SOURCES,NOW,logo='')
    def test_paths_ranges_and_weeks(self):
        self.assertEqual(sorted(self.pages),['weekly/2026-w41.html','weekly/2026-w42.html','weekly/ar-2026-w41.html','weekly/ar-2026-w42.html',
                                             'weekly/ar-uae-2026-w42.html','weekly/index.html','weekly/uae-2026-w42.html'])
        self.assertEqual(weekly.week_of('2026-10-11T20:30:00+00:00'),(2026,42))  # UAE time decides the week
        self.assertEqual(weekly.range_text(2026,42,'en'),'12–18 Oct 2026');self.assertEqual(weekly.range_text(2026,42,'ar'),'12–18 أكتوبر 2026')
        self.assertEqual(weekly.range_text(2026,40,'en'),'28 Sep – 4 Oct 2026');self.assertEqual(weekly.range_text(2026,53,'en'),'28 Dec 2026 – 3 Jan 2027')
        self.assertEqual(self.links['all'],{'en':'weekly/2026-w42.html','ar':'weekly/ar-2026-w42.html','week':42,'range_en':'12–18 Oct 2026','range_ar':'12–18 أكتوبر 2026'})
        self.assertEqual(self.links['uae']['en'],'weekly/uae-2026-w42.html')
        self.assertEqual(weekly.latest(CURRENT,ARCHIVED,SOURCES),self.links)
    def test_grouped_by_day_then_topic_with_summaries_and_links(self):
        page=self.pages['weekly/2026-w42.html']
        days=re.findall(r'<section class="w-day"><h2>([^<]+)</h2>',page)
        self.assertEqual(days,['Friday 16 Oct 2026','Monday 12 Oct 2026'])  # newest first; only days with English stories
        friday=page[page.index('Friday 16 Oct'):page.index('Monday 12 Oct')]
        heads=re.findall(r'<section class="w-topic"><h3>([^<]+) <span class="n">(\d+)</span></h3>',friday)
        want=sorted({topics.topic_of(CURRENT[0],SOURCES[0]),topics.topic_of(CURRENT[1],SOURCES[0])},key=list(topics.TOPICS).index)
        self.assertEqual([html.unescape(h) for h,_ in heads],[topics.label(t,'en') for t in want])
        self.assertIn('<p class="w-sum" lang="en" dir="ltr">The GPU has 288 GB.</p><p class="w-by">AI summary</p>',page)
        self.assertIn('<p class="w-sum" lang="en" dir="ltr">The model reasons over images.</p><p class="w-by">From the publisher</p>',page)
        self.assertIn('<a class="w-src" href="https://g.example/1" target="_blank" rel="noopener noreferrer">Source: Global Pub',page)
        self.assertNotIn('Duplicate of the current story',page)  # one copy per id: the current list's
        self.assertIn('<span>3 stories</span>',page)
        self.assertNotIn('دبي تطلق',page)  # an Arabic story is on the Arabic page
    def test_arabic_page(self):
        page=self.pages['weekly/ar-2026-w42.html']
        self.assertTrue(page.startswith('<!doctype html>\n<html lang="ar" dir="rtl">'))
        self.assertIn('<h1>الذكاء الاصطناعي هذا الأسبوع</h1>',page)
        self.assertIn('إنفيديا تشحن معالجاً',page);self.assertIn('<span class="mt">ترجمة بالذكاء الاصطناعي</span>',page)
        self.assertIn('دبي تطلق برنامجاً للذكاء الاصطناعي',page);self.assertIn('المصدر: ناشر عربي',page)
        self.assertNotIn('OpenAI releases a new model',page)  # no translation: not on the Arabic list
        self.assertIn('الجمعة 16 أكتوبر 2026',page)
        self.assertIn('<a class="w-lang" href="2026-w42.html" lang="en" hreflang="en">English</a>',page)
    def test_uae_pages_list_uae_stories_only(self):
        page=self.pages['weekly/uae-2026-w42.html']
        self.assertIn('<h1>UAE AI this week</h1>',page);self.assertIn('Abu Dhabi opens an AI campus',page)
        self.assertNotIn('NVIDIA ships',page);self.assertIn('Monday 12 Oct 2026',page)
        self.assertIn('<p class="w-also"><a href="2026-w42.html">AI this week</a></p>',page)
        self.assertNotIn('weekly/uae-2026-w41.html',self.pages)  # no UAE story that week: no page
    def test_notes_pager_and_archive_start(self):
        w42,w41=self.pages['weekly/2026-w42.html'],self.pages['weekly/2026-w41.html']
        self.assertIn('This week is still in progress',w42);self.assertNotIn('still in progress',w41)
        self.assertIn('This page starts on 6 Oct 2026, when the archive began.',w41)  # Monday 5 Oct is before the first story
        self.assertIn('<a class="w-prev" rel="prev" href="2026-w41.html">← Week 41</a>',w42)
        self.assertIn('<a class="w-next" rel="next" href="2026-w42.html">Week 42 →</a>',w41)
        self.assertIn('A study of AI benchmarks',w41)  # from the archive, with its AI summary
        self.assertIn('Researchers compared benchmarks.</p><p class="w-by">AI summary</p>',w41)
    def test_share_tags_and_no_requests_elsewhere(self):
        for path,page in self.pages.items():
            head=page[:page.index('</head>')]
            for tag in ('og:title','og:description','og:url','og:image','twitter:card','twitter:title','twitter:image'):self.assertIn(tag,head,path)
            self.assertIn(f'<meta property="og:url" content="https://cipherlacuna.ae/{path}">',head)
            self.assertNotRegex(page,r'<script|<iframe|<form|<img[^>]+src="(?:https?:)?//|<link[^>]+href="(?:https?:)?//(?!cipherlacuna\.ae)',path)
            self.assertIn('<link rel="stylesheet" href="weekly.css">',head,path)
            for tag in re.findall(r'<a\b[^>]*target="_blank"[^>]*>',page):self.assertIn('rel="noopener noreferrer"',tag)
            self.assertNotIn('Updated',page)  # the freshness line belongs to AI news only
        self.assertIn('<link rel="alternate" hreflang="ar" href="https://cipherlacuna.ae/weekly/ar-2026-w42.html">',self.pages['weekly/2026-w42.html'])
    def test_index_lists_weeks_in_both_languages(self):
        page=self.pages['weekly/index.html']
        self.assertLess(page.index('Week 42'),page.index('Week 41'))
        self.assertIn('<a class="w-wk-all" href="2026-w42.html">AI this week <span class="n">3 stories</span></a>',page)
        self.assertIn('<a class="w-wk-uae" href="uae-2026-w42.html">UAE AI this week <span class="n">1 story</span></a>',page)
        ar=page[page.index('id="ar"'):]
        # The Arabic list: Arabic stories and English ones with an AI translation (2 that week, none the week before).
        self.assertIn('href="ar-2026-w42.html">الذكاء الاصطناعي هذا الأسبوع <span class="n">خبران</span>',ar)
        self.assertIn('href="ar-2026-w41.html">الذكاء الاصطناعي هذا الأسبوع <span class="n">0 خبر</span>',ar)
        self.assertIn('لا توجد أخبار بالعربية هذا الأسبوع.',self.pages['weekly/ar-2026-w41.html'])
        self.assertIn('الأسبوع 41',ar)
    def test_write_removes_stale_pages_and_copies_the_stylesheet(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'weekly').mkdir();(Path(d)/'weekly'/'2020-w01.html').write_text('old',encoding='utf-8')
            written=weekly.write(d,self.pages)
            self.assertEqual(written,sorted(self.pages))
            self.assertFalse((Path(d)/'weekly'/'2020-w01.html').exists());self.assertTrue((Path(d)/'weekly'/'weekly.css').exists())
    def test_no_stories_no_weeks(self):
        pages,links=weekly.pages([],[],SOURCES,NOW)
        self.assertEqual(list(pages),['weekly/index.html']);self.assertEqual(links,{})
        self.assertIn('No weeks yet.',pages['weekly/index.html'])
    def test_css_is_rtl_safe(self):
        css=(build.ROOT/'web/weekly.css').read_text(encoding='utf-8')
        self.assertNotRegex(re.sub(r'/[*].*?[*]/','',css,flags=re.S),r'\b(?:margin|padding)-(?:left|right)\b|\b(?:left|right):')
        self.assertIn('@media (prefers-color-scheme:dark)',css)

class LinkTests(unittest.TestCase):
    """AI news and UAE AI link to the newest weekly page of their kind, in the page language, and to all weeks."""
    def test_week_links(self):
        c={'weeks':weekly.latest(CURRENT,ARCHIVED,SOURCES)}
        news=build.week_links(c,'all')
        self.assertIn('<a class="wk-this" data-lang="en" href="weekly/2026-w42.html"><span>AI this week</span><small>12–18 Oct 2026</small></a>',news)
        self.assertIn('<a class="wk-this" data-lang="ar" href="weekly/ar-2026-w42.html"><span>الذكاء الاصطناعي هذا الأسبوع</span>',news)
        self.assertIn('<a class="wk-all" href="weekly/index.html">',news)
        self.assertIn('href="weekly/uae-2026-w42.html"',build.week_links(c,'uae'))
        self.assertEqual(build.week_links({'weeks':{}},'all'),'')
    def test_page_links_to_the_weekly_pages(self):
        data,feed,sources,uae,models=build.load_all()
        with tempfile.TemporaryDirectory() as d:
            page,_=build.render_page(data,feed,sources,uae,models,brand_dir=Path(d),archive=[])
        items=build.news_items(feed,sources)
        if not items:
            self.skipTest('no headlines in data/news.json')
        news=page[page.index('id="news"'):page.index('id="uae"')]
        self.assertIn('<div class="wk-links">',news)
        links=weekly.latest(items,[],sources)
        self.assertIn(f'href="{links["all"]["en"]}"',news)

if __name__=='__main__':unittest.main()
