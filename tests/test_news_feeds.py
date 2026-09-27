"""The news source list and the non-RSS feed types (news sitemaps, the Anthropic listing page), tested on trimmed
copies of the real feeds saved in tests/fixtures/news (fetched 2026-09-27)."""
import json,re,sys,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import news,policy
FIX=ROOT/'tests/fixtures/news'
NOW=datetime(2026,9,27,18,tzinfo=timezone.utc)
SOURCES=json.loads((ROOT/'data/news-sources.json').read_text(encoding='utf-8'))
SRC={s['id']:s for s in SOURCES}
NEW_UAE={'kt-tech','gulftoday-business','wam-en','wam-ar','albayan','sharjah24-en','sharjah24-ar'}
REMOVED={'nvidia-blog','thenational-uae2'}
ARABIC=re.compile(r'[؀-ۿ]')

def fixture(name):return (FIX/name).read_bytes()

def collect(sid,raw,**over):
    with mock.patch.object(news,'fetch',return_value=raw):return news.collect({**SRC[sid],**over},NOW)

def sitemap(*urls):
    """A news sitemap with (loc, title, ISO date) entries."""
    body=''.join(f'<url><loc>{l}</loc><news:news><news:publication><news:name>X</news:name><news:language>en</news:language></news:publication>'
                 f'<news:publication_date>{d}</news:publication_date><news:title>{t}</news:title></news:news></url>' for l,t,d in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">'+body+'</urlset>').encode('utf-8')

def listing(*posts,directory='news'):
    """An anthropic.com listing page whose Next.js data holds these posts (title, slug, ISO date, summary)."""
    data=[{'_type':'post','directories':[{'_key':directory,'_type':'tag','label':directory.title(),'value':directory}],'publishedOn':d,
           'slug':{'_type':'slug','current':s},'summary':x,'title':t} for t,s,d,x in posts]
    flight='5:["$","div",null,{"posts":'+json.dumps(data,ensure_ascii=False)+'}]\n'
    return ('<html><body><script>self.__next_f.push('+json.dumps([1,flight])+')</script></body></html>').encode('utf-8')

class NewsSitemapTests(unittest.TestCase):
    def test_parse_newest_first_without_image_links(self):
        rows=news.parse_news_sitemap(fixture('wam-en-sitemap.xml'))
        self.assertEqual(len(rows),6)
        self.assertEqual([r[2] for r in rows],sorted((r[2] for r in rows),reverse=True))
        for title,link,published,description,*_ in rows:
            self.assertTrue(title);self.assertTrue(link.startswith('https://www.wam.ae/en/article/'),link)
            self.assertEqual(published.tzinfo,timezone.utc);self.assertEqual(description,'')
        # 2026-09-27T20:16:47+04:00 in the sitemap
        self.assertEqual(rows[0][2],datetime(2026,9,27,16,16,47,tzinfo=timezone.utc))
    def test_wam_english(self):
        items=collect('wam-en',fixture('wam-en-sitemap.xml'))
        self.assertEqual([i['title'] for i in items],['Warnings of toxic e-waste tsunami driven by AI boom','OpenAI says AI agents posted 53 user images online',
                                                      'UN Women launches digital, AI hub for gender equality'])
        self.assertTrue(all(i['lang']=='en' and 'excerpt' not in i for i in items))
        self.assertFalse(any(i['uae'] for i in items))  # uae_by_content: global wire stories that don't name the UAE
    def test_wam_arabic_titles_and_links_decode(self):
        items=collect('wam-ar',fixture('wam-ar-sitemap.xml'))
        self.assertEqual(len(items),3)
        self.assertEqual(items[0]['title'],'صادرات الذكاء الاصطناعي تقود اقتصاد هونغ كونغ لتحقيق نمو يلامس 4 %')
        self.assertEqual(items[2]['title'],'"أوبن إيه آي": وكلاء ذكاء اصطناعي تسببوا في نشر 53 صورة لمستخدمين')
        # Links carry raw Arabic letters; they stay on WAM's domain.
        self.assertTrue(all(i['url'].startswith('https://www.wam.ae/ar/article/') and ARABIC.search(i['url']) and i['lang']=='ar' for i in items))
    def test_albayan_cdata_titles(self):
        items=collect('albayan',fixture('albayan-sitemap.xml'))
        self.assertEqual([i['url'] for i in items],['https://www.albayan.ae/lifestyle/entertainment/1554606','https://www.albayan.ae/technology/tech-radar/1554552',
                                                    'https://www.albayan.ae/technology/science-technology/artificial-intelligence/1554535'])
        for i in items:  # CDATA and its padding gone
            self.assertEqual(i['title'],i['title'].strip());self.assertNotIn('CDATA',i['title']);self.assertIn('الذكاء الاصطناعي',i['title'])
    def test_sharjah24_one_sitemap_two_languages(self):
        raw=fixture('sharjah24-sitemap.xml')
        en,ar=collect('sharjah24-en',raw),collect('sharjah24-ar',raw)
        self.assertEqual([i['url'] for i in en],['https://sharjah24.ae/en/Articles/2026/09/26/AL020',
                                                 'https://sharjah24.ae/en/Articles/2026/09/26/OpenAI-says-its-AI-agents-posted-user-images-online-in-error'])
        self.assertEqual([i['title'] for i in ar],['"ميتا" تراهن على الذكاء الاصطناعي لقيادة عصر ما بعد الهواتف الذكية','الشارقة للتعليم العالي ينظم ورشة الذكاء الاصطناعي والإعلام الرقمي'])
        self.assertTrue(all(i['lang']=='en' for i in en) and all(i['lang']=='ar' and '/ar/' in i['url'] for i in ar))
    def test_link_prefix_applies_before_the_raw_limit(self):
        raw=sitemap(*[(f'https://sharjah24.ae/en/Articles/2026/09/27/E{n}',f'English story {n}','2026-09-27T10:00:00+04:00') for n in range(3)],
                    ('https://sharjah24.ae/ar/Articles/2026/09/26/A1','ورشة عن الذكاء الاصطناعي في الشارقة','2026-09-26T10:00:00+04:00'))
        with mock.patch.object(news,'SITEMAP_RAW_LIMIT',2):
            self.assertEqual([i['url'] for i in collect('sharjah24-ar',raw)],['https://sharjah24.ae/ar/Articles/2026/09/26/A1'])
        # No entry in this source's language: the source keeps its earlier items.
        with self.assertRaises(news.EmptyFeed):collect('sharjah24-ar',sitemap(('https://sharjah24.ae/en/a','AI story','2026-09-27T10:00:00Z')))
    def test_entities_hosts_and_bad_input(self):
        raw=sitemap(('https://www.wam.ae/en/article/a','AI &amp;amp; chips: &#x201C;G42&#x201D; &lt;b&gt;deal&lt;/b&gt;','2026-09-27T10:00:00Z'),
                    ('https://evil.example/b','AI story elsewhere','2026-09-27T09:00:00Z'),
                    ('http://www.wam.ae/en/article/c','AI story over http','2026-09-27T08:00:00Z'),
                    ('https://www.wam.ae/en/article/d','AI story with no date',''))
        self.assertEqual([i['title'] for i in collect('wam-en',raw)],['AI & chips: “G42” deal'])  # link_hosts enforced
        with self.assertRaises(news.EmptyFeed):collect('wam-en',sitemap())
        with self.assertRaises(ValueError):collect('wam-en',b'<rss><channel><item><title>AI</title></item></channel></rss>')
        with self.assertRaises(ValueError):collect('wam-en',b'{}',feed_type='json')  # an unknown feed_type fails loudly

class AnthropicListingTests(unittest.TestCase):
    def test_embedded_post_list(self):
        rows=news.parse_anthropic(fixture('anthropic-news.html'))
        # Posts under /research/ and a post the page lists twice are left out; newest first.
        self.assertEqual([r[1] for r in rows],['https://www.anthropic.com/news/claude-discovers-novel-enzyme-system','https://www.anthropic.com/news/accenture-embedded-evaluation',
                                               'https://www.anthropic.com/news/life-sciences-verification-program','https://www.anthropic.com/news/enterprise-frontier-safeguards',
                                               'https://www.anthropic.com/news/series-h'])
        self.assertEqual(rows[0][0],'Claude discovers a novel enzyme system with CRISPR-like repeats')
        self.assertEqual(rows[0][2],datetime(2026,9,23,16,6,tzinfo=timezone.utc))
        self.assertTrue(rows[0][3].startswith('We’re announcing a new life sciences research group'))
        research=news.parse_anthropic(fixture('anthropic-news.html'),'research')
        self.assertEqual([r[1] for r in research],['https://www.anthropic.com/research/glasswing-initial-update'])
    def test_collect(self):
        items=collect('anthropic-news',fixture('anthropic-news.html'))
        self.assertEqual([i['url'].rsplit('/',1)[1] for i in items],['claude-discovers-novel-enzyme-system','accenture-embedded-evaluation','life-sciences-verification-program'])
        self.assertTrue(all(i['lang']=='en' and not i['uae'] for i in items))
        self.assertTrue(items[0]['excerpt'].startswith('We’re announcing a new life sciences research group'))
        self.assertLessEqual(len(items[0]['excerpt']),news.EXCERPT_MAX)
    def test_rendered_links_when_the_data_is_missing(self):
        page=re.sub(rb'<script>self\.__next_f\.push.*?</script>',b'',fixture('anthropic-news.html'),flags=re.S)
        rows=news.parse_anthropic(page)
        self.assertEqual([(r[0],r[1].rsplit('/',1)[1],r[2].date().isoformat(),r[3]) for r in rows],[
            ('Claude discovers a novel enzyme system with CRISPR-like repeats','claude-discovers-novel-enzyme-system','2026-09-23',''),
            ('Partnering with Accenture on embedded evaluation','accenture-embedded-evaluation','2026-09-18',''),
            ('Introducing the Life Sciences Verification Program','life-sciences-verification-program','2026-09-17','')])
        # Neither the data nor the links: the source keeps its earlier items.
        with self.assertRaises(news.EmptyFeed):collect('anthropic-news',b'<html><body><p>Something went wrong</p></body></html>')
    def test_odd_posts_are_skipped(self):
        raw=listing(('AI one','good-slug','2026-09-26T10:00:00.000Z','A summary.'),('AI two','../../evil','2026-09-26T09:00:00.000Z',''),
                    ('AI three','','2026-09-26T08:00:00.000Z',''),('AI four','no-date','',''))
        self.assertEqual([r[1] for r in news.parse_anthropic(raw)],['https://www.anthropic.com/news/good-slug','https://www.anthropic.com/news/no-date'])
        self.assertEqual([i['url'] for i in collect('anthropic-news',raw)],['https://www.anthropic.com/news/good-slug'])  # no date: skipped

class OtherNewFeedTests(unittest.TestCase):
    def test_khaleej_times_tech(self):
        items=collect('kt-tech',fixture('kt-tech.xml'))
        self.assertEqual([i['title'] for i in items],['Bill Gates joins calls for AI safeguards, says he wants to meet Trump',
                                                      'AI agents to become the new ‘staff’ as firms go AI-first, say experts',"US, China to set up 'communication channel' for AI incidents"])
        self.assertFalse(any('excerpt' in i for i in items))  # feed_excerpt false: the feed only repeats the headline
    def test_gulf_today_business(self):
        items=collect('gulftoday-business',fixture('gulftoday-business.xml'))
        self.assertEqual(len(items),3);self.assertIn('Alibaba to expand data centre footprint in UAE',items[1]['title'])
        self.assertTrue(all(i.get('excerpt') and len(i['excerpt'])<=news.EXCERPT_MAX for i in items))
    def test_register_drops_sponsored_links(self):
        items=collect('register-ai',fixture('register.xml'))
        urls=[i['url'] for i in items]
        self.assertFalse([u for u in urls if '/sponsored/' in u or '/partner-content-' in u])
        # A news story about sponsored ads is not sponsored content.
        self.assertIn("OpenAI's new sponsored agents are happy to chat about selling you things",[i['title'] for i in items])
        self.assertEqual(len(items),2)

class FeedCacheTests(unittest.TestCase):
    def test_sources_sharing_a_feed_fetch_it_once(self):
        raw,cache=fixture('sharjah24-sitemap.xml'),{}
        with mock.patch.object(news,'fetch',return_value=raw) as f:
            news.collect(SRC['sharjah24-en'],NOW,None,cache);news.collect(SRC['sharjah24-ar'],NOW,None,cache)
        self.assertEqual(f.call_count,1)
        cache={}
        with mock.patch.object(news,'fetch',side_effect=TimeoutError('slow')) as f:
            for sid in ('sharjah24-en','sharjah24-ar'):
                with self.assertRaises(TimeoutError):news.collect(SRC[sid],NOW,None,cache)
        self.assertEqual(f.call_count,1)  # a failing server is not asked twice
        with mock.patch.object(news,'fetch',return_value=raw) as f:  # no cache: every call fetches
            news.collect(SRC['sharjah24-en'],NOW);news.collect(SRC['sharjah24-ar'],NOW)
        self.assertEqual(f.call_count,2)

class RegionPolicyTests(unittest.TestCase):
    def test_new_uae_sources_may_carry_uae_stories(self):
        raw=sitemap(('https://www.wam.ae/en/article/x','UAE launches national AI strategy for schools','2026-09-27T10:00:00Z'))
        items=collect('wam-en',raw)
        self.assertEqual(len(items),1);self.assertTrue(items[0]['uae'])
        for sid in NEW_UAE:self.assertTrue(policy.may_cover_region(SRC[sid]),sid)
        self.assertEqual(news.m1_violations([{**items[0],'summary_en':'Abu Dhabi schools start in October.'}],SOURCES),[])
    def test_anthropic_cannot_carry_uae_or_gcc_stories(self):
        self.assertFalse(policy.may_cover_region(SRC['anthropic-news']))
        raw=listing(('Anthropic opens an office in Abu Dhabi','abu-dhabi-office','2026-09-26T10:00:00.000Z','Claude comes to the region.'),
                    ('Claude learns chemistry','claude-chemistry','2026-09-26T09:00:00.000Z','A new model for lab work.'),
                    ('Partnering on AI safety','safety-partner','2026-09-26T08:00:00.000Z','We are working with the Saudi Data and AI Authority on evaluations.'))
        news.STATS.clear()
        self.assertEqual([i['url'].rsplit('/',1)[1] for i in collect('anthropic-news',raw)],['claude-chemistry'])  # M1 at collection
        self.assertEqual(news.STATS['m1_dropped'],2)
        item={'id':'a','title':'Claude learns chemistry','url':'https://www.anthropic.com/news/claude-chemistry','source':'anthropic-news','lang':'en',
              'published':'2026-09-26T09:00:00+00:00','summary_en':'The model was tested with a lab in Dubai.'}
        self.assertEqual(news.m1_violations([item],SOURCES),[(item,'M1')])  # and again once the summary is known
        verified={**item,'policy_ok':True,'policy_version':policy.POLICY_VERSION}
        verified['policy_hash']=policy.fingerprint(verified)
        self.assertFalse(policy.shown_ok(verified,SRC['anthropic-news']))
        self.assertTrue(policy.shown_ok({**verified,'source':'wam-en'},SRC['wam-en']))

class PaidContentTests(unittest.TestCase):
    """Sponsored items sit under the same links as the news; only their byline or category shows it."""
    def test_feed_authors_and_categories(self):
        rows={r.title:r for r in news.parse_feed(fixture('kt-tech-sponsored.xml'))}
        sophos=rows['Sophos at GISEC 2026: How AI Is Reshaping Cybersecurity in the Middle East']
        self.assertEqual(sophos.authors,('Partner Content',))
        self.assertEqual(sophos.categories,('Tech','UAE','KT Engage'))
        self.assertEqual(rows['Bill Gates joins calls for AI safeguards, says he wants to meet Trump'].authors,('Reuters',))
        mit={r.title:r for r in news.parse_feed(fixture('mittr-sponsored.xml'))}
        self.assertEqual(mit['Building the materials foundation for AI'].authors,('MIT Technology Review Insights',))
        self.assertIn('sponsored',mit['Building the materials foundation for AI'].categories)
        atom=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>AI</title><link href="https://x.example/a"/><updated>2026-09-27T10:00:00Z</updated><author><name>A Writer</name></author><category term="Sponsored"/></entry></feed>'
        entry=next(news.parse_feed(atom))
        self.assertEqual((entry.authors,entry.categories),(('A Writer',),('Sponsored',)))
    def test_khaleej_times_partner_content_is_dropped(self):
        raw=fixture('kt-tech-sponsored.xml')
        self.assertEqual(len(collect('kt-tech',raw,drop_authors='')),3)  # the filter is what drops them
        for sid in ('kt-tech','kt-business','kt-uae'):
            self.assertEqual([i['title'] for i in collect(sid,raw)],['Bill Gates joins calls for AI safeguards, says he wants to meet Trump'],sid)
    def test_mit_technology_review_insights_is_dropped(self):
        raw=fixture('mittr-sponsored.xml')
        self.assertEqual([i['title'] for i in collect('mittr-ai',raw)],['The Pentagon wants $30 million to build an AI-powered lie detector'])
        self.assertEqual(len(collect('mittr-ai',raw,drop_authors='')),2)

class ScanLimitTests(unittest.TestCase):
    def test_busy_sitemaps_are_scanned_past_the_first_80_entries(self):
        start=datetime(2026,9,27,16,tzinfo=timezone.utc)
        rows=[(f'https://www.albayan.ae/local/{n}',f'خبر محلي رقم {n}',(start-timedelta(minutes=5*n)).isoformat()) for n in range(150)]
        rows+=[(f'https://www.albayan.ae/technology/{n}',f'الذكاء الاصطناعي يغير قطاع {n}',(start-timedelta(minutes=5*n)).isoformat()) for n in range(150,260)]
        items=collect('albayan',sitemap(*rows))
        self.assertEqual(len(items),news.PER_FEED)  # found past entry 150, and still at most PER_FEED
        self.assertEqual(items[0]['url'],'https://www.albayan.ae/technology/150')
        self.assertEqual(news.raw_limit(SRC['albayan']),news.SITEMAP_RAW_LIMIT)
        self.assertEqual(news.raw_limit(SRC['techcrunch-ai']),news.RAW_LIMIT)
        self.assertEqual(news.raw_limit({**SRC['techcrunch-ai'],'raw_limit':5}),5)
        with mock.patch.object(news,'SITEMAP_RAW_LIMIT',80):
            self.assertEqual(collect('albayan',sitemap(*rows)),[])  # the old limit: no AI headline among the first 80

class FetchOptionTests(unittest.TestCase):
    def options(self,sid):
        with mock.patch.object(news,'fetch',return_value=fixture('wam-en-sitemap.xml')) as f:
            try:news.collect(SRC[sid],NOW)
            except Exception:pass
        return f.call_args.kwargs
    def test_accept_header_and_timeout_by_source(self):
        self.assertIn('text/html',self.options('anthropic-news')['accept'])
        self.assertTrue(self.options('wam-en')['accept'].startswith('application/xml'))
        self.assertIn('application/rss+xml',self.options('techcrunch-ai')['accept'])
        self.assertEqual(self.options('techcrunch-ai')['timeout'],news.FEED_TIMEOUT)
        for sid in ('mediaoffice-en2','mediaoffice-ar2'):self.assertEqual(self.options(sid)['timeout'],45,sid)
    def test_the_request_carries_them(self):
        seen={}
        class Resp:
            def read(self,n):return b'<rss/>'
            def __enter__(self):return self
            def __exit__(self,*a):return False
        def fake(req,timeout):
            seen.update(accept=req.get_header('Accept'),ua=req.get_header('User-agent'),timeout=timeout);return Resp()
        with mock.patch.object(news,'urlopen',side_effect=fake):
            news.fetch('https://www.anthropic.com/news',accept=news.ACCEPT['anthropic_listing'],timeout=45)
        self.assertEqual(seen,{'accept':news.ACCEPT['anthropic_listing'],'ua':news.UA,'timeout':45})

class UaeFlagTests(unittest.TestCase):
    def test_wire_heavy_sources_flag_uae_by_content(self):
        raw=sitemap(('https://www.wam.ae/en/article/a','Hong Kong AI exports drive growth','2026-09-27T10:00:00Z'),
                    ('https://www.wam.ae/en/article/b','Abu Dhabi launches AI academy for civil servants','2026-09-27T09:00:00Z'))
        self.assertEqual([i['uae'] for i in collect('wam-en',raw)],[False,True])
        ar=sitemap(('https://www.albayan.ae/technology/1','الذكاء الاصطناعي يعزز صادرات هونغ كونغ','2026-09-27T10:00:00Z'),
                   ('https://www.albayan.ae/technology/2','الإمارات تطلق منصة للذكاء الاصطناعي','2026-09-27T09:00:00Z'))
        self.assertEqual([i['uae'] for i in collect('albayan',ar)],[False,True])
        # A UAE newsroom without the setting still flags every item.
        self.assertTrue(all(i['uae'] for i in collect('kt-uae',fixture('kt-tech.xml'))))
        for sid in ('wam-en','wam-ar','albayan','sharjah24-en','sharjah24-ar','kt-tech'):self.assertTrue(SRC[sid].get('uae_by_content'),sid)
    def test_an_excerpt_that_names_the_uae_counts(self):
        items=[{'source':'sharjah24-en','title':'New AI skills programme opens','excerpt':'The Sharjah programme trains 500 students.','uae':False},
               {'source':'wam-en','title':'US stocks rise on AI optimism','uae':True},  # stored before the setting
               {'source':'kt-business','title':'US stocks rise on AI optimism','uae':True}]
        self.assertEqual(news.flag_uae(items,SOURCES),2)
        self.assertEqual([i['uae'] for i in items],[True,False,True])

class DuplicateTests(unittest.TestCase):
    def it(self,source,title,hours,**kw):
        return {'id':f'{source}{hours}','source':source,'title':title,'url':f'https://x/{source}/{hours}','lang':SRC[source]['lang'],
                'published':(NOW-timedelta(hours=hours)).isoformat(),**kw}
    def test_one_copy_of_a_wire_story(self):
        items=[self.it('techcrunch-ai',"OpenAI's agents accidentally posted users' images to the web",30,excerpt='OpenAI said its agents posted images.'),
               self.it('gulfnews-tech','OpenAI agents leaked 53 ChatGPT-user images onto the internet',20),
               self.it('kt-tech','OpenAI says its AI agents posted ChatGPT user images online in error',21),
               self.it('sharjah24-en','OpenAI says its AI agents posted user images online in error',24),
               self.it('wam-en','OpenAI says AI agents posted 53 user images online',23),
               self.it('wam-ar','"أوبن إيه آي": وكلاء ذكاء اصطناعي تسببوا في نشر 53 صورة لمستخدمين',23),
               self.it('albayan','«أوبن إيه آي»: وكلاء الذكاء الاصطناعي تسببوا في نشر 53 صورة لمستخدمين',25),
               self.it('verge-ai','NVIDIA unveils Rubin CPX for AI inference',5),
               self.it('ars-ai','NVIDIA unveils Rubin GPUs for AI data centers',6)]
        kept,dropped=news.dedupe_stories(items,SOURCES)
        # Official sources first (WAM, Sharjah24), then the first published: Sharjah24 English; WAM Arabic. Gulf News'
        # wording matches Sharjah24's only through WAM's (live headlines of 2026-09-27): one story all the same.
        self.assertFalse(news.same_story(items[1],items[3]));self.assertTrue(news.same_story(items[1],items[4]))
        self.assertEqual([i['source'] for i in kept],['sharjah24-en','wam-ar','verge-ai','ars-ai'])
        self.assertEqual(dropped,5)
    def test_an_excerpt_or_summary_wins_between_news_outlets(self):
        items=[self.it('gulfnews-tech','Microsoft to invest $15 billion in AI data centres in the UAE',3),
               self.it('thenational','Microsoft to invest $15 billion in UAE AI data centres by 2029',5,summary_en='A summary.'),
               self.it('kt-business','Microsoft to invest $15bn in UAE AI data centres',4,excerpt='An excerpt of the story.')]
        kept,_=news.dedupe_stories(items,SOURCES)
        self.assertEqual([i['source'] for i in kept],['thenational'])  # both have text: the first published
        hidden=[{**items[1],'ai_focus':False},items[0]]
        self.assertEqual([i['source'] for i in news.dedupe_stories(hidden,SOURCES)[0]],['gulfnews-tech'])
    def test_what_is_not_a_duplicate(self):
        a=self.it('wam-en','UAE and France sign agreement on AI research cooperation',2)
        for b in (self.it('sharjah24-en','UAE and France sign agreement on AI research cooperation',60),  # 58 hours apart
                  self.it('wam-en','UAE and France sign agreement on AI research cooperation',3),       # same source
                  self.it('wam-ar','UAE and France sign agreement on AI research cooperation',3),       # other language
                  self.it('kt-tech','UAE and Japan sign agreement on AI chips',3)):
            self.assertEqual(len(news.dedupe_stories([a,b],SOURCES)[0]),2,b['id'])
        self.assertEqual(news.headline_words('Why the UAE is betting on AI agents'),{'uae','betting','agent'})
    def test_a_chain_of_similar_headlines_over_days_is_not_one_story(self):
        # A daily feature under one headline, from alternating sources, 30 hours apart: copies link pairwise, but no
        # group may span more than DUPLICATE_HOURS.
        items=[self.it(('techcrunch-ai','verge-ai')[n%2],'The week in AI agents, chips and models explained',30*n) for n in range(6)]
        kept,_=news.dedupe_stories(items,SOURCES)
        self.assertGreaterEqual(len(kept),3)
    def test_one_link_in_two_sections(self):
        link='https://www.khaleejtimes.com/business/tech/ai-story'
        base={'title':'AI story','url':link,'lang':'en','published':NOW.isoformat()}
        fresh={'kt-business':[{**base,'id':'1','source':'kt-business','uae':True}],'kt-tech':[{**base,'id':'1','source':'kt-tech','uae':False}]}
        self.assertEqual([i['source'] for i in news.merge([],fresh,{},SOURCES)],['kt-tech'])
        fresh={'kt-tech':fresh['kt-tech'],'kt-business':fresh['kt-business']}  # whatever order the feeds arrive in
        self.assertEqual([i['source'] for i in news.merge([],fresh,{},SOURCES)],['kt-tech'])
        fresh={'wam-en':[{**base,'id':'2','url':'https://x/a','source':'wam-en'}],'techcrunch-ai':[{**base,'id':'2','url':'https://x/a','source':'techcrunch-ai','excerpt':'Text.'}]}
        self.assertEqual([i['source'] for i in news.merge([],fresh,{},SOURCES)],['wam-en'])  # primary first

class WeakAiTermTests(unittest.TestCase):
    def test_register_needs_more_than_datacenter(self):
        titles=('Uncle Sam coughs up $1.9B for grid upgrades to feed datacenters','UK wants more homes heated by waste heat from datacenters',
                'AI datacenter boom strains the grid','Datacenter GPUs sell out again')
        rss=('<rss><channel>'+''.join(f'<item><title>{t}</title><link>https://www.theregister.com/2026/09/27/s{n}</link><pubDate>Sun, 27 Sep 2026 1{n}:00:00 GMT</pubDate></item>'
             for n,t in enumerate(titles))+'</channel></rss>').encode()
        self.assertEqual(sorted(i['title'] for i in collect('register-ai',rss)),['AI datacenter boom strains the grid','Datacenter GPUs sell out again'])
        self.assertEqual(len(collect('register-ai',rss,weak_ai_terms='')),4)
        self.assertTrue(news.mentions_ai('New data centre for AI',SRC['register-ai']))
        self.assertFalse(news.mentions_ai('New data centre in Wales',SRC['register-ai']))
        self.assertTrue(news.mentions_ai('New data centre in Wales',SRC['kt-tech']))  # only where the source says so

class PageFurnitureTests(unittest.TestCase):
    """Article pages end in page furniture (related and popular stories, browser notices); the summary must not read it.
    The markup follows the live pages of 2026-09-27."""
    @staticmethod
    def P(*ps):return ''.join(f'<p>{p}</p>' for p in ps)
    def text(self,sid,page):return news.article_text(page,None,SRC[sid])
    def test_khaleej_times(self):
        page=('<html><body><div class="article">'+self.P('AI requires safeguards that go beyond self-regulation, Gates said on Sunday.',
              '<strong><a href="https://whatsapp.com/channel/x">Stay up to date with the latest news. Follow KT on WhatsApp Channels.</a></strong>',
              'The US and China agreed to launch a dialogue on AI following the visit.')+
              '<div class="related"><h3><span>ALSO READ</span></h3><ul><li><a href="/a">Trump renames AI super intelligence</a></li></ul></div>'
              '<div class="follow-wrap"><div class="author-details-below"><span>Written by</span><a href="/author/x"><h4>Waheed Abbas</h4></a></div>'
              '<p class="more">Waheed Abbas is Assistant Editor, covering real estate, aviation and other business stories.</p></div></div>'
              '<div class="most-popular-right-nf"><h3><span class="leftblue-nf">MOST</span><span class="rightyellow-nf"> POPULAR</span></h3>'
              '<div class="list"><div class="count">1</div><p><a href="/b">Dubai gold prices fall further as 24K drops Dh40 per gram in a month</a></p></div></div></body></html>')
        self.assertEqual(self.text('kt-tech',page),'AI requires safeguards that go beyond self-regulation, Gates said on Sunday.\n\nThe US and China agreed to launch a dialogue on AI following the visit.')
    def test_sharjah24(self):
        en=('<div class="animate text-contain">'+self.P('The agreements include a $30 billion reciprocal tariff-reduction arrangement.',
            'Following the talks, President Xi returned to Beijing on Saturday.')+'</div>'
            '<div class="news-detail-side side-related-articles"><h3 class="mb-5">Related News</h3>'+self.P("S. Korea's electronic payments gain over 12% in H1")+'</div>'
            '<div class="modal-body"><h3>Notice</h3>'+self.P('Your web browser is not fully supported by Sharjah24 and sharjah24.ae. For optimal experience, please upgrade.')+'</div>')
        self.assertEqual(self.text('sharjah24-en',en),'The agreements include a $30 billion reciprocal tariff-reduction arrangement.\n\nFollowing the talks, President Xi returned to Beijing on Saturday.')
        # The Arabic pages put the article in <br> lines, not paragraphs: what follows is only related headlines, so
        # there is no article text and the summary uses the headline and the page's own description instead.
        ar=('<div class="animate text-contain"><strong>الشارقة 24 - وام:<br /></strong><br />تراهن شركة ميتا بقوة على تطوير وكيل ذكاء اصطناعي.<br /></div>'
            '<h2 class="fw-500">أخبار ذات صلة</h2>'+self.P('في تحذير أممي.. الذكاء الاصطناعي يشكل تهديداً وجودياً على البشرية','"إنفيديا" تتجه لرفع أسعار خوادم الذكاء الاصطناعي 15%'))
        self.assertEqual(self.text('sharjah24-ar',ar),'')
        self.assertTrue(news.article_text(ar))  # without the setting the headlines would have been read as the article
    def test_anthropic_related_content(self):
        page=('<article>'+self.P('We are introducing a new life sciences research group and laboratory at Anthropic.',
              'We hope this work demonstrates the value of AI-driven hypothesis generation.')+'</article>'
              '<section><div><h2 class="headline-4">Related content</h2></div><div><h3 class="headline-6">Introducing the Life Sciences Verification Program</h3>'+
              self.P('The Life Sciences Verification Program (LSVP) gives life science professionals access to Claude.')+'</div></section>')
        self.assertEqual(self.text('anthropic-news',page),'We are introducing a new life sciences research group and laboratory at Anthropic.\n\n'
                         'We hope this work demonstrates the value of AI-driven hypothesis generation.')
    def test_a_related_heading_before_the_article_does_not_cut_it(self):
        page=('<div class="sidebar"><h3>Most popular</h3></div><h1>Headline</h1>'+self.P('The article text starts here and goes on for a while.')+
              '<h2>How it works</h2>'+self.P('A second section of the article with more detail.')+'<h2>More from Tech</h2>'+self.P('Another story entirely, not this one.'))
        self.assertEqual(news.article_text(page),'The article text starts here and goes on for a while.\n\nA second section of the article with more detail.')

class WindowTests(unittest.TestCase):
    def it(self,source,hours,**kw):
        return {'id':f'{source}{hours}','source':source,'url':f'https://x/{source}/{hours}','published':(NOW-timedelta(hours=hours)).isoformat(),**kw}
    def test_quiet_sources_keep_their_newest_items(self):
        busy=[self.it('busy',h) for h in range(1,211)]
        quiet=[self.it('quiet',300+h) for h in range(5)]
        hidden=[self.it('lifestyle',250,ai_focus=False)]
        old=[self.it('quiet',24*15)]
        kept=news.window(busy+quiet+hidden+old,NOW)
        self.assertEqual(sum(1 for i in kept if i['source']=='busy'),news.MAX_ITEMS)
        self.assertEqual([i['id'] for i in kept if i['source']=='quiet'],['quiet300','quiet301','quiet302'])  # PER_SOURCE_MIN newest
        self.assertFalse([i for i in kept if i['source']=='lifestyle'])  # never shown, so it does not use the minimum
        self.assertEqual([i['published'] for i in kept],sorted((i['published'] for i in kept),reverse=True))
        self.assertEqual(len(news.window(busy[:10]+old,NOW)),10)  # nothing older than KEEP_DAYS

class SourceListTests(unittest.TestCase):
    def test_removed_and_replaced_sources(self):
        self.assertFalse(REMOVED&set(SRC))
        items=json.loads((ROOT/'data/news.json').read_text(encoding='utf-8'))['items']
        self.assertFalse(REMOVED&{i['source'] for i in items})
        self.assertNotIn('blogs.nvidia.com/feed',' '.join(s['feed'] for s in SOURCES))
        self.assertIn('blogs.nvidia.com',SRC['nvidia-news']['link_hosts'])  # NVIDIA's blog posts still come through the newsroom feed
        self.assertEqual(SRC['emaratalyoum']['feed'],'https://www.emaratalyoum.com/1.533089?ot=ot.AjaxPageLayout')
        self.assertEqual((SRC['register-ai']['feed'],SRC['register-ai']['ai_only']),('https://www.theregister.com/headlines.atom',False))
        self.assertTrue(SRC['register-ai'].get('drop_links'))
        self.assertEqual(SRC['ms-cloud']['feed'],'https://blogs.microsoft.com/feed/')
    def test_new_sources(self):
        self.assertLessEqual(NEW_UAE|{'anthropic-news'},set(SRC))
        for sid in NEW_UAE:
            s=SRC[sid];self.assertEqual(s['region'],'uae',sid);self.assertFalse(s['ai_only'],sid)
        self.assertEqual({sid:SRC[sid]['kind'] for sid in NEW_UAE},{'kt-tech':'news','gulftoday-business':'news','albayan':'news','wam-en':'primary','wam-ar':'primary','sharjah24-en':'primary','sharjah24-ar':'primary'})
        a=SRC['anthropic-news']
        self.assertEqual((a['region'],a['kind'],a['ai_only'],a['feed_type'],a.get('listing_directory')),('global','primary',True,'anthropic_listing','news'))
        self.assertFalse(a.get('regional_outlet') or a.get('official_region'))
        self.assertIs(SRC['wam-en']['read_pages'],False);self.assertIs(SRC['wam-ar']['read_pages'],False)  # WAM's article pages are an empty app shell
    def test_every_source_is_well_formed(self):
        self.assertEqual(len(SRC),len(SOURCES))
        for s in SOURCES:
            sid=s['id']
            self.assertLessEqual({'id','name','name_ar','feed','homepage','lang','region','ai_only','link_hosts','kind'},set(s),sid)
            self.assertIn(s['lang'],('en','ar'),sid);self.assertIn(s['region'],('global','uae'),sid);self.assertIn(s['kind'],('primary','news'),sid)
            self.assertTrue(ARABIC.search(s['name_ar']),sid)
            self.assertTrue(s['feed'].startswith('https://') and s['homepage'].startswith('https://'),sid)
            self.assertTrue(news.allowed(s['homepage'],s),sid)
            self.assertTrue(s['link_hosts'] and all(news.allowed(f'https://{h}/x',s) for h in s['link_hosts']),sid)
            self.assertIn(s.get('feed_type','rss'),news.FEED_TYPES,sid)
            if s.get('link_prefix'):self.assertTrue(news.allowed(s['link_prefix'],s),sid)
            for k in ('drop_titles','drop_links','drop_authors','weak_ai_terms','page_stop','page_drop'):
                if k in s:self.assertTrue(s[k],sid);re.compile(s[k])
            for k in ('timeout','raw_limit'):
                if k in s:self.assertTrue(isinstance(s[k],int) and s[k]>0,sid)
            if 'uae_by_content' in s:self.assertIs(s['uae_by_content'],True,sid);self.assertEqual(s['region'],'uae',sid)
        # Sources that share a feed split it by language.
        by_feed={}
        for s in SOURCES:by_feed.setdefault(s['feed'],[]).append(s)
        for feed,group in by_feed.items():
            if len(group)>1:
                self.assertEqual(len({s['link_prefix'] for s in group}),len(group),feed)
                for s in group:self.assertTrue(s['link_prefix'].rstrip('/').endswith('/'+s['lang']),s['id'])

if __name__=='__main__':unittest.main()
