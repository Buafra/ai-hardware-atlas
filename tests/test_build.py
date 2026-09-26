import json,re,sys,tempfile,unittest
from pathlib import Path
from urllib.parse import unquote,urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build
ROOT=Path(__file__).resolve().parents[1]

class BrandSlotTests(unittest.TestCase):
    def test_sanitize_strips_active_content_and_external_refs(self):
        dirty=('<?xml version="1.0"?><!-- c --><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" onload="alert(1)">'
               '<script>alert(2)</script><defs><linearGradient id="g"><stop offset="0"/></linearGradient></defs>'
               '<rect width="64" height="64" fill="url(#g)" onclick=\'x()\'/><use href="#g"/><image href="https://evil.example/x.png"/>'
               '<a href="javascript:alert(3)"><circle r="4" style="fill:url(https://evil.example/f)"/></a>'
               '<foreignObject><div onmouseover="y()">hi</div></foreignObject></svg>')
        s=build.sanitize_svg(dirty)
        self.assertTrue(s.startswith('<svg') and s.endswith('</svg>'))
        for bad in ('script','onload','onclick','onmouseover','javascript:','evil.example','foreignObject','<a ','<?xml','<!--'):self.assertNotIn(bad,s)
        self.assertIn('id="logo-g"',s);self.assertIn('url(#logo-g)',s);self.assertIn('href="#logo-g"',s)
        self.assertEqual(build.sanitize_svg('<div>not svg</div>'),'')
    # The logo is an <img> of a data: URI: whatever slips past the regex sanitiser, an SVG image runs no script and loads nothing.
    INERT=re.compile(r'^<img class="brand-logo" src="data:image/svg\+xml,[^"<>]*" alt="">$')
    PAYLOADS={
        'slash_onload':'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"/onload="window.__hit=1"><rect width="10" height="10"/></svg>',
        'nospace_img':'<svg viewBox="0 0 10 10"><rect width="10" height="10"/><img src="nope.png"onerror="window.__hit=1"></svg>',
        'split_script':'<svg viewBox="0 0 10 10"><scr<script>ipt>window.__hit=1</script x><rect width="10" height="10"/></svg>',
        'unquoted_href':'<svg viewBox="0 0 10 10"><image href=https://example.com/unquoted.png width="10" height="10"/></svg>',
        'img_src':'<svg viewBox="0 0 10 10"><rect width="10" height="10"/><img src="https://example.com/breakout.png"></svg>',
        'image_set':"<svg viewBox=\"0 0 10 10\" style=\"background-image:image-set('https://example.com/imageset.png' 1x)\"><rect width=\"10\" height=\"10\"/></svg>",
    }
    def test_logo_bypass_payloads_stay_inside_an_image(self):
        data,feed,sources,uae,models=build.load_all()
        for name,svg in self.PAYLOADS.items():
            with tempfile.TemporaryDirectory() as d:
                (Path(d)/'logo.svg').write_text(svg,encoding='utf-8')
                logo,_=build.brand_assets(Path(d))
                page,_=build.render_page(data,feed,sources,uae,models,brand_dir=Path(d))
            self.assertRegex(logo,self.INERT,name)
            header=page[page.index('<header'):page.index('</header>')]
            self.assertIn(logo,header,name)
            for raw in ('__hit','example.com','onerror','onload','<script','<image','<img src="nope'):self.assertNotIn(raw,header.replace(logo,''),name)
    def test_no_logo_means_wordmark_only_and_neutral_favicon(self):
        with tempfile.TemporaryDirectory() as d:
            logo,icon=build.brand_assets(Path(d))
        self.assertEqual(logo,'')
        svg=unquote(icon.split(',',1)[1])
        self.assertTrue(icon.startswith('data:image/svg+xml,'))
        self.assertEqual(re.findall(r'<(\w+)',svg),['svg','defs','linearGradient','stop','stop','stop','rect'])  # a gradient square, no letter or symbol
    def test_owner_logo_and_favicon_are_used(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'logo.svg').write_text('<svg viewBox="0 0 64 64" width="64" height="64"><circle cx="32" cy="32" r="30" onclick="x()"/></svg>',encoding='utf-8')
            (Path(d)/'favicon.svg').write_text('<svg viewBox="0 0 32 32"><rect width="32" height="32"/><script>x()</script></svg>',encoding='utf-8')
            logo,icon=build.brand_assets(Path(d))
        self.assertRegex(logo,self.INERT)
        svg=unquote(logo.split(',',1)[1].split('"')[0])
        self.assertTrue(svg.startswith('<svg') and 'xmlns="http://www.w3.org/2000/svg"' in svg and '<circle' in svg,svg)
        self.assertNotIn('onclick',svg)
        self.assertIn('<rect',unquote(icon));self.assertNotIn('script',unquote(icon));self.assertIn('xmlns=',unquote(icon))

class BrandTests(unittest.TestCase):
    """The owner's Cipher Lacuna brand files, the page head and the share preview."""
    @classmethod
    def setUpClass(cls):
        cls.html,_=build.render_page(*build.load_all())
        cls.head=cls.html[:cls.html.index('<style>')]
    def meta(self,attr,name):
        m=re.search(r'<meta %s="%s" content="([^"]*)">'%(attr,re.escape(name)),self.head)
        self.assertTrue(m,name);return m.group(1)
    def test_owner_logo_and_favicon_are_shipped(self):
        logo,icon=build.brand_assets()
        self.assertRegex(logo,BrandSlotTests.INERT)
        self.assertIn(logo,self.html[self.html.index('<header'):self.html.index('</header>')])
        self.assertIn('<path',unquote(icon));self.assertNotIn('<rect width="32"',unquote(icon))  # not the placeholder square
    def test_head_title_description_and_share_preview(self):
        self.assertIn('<title>Cipher Lacuna | AI hardware, AI news and UAE AI</title>',self.head)
        self.assertIn('Cipher Lacuna',self.meta('name','description'))
        self.assertIn('<link rel="apple-touch-icon" href="brand/apple-touch-icon.png">',self.head)
        # PNG tab icon for browsers without SVG favicons, listed before the SVG one so the others keep using the SVG.
        png_icon='<link rel="icon" type="image/png" sizes="32x32" href="brand/icon-32.png">'
        self.assertIn(png_icon+'<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,',self.head)
        url='https://buafra.github.io/ai-hardware-atlas/'
        want={'og:type':'website','og:url':url,'og:image':url+'brand/og.png','og:image:width':'1200','og:image:height':'630','og:locale':'en_US','og:locale:alternate':'ar_AE'}
        for k,v in want.items():self.assertEqual(self.meta('property',k),v,k)
        self.assertTrue(self.meta('property','og:title').startswith('Cipher Lacuna'));self.assertIn('Cipher Lacuna',self.meta('property','og:description'))
        self.assertEqual(self.meta('name','twitter:card'),'summary_large_image');self.assertEqual(self.meta('name','twitter:image'),url+'brand/og.png')
        png=(ROOT/'web/brand/og.png').read_bytes()
        self.assertEqual((png[1:4],png[12:16]),(b'PNG',b'IHDR'));self.assertEqual((int.from_bytes(png[16:20],'big'),int.from_bytes(png[20:24],'big')),(1200,630))
        for f in ('apple-touch-icon.png','icon-512.png','icon-32.png'):self.assertTrue((ROOT/'web/brand'/f).exists(),f)
    def test_brand_pngs_are_copied_next_to_the_page(self):
        with tempfile.TemporaryDirectory() as d:
            names=build.copy_brand_images(Path(d)/'brand')
            self.assertEqual(sorted(names),sorted(f.name for f in (Path(d)/'brand').iterdir()))
        self.assertTrue({'og.png','apple-touch-icon.png','icon-512.png','icon-32.png'}<=set(names))
    def test_old_name_is_gone_and_taglines_translate(self):
        for f in ('web/template.html','web/app.js','scripts/build.py','README.md','web/brand/README.md'):
            self.assertNotIn('Cipher AI Knowledge',(ROOT/f).read_text(encoding='utf-8'),f)
        js=(ROOT/'web/app.js').read_text(encoding='utf-8')
        self.assertIn("'Decoding the gaps in AI knowledge':'فكّ شيفرة الفجوات في معرفة الذكاء الاصطناعي'",js)
        self.assertIn("'[Cipher Lacuna] '",js)

class SiteChoicesTests(unittest.TestCase):
    def setUp(self):
        self.data,self.feed,self.sources,self.uae,self.models=build.load_all()
        self.ps,self.facts=self.data['products'],self.uae['facts']
    def pick(self,content):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'site.json'
            if content is not None:p.write_text(content,encoding='utf-8')
            return build.load_site(self.ps,self.facts,p)
    def test_owner_choices_in_order(self):
        f,h=self.pick(json.dumps({'featured_products':['gb300-nvl72','h200'],'uae_highlights':['jais-arabic-llm']}))
        self.assertEqual([p['id'] for p in f][:2],['gb300-nvl72','h200']);self.assertEqual(len(f),3)
        self.assertEqual(h[0]['id'],'jais-arabic-llm');self.assertEqual(len(h),2)
    def test_fallbacks(self):
        for content in (None,'{not json','[]',json.dumps({'featured_products':['nope','nope'],'uae_highlights':'x'})):
            f,h=self.pick(content)
            self.assertEqual(len(f),3,content);self.assertEqual(len({p['id'] for p in f}),3);self.assertEqual(len(h),2,content)
    def test_repository_site_json(self):
        site=json.loads((ROOT/'data/site.json').read_text(encoding='utf-8'))
        ids={p['id'] for p in self.ps};fids={f['id'] for f in self.facts}
        self.assertTrue(set(site['featured_products'])<=ids);self.assertTrue(set(site['uae_highlights'])<=fids)

class CountTests(unittest.TestCase):
    def test_counts_match_app_js_rules(self):
        self.assertEqual(build.cnt(1,'product','en'),'1 product');self.assertEqual(build.cnt(53,'product','en'),'53 products')
        self.assertEqual(build.cnt(2,'product','ar'),'منتجان');self.assertEqual(build.cnt(5,'product','ar'),'5 منتجات')
        self.assertEqual(build.cnt(53,'product','ar'),'53 منتجًا');self.assertEqual(build.cnt(100,'headline','ar'),'100 عنوان')
        self.assertEqual(build.ymd('2017-10','ar'),'أكتوبر 2017');self.assertEqual(build.ymd('2026-09-26T22:30:00+00:00','en'),'27 Sep 2026')
    def test_dates_for_people_match_app_js(self):
        # Same expectations as tests/test-sort.cjs for when() in app.js.
        cases={('2025-Q3','en'):'Q3 2025',('2025-Q3','ar'):'الربع الثالث 2025',('2026-H2','ar'):'النصف الثاني 2026',('2025-Summer','en'):'Summer 2025',
               ('2025-Summer','ar'):'صيف 2025',('2026-end','en'):'End of 2026',('2026-end','ar'):'نهاية 2026',('2025-03-05','en'):'5 Mar 2025',
               ('2025-03-05','ar'):'5 مارس 2025',('2023-07','en'):'Jul 2023',('2026-09-26T22:30:00+00:00','ar'):'27 سبتمبر 2026'}
        for (v,lang),want in cases.items():self.assertEqual(build.when(v,lang),want,(v,lang))
        self.assertEqual(build.change_text('GeForce RTX 5070: power_w changed from None to 250'),'GeForce RTX 5070: power changed from not listed to 250 W')
        self.assertEqual(build.change_text('Added X after review.'),'Added X after review.')

class ScheduleAndLinkTests(unittest.TestCase):
    def test_schedule_text_matches_publish_cron(self):
        # The page says when it updates (from data/catalog.json schedule); the workflow cron must say the same, in UTC.
        data=json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'))
        cron=re.search(r"cron:\s*'([^']+)'",(ROOT/'.github/workflows/publish.yml').read_text(encoding='utf-8')).group(1).split()
        uae=sorted(f'{(int(h)+4)%24:02d}:{int(cron[0]):02d}' for h in cron[1].split(','))
        self.assertEqual(sorted(build.schedule_times(data)),uae)
        self.assertEqual(build.schedule_phrase(data,'en'),'twice a day (07:15 and 19:15 UAE time)')
        self.assertEqual(build.schedule_phrase(data,'ar'),'مرتين يوميًا (7:15 و19:15 بتوقيت الإمارات)')
    def test_links_must_be_https(self):
        with self.assertRaises(AssertionError):build.validate_links([{'id':'x','homepage':'javascript:alert(1)'}],None)
        with self.assertRaises(AssertionError):build.validate_links([],{'facts':[{'id':'f','sources':[{'url':'http://x.example/'}]}]})
        items=build.news_items({'items':[{'source':'s','url':'javascript:x','published':'2026-01-01T00:00:00+00:00'},{'source':'s','url':'https://a.example/','published':'2026-01-01T00:00:00+00:00'}]},[{'id':'s'}])
        self.assertEqual([i['url'] for i in items],['https://a.example/'])

class PageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data,feed,sources,uae,models=build.load_all()
        cls.data,cls.feed,cls.uae,cls.sources=data,feed,uae,sources
        with tempfile.TemporaryDirectory() as d:
            cls.html,cls.public=build.render_page(data,feed,sources,uae,models,brand_dir=Path(d))
    def test_every_view_rendered_and_visible_without_js(self):
        for v in ('home','hardware','news','uae','contact'):
            m=re.search(r'<(?:div|section) id="%s" [^>]*data-view="%s"[^>]*>'%(v,v),self.html)
            self.assertTrue(m,v);self.assertNotIn('hidden',m.group(0))
        self.assertEqual(self.html.count('class="product '),len(self.data['products']))
    def test_one_h1_per_view(self):
        main=self.html[self.html.index('<main'):self.html.index('</main>')]
        views=re.split(r'<(?:div|section) id="\w+" class="view',main)[1:]
        self.assertEqual(len(views),5)
        for chunk in views:self.assertEqual(chunk.count('<h1'),1,chunk[:20])
    def test_site_rules(self):
        self.assertNotIn('buafra@gmail.com',self.html)
        self.assertNotIn('announcements',self.public);self.assertNotIn('"announcements"',self.html)
        for tag in re.findall(r'<a\b[^>]*target="_blank"[^>]*>',self.html):self.assertIn('rel="noopener noreferrer"',tag)
        self.assertIsNone(re.search(r'<script[^>]+src=|<link[^>]+stylesheet|<img[^>]+src="(?:https?:)?//|url\((?:["\'])?(?:https?:)?//|@import',self.html))
        self.assertIsNone(re.search(r'__[A-Z][A-Z0-9_]*__',self.html))
        self.assertNotIn('brand-logo',self.html.split('<style>')[0]+self.html.split('</style>')[1])
        self.assertIn('<span class="wordmark" lang="en" dir="ltr">Cipher <span class="wm-2">Lacuna</span></span>',self.html)
        self.assertIn('<span class="tagline" data-i18n>Decoding the gaps in AI knowledge</span>',self.html)
        # On phones the header has no room for the tagline, so the hero repeats it under the name (CSS shows it there only).
        self.assertIn('</h1><p class="hero-tag" data-i18n>Decoding the gaps in AI knowledge</p>',self.html)
    def test_release_without_a_date(self):
        # A product with no availability date shows "Not established" plus its kind when the kind explains something (for
        # example "Not on NVIDIA's current roadmap"), never "Not established" twice and never a leftover "Expected"; every
        # kind used in the catalog has an Arabic translation in app.js.
        js=(ROOT/'web/app.js').read_text(encoding='utf-8')
        for kind in {p['release_kind'] for p in self.data['products']}:
            self.assertTrue(f"'{kind}':" in js or f'"{kind}":' in js,kind)
        for p in self.data['products']:
            if p['release'] is None:
                card=re.search(r'<article class="product [^"]*" id="p-%s".*?</article>'%re.escape(p['id']),self.html,re.S).group(0)
                cell=card[card.index('Availability / target'):card.index('Announced / launched')]
                self.assertIn('<span data-i18n>Not established</span>',cell,p['id'])
                if p['release_kind'] in (None,'','Not established'):
                    self.assertEqual(cell.count('Not established'),1,p['id']);self.assertNotIn('<small>',cell,p['id'])
                else:
                    self.assertIn(f"<small>{build.T(p['release_kind'])}</small>",cell,p['id'])
                self.assertNotIn('>Expected<',cell,p['id'])
        self.assertEqual(build.release_kind('Not established'),'');self.assertEqual(build.release_kind(None),'')
        self.assertEqual(build.release_kind('Released'),'<small><span data-i18n>Released</span></small>')
    def test_counts_are_honest(self):
        # UAE headline counts per language (the list a reader can open), newsrooms counted once per outlet,
        # and "from N sources" counts the sources that actually supplied headlines.
        items=build.news_items(self.feed,self.sources)
        uae_items=[i for i in items if i.get('uae')]
        n_en,n_ar=sum(build.in_lang(i,'en') for i in uae_items),sum(build.in_lang(i,'ar') for i in uae_items)
        self.assertIn(f'<dt data-i18n>UAE headlines</dt><dd><bdi>{build.L(n_en,n_ar)}</bdi>',self.html)
        hosts={(urlparse(s['homepage']).hostname or '').removeprefix('www.') for s in self.sources if s['region']=='uae'}
        self.assertIn(f'<dt data-i18n>UAE newsrooms</dt><dd><bdi>{len(hosts)}</bdi>',self.html)
        self.assertIn(f'from {build.cnt(len({i["source"] for i in items}),"source","en")}',self.html)
    def test_stats_and_featured_come_from_data(self):
        ps=self.data['products']
        self.assertIn(f'<dt data-i18n>products</dt><dd><bdi>{len(ps)}</bdi>',self.html)
        self.assertIn(f'<dt data-i18n>with approx. price</dt><dd><bdi>{sum(1 for p in ps if p["price_view"])}</bdi>',self.html)
        self.assertIn(f'<dt data-i18n>key facts</dt><dd><bdi>{len(self.uae["facts"])}</bdi>',self.html)
        for pid in json.loads((ROOT/'data/site.json').read_text(encoding='utf-8'))['featured_products']:self.assertIn(f'data-route="hardware/p/{pid}"',self.html)
    def test_no_content_hard_coded_in_template_or_script(self):
        shell=(ROOT/'web/template.html').read_text(encoding='utf-8')+(ROOT/'web/app.js').read_text(encoding='utf-8')
        for p in self.data['products']:self.assertNotIn(p['model'],shell)
        for f in self.uae['facts']:self.assertNotIn(f['title_en'],shell)
        for i in self.feed['items'][:40]:self.assertNotIn(i['title'],shell)

if __name__=='__main__':unittest.main()
