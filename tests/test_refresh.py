import copy,json,re,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from refresh import Page,official,parse_spec,apply_values
from build import validate
ROOT=Path(__file__).resolve().parents[1]
class RefreshTests(unittest.TestCase):
    def test_catalog(self):validate(json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8')))
    def test_domain_boundary(self):
        self.assertTrue(official('https://docs.nvidia.com/a'))
        for u in ['http://amd.com/a','https://amd.com.evil.example/a','https://nvidia.com@evil.example/a','https://localhost/a']:
            self.assertFalse(official(u))
    def test_ambiguous_memory_rejected(self):
        rule={'title':'R9700','fields':{'memory_gb':r'Dedicated Memory Size\s+(\d+)\s*GB'}}
        page=Page();page.feed('<h1>R9700</h1><p>Dedicated Memory Size 32 GB</p><p>Dedicated Memory Size 64 GB</p>')
        with self.assertRaises(ValueError):parse_spec(page,rule)
    def test_title_mismatch_rejected(self):
        page=Page();page.feed('<h1>Other GPU</h1><p>Dedicated Memory Size 32 GB</p>')
        with self.assertRaises(ValueError):parse_spec(page,{'title':'R9700','fields':{}})
    def test_canonical_memory_and_display_stay_consistent(self):
        p={'model':'Test','memory_scope':'Per GPU','memory_gb':32,'memory':'32 GB GDDR6'}
        apply_values(p,{'memory_gb':64});self.assertEqual(p['memory'],'64 GB GDDR6')
        apply_values(p,{'power_w':300});self.assertEqual(p['power_note'],'Official specification, checked automatically')
        p['memory_scope']='Rack total'
        with self.assertRaises(ValueError):apply_values(p,{'memory_gb':128})
    def test_script_contents_excluded(self):
        page=Page();page.feed('<h1>R9700</h1><script>Dedicated Memory Size 999 GB</script><p>Dedicated Memory Size 32 GB</p>')
        self.assertEqual(parse_spec(page,{'title':'R9700','fields':{'memory_gb':r'Dedicated Memory Size\s+(\d+)\s*GB'}}),{'memory_gb':32})
    def test_refresh_rules_well_formed(self):
        rules=json.loads((ROOT/'data/refresh-rules.json').read_text(encoding='utf-8'))
        ids={p['id'] for p in json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'))['products']}
        for pid,rule in rules.items():
            self.assertIn(pid,ids);self.assertTrue(official(rule['url']),pid);self.assertTrue(rule['title'].strip(),pid)
            self.assertTrue(rule['fields']);self.assertLessEqual(set(rule['fields']),{'memory_gb','power_w'},pid)
            for pattern in rule['fields'].values():self.assertEqual(re.compile(pattern).groups,1,pid)
class FailedSourceTests(unittest.TestCase):
    def test_short_safe_reasons(self):
        import refresh
        from urllib.error import HTTPError,URLError
        self.assertEqual(refresh.reason(HTTPError('https://forums.developer.nvidia.com/t/x?token=abc',403,'Forbidden',{},None)),'HTTPError 403: Forbidden')
        self.assertEqual(refresh.reason(URLError('[Errno -2] Name or service not known')),'URLError: [Errno -2] Name or service not known')
        self.assertEqual(refresh.reason(ValueError('Source incomplete or blocked')),'ValueError: Source incomplete or blocked')
        self.assertEqual(refresh.reason(TimeoutError('The read operation timed out')),'TimeoutError: The read operation timed out')
        self.assertEqual(refresh.reason(TimeoutError()),'TimeoutError')
        r=refresh.reason(ValueError('redirected to https://cdn.example/a?key=SECRET then\n  failed '+'x'*300))
        self.assertNotIn('SECRET',r);self.assertNotIn('https',r);self.assertIn('<address>',r);self.assertLessEqual(len(r),120);self.assertNotIn('\n',r)
    def test_script_rendered_pages_are_manual_checks(self):
        import refresh
        for u in ('https://marketplace.nvidia.com/en-us/products/rtx-spark/','https://Marketplace.nvidia.com/en-us/enterprise/robotics-edge/?category=igx_developer_kit'):
            self.assertTrue(refresh.manual(u),u)
        for u in ('https://www.nvidia.com/en-us/','https://nvidianews.nvidia.com/news/latest','https://marketplace.nvidia.com.example/x'):
            self.assertFalse(refresh.manual(u),u)
    def test_run_keeps_reasons_and_lists_manual_checks(self):
        import refresh,shutil,tempfile
        from unittest import mock
        from urllib.error import HTTPError
        fetched=[]
        def fake(url):
            fetched.append(url)
            if 'forums.developer.nvidia.com' in url:raise HTTPError(url,403,'Forbidden',{},None)
            page=Page();page.feed('<h1>Official page</h1><p>'+'Text. '*100+'</p>');return page
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);(d/'data').mkdir()
            for name in ('catalog.json','refresh-rules.json'):shutil.copy(ROOT/'data'/name,d/'data'/name)
            # Sources of both kinds, whatever the real catalog cites today.
            catalog=json.loads((d/'data/catalog.json').read_text(encoding='utf-8'))
            catalog['products'][0]['sources']+=[{'label':'Marketplace','url':'https://marketplace.nvidia.com/en-us/products/test-item/'},
                                                {'label':'Forum','url':'https://forums.developer.nvidia.com/t/test-thread/1'}]
            (d/'data/catalog.json').write_text(json.dumps(catalog),encoding='utf-8')
            with mock.patch.object(refresh,'ROOT',d),mock.patch.object(refresh,'fetch',fake),mock.patch('builtins.print'):
                refresh.main()
            report=json.loads((d/'data/refresh-report.json').read_text(encoding='utf-8'))
            catalog=json.loads((d/'data/catalog.json').read_text(encoding='utf-8'))
        manual=[m['url'] for m in report['manual_checks']]
        self.assertIn('https://marketplace.nvidia.com/en-us/products/test-item/',manual);self.assertTrue(all(refresh.manual(u) for u in manual))
        self.assertTrue(all(m['why']==refresh.MANUAL_WHY for m in report['manual_checks']))
        self.assertFalse([u for u in fetched if refresh.manual(u)])  # never fetched ...
        self.assertTrue(set(manual)<={s['url'] for p in catalog['products'] for s in p['sources']})  # ... but still sources
        self.assertEqual(report['health']['attempted_sources'],len(fetched))
        forum=[u for u in fetched if 'forums.developer.nvidia.com' in u]
        self.assertIn('https://forums.developer.nvidia.com/t/test-thread/1',forum);self.assertEqual(report['errors'],{u:'HTTPError 403: Forbidden' for u in forum})
        self.assertEqual(report['new_errors'],[])  # a first failure is not news yet
if __name__=='__main__':unittest.main()
class PriceViewTests(unittest.TestCase):
    def test_ranges_and_peg_fallback(self):
        from build import price_view
        v=price_view({'price':{'usd_low':1999,'usd_high':2499,'usd_kind':'US retail','aed_low':None,'aed_high':None,'checked':'2026-09-26','sources':[]}})
        self.assertEqual(v['usd'],'$1,999–2,499');self.assertEqual(v['aed'],'≈ AED 7,340–9,180');self.assertEqual(v['aed_kind'],'Converted from USD at 3.6725')
        v=price_view({'price':{'usd_low':549,'usd_high':549,'aed_low':2199,'aed_high':2599,'aed_kind':'UAE retail','checked':'2026-09-26'}})
        self.assertEqual(v['usd'],'$549');self.assertEqual(v['aed'],'AED 2,199–2,599')
        self.assertIsNone(price_view({'price':None}));self.assertIsNone(price_view({'price':{'usd_low':None,'aed_low':None}}))
