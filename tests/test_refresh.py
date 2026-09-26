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
if __name__=='__main__':unittest.main()
