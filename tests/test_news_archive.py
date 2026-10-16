"""The news archive (scripts/news_archive.py): stories that leave the AI news window are kept (verified ones only, one
entry per id), a story that comes back reuses its archived AI summary and Arabic headline instead of paying again, the
build and the app export only what the site may still show. No network: the feed and Claude are mocked."""
import contextlib,io,json,os,sys,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import news,news_archive,policy,topics,build,app_data
news.PENDING=Path(tempfile.mkdtemp())/'news-batches.json'

NOW=datetime(2026,9,26,12,tzinfo=timezone.utc)
SRC={'id':'ex','name':'Example News','name_ar':'أخبار المثال','feed':'https://www.example-news.com/rss','homepage':'https://www.example-news.com/',
     'link_hosts':['www.example-news.com'],'lang':'en','region':'global','ai_only':False}
SRC_UAE={**SRC,'id':'gulf','name':'Gulf Daily','name_ar':'صحيفة الخليج','region':'uae'}
SRC_AR={**SRC,'id':'ar','name':'Arabic Pub','name_ar':'ناشر عربي','lang':'ar','region':'uae'}

def verified(**kw):
    """A story as news.json stores it after a passing content check (policy_ok, version and the hash of its texts)."""
    i={'id':'x1','title':'NVIDIA ships a new AI chip','url':'https://www.example-news.com/chip','source':'ex','lang':'en','uae':False,
       'published':'2026-09-20T08:00:00+00:00','excerpt':'The chip has 288 GB of memory.','summary_en':'NVIDIA began shipping the chip.',
       'summary_ar':'بدأت NVIDIA شحن الشريحة.','summary_source':'ai','summary_version':news.SUMMARY_VERSION,'ai_focus':True,
       'title_ar':'إنفيديا تشحن شريحة جديدة للذكاء الاصطناعي',**kw}
    i.update(policy_ok=True,policy_version=policy.POLICY_VERSION,policy_hash=policy.fingerprint(i))
    return i

class ArchiveFileTests(unittest.TestCase):
    def test_slim_items_have_exactly_the_contract_fields(self):
        s=news_archive.slim(verified(),SRC)
        self.assertEqual(tuple(s),news_archive.FIELDS)
        self.assertEqual(news_archive.FIELDS,('id','source','lang','uae','topic','published','title','title_ar','url','summary_en','summary_ar','excerpt'))
        self.assertEqual(s['topic'],topics.topic_of(verified(),SRC))
        self.assertEqual((s['summary_en'],s['title_ar'],s['excerpt']),('NVIDIA began shipping the chip.','إنفيديا تشحن شريحة جديدة للذكاء الاصطناعي','The chip has 288 GB of memory.'))
        # Null over guesses: no AI summary, no translation, no excerpt.
        bare=news_archive.slim(verified(summary_en=None,summary_ar=None,summary_source=None,title_ar=None,excerpt=None),SRC)
        self.assertEqual((bare['summary_en'],bare['summary_ar'],bare['title_ar'],bare['excerpt']),(None,None,None,None))
        # A publisher's text is never stored as a summary, and an Arabic story has no "translation".
        self.assertIsNone(news_archive.slim(verified(summary_source='publisher'),SRC)['summary_en'])
        self.assertIsNone(news_archive.slim(verified(lang='ar',title='الذكاء الاصطناعي في المدارس'),SRC_AR)['title_ar'])
    def test_only_stories_the_site_could_show(self):
        ok=verified()
        self.assertTrue(news_archive.archivable(ok,SRC))
        unchecked={k:v for k,v in ok.items() if not k.startswith('policy')}
        failed={**ok,'policy_ok':False}
        edited={**ok,'title':'NVIDIA ships a new AI chip, edited'}  # the verdict no longer matches the texts
        old_policy={**ok,'policy_version':policy.POLICY_VERSION-1}
        off_topic=verified(ai_focus=False)
        http=verified(url='http://www.example-news.com/chip')
        for name,i,s in (('unchecked',unchecked,SRC),('failed',failed,SRC),('edited',edited,SRC),('old policy',old_policy,SRC),
                         ('not about AI',off_topic,SRC),('http',http,SRC),('source gone',ok,None)):
            self.assertFalse(news_archive.archivable(i,s),name)
        # A story that mentions the region only from a source that may cover it (rule M1).
        regional=verified(title='Abu Dhabi opens an AI lab',uae=True)
        self.assertFalse(news_archive.archivable(regional,SRC));self.assertTrue(news_archive.archivable(regional,SRC_UAE))
    def test_append_is_idempotent_and_keeps_one_entry_per_story(self):
        with tempfile.TemporaryDirectory() as d:
            a=verified();b=verified(id='x2',url='https://www.example-news.com/two',title='OpenAI releases a model',published='2026-09-21T08:00:00+00:00')
            self.assertEqual(news_archive.append([a,b,verified(ai_focus=False,id='x3',url='https://www.example-news.com/3')],[SRC],d),2)
            path=Path(d)/'2026-09.json';first=path.read_text(encoding='utf-8')
            doc=json.loads(first)
            self.assertEqual((doc['month'],doc['policy_version']),('2026-09',policy.POLICY_VERSION))
            self.assertEqual([i['id'] for i in doc['items']],['x2','x1'])  # newest first
            self.assertTrue(all(tuple(i)==news_archive.FIELDS for i in doc['items']))
            # The same stories again: nothing changes, the file is not rewritten.
            self.assertEqual(news_archive.append([a,b],[SRC],d),0);self.assertEqual(path.read_text(encoding='utf-8'),first)
            # A newer copy of one story (same link, new id: a tracking query was dropped) replaces it.
            c=verified(id='x1b',summary_en='A better summary.')
            self.assertEqual(news_archive.append([c],[SRC],d),1)
            items=json.loads(path.read_text(encoding='utf-8'))['items']
            self.assertEqual(sorted(i['id'] for i in items),['x1b','x2']);self.assertEqual([i['summary_en'] for i in items if i['id']=='x1b'],['A better summary.'])
            # Month of publication in UAE time: 23:30 UTC on 30 Sep is 1 Oct in the UAE.
            late=verified(id='x4',url='https://www.example-news.com/4',published='2026-09-30T23:30:00+00:00')
            news_archive.append([late],[SRC],d)
            self.assertEqual(news_archive.months(d),['2026-10','2026-09'])
    def test_a_damaged_month_is_left_for_a_person_to_repair(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'2026-09.json').write_text('{broken',encoding='utf-8')
            news_archive.DAMAGED.clear()
            self.assertEqual(news_archive.append([verified()],[SRC],d),0)
            self.assertEqual((Path(d)/'2026-09.json').read_text(encoding='utf-8'),'{broken');self.assertEqual(news_archive.DAMAGED,{'2026-09'})
            self.assertEqual(news_archive.load(d),[])  # the build leaves it out
    def test_reuse_gives_back_summary_and_translation(self):
        with tempfile.TemporaryDirectory() as d:
            news_archive.append([verified()],[SRC],d)
            archived=news_archive.lookup(d)
            back={'id':'x1','title':'NVIDIA ships a new AI chip','url':'https://www.example-news.com/chip','source':'ex','lang':'en','published':'2026-09-20T08:00:00+00:00','summary_attempts':1}
            by_link={**back,'id':'other-id'}
            renamed={**back,'id':'x9','url':'https://www.example-news.com/9'}
            has={**back,'summary_en':'Own summary.','summary_ar':'ملخص.','summary_source':'ai','title_ar':'عنوان'}
            new_title={**back,'title':'NVIDIA ships its new AI chip'}
            self.assertEqual(news_archive.reuse([back,by_link,renamed,has,new_title],archived,news.SUMMARY_VERSION),3)
            for i in (back,by_link):
                self.assertEqual((i['summary_en'],i['summary_ar'],i['summary_source'],i['summary_version'],i['ai_focus']),
                                 ('NVIDIA began shipping the chip.','بدأت NVIDIA شحن الشريحة.','ai',news.SUMMARY_VERSION,True))
                self.assertEqual(i['title_ar'],'إنفيديا تشحن شريحة جديدة للذكاء الاصطناعي');self.assertNotIn('summary_attempts',i)
                self.assertTrue(news._current(i))  # so summarize() does not ask Claude again
            self.assertNotIn('summary_en',renamed)
            self.assertEqual((has['summary_en'],has['title_ar']),('Own summary.','عنوان'))  # never overwritten
            self.assertNotIn('title_ar',new_title);self.assertEqual(new_title['summary_en'],'NVIDIA began shipping the chip.')  # a changed headline needs its own translation
            self.assertNotIn('policy_ok',back)  # the content check runs again: its verdict is never reused
    def test_shown_applies_the_policy_rules_to_the_archive(self):
        with tempfile.TemporaryDirectory() as d:
            plain=verified()
            regional=verified(id='r1',url='https://www.example-news.com/r1',title='Abu Dhabi opens an AI lab',uae=True,source='gulf')
            news_archive.append([plain,regional],[SRC,SRC_UAE],d)
            got=news_archive.shown(news_archive.load(d),[SRC,SRC_UAE])
            self.assertEqual(sorted(i['id'] for i in got),['r1','x1'])
            self.assertTrue(all(tuple(i)==news_archive.FIELDS for i in got))  # no working keys ('_pv')
            # A source no longer followed: its stories go. The current list's stories are not repeated.
            self.assertEqual([i['id'] for i in news_archive.shown(news_archive.load(d),[SRC_UAE])],['r1'])
            self.assertEqual([i['id'] for i in news_archive.shown(news_archive.load(d),[SRC,SRC_UAE],exclude={'x1'})],['r1'])
            # The policy changed since: a story that mentions the region is hidden until checked again (fail closed).
            with mock.patch.object(policy,'POLICY_VERSION',policy.POLICY_VERSION+1):
                self.assertEqual([i['id'] for i in news_archive.shown(news_archive.load(d),[SRC,SRC_UAE])],['x1'])
            # A file that holds a regional story under an older version keeps the lowest version.
            news_archive.append([verified(id='r2',url='https://www.example-news.com/r2')],[SRC],d,policy_version=0)
            self.assertEqual(json.loads((Path(d)/'2026-09.json').read_text(encoding='utf-8'))['policy_version'],0)
            self.assertNotIn('r1',[i['id'] for i in news_archive.shown(news_archive.load(d),[SRC,SRC_UAE])])
    def test_publish_writes_same_origin_files_and_removes_stale_months(self):
        with tempfile.TemporaryDirectory() as d,tempfile.TemporaryDirectory() as out:
            news_archive.append([verified(),verified(id='x2',url='https://www.example-news.com/2',published='2026-08-30T10:00:00+00:00')],[SRC],d)
            (Path(out)/'news-archive').mkdir();(Path(out)/'news-archive'/'2025-01.json').write_text('{}',encoding='utf-8')
            items=news_archive.shown(news_archive.load(d),[SRC])
            index=news_archive.publish(out,items,[SRC])
            files=sorted(p.name for p in (Path(out)/'news-archive').iterdir())
            self.assertEqual(files,['2026-08.json','2026-09.json','index.json'])
            self.assertEqual([m['month'] for m in index['months']],['2026-09','2026-08'])
            self.assertEqual(index['sources'],{'ex':{'name':'Example News','name_ar':'أخبار المثال','region':'global'}})
            month=json.loads((Path(out)/'news-archive'/'2026-09.json').read_text(encoding='utf-8'))
            self.assertEqual([i['id'] for i in month['items']],['x1']);self.assertNotIn('policy_hash',json.dumps(month))
            raw=''.join(p.read_text(encoding='utf-8') for p in (Path(out)/'news-archive').iterdir())
            self.assertNotIn('feed',raw)  # the sources' feed addresses are not published
    def test_app_items_last_60_days_newest_first(self):
        items=[{'id':str(n),'published':(NOW-timedelta(days=n*10)).isoformat()} for n in range(9)]
        self.assertEqual([i['id'] for i in news_archive.app_items(items,NOW)],['0','1','2','3','4','5','6'])

class FixedNow(datetime):
    @classmethod
    def now(cls,tz=None):return NOW

RSS=b'''<?xml version="1.0"?><rss><channel>
<item><title>NVIDIA ships a new AI chip</title><link>https://www.example-news.com/chip</link><pubDate>Fri, 25 Sep 2026 08:00:00 GMT</pubDate><description>The chip has 288 GB of memory and ships to cloud providers first.</description></item>
<item><title>OpenAI releases a model for AI agents</title><link>https://www.example-news.com/agents</link><pubDate>Fri, 25 Sep 2026 10:00:00 GMT</pubDate><description>The model plans and runs multi-step tasks for developers.</description></item>
</channel></rss>'''

class RunTests(unittest.TestCase):
    """A whole news.py run: what leaves the window is archived beside news.json; a story that comes back is not paid twice."""
    def run_main(self,d,previous,archive_items,verdict=lambda i:True,cap=None):
        out,srcs=Path(d)/'news.json',Path(d)/'news-sources.json'
        srcs.write_text(json.dumps([SRC]),encoding='utf-8')
        out.write_text(json.dumps({'ai':{'summary_tries_rule':news.TRIES_RULE},'items':previous}),encoding='utf-8')
        news_archive.append(archive_items,[SRC],Path(d)/'news-archive')
        calls={'summary':[],'translate':[],'policy':[]}
        def parse(**kw):
            prompt=kw['messages'][0]['content']
            if kw.get('output_format') is news.PolicyVerdicts:
                ids=[l.split('"')[1] for l in prompt.splitlines() if l.startswith('<item id=')];calls['policy']+=ids
                return SimpleNamespace(stop_reason='end_turn',parsed_output=news.PolicyVerdicts(items=[news.PolicyVerdict(id=i,policy_ok=verdict(i),rule=None if verdict(i) else 'P1') for i in ids]))
            if kw.get('output_format') is news.Summaries:
                ids=[l.split('"')[1] for l in prompt.splitlines() if l.startswith('<item id=')];calls['summary']+=ids
                return SimpleNamespace(stop_reason='end_turn',parsed_output=news.Summaries(items=[news.Summary(id=i,summary_en=f'Summary of {i}. Two sentences.',summary_ar=f'ملخص الخبر {i}.',ai_focus=True) for i in ids]))
            ids=[l.split('\t')[0] for l in prompt.splitlines()[1:]];calls['translate']+=ids
            return SimpleNamespace(stop_reason='end_turn',parsed_output=news.Translations(translations=[news.Translation(id=i,title_ar=f'عنوان {i}') for i in ids]))
        client=SimpleNamespace(messages=SimpleNamespace(parse=parse))
        buf=io.StringIO()
        caps=(mock.patch.object(news,'MAX_ITEMS',cap),mock.patch.object(news,'PER_SOURCE_MIN',0)) if cap else ()
        with contextlib.ExitStack() as stack:
            for c in caps:stack.enter_context(c)
            return self._main(out,srcs,client,buf,calls,d)
    def _main(self,out,srcs,client,buf,calls,d):
        with mock.patch.object(news,'OUT',out),mock.patch.object(news,'SOURCES',srcs),mock.patch.object(news,'BLOCKED',Path(d)/'news-blocked.json'),\
             mock.patch.object(news,'PENDING',Path(d)/'news-batches.json'),mock.patch.object(news,'fetch',return_value=RSS),\
             mock.patch.object(news,'datetime',FixedNow),mock.patch.object(news,'read_page',return_value=([],'')),\
             mock.patch.object(news,'fetch_article',return_value=''),mock.patch.dict(os.environ,{'ANTHROPIC_API_KEY':'test-key'},clear=True),\
             mock.patch('anthropic.Anthropic',return_value=client),mock.patch.object(news,'PROBLEMS',news.collections.Counter()),\
             mock.patch.object(news,'urlopen',mock.MagicMock(side_effect=AssertionError('no network'))),contextlib.redirect_stdout(buf),contextlib.redirect_stderr(buf):
            self.assertEqual(news.main(),0)
        return json.loads(out.read_text(encoding='utf-8')),calls,buf.getvalue()
    def test_leaving_stories_are_archived_and_returning_ones_reuse_their_texts(self):
        chip_id=news._hash('https://www.example-news.com/chip')
        back=verified(id=chip_id)  # archived by an earlier run, now listed by the feed again
        leaving=verified(id='old1',url='https://www.example-news.com/old',title='An older AI story',published='2026-09-10T08:00:00+00:00')
        unverified={k:v for k,v in verified(id='old2',url='https://www.example-news.com/old2',title='An unchecked AI story',published='2026-09-09T08:00:00+00:00').items() if not k.startswith('policy')}
        with tempfile.TemporaryDirectory() as d:
            data,calls,log=self.run_main(d,[leaving,unverified],[back])
            by_id={i['id']:i for i in data['items']}
            chip=by_id[chip_id]
            # The returning story: summary and Arabic headline from the archive, no Claude request for either.
            self.assertEqual((chip['summary_en'],chip['title_ar'],chip['summary_source']),('NVIDIA began shipping the chip.','إنفيديا تشحن شريحة جديدة للذكاء الاصطناعي','ai'))
            self.assertNotIn(chip_id,calls['summary']);self.assertNotIn(chip_id,calls['translate'])
            self.assertIn(chip_id,calls['policy'])  # its content check runs again
            self.assertTrue(chip['policy_ok'])
            agents=next(i for i in data['items'] if 'agents' in i['url'])
            self.assertIn(agents['id'],calls['summary']);self.assertIn(agents['id'],calls['translate'])
            # Every stored story carries its topic, by the rule of its topic image.
            for i in data['items']:self.assertEqual(i['topic'],topics.topic_of(i,SRC))
            # The verified story that left the window is in the archive beside news.json; the unchecked one is not.
            doc=json.loads((Path(d)/'news-archive'/'2026-09.json').read_text(encoding='utf-8'))
            ids=[i['id'] for i in doc['items']]
            self.assertIn('old1',ids);self.assertNotIn('old2',ids);self.assertIn(chip_id,ids)
            self.assertEqual(data['archive'],{'archived':1,'reused':1,'damaged_months':0})
            self.assertIn('News archive: 1 stories archived',log)
            # The next run: nothing left the window, the archive does not change.
            before=(Path(d)/'news-archive'/'2026-09.json').read_text(encoding='utf-8')
            data2,calls2,_=self.run_main(d,data['items'],[])
            self.assertEqual((Path(d)/'news-archive'/'2026-09.json').read_text(encoding='utf-8'),before)
            self.assertEqual((calls2['summary'],calls2['translate']),([],[]))
            self.assertEqual(data2['archive']['archived'],0)
    def test_the_cap_and_the_content_policy(self):
        chip_id,agents_id=news._hash('https://www.example-news.com/chip'),news._hash('https://www.example-news.com/agents')
        chip=verified(id=chip_id,published='2026-09-25T08:00:00+00:00',excerpt='The chip has 288 GB of memory and ships to cloud providers first.')
        agents=verified(id=agents_id,url='https://www.example-news.com/agents',title='OpenAI releases a model for AI agents',published='2026-09-25T10:00:00+00:00',
                        excerpt='The model plans and runs multi-step tasks for developers.',title_ar='أوبن إيه آي تطلق نموذجاً للوكلاء')
        with tempfile.TemporaryDirectory() as d:
            # Both stories were stored; the feed still lists both, but the cap keeps one: the other leaves and is archived.
            data,_,_=self.run_main(d,[chip,agents],[],cap=1)
            self.assertEqual([i['id'] for i in data['items']],[agents_id])
            ids=[i['id'] for i in json.loads((Path(d)/'news-archive'/'2026-09.json').read_text(encoding='utf-8'))['items']]
            self.assertEqual(ids,[chip_id]);self.assertEqual(data['archive']['archived'],1)
        with tempfile.TemporaryDirectory() as d:
            # A stored story whose texts changed fails the content check this run: removed and blocked, never archived.
            changed=verified(**{**{k:v for k,v in agents.items() if not k.startswith('policy')},'excerpt':'An older description.'})
            data,_,_=self.run_main(d,[chip,changed],[],verdict=lambda i:i!=agents_id)
            self.assertEqual([i['id'] for i in data['items']],[chip_id])
            self.assertFalse((Path(d)/'news-archive'/'2026-09.json').exists())
            self.assertEqual(data['archive']['archived'],0)
    def test_archive_dir_follows_news_json(self):
        with mock.patch.object(news,'OUT',Path('/tmp/x/news.json')),mock.patch.object(news,'ARCHIVE',None):
            self.assertEqual(news.archive_dir(),Path('/tmp/x/news-archive'))
        self.assertEqual(news.archive_dir(),news.ROOT/'data'/'news-archive')

class SiteAndAppTests(unittest.TestCase):
    """The build and the app export use the archive's stories the site may show, never those still in the list."""
    @classmethod
    def setUpClass(cls):
        cls.data,cls.feed,cls.sources,cls.uae,cls.models=build.load_all()
        items=build.news_items(cls.feed,cls.sources)
        cls.current=items[0]
        src={s['id']:s for s in cls.sources}
        # Two stories of the current list, as if archived; one of them is still in the list.
        cls.gone={**items[-1],'id':'gone0001','url':items[-1]['url']+'?archived=1','published':(datetime.fromisoformat(items[-1]['published'])-timedelta(days=20)).isoformat()}
        cls.archive=[{**news_archive.slim(cls.gone,src[cls.gone['source']]),'_pv':policy.POLICY_VERSION},
                     {**news_archive.slim(cls.current,src[cls.current['source']]),'_pv':policy.POLICY_VERSION}]
        cls.docs=build.learn.load()
        cls.out=app_data.payloads(cls.data,cls.feed,cls.sources,cls.uae,cls.models,*cls.docs,archive=cls.archive)
    def test_app_archive_json(self):
        a=self.out['archive.json']
        self.assertEqual((a['schema'],a['days'],a['updated_at']),(app_data.APP_SCHEMA,60,self.feed.get('updated_at')))
        self.assertEqual([i['id'] for i in a['items']],['gone0001'])  # the story still in news.json is not repeated
        self.assertEqual(tuple(a['items'][0]),news_archive.FIELDS)
    def test_app_news_items_carry_their_topic(self):
        src={s['id']:s for s in self.sources}
        for i,full in zip(self.out['news.json']['items'],build.news_items(self.feed,self.sources)):
            self.assertEqual(i['topic'],topics.topic_of(full,src[full['source']]))
    def test_page_offers_older_stories_only_with_an_archive(self):
        with tempfile.TemporaryDirectory() as d:
            with_archive,_=build.render_page(self.data,self.feed,self.sources,self.uae,self.models,brand_dir=Path(d),archive=self.archive)
            without,_=build.render_page(self.data,self.feed,self.sources,self.uae,self.models,brand_dir=Path(d),archive=[])
        self.assertIn('<div class="n-older js-only" id="news-older" hidden data-archive="news-archive/index.json">',with_archive)
        self.assertNotIn('id="news-older"',without);self.assertNotIn('id="uae-older"',without)
        # The block comes after the no-match box and before the note, in both views that have it.
        news_view=with_archive[with_archive.index('id="news"'):with_archive.index('id="uae"')]
        self.assertLess(news_view.index('id="news-empty"'),news_view.index('id="news-older"'));self.assertLess(news_view.index('id="news-older"'),news_view.index('class="muted n-note"'))
        for need in ('data-older="news"','id="news-older-list"','id="news-older-count" aria-live="polite"','id="news-older-more" hidden data-i18n>Show more','Search earlier months'):
            self.assertIn(need,news_view)

if __name__=='__main__':unittest.main()
