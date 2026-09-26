import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from draft import Draft,check_draft,record,slug
ROOT=Path(__file__).resolve().parents[1]
CATALOG=json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'))
PAGE='AMD today announced the Instinct MI999X accelerator with 512 GB HBM4 memory, available in Q3 2027.'
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
if __name__=='__main__':unittest.main()
