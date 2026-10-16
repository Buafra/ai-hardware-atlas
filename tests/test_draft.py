import json,os,re,subprocess,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import draft as D
import review_issue
from draft import Draft,check_draft,record,slug
ROOT=Path(__file__).resolve().parents[1]
CATALOG=json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'))
PAGE='AMD today announced the Instinct MI999X accelerator with 512 GB HBM4 memory, available in Q3 2027.'
URL='https://newsroom.amd.com/news/x/'
def draft(**kw):
    d=dict(is_new_product=True,vendor='AMD',model='Instinct MI999X',level='Data center',type='GPU',architecture='CDNA 9',memory='512 GB HBM4',memory_gb=512,memory_scope='Per GPU',announcement='2027-01-05',release='2027-Q3',release_kind='Vendor target',power_w=None,use='Large-scale training',notes='Target date.',evidence=['Instinct MI999X accelerator with 512 GB HBM4','available in Q3 2027'])
    d.update(kw);return Draft(**d).model_dump()
class DraftTests(unittest.TestCase):
    def test_valid_draft_accepted(self):self.assertIsNone(check_draft(draft(),PAGE,CATALOG))
    def test_invented_evidence_rejected(self):
        self.assertIn('evidence',check_draft(draft(evidence=['1 TB HBM4']),PAGE,CATALOG))
        self.assertIn('evidence',check_draft(draft(evidence=[]),PAGE,CATALOG))
    def test_existing_product_rejected(self):self.assertEqual(check_draft(draft(model='H200'),PAGE,CATALOG),'already in catalog')
    def test_not_product_and_bad_date_rejected(self):
        self.assertEqual(check_draft(draft(is_new_product=False),PAGE,CATALOG),'not a new product')
        self.assertEqual(check_draft(draft(release='Q3 2027'),PAGE,CATALOG),'bad release format')
    def test_record_shape(self):
        r=record(draft(),'https://newsroom.amd.com/news/x/','2027-01-05T00:00:00+00:00')
        self.assertEqual(r['id'],slug('Instinct MI999X'));self.assertEqual(r['sources'][0]['url'],'https://newsroom.amd.com/news/x/')
        self.assertNotIn('evidence',r);self.assertEqual(len(r['_draft']['evidence']),2)
class FakeClient:
    def __init__(self,d):self.calls=0;self.d=d;self.messages=SimpleNamespace(parse=self.parse)
    def parse(self,**kw):
        self.calls+=1;return SimpleNamespace(stop_reason='end_turn',parsed_output=Draft(**self.d),usage=None)
class PullRequestFlowTests(unittest.TestCase):
    """A draft counts as done only once it is in a pull request; until then it is kept (no new Claude request)."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();d=Path(self.tmp.name)
        self.catalog={**CATALOG,'products':list(CATALOG['products']),
                      'announcements':[{'url':URL,'title':'AMD announces Instinct MI999X','discovered_at':'2027-01-05T00:00:00+00:00'}]}
        (d/'catalog.json').write_text(json.dumps(self.catalog),encoding='utf-8')
        self.patches=[mock.patch.object(D,'STATE',d/'draft-state.json'),mock.patch.object(D,'REPORT',d/'draft-report.json'),
                      mock.patch.object(D,'DRAFTS',d/'drafts'),mock.patch.object(D,'CATALOG',d/'catalog.json'),
                      mock.patch.dict(os.environ,{'ANTHROPIC_API_KEY':'test-key'})]
        for p in self.patches:p.start()
        self.d=d;self.client=FakeClient(draft());self.asked=[]
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def run_draft(self,pr='OPEN'):
        def ask(n):self.asked.append(n);return pr
        with mock.patch('builtins.print'):D.run(client=self.client,get=lambda u:SimpleNamespace(text=PAGE),ask=ask)
        return json.loads(D.STATE.read_text(encoding='utf-8')),json.loads(D.REPORT.read_text(encoding='utf-8'))
    def record(self,outcome,number):
        with mock.patch('builtins.print'):D.record_pr(outcome,number,'2027-01-05T12:00:00+00:00')
        return json.loads(D.STATE.read_text(encoding='utf-8')),json.loads(D.REPORT.read_text(encoding='utf-8'))
    def file(self):return self.d/'drafts'/'instinct-mi999x.json'
    def test_new_draft_waits_for_its_pull_request_and_is_kept(self):
        state,report=self.run_draft()
        self.assertEqual(state[URL]['result'],'pending');self.assertEqual(state[URL]['draft']['id'],'instinct-mi999x')
        self.assertEqual((report['created'],report['waiting'],report['in_pull_request']),(['Instinct MI999X'],['Instinct MI999X'],[]))
        self.assertEqual(json.loads(self.file().read_text(encoding='utf-8'))['model'],'Instinct MI999X')
        # The next run writes the kept draft again for the pull request; Claude is not asked again.
        self.file().unlink();state,report=self.run_draft()
        self.assertEqual(self.client.calls,1);self.assertTrue(self.file().exists())
        self.assertEqual((report['created'],report['waiting']),([],['Instinct MI999X']))
    def test_failed_pull_request_keeps_the_draft_and_is_reported(self):
        self.run_draft()
        for outcome,number in (('failure',''),('success','')):
            state,report=self.record(outcome,number)
            self.assertEqual(state[URL]['result'],'pending');self.assertIn('draft',state[URL])
            self.assertIn('Allow GitHub Actions to create and approve pull requests',report['pr_error'])
            self.assertEqual(report['waiting'],['Instinct MI999X'])
        line=review_issue.drafts_status(report)
        self.assertIn('AI drafts waiting for a pull request',line);self.assertIn('- Instinct MI999X',line)
        self.assertEqual(review_issue.drafts_status({'created':[]}),'')
    def test_done_once_in_a_pull_request_then_kept_in_it_until_closed(self):
        self.run_draft();self.record('failure','')
        state,report=self.record('success','7')
        self.assertEqual((state[URL]['result'],state[URL]['pr']),('drafted',7))
        self.assertNotIn('pr_error',report);self.assertEqual((report['pull_requests'],report['waiting'],report['in_pull_request']),([7],[],['Instinct MI999X']))
        # While the pull request is open its drafts are written again, so a later run adds to it instead of emptying it.
        self.file().unlink();state,_=self.run_draft('OPEN')
        self.assertEqual(self.asked,[7]);self.assertTrue(self.file().exists());self.assertEqual(self.client.calls,1)
        # Merged or closed: the draft leaves the state and is not written again; the announcement is not drafted again.
        self.file().unlink();state,report=self.run_draft('CLOSED')
        self.assertNotIn('draft',state[URL]);self.assertEqual(state[URL]['closed'],'pull request closed')
        self.assertFalse(self.file().exists());self.assertEqual(self.client.calls,1);self.assertEqual(report['in_pull_request'],[])
    def test_unknown_pull_request_state_keeps_the_draft(self):
        # gh cannot tell (no token, network): the draft is written again rather than lost.
        self.run_draft();self.record('success','7')
        self.file().unlink();state,_=self.run_draft(None)
        self.assertIn('draft',state[URL]);self.assertTrue(self.file().exists())
    def test_no_waiting_drafts_nothing_recorded(self):
        D.STATE.write_text('{}',encoding='utf-8')
        with mock.patch('builtins.print'):self.assertEqual(D.record_pr('failure',''),0)
        self.assertFalse(D.REPORT.exists())
    def test_legacy_drafted_without_a_pull_request_is_drafted_again(self):
        # The old code said "drafted" before any pull request existed; that draft never reached the owner.
        D.STATE.write_text(json.dumps({URL:{'at':'2026-09-26T18:19:28+00:00','result':'drafted'}}),encoding='utf-8')
        state,_=self.run_draft()
        self.assertEqual(self.client.calls,1);self.assertEqual(state[URL]['result'],'pending')
        # Other outcomes stay done.
        D.STATE.write_text(json.dumps({URL:{'at':'2026-09-26T18:19:28+00:00','result':'not a new product'}}),encoding='utf-8')
        self.client.calls=0;state,_=self.run_draft();self.assertEqual(self.client.calls,0)
    def test_product_in_the_catalog_settles_its_draft(self):
        self.run_draft()
        self.catalog['products'].append({**self.catalog['products'][0],'id':'instinct-mi999x','model':'Instinct MI999X'})
        D.CATALOG.write_text(json.dumps(self.catalog),encoding='utf-8')
        self.file().unlink();state,report=self.run_draft()
        self.assertEqual(state[URL]['closed'],'in catalog');self.assertFalse(self.file().exists());self.assertEqual(report['waiting'],[])
    def test_same_product_from_a_second_announcement(self):
        self.run_draft()
        second='https://newsroom.amd.com/news/y/'
        self.catalog['announcements'].append({'url':second,'title':'AMD Instinct MI999X details','discovered_at':'2027-01-06T00:00:00+00:00'})
        D.CATALOG.write_text(json.dumps(self.catalog),encoding='utf-8')
        state,_=self.run_draft()
        self.assertEqual(state[second]['result'],'already drafted');self.assertEqual(state[URL]['result'],'pending')
    def test_without_a_key_no_claude_but_kept_drafts_are_written(self):
        self.run_draft();self.file().unlink()
        with mock.patch.dict(os.environ,{'ANTHROPIC_API_KEY':''}):_,report=self.run_draft()
        self.assertEqual(self.client.calls,1);self.assertTrue(self.file().exists());self.assertEqual(report['skipped'],'ANTHROPIC_API_KEY not set')
    def test_pr_state_reads_gh(self):
        done=lambda out,code=0:(lambda *a,**k:subprocess.CompletedProcess(a,code,stdout=out,stderr=''))
        self.assertEqual(D.pr_state(7,done('MERGED\n')),'MERGED');self.assertEqual(D.pr_state(7,done('OPEN')),'OPEN')
        self.assertIsNone(D.pr_state(7,done('',1)));self.assertIsNone(D.pr_state(7,done('weird')))
        def missing(*a,**k):raise FileNotFoundError('gh')
        self.assertIsNone(D.pr_state(7,missing))
class DraftWorkflowTests(unittest.TestCase):
    def test_pull_request_step(self):
        wf=(ROOT/'.github/workflows/publish.yml').read_text(encoding='utf-8')
        # The third-party action gets the write token: pinned to a full commit SHA (v8.1.1), never a movable tag.
        uses=re.findall(r'uses: peter-evans/create-pull-request@(\S+)',wf)
        self.assertEqual(len(uses),1);self.assertRegex(uses[0],r'^[0-9a-f]{40}$')
        pr=wf.index('uses: peter-evans/create-pull-request@');step=wf[wf.rindex('- name:',0,pr):pr]
        self.assertIn('id: drafts-pr',step);self.assertIn("hashFiles('data/drafts/*.json') != ''",step)
        # Recorded before the data is saved, so data/draft-state.json says whether the pull request exists.
        rec=wf.index('run: python scripts/draft.py --pr-result');rstep=wf[wf.rindex('- name:',0,rec):rec]
        self.assertIn('PR_NUMBER: ${{ steps.drafts-pr.outputs.pull-request-number }}',rstep);self.assertIn('PR_OUTCOME: ${{ steps.drafts-pr.outcome }}',rstep)
        run=wf.index('run: python scripts/draft.py\n')
        self.assertLess(run,pr);self.assertLess(pr,rec);self.assertLess(rec,wf.index('name: Save refreshed data'))
        self.assertLess(rec,wf.index('run: python scripts/review_issue.py'))
        self.assertIn('GH_TOKEN: ${{ github.token }}',wf[wf.rindex('- name:',0,run):run])
if __name__=='__main__':unittest.main()
