import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import app_data,build

class AppDataTests(unittest.TestCase):
    """dist/app/*.json feeds the Android app: same public data and the same news rules as the site."""
    @classmethod
    def setUpClass(cls):
        cls.data,cls.feed,cls.sources,cls.uae,cls.models=build.load_all()
        cls.docs=build.learn.load()
        cls.out=app_data.payloads(cls.data,cls.feed,cls.sources,cls.uae,cls.models,*cls.docs)

    def test_files_and_schema(self):
        self.assertEqual(set(self.out),{'catalog.json','news.json','uae.json','learn.json','models.json','about.json'})
        for name,payload in self.out.items():self.assertEqual(payload['schema'],app_data.APP_SCHEMA,name)

    def test_catalog_keeps_backend_fields_out(self):
        cat=self.out['catalog.json']
        for key in build.BACKEND_ONLY:self.assertNotIn(key,cat)
        self.assertEqual(len(cat['products']),len(self.data['products']))
        ids={p['id'] for p in cat['products']}
        self.assertTrue(set(cat['featured'])<=ids)
        self.assertEqual(cat['levels'],build.LEVELS)

    def test_news_matches_the_site_list(self):
        items=self.out['news.json']['items']
        site=build.news_items(self.feed,self.sources)
        self.assertEqual([i['id'] for i in items],[i['id'] for i in site])
        by_id={i['id']:i for i in site}
        src={s['id']:s for s in self.sources}
        for i in items:
            raw=by_id[i['id']]
            self.assertEqual(i['in_ar'],build.in_lang(raw,'ar'))
            self.assertEqual(i['in_en'],build.in_lang(raw,'en'))
            self.assertEqual(i['regions'],build.regions(raw,src))
            for lang in ('en','ar'):
                self.assertEqual((i[f'summary_{lang}'],i[f'summary_kind_{lang}']),build.summary_of(raw,lang))

    def test_hidden_news_stays_hidden(self):
        feed={**self.feed,'items':[{**self.feed['items'][0],'id':'off-topic','ai_focus':False}]+self.feed['items'][1:]}
        out=app_data.payloads(self.data,feed,self.sources,self.uae,self.models,*self.docs)
        self.assertNotIn('off-topic',[i['id'] for i in out['news.json']['items']])

    def test_uae_facts_newest_first(self):
        facts=self.out['uae.json']['facts']
        dates=[str(f.get('as_of') or '') for f in facts]
        self.assertEqual(dates,sorted(dates,reverse=True))

    def test_learn_and_models(self):
        learn=self.out['learn.json']
        self.assertEqual(len(learn['concepts']),len(self.docs[0]['concepts']))
        orders=[s.get('order',0) for s in learn['stacks']]
        self.assertEqual(orders,sorted(orders))
        models=self.out['models.json']['models']
        self.assertEqual(len(models),len(self.models['models']))
        self.assertTrue(all(set(m)==set(app_data.MODEL_KEYS) for m in models))

    def test_learn_lists_only_published_lessons(self):
        # A lesson not published on qahwa.html yet must not reach the app (its title would spoil the schedule).
        planned=sorted({les['lesson'] for c in self.docs[0]['concepts'] for les in c.get('related_lessons') or []})
        self.assertIn(4,planned)
        for c in self.out['learn.json']['concepts']:self.assertEqual(c['related_lessons'],[],c['id'])
        empty={'schema':1,'posts':[]}
        out=app_data.payloads(self.data,self.feed,self.sources,self.uae,self.models,*self.docs,lessons_doc=empty)
        self.assertFalse([c['id'] for c in out['learn.json']['concepts'] if c['related_lessons']])
        four={'schema':1,'posts':[{'id':'week-01-day-04--1-learn-lesson-04','kind':'lesson','lesson':4}]}
        out=app_data.payloads(self.data,self.feed,self.sources,self.uae,self.models,*self.docs,lessons_doc=four)
        got=[(c['id'],les['lesson'],les['url']) for c in out['learn.json']['concepts'] for les in c['related_lessons']]
        want=[(c['id'],4,'qahwa.html#lesson-04') for c in self.docs[0]['concepts'] if 4 in [les['lesson'] for les in c.get('related_lessons') or []]]
        self.assertTrue(want)
        self.assertEqual(got,want)
        raw=app_data.encode(out['learn.json']).decode('utf-8')
        for c in self.docs[0]['concepts']:
            for les in c.get('related_lessons') or []:
                if les['lesson']!=4:
                    self.assertNotIn(les['title_en'],raw)
                    self.assertNotIn(les['title_ar'],raw)
        waiting={'schema':1,'posts':[{**four['posts'][0],'status':'waiting'}]}
        out=app_data.payloads(self.data,self.feed,self.sources,self.uae,self.models,*self.docs,lessons_doc=waiting)
        self.assertFalse([c['id'] for c in out['learn.json']['concepts'] if c['related_lessons']])
        # The concepts' other fields pass through untouched.
        for a,b in zip(out['learn.json']['concepts'],self.docs[0]['concepts']):
            self.assertEqual({k:v for k,v in a.items() if k!='related_lessons'},{k:v for k,v in b.items() if k!='related_lessons'})

    def test_write_uses_the_published_lessons(self):
        four={'schema':1,'posts':[{'id':'week-01-day-04--1-learn-lesson-04','kind':'lesson','lesson':4}]}
        with tempfile.TemporaryDirectory() as tmp:
            app_data.write(tmp,self.data,self.feed,self.sources,self.uae,self.models,*self.docs,lessons_doc=four)
            doc=json.loads((Path(tmp)/app_data.APP_DIR/'learn.json').read_text(encoding='utf-8'))
        self.assertEqual({les['lesson'] for c in doc['concepts'] for les in c['related_lessons']},{4})

    def test_about_is_the_shared_file(self):
        about=self.out['about.json']
        self.assertEqual({k:v for k,v in about.items() if k!='schema'},app_data.load_about())
        self.assertEqual([a['id'] for a in about['areas']],['hardware','news','uae','learn'])
        for key in ('promise','name_story','trust','qahwa'):self.assertTrue(about[key]['en'] and about[key]['ar'],key)
        self.assertEqual(len(about['about']['en']),len(about['about']['ar']))

    def test_manifest_hashes_match_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest=app_data.write(tmp,self.data,self.feed,self.sources,self.uae,self.models,*self.docs)
            folder=Path(tmp)/app_data.APP_DIR
            self.assertEqual(set(manifest['files']),set(self.out))
            for name,meta in manifest['files'].items():
                raw=(folder/name).read_bytes()
                self.assertEqual(meta['sha256'],hashlib.sha256(raw).hexdigest())
                self.assertEqual(meta['bytes'],len(raw))
                json.loads(raw.decode('utf-8'))
            self.assertEqual(json.loads((folder/'manifest.json').read_text(encoding='utf-8')),manifest)

if __name__=='__main__':unittest.main()
