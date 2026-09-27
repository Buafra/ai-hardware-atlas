import json,re,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import app_data,build,policy,review_issue
ROOT=Path(__file__).resolve().parents[1]
REMOVED_SOURCES={'guardian-ai','bbc-tech','bbc-ar','aljazeera-ar','cnn-ar','dw-ar'}

class RegionDetectionTests(unittest.TestCase):
    """Whole words, English and Arabic, any case or diacritics: the UAE and the GCC states, their cities, rulers and state entities."""
    EN=['UAE unveils a national AI plan','The U.A.E. said on Monday','the United Arab Emirates','Emirati students win','Saudi Arabia opens a lab','KSA data centre',
        'a Qatari fund','Kuwaiti bank adopts AI','Bahrain hosts a summit','Omani ministry','GCC ministers met','Gulf states invest','the Arabian Gulf',
        'Abu Dhabi','ABU DHABI','Dubai','Sharjah','Ajman','Ras Al Khaimah','Ras al-Khaimah','Fujairah','Umm Al Quwain','Al Ain','Riyadh','Jeddah','NEOM','Doha',
        'Kuwait City','Manama','Muscat','Sheikh Mohamed bin Zayed','Al Nahyan','Al-Maktoum','Al Qasimi','Al Saud','Al Thani','Al Sabah','Al Khalifa','Al Said',
        'the crown prince of Abu Dhabi','the Emir of Qatar','King Hamad','G42','Core42','MGX','Mubadala','ADNOC','ADQ','TII','e& expands 5G','PIF','HUMAIN',
        'Aramco','QIA','Ooredoo','KIA','Mumtalakat','Omantel','Khazna','MBZUAI','Falcon-H1','Jais','Dubaï','Stargate UAE',
        # glued and variant spellings, leaders by first name or title, places and companies (red-team hole 1)
        'Abudhabi','AbuDhabi AI week','MbS backs an AI push','MBZ','Prince Mohammed unveils a plan','Prince Mohamed','Tahnoun','Tahnoon','Riyad summit',
        'Jebel Ali','Yas Island','Saadiyat','DP World','Emaar','flydubai','Saudia','the Emir said','Sultan Al Jaber','Khalifa University','Hamdan',
        'Dubаi','UАE']  # Cyrillic look-alike letters
    AR=['الإمارات','والإمارات','بالإمارات','للإمارات','إماراتي','الإماراتية','الإماراتيين','دولة الإمارات','أبوظبي','أبو ظبي','دبي','بدبي','الشارقة','عجمان',
        'الفجيرة','رأس الخيمة','أم القيوين','السعودية','بالسعودية','سعودي','الرياض','بالرياض','في جدة','مكة المكرمة','نيوم','قطر','وقطر','القطرية','الدوحة',
        'الكويت','الكويتي','البحرين','البحرينية','عُمان','سلطنة عمان','العمانية','مسقط','المنامة','الخليج','الخليجية','مجلس التعاون','آل نهيان','آل مكتوم',
        'آل سعود','آل ثاني','آل صباح','آل خليفة','آل سعيد','محمد بن زايد','محمد بن راشد','سمو الشيخ','صاحب السمو','ولي العهد','خادم الحرمين','أرامكو','مبادلة',
        'أدنوك','صندوق الاستثمارات العامة','جي 42','هيوماين','أوريدو','عمانتل','الإمـــارات','الإِمَارَات','إمارة الشارقة',
        'الشيخ طحنون','طحنون','الملك سلمان','الأمير تميم','ابن سلمان','السلطان هيثم','الملك حمد','الأمير محمد','سلطنة عمّان','سَلطنةُ عُمّان','أمير قطر','الشيخ']
    NOT=['A woman leads the lab','Romania joins the programme','Gulf of Mexico storm','Gulf Coast refinery','A Gulfstream jet','Kia cars get AI','Alain Aspect wins',
         'Amman, Jordan','Omaha data centre','nominal growth','Falcon 9 launch','Human rights groups','the ksa was lowercase','pif','tii','Sheikhupura',
         'NVIDIA ships Blackwell','OpenAI releases GPT-5','Anthropic Claude','Dubrovnik','Doha'[:0]+'Dohany street',
         'عمّان','مسقط رأسه','خليج المكسيك','رياض الأطفال','وجده في المكتب','جدة','الخبر','مصدر مطلع','قطار سريع','نظام الذكاء الاصطناعي','شركة إنفيديا',
         '8 MBs of cache','Prince Harry','Yasmin','Mohammed Ali','الملكية الفكرية','السلطات المحلية','الشيخوخة','أمير خان','في عمّان عاصمة الأردن']
    def test_english_names(self):
        for t in self.EN:self.assertTrue(policy.mentions_region(t),t)
    def test_arabic_names(self):
        for t in self.AR:self.assertTrue(policy.mentions_region(t),t)
    def test_no_false_positives(self):
        for t in self.NOT:self.assertFalse(policy.mentions_region(t),(t,policy.region_terms(t)))
    def test_normalisation(self):
        self.assertEqual(policy.normalize('الإِمَارَاتـــية'),'الاماراتيه')
        self.assertEqual(policy.normalize('Dubaï'),'Dubai')
        self.assertTrue(policy.mentions_region('the GCC​ region'))  # invisible characters removed
        self.assertTrue(policy.mentions_region('','','an item about Qatar'))  # any of the texts
        self.assertFalse(policy.mentions_region(None,''))
        self.assertEqual(policy.region_terms('AI in Abu Dhabi and Riyadh'),['Abu Dhabi','Riyadh'])
    def test_item_texts(self):
        base={'title':'NVIDIA ships a chip','lang':'en'}
        self.assertFalse(policy.item_mentions_region(base))
        for k in policy.TEXT_FIELDS[1:]:self.assertTrue(policy.item_mentions_region({**base,k:'شراكة مع أبوظبي'}),k)
        self.assertNotEqual(policy.fingerprint(base),policy.fingerprint({**base,'summary_en':'x'}))

class SourceTests(unittest.TestCase):
    def setUp(self):
        self.sources=json.loads((ROOT/'data/news-sources.json').read_text(encoding='utf-8'))
    def test_removed_sources_are_gone(self):
        self.assertFalse(REMOVED_SOURCES&{s['id'] for s in self.sources})
        feed=json.loads((ROOT/'data/news.json').read_text(encoding='utf-8'))
        self.assertFalse(REMOVED_SOURCES&{i['source'] for i in feed['items']})
    def test_regional_outlets(self):
        regional={s['id'] for s in self.sources if policy.regional_outlet(s)}
        self.assertEqual(regional-{s['id'] for s in self.sources if s['region']=='uae'},{'skynews-ar-tech','indy-ar-new'})
        # M1: regional outlets and official sources of the region (the Dubai Media Office feeds are region "uae");
        # global vendor newsrooms (kind "primary") are not official sources of the region.
        for s in self.sources:
            self.assertEqual(policy.may_cover_region(s),policy.regional_outlet(s) or s.get('official_region') is True,s['id'])
        self.assertTrue(all(policy.regional_outlet(s) for s in self.sources if s['id'].startswith('mediaoffice')))
        for sid in ('techcrunch-ai','verge-ai','euronews-ar','aitnews','wired-ai','nvidia-news','openai-news','mit-news-ai'):
            self.assertFalse(policy.may_cover_region(next(s for s in self.sources if s['id']==sid)),sid)
    def test_blocklist_holds_ids_only(self):
        path=ROOT/'data/news-blocked.json'
        if not path.exists():return
        data=json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(set(data),{'about','ids'})
        for k,v in data['ids'].items():
            self.assertRegex(k,r'^[0-9a-f]{12}$');self.assertRegex(v,r'^\d{4}-\d{2}-\d{2}$')
        feed=json.loads((ROOT/'data/news.json').read_text(encoding='utf-8'))
        self.assertFalse(set(data['ids'])&{i['id'] for i in feed['items']})  # blocked items are gone from news.json

class DisplayRuleTests(unittest.TestCase):
    """build.news_items() (the site) and app_data (the Android app) hide UAE/GCC items without a passing verdict."""
    @classmethod
    def setUpClass(cls):
        cls.data,cls.feed,cls.sources,cls.uae,cls.models=build.load_all()
        cls.docs=build.learn.load()
    def fixed(self):
        src={r:next(s for s in self.sources if s['region']==r and s['kind']=='news') for r in ('global','uae')}
        host=lambda s:'https://'+build.urlparse(s['homepage']).hostname
        ok={'policy_ok':True,'policy_version':policy.POLICY_VERSION}
        items=[
            ('plain',src['global'],{'title':'Lab releases a new open model'}),
            ('uae-ok',src['uae'],{'title':'Abu Dhabi opens an AI campus',**ok}),
            ('uae-none',src['uae'],{'title':'Dubai launches an AI programme'}),
            ('uae-old',src['uae'],{'title':'Riyadh hosts an AI summit','policy_ok':True,'policy_version':policy.POLICY_VERSION-1}),
            ('uae-summary',src['uae'],{'title':'New AI programme launched','summary_en':'The programme starts in Sharjah. It is free.','summary_ar':'يبدأ البرنامج في الشارقة.','summary_source':'ai'}),
            ('failed',src['global'],{'title':'Lab releases a second model','policy_ok':False}),
            ('global-uae',src['global'],{'title':'AI deal in Qatar',**ok}),
        ]
        out=[{'id':i,'url':host(s)+'/'+i,'source':s['id'],'lang':'en','uae':s['region']=='uae',
              'published':f'2026-09-26T{10-n:02d}:00:00+00:00',**kw} for n,(i,s,kw) in enumerate(items)]
        for it in out:  # a verdict holds for the texts it was given
            if it.get('policy_ok'):it['policy_hash']=policy.fingerprint(it)
        return {'updated_at':'2026-09-26T13:00:00+00:00','items':out}
    def test_verdict_for_other_texts_is_not_trusted(self):
        feed=self.fixed();ok=next(i for i in feed['items'] if i['id']=='uae-ok')
        ok['summary_en'],ok['summary_source']='Critics accuse Abu Dhabi rulers of abuses.','ai'  # a hand edit after the check
        self.assertEqual([i['id'] for i in build.news_items(feed,self.sources)],['plain'])
    def test_unusable_answer_hides_any_item(self):
        feed=self.fixed();feed['items'][0]['policy_attempts']=1  # a refusal: hidden even without a region name
        self.assertEqual([i['id'] for i in build.news_items(feed,self.sources)],['uae-ok'])
    def test_site_list(self):
        self.assertEqual([i['id'] for i in build.news_items(self.fixed(),self.sources)],['plain','uae-ok'])
    def test_app_export(self):
        out=app_data.payloads(self.data,self.fixed(),self.sources,self.uae,self.models,*self.docs)
        self.assertEqual([i['id'] for i in out['news.json']['items']],['plain','uae-ok'])
    def test_rendered_page(self):
        with tempfile.TemporaryDirectory() as d:
            html,_=build.render_page(self.data,self.fixed(),self.sources,self.uae,self.models,brand_dir=Path(d))
        self.assertIn('Abu Dhabi opens an AI campus',html)
        for t in ('Dubai launches','Riyadh hosts','New AI programme launched','second model','AI deal in Qatar'):self.assertNotIn(t,html,t)
    def test_live_data(self):
        for i in build.news_items(self.feed,self.sources):
            if policy.item_mentions_region(i):self.assertTrue(policy.verified(i),i['id'])

class ReviewIssueTests(unittest.TestCase):
    """The review issue is public: counts only, never a news title, link or reason."""
    def test_counts_only(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'news.json'
            p.write_text(json.dumps({'ai':{'key_set':True,'policy_version':1,'policy_checked':12,'policy_blocked':2,'m1_dropped':3,'regional':9,'policy_pending':4,
                                           'problems':{'policy: stop reason refusal':1}},
                                     'items':[{'id':'a1','title':'Secret failing headline','url':'https://x.example/a1','source':'s'}]}),encoding='utf-8')
            text=review_issue.ai_status(p)+'\n'+review_issue.policy_status(p)
            self.assertIn('12 checked, 2 removed, 3 dropped from non-regional sources, 4 of 9 UAE/GCC items hidden until verified',text)
            for bad in ('Secret failing headline','x.example','P1','P2'):self.assertNotIn(bad,text)
            p.write_text(json.dumps({'ai':{'key_set':False}}),encoding='utf-8')
            self.assertIn('stay hidden until they pass the check',review_issue.ai_status(p))
            self.assertEqual(review_issue.policy_status(p),'')
        src=(ROOT/'scripts/review_issue.py').read_text(encoding='utf-8')
        self.assertNotIn("['title']",src);self.assertNotIn('news-blocked',src)

if __name__=='__main__':unittest.main()
